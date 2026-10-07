"""llama-cpp model manager: one loaded model, swapped on demand."""
import os
import queue
import threading
import logging
import time
from pathlib import Path

from app import config, resources, runtime
from app.server_llm import ServerLLM

_DEFAULT_KEEP = 300  # seconds; -1 = indefinite


def _norm(name: str) -> str:
    """Strip ':latest' suffix for consistent comparisons."""
    return name.removesuffix(":latest")

log = logging.getLogger("herama")


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

    def _find_mmproj(self, p: Path) -> Path | None:
        """The vision projector that belongs to this model, if one sits next to it."""
        stem = p.stem.lower()
        best, score = None, 0
        for q in p.parent.glob("*.gguf"):
            if q.name.lower().startswith("mmproj"):
                n = len(os.path.commonprefix([stem, q.stem.lower().removeprefix("mmproj-")]))
                if n > score:
                    best, score = q, n
        return best if score >= 4 else None

    def _vision_handler(self, p: Path):
        """llama-cpp-python fallback: chat handler for image input (Gemma 3 and LLaVA only)."""
        stem = p.stem.lower()
        family = ("Gemma3ChatHandler" if "gemma-3" in stem or "gemma3" in stem
                  else "Llava15ChatHandler" if "llava" in stem else None)
        if family is None:
            raise RuntimeError("image input is not supported for this model without the llama.cpp runtime")
        mm = self._find_mmproj(p)
        if mm is None:
            raise RuntimeError("image input needs the matching mmproj .gguf file next to the model")
        from llama_cpp import llama_chat_format as cf
        handler = getattr(cf, family, None)
        if handler is None:
            raise RuntimeError(f"this llama-cpp-python build has no {family}")
        return handler(clip_model_path=str(mm), verbose=False)

    def _start_server(self, binary: Path, p: Path, n_ctx: int, vision: bool):
        mm = self._find_mmproj(p)
        if vision and mm is None:
            raise RuntimeError("image input needs the matching mmproj .gguf file next to the model")
        log_path = runtime.RUNTIME_DIR / "server.log"
        ngl = self._gpu_layers(p, n_ctx)
        log.info("llama-server: %s backend=%s ngl=%s ctx=%d", p.name, runtime.current_backend(), ngl, n_ctx)
        try:
            return ServerLLM(binary, p, n_ctx, mm, log_path, ngl)
        except RuntimeError as e:
            log.warning("llama-server failed with ngl=%s: %s", ngl, str(e)[-300:])
        if ngl not in (None, 0):  # our layer count may be too high: let llama-server fit it itself
            try:
                return ServerLLM(binary, p, n_ctx, mm, log_path, None)
            except RuntimeError as e:
                log.warning("llama-server failed with automatic layers: %s", str(e)[-300:])
        nxt = runtime.fallback()  # e.g. CUDA build cannot start -> Vulkan -> CPU
        if nxt is None:
            raise RuntimeError("llama-server could not start; see runtime/server.log")
        return ServerLLM(nxt, p, n_ctx, mm, log_path, None if runtime.current_backend() != "cpu" else 0)

    @staticmethod
    def _gpu_layers(p: Path, n_ctx: int) -> int | None:
        """Layers to offload: all when the weights fit in total VRAM, a proportional share otherwise."""
        backend = runtime.current_backend()
        if backend == "cpu":
            return 0
        try:
            from app import hub
            vram = hub.hardware()["vram_total_gb"] * 1024 ** 3
            if not vram:
                return None  # unknown VRAM (non-NVIDIA): let llama-server decide
            budget = vram - 1.2 * 1024 ** 3 - n_ctx * 256 * 1024  # OS/driver reserve plus a rough KV cache allowance
            size = p.stat().st_size
            if size <= budget:
                return 999
            layers = int(resources.gguf_meta(p).get("block_count") or 0)
            return max(0, int(layers * budget / size)) if layers else None
        except Exception:
            return None

    def load(self, name: str, num_ctx=None, num_gpu=None, keep_alive: int = _DEFAULT_KEEP, vision: bool = False):
        p = self.path(name)
        binary = runtime.ensure_binary()
        use_server = binary is not None
        key = (p, num_ctx, num_gpu, False if use_server else vision, use_server)
        if self._key == key:
            self._reset_timer(keep_alive)
            return self._llm
        self.unload()
        if use_server:
            n_ctx = int(num_ctx or 4096)
            self._llm = self._start_server(binary, p, n_ctx, vision)
            backend = runtime.current_backend()
            self.plan = resources.Plan(n_ctx, 0 if backend == "cpu" else -1, 0, 0)
        else:
            try:
                from llama_cpp import Llama
            except ImportError:
                raise RuntimeError(f"no inference runtime available: {runtime.status().get('error') or 'llama.cpp download disabled'}"
                                   " and llama-cpp-python is not installed") from None
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
        close = getattr(self._llm, "close", None)
        if close:
            close()
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
            max_tokens=opts.get("num_predict", -1),
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
