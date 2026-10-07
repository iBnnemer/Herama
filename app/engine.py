"""llama-cpp model manager: one loaded model, swapped on demand."""
import os
import queue
import threading
import time
from pathlib import Path

from app import config, resources

_DEFAULT_KEEP = 300  # seconds; -1 = indefinite


def _norm(name: str) -> str:
    """Strip ':latest' suffix for consistent comparisons."""
    return name.removesuffix(":latest")


class Engine:
    def __init__(self):
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._llm = None
        self._key = None
        self.plan = None
        self._loaded_name: str | None = None
        self._loaded_at: float = 0.0
        self._timer: threading.Timer | None = None

    def models(self) -> list[Path]:
        return sorted(p for p in config.MODELS_DIR.glob("**/*.gguf")
                      if not p.name.lower().startswith("mmproj"))  # vision projectors are not chat models

    def path(self, name: str) -> Path:
        n = _norm(name)
        for p in self.models():
            if n in (p.stem, p.name):
                return p
        raise FileNotFoundError(name)

    def _vision_handler(self, p: Path):
        """Chat handler for image input; needs the matching mmproj file next to the model."""
        stem = p.stem.lower()
        family = ("Gemma3ChatHandler" if "gemma-3" in stem or "gemma3" in stem
                  else "Llava15ChatHandler" if "llava" in stem else None)
        if family is None:
            raise RuntimeError("image input is not supported for this model by llama-cpp-python "
                               "(supported: Gemma 3 and LLaVA models)")
        cands = [q for q in p.parent.glob("*.gguf") if q.name.lower().startswith("mmproj")]
        if not cands:
            raise RuntimeError("image input needs the matching mmproj .gguf file next to the model")
        best = max(cands, key=lambda q: len(os.path.commonprefix([stem, q.stem.lower().removeprefix("mmproj-")])))
        from llama_cpp import llama_chat_format as cf
        handler = getattr(cf, family, None)
        if handler is None:
            raise RuntimeError(f"this llama-cpp-python build has no {family}")
        return handler(clip_model_path=str(best), verbose=False)

    def load(self, name: str, num_ctx=None, num_gpu=None, keep_alive: int = _DEFAULT_KEEP, vision: bool = False):
        from llama_cpp import Llama

        p = self.path(name)
        key = (p, num_ctx, num_gpu, vision)
        if self._key == key:
            self._reset_timer(keep_alive)
            return self._llm
        self.unload()
        self.plan = resources.plan(p, num_ctx, num_gpu)
        extra = {"chat_handler": self._vision_handler(p)} if vision else {}
        self._llm = Llama(model_path=str(p), n_ctx=self.plan.n_ctx,
                          n_gpu_layers=self.plan.n_gpu_layers, verbose=False, **extra)
        self._key = key
        self._loaded_name = _norm(name)
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
        if not self._loaded_name:
            return None
        return {
            "name": self._loaded_name,
            "model": self._loaded_name,
            "loaded_at": self._loaded_at,
            "n_ctx": self.plan.n_ctx if self.plan else 0,
            "n_gpu_layers": self.plan.n_gpu_layers if self.plan else 0,
        }

    def _kw(self, opts: dict) -> dict:
        return dict(
            max_tokens=opts.get("num_predict", 512),
            temperature=opts.get("temperature", 0.8),
            top_p=opts.get("top_p", 0.95),
            top_k=opts.get("top_k", 40),
            stop=opts.get("stop") or None,
            seed=opts.get("seed", -1),
        )

    def generate(self, name: str, prompt: str, opts: dict, stream: bool):
        """Yields text chunks then final llama-cpp response dict."""
        with self._lock:
            keep = opts.get("keep_alive", _DEFAULT_KEEP)
            llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"), keep_alive=keep)
            kw = self._kw(opts)
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

    def chat(self, name: str, messages: list[dict], opts: dict, stream: bool, vision: bool = False):
        """Native chat_completion path. Yields content chunks then final dict."""
        with self._lock:
            keep = opts.get("keep_alive", _DEFAULT_KEEP)
            llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"), keep_alive=keep, vision=vision)
            kw = self._kw(opts)
            if not stream:
                r = llm.create_chat_completion(messages=messages, **kw)
                msg = r["choices"][0]["message"]
                yield msg.get("content", "")
                yield r
                return
            last = None
            for c in llm.create_chat_completion(messages=messages, stream=True, **kw):
                last = c
                delta = c["choices"][0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    yield text
            yield last or {}


engine = Engine()
