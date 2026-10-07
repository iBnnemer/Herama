"""Live status of the model (idle / reading / generating / loading / error), request history and hardware readings."""
import threading
import time
from collections import deque

from app import runtime

ERROR_SHOW_SECONDS = 15
HW_CACHE_SECONDS = 0.8

_lock = threading.Lock()
_state = {"state": "idle", "detail": "", "progress": 0.0, "tps": 0.0, "since": time.time()}
_last = {"decode_tps": 0.0, "prefill_tps": 0.0, "ctx_used": 0}
_requests: deque = deque(maxlen=30)
_hw = {"at": 0.0, "data": {}}
_disk = {"at": 0.0, "bytes": 0, "rate": 0.0}


def set_state(state: str, detail: str = "", progress: float = 0.0, tps: float = 0.0) -> None:
    with _lock:
        _state.update(state=state, detail=detail, progress=progress, tps=tps, since=time.time())


def progress(done: int, total: int) -> None:
    """Prompt processing progress while the model is reading the input."""
    with _lock:
        if _state["state"] in ("reading", "queued", "idle"):
            _state.update(state="reading", progress=min(1.0, done / total) if total else 0.0)


def generating(tps: float = 0.0) -> None:
    with _lock:
        if _state["state"] != "generating":
            _state.update(state="generating", progress=1.0, since=time.time())
        _state["tps"] = tps


def fail(message: str) -> None:
    set_state("error", message[:200])


def finish(status: str, prompt: int, reused: int, output: int, decode_tps: float, prefill_tps: float,
           duration: float, ctx_used: int | None = None) -> None:
    """Record one request and return to idle (an error stays visible for a few seconds)."""
    with _lock:
        _requests.appendleft({
            "time": time.time(), "status": status, "prompt": prompt, "reused": reused, "output": output,
            "tps": round(decode_tps, 1), "hit_rate": round(reused / prompt, 3) if prompt else 0.0,
            "duration": round(duration, 2),
        })
        if decode_tps:
            _last["decode_tps"] = decode_tps
        if prefill_tps:
            _last["prefill_tps"] = prefill_tps
        _last["ctx_used"] = ctx_used if ctx_used is not None else prompt + output
        if _state["state"] != "error":
            _state.update(state="idle", detail="", progress=0.0, tps=0.0, since=time.time())


def state() -> dict:
    with _lock:
        if _state["state"] == "error" and time.time() - _state["since"] > ERROR_SHOW_SECONDS:
            _state.update(state="idle", detail="", progress=0.0, since=time.time())
        return dict(_state)


# ── hardware ──────────────────────────────────────────────────────────────────

_GPU_FIELDS = ("name", "utilization.gpu", "memory.used", "memory.total", "temperature.gpu", "power.draw",
               "power.limit", "pcie.link.gen.current", "pcie.link.width.current")


def _num(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def parse_gpu(out: str) -> dict:
    """Parse one `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` line (first GPU)."""
    line = next((ln for ln in out.splitlines() if ln.strip()), "")
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < len(_GPU_FIELDS):
        return {}
    v = [_num(p) for p in parts[1:]]
    return {"name": parts[0], "load": v[0], "vram_used_mb": v[1], "vram_total_mb": v[2], "temp": v[3],
            "power": v[4], "power_limit": v[5], "pcie_gen": v[6], "pcie_width": v[7]}


def _gpu() -> dict:
    exe = runtime.nvidia_smi_path()
    if not exe:
        return {}
    return parse_gpu(runtime._run([exe, f"--query-gpu={','.join(_GPU_FIELDS)}", "--format=csv,noheader,nounits"], 4))


def _system() -> dict:
    import psutil
    now = time.time()
    io = psutil.disk_io_counters()
    if io:
        if _disk["at"]:
            dt = max(now - _disk["at"], 1e-3)
            _disk["rate"] = max(0.0, (io.read_bytes - _disk["bytes"]) / dt)
        _disk.update(at=now, bytes=io.read_bytes)
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(interval=None), "threads": psutil.cpu_count(logical=True),
            "ram_used_gb": round((vm.total - vm.available) / 1e9, 1), "ram_total_gb": round(vm.total / 1e9, 1),
            "disk_read_mb_s": round(_disk["rate"] / 1e6, 1)}


def hardware() -> dict:
    now = time.time()
    with _lock:
        if now - _hw["at"] < HW_CACHE_SECONDS:
            return _hw["data"]
    data = {"gpu": _gpu(), "system": _system()}
    with _lock:
        _hw.update(at=now, data=data)
    return data


def snapshot(ctx_total: int = 0, experts: dict | None = None) -> dict:
    st = state()
    with _lock:
        last, reqs = dict(_last), list(_requests)
    return {"state": st, "decode_tps": last["decode_tps"], "prefill_tps": last["prefill_tps"],
            "ctx_used": last["ctx_used"], "ctx_total": ctx_total, "experts": experts, "requests": reqs, **hardware()}
