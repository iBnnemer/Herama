"""Hugging Face GGUF search, speed estimate for this machine, and background downloads (REST only)."""
import json
import logging
import os
import platform
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid

import psutil

from app import config, runtime

log = logging.getLogger("herama")

HF = "https://huggingface.co"
GPU_EFFICIENCY = 0.55   # share of memory bandwidth reached by llama.cpp decoding (measured on RTX 3080 Ti)
CPU_BANDWIDTH = 50.0    # GB/s effective for CPU inference
DEFAULT_GPU_BW = 250.0  # GB/s when the GPU model is unknown

# (name fragment, memory bandwidth GB/s); more specific fragments come first
_BANDWIDTH = [
    ("4090", 1008), ("4080", 717), ("4070 ti", 504), ("4070", 504), ("4060 ti", 288), ("4060", 272),
    ("3090", 936), ("3080 ti", 912), ("3080", 760), ("3070", 448), ("3060 ti", 448), ("3060", 360),
    ("3050", 224), ("2080", 448), ("2070", 448), ("2060", 336), ("1080 ti", 484), ("1080", 320),
    ("1070", 256), ("1060", 192), ("1650", 128), ("5090", 1792), ("5080", 960), ("5070", 672),
    ("7900 xtx", 960), ("7900 xt", 800), ("7800 xt", 624), ("7700 xt", 432), ("7600", 288),
    ("6900", 512), ("6800", 512), ("6700", 384), ("6600", 224),
]

_hw_cache: dict = {}
_hw_time = 0.0


# ── hardware ──────────────────────────────────────────────────────────────────

def _smi_query() -> tuple[str, float, float] | None:
    """(name, total_gb, free_gb) of the first NVIDIA GPU, or None."""
    exe = runtime.nvidia_smi_path()
    if not exe:
        return None
    out = runtime._run([exe, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"], 40)
    try:
        name, total, free = [x.strip() for x in out.splitlines()[0].split(",")]
        return name, float(total) / 1024, float(free) / 1024
    except (IndexError, ValueError):
        return None


def hardware() -> dict:
    """GPU name, VRAM, estimated bandwidth and RAM. Cached for a minute."""
    global _hw_cache, _hw_time
    if _hw_cache and time.time() - _hw_time < 60:
        return _hw_cache
    smi = _smi_query()
    gpus = runtime.gpu_names()
    name = smi[0] if smi else (gpus[0] if gpus else "")
    low = name.lower()
    bw = next((b for k, b in _BANDWIDTH if k in low), DEFAULT_GPU_BW if name else 0)
    vm = psutil.virtual_memory()
    cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 4
    _hw_cache = {
        "cpu": platform.processor() or "CPU", "cpu_cores": cores,
        "cpu_bandwidth": float(min(90, max(30, 20 + 4 * cores))),
        "gpu": name, "vram_total_gb": round(smi[1], 1) if smi else 0.0,
        "vram_free_gb": round(smi[2], 1) if smi else 0.0, "gpu_bandwidth": bw,
        "ram_total_gb": round(vm.total / 1024 ** 3, 1), "ram_free_gb": round(vm.available / 1024 ** 3, 1),
    }
    _hw_time = time.time()
    return _hw_cache


_MOE_ACTIVE = re.compile(r"(\d+(?:\.\d+)?)b[-_ ]a(\d+(?:\.\d+)?)b", re.I)   # Qwen3-30B-A3B
_MOE_EXPERTS = re.compile(r"(\d+)x(\d+(?:\.\d+)?)b", re.I)                    # Mixtral 8x7B


def moe_active_ratio(text: str) -> float | None:
    """Share of the weights read per token for a mixture-of-experts model, or None for a dense one."""
    m = _MOE_ACTIVE.search(text)
    if m:
        return min(1.0, float(m.group(2)) / float(m.group(1)))
    m = _MOE_EXPERTS.search(text)
    if m:  # top-2 routing: ~2 experts plus shared layers out of ~0.84 of the nominal total
        n, per = int(m.group(1)), float(m.group(2))
        return min(1.0, 2 * per / (n * per * 0.84))
    return 0.2 if re.search(r"moe", text, re.I) else None


def quant_speed_factor(quant: str) -> float:
    """Low-bit and i-quants cost more compute per byte to dequantise, so they run below the bandwidth limit."""
    q = quant.upper()
    if q.startswith("IQ"):
        return 0.75
    return 0.85 if q.startswith(("Q2", "Q3")) else 1.0


def estimate(size_bytes: int, hw: dict | None = None, active_ratio: float = 1.0, quant: str = "") -> dict:
    """Rough decode speed (tokens/s) and memory fit for a model file on this machine.

    Memory fit uses the whole file; speed uses only the bytes read per token, which for a
    mixture-of-experts model is the active share (`active_ratio`) of the weights.
    """
    hw = hw or hardware()
    size = max(size_bytes, 1) / 1024 ** 3
    read = size * active_ratio / quant_speed_factor(quant)  # effective bytes, slower quants count extra
    need = size * 1.1  # weights plus KV cache and buffers
    # totals, not free memory: a model loaded right now can be unloaded, so it must not shrink the budget
    vram = max(hw["vram_total_gb"] - 0.7, 0.0)
    ram = max(hw["ram_total_gb"] * 0.9 - 2.0, 0.0)
    gpu_bw = hw["gpu_bandwidth"] * GPU_EFFICIENCY
    cpu_bw = hw.get("cpu_bandwidth", CPU_BANDWIDTH)
    if vram and gpu_bw and need <= vram:
        return {"fit": "gpu", "tps": round(gpu_bw / read, 1), "vram_gb": round(need, 1), "ram_gb": 0.0}
    if vram and gpu_bw:
        frac = max(0.0, (vram - 0.5) / need)  # share of the weights that fits in VRAM
        sec = read * (frac / gpu_bw + (1 - frac) / cpu_bw)
        fit = "split" if need <= vram + ram else "too_big"
        return {"fit": fit, "tps": round(1 / sec, 1), "vram_gb": round(vram, 1), "ram_gb": round(need - vram, 1)}
    fit = "cpu" if need <= ram else "too_big"
    return {"fit": fit, "tps": round(cpu_bw / read, 1), "vram_gb": 0.0, "ram_gb": round(need, 1)}


# ── Hugging Face REST ─────────────────────────────────────────────────────────

def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "herama"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


_MOE = re.compile(r"moe|mixtral|\d+x\d+b|[-_ ]a\d+(\.\d+)?b\b", re.I)
_UNCENSORED = re.compile(r"abliterat|uncensor", re.I)


def _query(q: str, limit: int) -> list[dict]:
    params = {"filter": "gguf", "sort": "downloads", "direction": "-1", "limit": str(limit)}
    if q.strip():
        params["search"] = q.strip()
    return _get_json(f"{HF}/api/models?{urllib.parse.urlencode(params)}")


def search(query: str, moe: bool = False, uncensored: bool = False, limit: int = 30) -> list[dict]:
    """GGUF repos by downloads. `uncensored` keeps abliterated/uncensored models; `moe` keeps mixture-of-experts."""
    if uncensored:  # the Hub search has no OR, so query both words and merge
        rows = [m for w in ("abliterated", "uncensored") for m in _query(f"{query} {w}", 100)]
    else:
        rows = _query(query, 100 if moe else limit)
    seen, out = set(), []
    for m in sorted(rows, key=lambda m: -m.get("downloads", 0)):
        text = m["id"] + " " + " ".join(m.get("tags") or [])
        if m["id"] in seen or (moe and not _MOE.search(text)) or (uncensored and not _UNCENSORED.search(text)):
            continue
        seen.add(m["id"])
        out.append({"id": m["id"], "downloads": m.get("downloads", 0), "likes": m.get("likes", 0)})
    return out[:limit]


_QUANT = re.compile(r"(IQ\d_[A-Z]+|Q\d(?:_K)?(?:_[A-Z0-9]+)?|BF16|F16|F32)", re.I)
_SHARD = re.compile(r"-\d{5}-of-\d{5}")


def files(repo: str) -> list[dict]:
    """Single-file GGUF weights of a repo with size, quantisation and speed estimate."""
    tree = _get_json(f"{HF}/api/models/{urllib.parse.quote(repo, safe='/')}/tree/main?recursive=1")
    hw = hardware()
    out = []
    for f in tree:
        path = f.get("path", "")
        base = path.rsplit("/", 1)[-1]
        if f.get("type") != "file" or not path.lower().endswith(".gguf"):
            continue
        if base.lower().startswith("mmproj") or _SHARD.search(base):
            continue
        size = (f.get("lfs") or {}).get("size") or f.get("size") or 0
        q = _QUANT.search(base)
        ratio = moe_active_ratio(f"{repo} {base}")
        out.append({"file": path, "size": size, "quant": q.group(1).upper() if q else "",
                    "moe": ratio is not None, "active_ratio": round(ratio or 1.0, 2),
                    **estimate(size, hw, ratio or 1.0, q.group(1) if q else "")})
    return sorted(out, key=lambda x: x["size"])


# ── downloads ─────────────────────────────────────────────────────────────────

_downloads: dict[str, dict] = {}
_dl_lock = threading.Lock()


def _run_download(job: dict) -> None:
    dest = config.MODELS_DIR / job["name"]
    part = dest.with_name(dest.name + ".part")
    url = f"{HF}/{urllib.parse.quote(job['repo'], safe='/')}/resolve/main/{urllib.parse.quote(job['file'])}"
    try:
        config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "herama"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as out:
            job["total"] = int(r.headers.get("Content-Length") or job["total"])
            t0 = time.time()
            while chunk := r.read(1 << 20):
                if job["cancel"]:
                    raise InterruptedError("cancelled")
                out.write(chunk)
                job["done"] += len(chunk)
                job["speed"] = job["done"] / max(time.time() - t0, 1e-6)
        os.replace(part, dest)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "cancelled" if isinstance(e, InterruptedError) else "error"
        job["error"] = "" if job["state"] == "cancelled" else str(e)
        part.unlink(missing_ok=True)
        log.warning("model download %s: %s", job["name"], e)


def start_download(repo: str, file: str, size: int = 0) -> dict:
    name = file.rsplit("/", 1)[-1]
    if not name.lower().endswith(".gguf"):
        raise ValueError("only .gguf files can be downloaded")
    with _dl_lock:
        for j in _downloads.values():
            if j["name"] == name and j["state"] == "downloading":
                return j
        job = {"id": uuid.uuid4().hex[:8], "repo": repo, "file": file, "name": name, "state": "downloading",
               "done": 0, "total": size, "speed": 0.0, "error": "", "cancel": False}
        _downloads[job["id"]] = job
    threading.Thread(target=_run_download, args=(job,), daemon=True).start()
    return job


def cancel_download(job_id: str) -> bool:
    job = _downloads.get(job_id)
    if job:
        job["cancel"] = True
    return bool(job)


def downloads() -> list[dict]:
    return [{k: v for k, v in j.items() if k != "cancel"} for j in _downloads.values()]
