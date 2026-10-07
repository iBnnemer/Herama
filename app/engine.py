"""llama-cpp model manager: one loaded model, swapped on demand."""
import os
import queue
import threading
import logging
import time
from pathlib import Path

from app import calib, config, monitor, resources, runtime
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

    def _start_server(self, binary: Path, p: Path, n_ctx: int, vision: bool, num_gpu=None, cpu_moe: int = 0,
                      expert_used: int = 0, kv_type: str = "f16", threads: int = 0):
        mm = self._find_mmproj(p)
        if vision and mm is None:
            raise RuntimeError("image input needs the matching mmproj .gguf file next to the model")
        log_path = runtime.RUNTIME_DIR / "server.log"
        ngl = self._gpu_layers(p, n_ctx, num_gpu)
        self._last_ngl = ngl
        log.info("llama-server: %s backend=%s ngl=%s cpu_moe=%s kv=%s ctx=%d", p.name, runtime.current_backend(), ngl,
                 cpu_moe, kv_type, n_ctx)
        override = self._expert_override(p, expert_used)
        try:
            return ServerLLM(binary, p, n_ctx, mm, log_path, ngl, cpu_moe, override, kv_type, threads)
        except RuntimeError as e:
            log.warning("llama-server failed with ngl=%s: %s", ngl, str(e)[-300:])
        if ngl not in (None, 0):  # our layer count may be too high: let llama-server fit it itself
            try:
                return ServerLLM(binary, p, n_ctx, mm, log_path, None, cpu_moe, override, kv_type, threads)
            except RuntimeError as e:
                log.warning("llama-server failed with automatic layers: %s", str(e)[-300:])
        nxt = runtime.fallback()  # e.g. CUDA build cannot start -> Vulkan -> CPU
        if nxt is None:
            raise RuntimeError("llama-server could not start; see runtime/server.log")
        return ServerLLM(nxt, p, n_ctx, mm, log_path, None if runtime.current_backend() != "cpu" else 0)

    @staticmethod
    def _auto_plan(p: Path, n_ctx: int) -> dict | None:
        """Automatic GPU/CPU layout for this model and context (see tune.auto), or None when unavailable."""
        if runtime.current_backend() == "cpu":
            return None
        try:
            from app import hub, tune
            if not hub.hardware()["vram_total_gb"]:
                return None
            a = tune.auto(p, n_ctx, learn=False)
            return {"ctx": a["ctx"], "ngl": 999 if a["ngl"] >= a["layers"] else a["ngl"],
                    "cpu_moe": a["cpu_moe"], "kv": a["kv_type"]}
        except Exception:
            log.debug("automatic layout unavailable", exc_info=True)
            return None

    @staticmethod
    def _expert_override(p: Path, k: int) -> tuple[str, int] | None:
        if not k:
            return None
        try:
            arch = resources.gguf_meta(p).get("architecture")
        except Exception:
            return None
        return (arch, int(k)) if arch else None

    @staticmethod
    def _gpu_layers(p: Path, n_ctx: int, num_gpu: int | None = None) -> int | None:
        """Layers to offload: all when the weights fit in total VRAM, a proportional share otherwise."""
        backend = runtime.current_backend()
        if backend == "cpu":
            return 0
        if num_gpu is not None:  # chosen and approved by the user
            return 999 if num_gpu < 0 else int(num_gpu)
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

    def load(self, name: str, num_ctx=None, num_gpu=None, keep_alive: int = _DEFAULT_KEEP, vision: bool = False,
             cpu_moe: int = 0, expert_used: int = 0, kv_type: str = "f16", threads: int = 0):
        p = self.path(name)
        binary = runtime.ensure_binary()
        use_server = binary is not None
        key = (p, num_ctx, num_gpu, cpu_moe, expert_used, kv_type, threads, False if use_server else vision, use_server)
        if self._key == key:
            self._reset_timer(keep_alive)
            return self._llm
        self.unload()
        monitor.set_state("queued", f"Loading {p.stem}")
        if use_server:
            n_ctx = int(num_ctx or 65536)  # default context: 64K
            cpu_moe, kv_type = int(cpu_moe or 0), kv_type or "f16"
            if num_gpu is None and (auto := self._auto_plan(p, n_ctx)):  # no manual layout: choose it automatically
                n_ctx, num_gpu, cpu_moe, kv_type = auto["ctx"], auto["ngl"], auto["cpu_moe"], auto["kv"]
            self._llm = self._start_server(binary, p, n_ctx, vision, num_gpu, cpu_moe, int(expert_used or 0),
                                           kv_type, int(threads or 0))
            self._settings = {"model": p.stem, "ctx": n_ctx, "ngl": self._last_ngl, "cpu_moe": cpu_moe,
                              "top_k": int(expert_used or 0), "kv": kv_type}
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
        monitor.set_state("idle")
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
        self._settings = None

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
            llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"), keep_alive=keep, cpu_moe=opts.get("num_cpu_moe", 0), expert_used=opts.get("num_expert_used", 0),
                            kv_type=opts.get("kv_type", "f16"), threads=opts.get("num_thread", 0))
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
            t_req = time.perf_counter()
            try:
                keep = opts.get("keep_alive", _DEFAULT_KEEP)
                llm = self.load(name, opts.get("num_ctx"), opts.get("num_gpu"), keep_alive=keep, vision=vision,
                                cpu_moe=opts.get("num_cpu_moe", 0), expert_used=opts.get("num_expert_used", 0),
                                kv_type=opts.get("kv_type", "f16"), threads=opts.get("num_thread", 0))
                kw = self._kw(opts)
                monitor.set_state("reading")
                if not stream:
                    r = llm.create_chat_completion(messages=messages, **kw)
                    msg = r["choices"][0]["message"]
                    self._record(r, t_req, "done")
                    yield msg.get("content", "")
                    yield r
                    return
                last, t_first, n = None, 0.0, 0
                for c in llm.create_chat_completion(messages=messages, stream=True, **kw):
                    last = c
                    delta = c["choices"][0].get("delta", {}) if c.get("choices") else {}
                    text = delta.get("content") or ""
                    if text:
                        n += 1
                        t_first = t_first or time.perf_counter()
                        elapsed = time.perf_counter() - t_first
                        monitor.generating(n / elapsed if n > 3 and elapsed > 0.2 else 0.0)
                        yield text
                self._learn_speed(last, t_first)
                self._record(last, t_req, "done")
                yield last or {}
            except GeneratorExit:  # the client stopped reading
                monitor.finish("stopped", 0, 0, 0, 0.0, 0.0, time.perf_counter() - t_req)
                raise
            except Exception as e:
                monitor.fail(str(e))
                raise

    def _record(self, raw: dict | None, t_req: float, status: str) -> None:
        """Send the finished request's token counts and timings to the monitor."""
        raw = raw or {}
        usage, timings = raw.get("usage") or {}, raw.get("timings") or {}
        out = usage.get("completion_tokens", 0)
        dur = time.perf_counter() - t_req
        monitor.finish(status, usage.get("prompt_tokens", 0), timings.get("cache_n", 0), out,
                       timings.get("predicted_per_second") or (out / dur if dur > 0 else 0.0),
                       timings.get("prompt_per_second") or 0.0, dur)

    def monitor_info(self) -> tuple[int, dict | None]:
        """(context size, expert placement) of the loaded model for the monitor."""
        st = getattr(self, "_settings", None)
        if not st:
            return 0, None
        experts = None
        try:
            meta = resources.gguf_meta(self.path(st["model"]))
            layers, n_exp = int(meta.get("block_count") or 0), int(meta.get("expert_count") or 0)
            if layers and n_exp > 1:
                experts = {"gpu_layers": max(0, layers - int(st["cpu_moe"] or 0)), "layers": layers}
        except Exception:
            pass
        return st["ctx"], experts

    def _learn_speed(self, last: dict | None, t_first: float) -> None:
        """Store the measured generation speed for the settings in use (used to correct estimates)."""
        st = getattr(self, "_settings", None)
        tokens = ((last or {}).get("usage") or {}).get("completion_tokens", 0)
        elapsed = time.perf_counter() - t_first if t_first else 0.0
        if not st or st["ngl"] is None or tokens < 64 or elapsed < 1.0:
            return
        try:
            layers = int(resources.gguf_meta(self.path(st["model"])).get("block_count") or 0)
            calib.record(st["model"], st["ctx"], min(st["ngl"], layers) if layers else st["ngl"],
                         st["cpu_moe"], st["top_k"], tokens / elapsed, st["kv"])
        except Exception:
            log.debug("calibration not recorded", exc_info=True)


engine = Engine()
