"""Per-model settings proposal: GPU layers and MoE experts kept on the CPU for a chosen context length."""
import math
from pathlib import Path

from app import hub, resources

GB = 1024 ** 3
EXPERT_SHARE = 0.88       # share of a MoE file that is expert tensors
EXPERT_READ_SHARE = 0.8   # share of the bytes read per token that comes from experts
RESERVE_GB = 1.2          # driver, display and compute buffers kept free in VRAM


def _kv_gb(m: dict, ctx: int, layers: int) -> float:
    emb = int(m.get("embedding_length") or 4096)
    heads = int(m.get("attention.head_count") or 32)
    kv_heads = m.get("attention.head_count_kv")
    kv_heads = int(kv_heads) if isinstance(kv_heads, (int, float)) and kv_heads > 0 else heads
    return 2 * layers * (emb * kv_heads // heads) * 2 * ctx / GB  # K and V in f16


def _speed(size: float, ratio: float, moe: bool, layers: int, ngl: int, cpu_moe: int,
           hw: dict, quant_factor: float) -> float:
    g = min(1.0, ngl / layers)
    active = size * ratio / quant_factor
    expert = active * EXPERT_READ_SHARE if moe else 0.0
    other = active - expert
    expert_gpu = max(0.0, g - cpu_moe / layers) if moe else 0.0
    gpu_read = other * g + expert * expert_gpu
    cpu_read = active - gpu_read
    gpu_bw = hw["gpu_bandwidth"] * hub.GPU_EFFICIENCY
    cpu_bw = hw.get("cpu_bandwidth", hub.CPU_BANDWIDTH)
    sec = (gpu_read / gpu_bw if gpu_read and gpu_bw else 0.0) + cpu_read / cpu_bw
    if gpu_read and not gpu_bw:
        sec += gpu_read / cpu_bw
    return round(1 / sec, 1) if sec > 0 else 0.0


def propose(model: Path, ctx: int, ngl: int | None = None, cpu_moe: int | None = None) -> dict:
    """Preliminary settings for `ctx`; pass ngl/cpu_moe to re-estimate user-edited values."""
    hw = hub.hardware()
    m = resources.gguf_meta(model)
    layers = int(m.get("block_count") or 32)
    ctx_train = int(m.get("context_length") or 4096)
    experts = int(m.get("expert_count") or 0)
    moe = experts > 1
    size = model.stat().st_size / GB
    kv = _kv_gb(m, ctx, layers)
    vram_budget = max(hw["vram_total_gb"] - RESERVE_GB, 0.0)
    ram_budget = max(hw["ram_total_gb"] * 0.9 - 2.0, 0.0)
    ratio = (hub.moe_active_ratio(model.name) or 0.2) if moe else 1.0
    ef = EXPERT_SHARE if moe else 0.0
    expert_layer = size * ef / layers

    auto_ngl, auto_moe = layers, 0
    if vram_budget <= 0:
        auto_ngl = 0
    elif size + kv > vram_budget:
        if moe:  # keep attention and shared weights on the GPU and move experts out layer by layer
            auto_moe = min(layers, math.ceil((size + kv - vram_budget) / expert_layer))
            if size * (1 - ef) + kv > vram_budget:
                auto_moe = layers
                auto_ngl = max(0, int(layers * (vram_budget - kv) / max(size * (1 - ef), 0.01)))
        else:
            auto_ngl = max(0, int(layers * max(vram_budget - kv, 0) / size))
    use_ngl = auto_ngl if ngl is None else max(0, min(layers, ngl))
    use_moe = auto_moe if cpu_moe is None else max(0, min(layers, cpu_moe)) if moe else 0

    g = use_ngl / layers
    gpu_experts = max(0.0, g - use_moe / layers) if moe else 0.0
    vram = size * (1 - ef) * g + size * ef * gpu_experts + kv * g
    ram = size + kv - vram
    q = hub._QUANT.search(model.name)
    tps = _speed(size, ratio, moe, layers, use_ngl, use_moe, hw, hub.quant_speed_factor(q.group(1) if q else ""))
    return {
        "layers": layers, "moe": moe, "experts": experts, "ctx": ctx, "ctx_train": ctx_train,
        "ngl": use_ngl, "cpu_moe": use_moe, "kv_gb": round(kv, 1), "vram_gb": round(vram, 1),
        "ram_gb": round(max(ram, 0.0), 1), "tps": tps, "size_gb": round(size, 1),
        "fits": vram <= vram_budget + 0.01 and ram <= ram_budget, "vram_budget_gb": round(vram_budget, 1),
        "ctx_over_training": ctx > ctx_train,
    }
