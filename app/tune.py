"""Per-model settings proposal: GPU layers and MoE experts kept on the CPU for a chosen context length."""
import math
from pathlib import Path

from app import hub, resources

GB = 1024 ** 3
EXPERT_SHARE = 0.88       # share of a MoE file that is expert tensors
EXPERT_READ_SHARE = 0.8   # share of the bytes read per token that comes from experts
RESERVE_GB = 1.2          # driver, display and compute buffers kept free in VRAM


def _per_layer(v, layers: int, default: int) -> list[int]:
    if isinstance(v, list) and v:
        return [int(x) for x in (v + [v[-1]] * layers)[:layers]]
    return [int(v) if isinstance(v, (int, float)) and v > 0 else default] * layers


def _kv_gb(m: dict, ctx: int, layers: int, name: str = "") -> float:
    """f16 KV cache size. Handles per-layer KV heads, layers without attention and sliding-window layers."""
    emb = int(m.get("embedding_length") or 4096)
    heads = int(m.get("attention.head_count") or 32)
    kvh = _per_layer(m.get("attention.head_count_kv"), layers, heads)
    kl, vl = m.get("attention.key_length"), m.get("attention.value_length")
    width = int(kl) + int(vl) if isinstance(kl, (int, float)) and isinstance(vl, (int, float)) else 2 * (emb // heads)
    window = m.get("attention.sliding_window")
    pattern = m.get("attention.sliding_window_pattern")
    window = int(window) if isinstance(window, (int, float)) and window > 0 else 0
    if isinstance(pattern, list) and window:
        sliding = [bool(x) for x in (pattern + [0] * layers)[:layers]]
    elif window and isinstance(pattern, int) and pattern > 1:
        sliding = [(i + 1) % pattern != 0 for i in range(layers)]
    elif "gemma" in name.lower():  # metadata gave no usable pattern: Gemma uses 5 local layers per global one
        window = window or 1024
        sliding = [(i + 1) % 6 != 0 for i in range(layers)]
    else:
        sliding = [False] * layers
    total = sum(width * k * 2 * (min(ctx, window) if sw else ctx) for k, sw in zip(kvh, sliding))
    return total / GB


def _speed(size: float, ratio: float, moe: bool, layers: int, ngl: int, cpu_moe: int,
           hw: dict, quant_factor: float, k_scale: float = 1.0) -> float:
    g = min(1.0, ngl / layers)
    active = size * ratio / quant_factor
    expert = active * EXPERT_READ_SHARE * k_scale if moe else 0.0
    other = active * (1 - EXPERT_READ_SHARE) if moe else active
    active = expert + other
    expert_gpu = max(0.0, g - cpu_moe / layers) if moe else 0.0
    gpu_read = other * g + expert * expert_gpu
    cpu_read = active - gpu_read
    gpu_bw = hw["gpu_bandwidth"] * hub.GPU_EFFICIENCY
    cpu_bw = hw.get("cpu_bandwidth", hub.CPU_BANDWIDTH)
    sec = (gpu_read / gpu_bw if gpu_read and gpu_bw else 0.0) + cpu_read / cpu_bw
    if gpu_read and not gpu_bw:
        sec += gpu_read / cpu_bw
    return round(1 / sec, 1) if sec > 0 else 0.0


def propose(model: Path, ctx: int, ngl: int | None = None, cpu_moe: int | None = None,
            top_k: int | None = None) -> dict:
    """Preliminary settings for `ctx`; pass ngl/cpu_moe to re-estimate user-edited values."""
    hw = hub.hardware()
    m = resources.gguf_meta(model)
    layers = int(m.get("block_count") or 32)
    ctx_train = int(m.get("context_length") or 4096)
    experts = int(m.get("expert_count") or 0)
    moe = experts > 1
    size = model.stat().st_size / GB
    kv = _kv_gb(m, ctx, layers, model.name)
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
    default_k = int(m.get("expert_used_count") or 0) if moe else 0
    use_k = max(1, min(experts, top_k)) if (moe and top_k and default_k) else default_k
    k_scale = use_k / default_k if default_k else 1.0
    q = hub._QUANT.search(model.name)
    tps = _speed(size, ratio, moe, layers, use_ngl, use_moe, hw, hub.quant_speed_factor(q.group(1) if q else ""), k_scale)
    return {
        "layers": layers, "moe": moe, "experts": experts, "ctx": ctx, "ctx_train": ctx_train,
        "ngl": use_ngl, "cpu_moe": use_moe, "top_k": use_k, "default_top_k": default_k, "kv_gb": round(kv, 1), "vram_gb": round(vram, 1),
        "ram_gb": round(max(ram, 0.0), 1), "tps": tps, "size_gb": round(size, 1),
        "fits": vram <= vram_budget + 0.01 and ram <= ram_budget, "vram_budget_gb": round(vram_budget, 1),
        "ctx_over_training": ctx > ctx_train,
    }
