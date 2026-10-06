"""Hugging Face GGUF model search, speed estimation, and download manager."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

# ---------------------------------------------------------------------------
# Hardware constants (user's machine: 10.8 GB VRAM, 31.2 GB RAM)
# Can be overridden via env vars.
# ---------------------------------------------------------------------------
VRAM_TOTAL_BYTES = int(float(os.getenv("HERAMA_VRAM_GB", "10.8")) * 1024 ** 3)
RAM_TOTAL_BYTES = int(float(os.getenv("HERAMA_RAM_GB", "31.2")) * 1024 ** 3)

# Empirical tokens/sec per GB/s memory bandwidth (rough but useful)
# RTX 3060 ~360 GB/s; typical CPU ~50 GB/s
VRAM_BW_GBPS = float(os.getenv("HERAMA_VRAM_BW", "360"))
CPU_BW_GBPS = float(os.getenv("HERAMA_CPU_BW", "50"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModelCard:
    repo_id: str
    filename: str
    size_bytes: int
    quantization: str         # e.g. "Q4_K_M", "Q8_0"
    param_billions: float     # estimated from name or size
    # filled by estimate_performance():
    vram_used_gb: float = 0.0
    ram_used_gb: float = 0.0
    gpu_layers: int = 0
    estimated_tps: float = 0.0
    fit_label: str = ""       # "Full VRAM" / "Split VRAM+RAM" / "CPU Only"

    @property
    def size_gb(self) -> float:
        return self.size_bytes / 1024 ** 3

    def __str__(self) -> str:
        return (
            f"{self.repo_id}/{self.filename}  "
            f"[{self.quantization}]  {self.size_gb:.1f} GB  "
            f"~{self.estimated_tps:.0f} tok/s  {self.fit_label}"
        )


@dataclass
class DownloadProgress:
    filename: str
    total_bytes: int
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    done: bool = False
    error: str = ""

    @property
    def pct(self) -> float:
        return self.downloaded_bytes / self.total_bytes * 100 if self.total_bytes else 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _ensure_hf() -> None:
    """Install huggingface_hub if missing."""
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "huggingface_hub", "--quiet"])


def _quant_from_name(filename: str) -> str:
    """Extract quantisation tag from filename, e.g. Q4_K_M."""
    import re
    m = re.search(r"(Q\d+_K_[MS]|Q\d+_\d|IQ\d+_[A-Z]+|F16|F32|BF16)", filename, re.IGNORECASE)
    return m.group(1).upper() if m else "UNKNOWN"


def _params_from_name(repo_id: str, size_bytes: int) -> float:
    """Rough param count (billions) from repo name or file size."""
    import re
    m = re.search(r"(\d+\.?\d*)b", repo_id, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # fallback: Q4 ≈ 0.5 bytes/param → params ≈ size/0.5
    return size_bytes / 0.5 / 1e9


def search_gguf(query: str, limit: int = 20) -> list[ModelCard]:
    """Search Hugging Face for GGUF models matching *query*."""
    _ensure_hf()
    from huggingface_hub import HfApi
    api = HfApi()
    results: list[ModelCard] = []

    repos = api.list_models(
        search=query,
        filter="gguf",
        sort="downloads",
        direction=-1,
        limit=limit,
    )

    for repo in repos:
        try:
            files = api.list_repo_files(repo.id)
            for fname in files:
                if not fname.lower().endswith(".gguf"):
                    continue
                try:
                    info = api.get_paths_info(repo.id, [fname])
                    size = next(iter(info)).size or 0
                except Exception:
                    size = 0
                quant = _quant_from_name(fname)
                params = _params_from_name(repo.id, size)
                card = ModelCard(
                    repo_id=repo.id,
                    filename=fname,
                    size_bytes=size,
                    quantization=quant,
                    param_billions=params,
                )
                results.append(card)
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Performance estimator
# ---------------------------------------------------------------------------

# Tokens/second formula:
#   memory_bandwidth_GB/s / (bytes_per_token) × 1000
#   bytes_per_token ≈ param_billions × 10^9 × bytes_per_param / tokens_per_step
#   Simplified to: BW_GB/s × 1e9 / model_size_bytes × context_factor
#   context_factor ≈ 1 (single-token decode; KV-cache already resident)

def estimate_performance(card: ModelCard,
                         vram_free_gb: float | None = None,
                         ram_free_gb: float | None = None) -> ModelCard:
    """Fill card.vram_used_gb, ram_used_gb, gpu_layers, estimated_tps, fit_label."""
    vram_free = (vram_free_gb or VRAM_TOTAL_BYTES / 1024 ** 3) * 1024 ** 3
    ram_free = (ram_free_gb or RAM_TOTAL_BYTES / 1024 ** 3) * 1024 ** 3
    size = card.size_bytes or 1

    # KV cache overhead ~5 % of model size for typical ctx
    kv_overhead = size * 0.05

    if size + kv_overhead <= vram_free:
        # --- Full VRAM ---
        card.fit_label = "Full VRAM"
        card.vram_used_gb = (size + kv_overhead) / 1024 ** 3
        card.ram_used_gb = 0.0
        card.gpu_layers = -1
        # bandwidth-limited: BW / bytes_per_param (Q4 ≈ 0.5 B, Q8 ≈ 1 B)
        bpb = _bytes_per_param(card.quantization)
        card.estimated_tps = (VRAM_BW_GBPS * 1e9) / (card.param_billions * 1e9 * bpb)
    elif size > vram_free + ram_free:
        # --- CPU Only ---
        card.fit_label = "CPU Only"
        card.vram_used_gb = 0.0
        card.ram_used_gb = size / 1024 ** 3
        card.gpu_layers = 0
        bpb = _bytes_per_param(card.quantization)
        card.estimated_tps = (CPU_BW_GBPS * 1e9) / (card.param_billions * 1e9 * bpb)
    else:
        # --- Split VRAM + RAM ---
        gpu_frac = min(1.0, vram_free / size)
        total_layers = max(32, int(card.param_billions * 4))  # rough
        card.gpu_layers = max(1, int(total_layers * gpu_frac))
        card.vram_used_gb = size * gpu_frac / 1024 ** 3
        card.ram_used_gb = size * (1 - gpu_frac) / 1024 ** 3
        card.fit_label = f"Split {card.vram_used_gb:.1f}GB VRAM + {card.ram_used_gb:.1f}GB RAM"
        bpb = _bytes_per_param(card.quantization)
        # Harmonic mean of GPU/CPU throughput weighted by fraction
        tps_gpu = (VRAM_BW_GBPS * 1e9) / (card.param_billions * 1e9 * bpb)
        tps_cpu = (CPU_BW_GBPS * 1e9) / (card.param_billions * 1e9 * bpb)
        card.estimated_tps = 1 / (gpu_frac / tps_gpu + (1 - gpu_frac) / tps_cpu)

    # Cap at a sane ceiling
    card.estimated_tps = min(card.estimated_tps, 999.0)
    return card


def _bytes_per_param(quant: str) -> float:
    """Approximate bytes per parameter for a quantisation level."""
    tbl = {
        "F32": 4.0, "F16": 2.0, "BF16": 2.0,
        "Q8_0": 1.0,
        "Q6_K": 0.75,
        "Q5_K_M": 0.625, "Q5_K_S": 0.625, "Q5_0": 0.625,
        "Q4_K_M": 0.5, "Q4_K_S": 0.5, "Q4_0": 0.5,
        "Q3_K_M": 0.375, "Q3_K_S": 0.375, "Q3_K_L": 0.375,
        "Q2_K": 0.3125,
    }
    for key, val in tbl.items():
        if quant.startswith(key):
            return val
    return 0.5  # default Q4-ish


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_model(
    repo_id: str,
    filename: str,
    dest_dir: Path,
    progress_cb: Callable[[DownloadProgress], None] | None = None,
) -> Path:
    """Download *filename* from *repo_id* into *dest_dir* with live progress."""
    _ensure_hf()
    from huggingface_hub import hf_hub_url
    import urllib.request

    url = hf_hub_url(repo_id, filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(filename).name

    req = urllib.request.Request(url, headers={"User-Agent": "herama/0.1"})
    prog = DownloadProgress(filename=filename, total_bytes=0)

    with urllib.request.urlopen(req) as resp:
        prog.total_bytes = int(resp.headers.get("Content-Length", 0))
        chunk = 1024 * 1024  # 1 MB
        t0 = time.perf_counter()
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                prog.downloaded_bytes += len(buf)
                elapsed = time.perf_counter() - t0 or 1e-9
                prog.speed_bps = prog.downloaded_bytes / elapsed
                if progress_cb:
                    progress_cb(prog)

    prog.done = True
    if progress_cb:
        progress_cb(prog)
    return dest


def download_model_async(
    repo_id: str,
    filename: str,
    dest_dir: Path,
    progress_cb: Callable[[DownloadProgress], None] | None = None,
) -> threading.Thread:
    """Start download in background thread; returns the Thread."""
    t = threading.Thread(
        target=download_model,
        args=(repo_id, filename, dest_dir, progress_cb),
        daemon=True,
    )
    t.start()
    return t
