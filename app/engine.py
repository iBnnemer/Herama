"""llama-cpp model manager: one loaded model, swapped on demand."""
import threading
import time
from pathlib import Path

from app import config, resources

_DEFAULT_KEEP = 300  # seconds; -1 = indefinite


class Engine:
    def __init__(self):
        self._lock = threading.Lock()
        self._llm = None
        self._key = None
        self.plan = None
        self._loaded_name: str | None = None
        self._loaded_at: float = 0.0
        self._timer: threading.Timer | None = None

    def models(self) -> list[Path]:
        return sorted(config.MODELS_DIR.glob("**/*.gguf"))

    def path(self, name: str) -> Path:
        for p in self.models():
            if name in (p.stem, p.name, f"{p.stem}:latest"):
                return p
        raise FileNotFoundError(name)

    def load(self, name: str, num_ctx=None, num_gpu=None, keep_alive: int = _DEFAULT_KEEP):
        from llama_cpp import Llama

        p = self.path(name)
        key = (p, num_ctx, num_gpu)
        if self._key == key:
            self._reset_timer(keep_alive)
            return self._llm
        self.unload()
        self.plan = resources.plan(p, num_ctx, num_gpu)
        self._llm = Llama(model_path=str(p), n_ctx=self.plan.n_ctx,
                          n_gpu_layers=self.plan.n_gpu_layers, verbose=False)
        self._key = key
        self._loaded_name = name
        self._loaded_at = time.time()
        self._reset_timer(keep_alive)
        return self._llm

    def _reset_timer(self, keep_alive: int):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if keep_alive > 0:
            self._timer = threading.Timer(keep_alive, self.unload)
            self._timer.daemon = True
            self._timer.start()

    def unload(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._llm, self._key, self.plan = None, None, None
        self._loaded_name, self._loaded_at = None, 0.0

    def ps(self) -> dict | None:
        """Return info about the currently loaded model, or None."""
        if not self._loaded_name:
            return None
        return {
            "name": self._loaded_name,
            "model": self._loaded_name,
            "loaded_at": self._loaded_at,
            "n_ctx": self.plan.n_ctx if self.plan else 0,
            "n_gpu_layers": self.plan.n_gpu_layers if self.plan else 0,
        }

    def generate(self, name: str, prompt: str, opts: dict, stream: bool):
        """Yields text chunks; last item is the final llama-cpp response dict."""
        with self._lock:
            keep = opts.get("keep_alive", _DEFAULT_KEEP)
            llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"), keep_alive=keep)
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
