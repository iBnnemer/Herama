"""RAM/VRAM probing -> n_ctx, n_gpu_layers."""
import struct
from dataclasses import dataclass
from pathlib import Path

import psutil

from app import config

_SCALAR = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_WANT = ("block_count", "context_length", "embedding_length", "attention.head_count", "attention.head_count_kv", "expert_count")


def _read_val(f, t):
    if t in _SCALAR:
        fmt = "<" + _SCALAR[t]
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]
    if t == 8:
        (n,) = struct.unpack("<Q", f.read(8))
        return f.read(n).decode("utf-8", "replace")
    if t == 9:
        it, n = struct.unpack("<IQ", f.read(12))
        if it in _SCALAR:  # skip numeric arrays (tokenizer scores etc.)
            f.seek(n * struct.calcsize(_SCALAR[it]), 1)
        else:
            for _ in range(n):
                _read_val(f, it)
        return None
    raise ValueError(f"gguf type {t}")


_meta_cache: dict[Path, dict] = {}


def gguf_meta(path: Path) -> dict:
    if path in _meta_cache:
        return _meta_cache[path]
    out = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not gguf")
        _, _, kv = struct.unpack("<IQQ", f.read(20))
        for _ in range(kv):
            (n,) = struct.unpack("<Q", f.read(8))
            key = f.read(n).decode()
            (t,) = struct.unpack("<I", f.read(4))
            v = _read_val(f, t)
            short = key.split(".", 1)[-1]
            if short in _WANT:
                out[short] = v
            if len(out) == len(_WANT):
                break
    _meta_cache[path] = out
    return out


def free_vram() -> int:
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        return pynvml.nvmlDeviceGetMemoryInfo(h).free
    except Exception:
        return 0


@dataclass
class Plan:
    n_ctx: int
    n_gpu_layers: int
    ram_free: int
    vram_free: int


def plan(model: Path, want_ctx: int | None = None, want_gpu: int | None = None) -> Plan:
    m = gguf_meta(model)
    size = model.stat().st_size
    def num(key: str, default: int) -> int:
        v = m.get(key)  # arrays (per-layer head counts in newer models) are read as None
        return int(v) if isinstance(v, (int, float)) and v > 0 else default

    layers = num("block_count", 32)
    ctx_train = num("context_length", 4096)
    emb, heads = num("embedding_length", 4096), num("attention.head_count", 32)
    kv_heads = num("attention.head_count_kv", heads)
    ram = int(psutil.virtual_memory().available * config.RAM_HEADROOM)
    vram = int(free_vram() * config.RAM_HEADROOM)

    if want_gpu is not None:
        gpu = want_gpu
    elif vram >= size:
        gpu = -1  # all layers
    else:
        gpu = max(0, int(layers * vram / size))

    on_gpu = size if gpu == -1 else size * gpu // layers
    budget = (vram - on_gpu if gpu == -1 else ram - (size - on_gpu))
    per_tok = 2 * layers * (emb * kv_heads // heads) * 2  # K+V, f16
    ctx = budget // per_tok if per_tok else 2048
    ctx = min(want_ctx or ctx_train, ctx, ctx_train)
    ctx = max(512, ctx // 256 * 256)
    return Plan(ctx, gpu, ram, vram)
