"""llama-cpp model manager: one loaded model, swapped on demand."""
import threading
from pathlib import Path

from app import config, resources


class Engine:
    def __init__(self):
        self._lock = threading.Lock()
        self._llm = None
        self._key = None
        self.plan = None

    def models(self) -> list[Path]:
        return sorted(config.MODELS_DIR.glob("**/*.gguf"))

    def path(self, name: str) -> Path:
        for p in self.models():
            if name in (p.stem, p.name, f"{p.stem}:latest"):
                return p
        raise FileNotFoundError(name)

    def load(self, name: str, num_ctx=None, num_gpu=None):
        from llama_cpp import Llama

        p = self.path(name)
        key = (p, num_ctx, num_gpu)
        if self._key == key:
            return self._llm
        self.unload()
        self.plan = resources.plan(p, num_ctx, num_gpu)
        self._llm = Llama(model_path=str(p), n_ctx=self.plan.n_ctx,
                          n_gpu_layers=self.plan.n_gpu_layers, verbose=False)
        self._key = key
        return self._llm

    def unload(self):
        self._llm, self._key, self.plan = None, None, None

    def generate(self, name: str, prompt: str, opts: dict, stream: bool):
        """Yields text chunks; last item is the final llama-cpp response dict."""
        with self._lock:
            llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"))
            kw = dict(
                max_tokens=opts.get("num_predict", 512),
                temperature=opts.get("temperature", 0.8),
                top_p=opts.get("top_p", 0.95),
                top_k=opts.get("top_k", 40),
                stop=opts.get("stop") or None,
                seed=opts.get("seed", -1),
            )
            if not stream:
                r = llm(prompt, **kw)
                yield r["choices"][0]["text"]
                yield r
                return
            last = None
            for c in llm(prompt, stream=True, **kw):
                last = c
                yield c["choices"][0]["text"]
            yield last or {}


engine = Engine()
