"""Per-model settings proposal: GPU layers and MoE experts kept on the CPU for a chosen context length."""
import math
import re
from pathlib import Path

from app import calib, hub, resources

GB = 1024 ** 3
EXPERT_SHARE = 0.88       # share of a MoE file that is expert tensors
EXPERT_READ_SHARE = 0.8   # share of the bytes read per token that comes from experts
KV_SCALE = {"f16": 1.0, "q8_0": 0.53, "q4_0": 0.28}   # relative KV cache size per cache type
KV_TYPES = tuple(KV_SCALE)
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
           hw: dict, quant_factor: float, k_scale: float = 1.0, kv: float = 0.0) -> float:
    g = min(1.0, ngl / layers)
    active = size * ratio / quant_factor
    expert = active * EXPERT_READ_SHARE * k_scale if moe else 0.0
    other = active * (1 - EXPERT_READ_SHARE) if moe else active
    active = expert + other
    expert_gpu = max(0.0, g - cpu_moe / layers) if moe else 0.0
    gpu_read = other * g + expert * expert_gpu + kv * 0.5 * g   # attention reads the filled half of the KV cache
    expert_cpu = expert * (1 - expert_gpu)
    other_cpu = other * (1 - g) + kv * 0.5 * (1 - g)
    gpu_bw = hw["gpu_bandwidth"] * hub.GPU_EFFICIENCY
    cpu_bw = hw.get("cpu_bandwidth", hub.CPU_BANDWIDTH)
    if not gpu_bw:  # no usable GPU: everything runs on the CPU
        other_cpu, gpu_read = other_cpu + gpu_read, 0.0
    sec = (gpu_read / gpu_bw if gpu_read else 0.0) + other_cpu / cpu_bw + expert_cpu / (cpu_bw * hub.MOE_CPU_EFFICIENCY)
    return round(1 / sec, 1) if sec > 0 else 0.0


def _learned_ratio(model: Path, ctx: int) -> tuple[float, int] | None:
    """Measured/estimated speed ratio for this model, interpolated over context length."""
    pts = []
    for e in calib.entries(model.stem):
        raw = propose(model, e["ctx"], e["ngl"], e["cpu_moe"], e["top_k"] or None, learn=False,
                      kv_type=e.get("kv", "f16"))["tps"]
        if raw > 0:
            pts.append((math.log2(e["ctx"]), e["tps"] / raw))
    if not pts:
        return None
    pts.sort()
    x = math.log2(ctx)
    lo = [p for p in pts if p[0] <= x]
    hi = [p for p in pts if p[0] >= x]
    if lo and hi and lo[-1][0] != hi[0][0]:
        (x0, r0), (x1, r1) = lo[-1], hi[0]
        r = r0 + (r1 - r0) * (x - x0) / (x1 - x0)
    else:
        r = (lo[-1] if lo else hi[0])[1]
    return min(1.5, max(0.2, r)), len(pts)


def propose(model: Path, ctx: int, ngl: int | None = None, cpu_moe: int | None = None,
            top_k: int | None = None, learn: bool = True, kv_type: str = "f16") -> dict:
    """Preliminary settings for `ctx`; pass ngl/cpu_moe to re-estimate user-edited values.

    With learn=True the speed is corrected by what this machine measured earlier for this model."""
    hw = hub.hardware()
    m = resources.gguf_meta(model)
    layers = int(m.get("block_count") or 32)
    ctx_train = int(m.get("context_length") or 4096)
    experts = int(m.get("expert_count") or 0)
    moe = experts > 1
    size = model.stat().st_size / GB
    kv = _kv_gb(m, ctx, layers, model.name) * KV_SCALE.get(kv_type, 1.0)
    vram_budget = max(hw["vram_total_gb"] - RESERVE_GB, 0.0)
    ram_budget = max(hw["ram_total_gb"] * 0.9 - 2.0, 0.0)
    used = int(m.get("expert_used_count") or 0)
    named = hub.moe_active_ratio(model.name)
    if not moe:
        ratio = 1.0
    elif named and named != 0.2:  # explicit "A3B" or "8x7B" in the name
        ratio = named
    else:  # shared layers plus the experts routed per token, from the GGUF header
        ratio = min(1.0, 0.07 + 0.93 * used / experts) if used else 0.2
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
    tps = _speed(size, ratio, moe, layers, use_ngl, use_moe, hw, hub.quant_speed_factor(q.group(1) if q else ""), k_scale, kv)
    learned = ""
    if learn:
        exact = next((e for e in calib.entries(model.stem) if e["ctx"] == ctx and e["ngl"] == min(use_ngl, layers)
                      and e["cpu_moe"] == use_moe and e["top_k"] in (0, use_k) and e.get("kv", "f16") == kv_type), None)
        if exact:
            tps, learned = exact["tps"], "measured"
        elif (lr := _learned_ratio(model, ctx)):
            tps, learned = round(tps * lr[0], 1), "learned"
    return {
        "calibrated": learned, "kv_type": kv_type, "layers": layers, "moe": moe, "experts": experts, "ctx": ctx, "ctx_train": ctx_train,
        "ngl": use_ngl, "cpu_moe": use_moe, "top_k": use_k, "default_top_k": default_k, "kv_gb": round(kv, 1), "vram_gb": round(vram, 1),
        "ram_gb": round(max(ram, 0.0), 1), "tps": tps, "size_gb": round(size, 1),
        "fits": vram <= vram_budget + 0.01 and ram <= ram_budget, "vram_budget_gb": round(vram_budget, 1),
        "ctx_over_training": ctx > ctx_train,
    }


def auto(model: Path, ctx: int, learn: bool = True) -> dict:
    """Settings chosen without user input: more experts/layers on the CPU first, then a compressed KV cache,
    and finally a lower context when nothing else makes it fit."""
    best, fitting = None, []
    # a model whose name says Q4 always keeps a q4_0 KV cache
    q4_named = bool(re.search(r"q4", model.name, re.I))
    q8_named = bool(re.search(r"q8", model.name, re.I))  # starts at q8_0 and drops to q4_0 when the context grows
    kinds = ("q4_0",) if q4_named else ("q8_0", "q4_0") if q8_named else KV_TYPES
    for kv in kinds:
        p = propose(model, ctx, learn=learn, kv_type=kv)
        if not p["fits"]:
            continue
        fitting.append(p)
        # MoE: moving expert layers to the CPU is cheap, so allow up to 60%. Dense: every layer stays on the GPU
        # and the KV cache is compressed first, because offloading dense layers costs much more speed.
        heavy = p["cpu_moe"] > 0.6 * p["layers"] if p["moe"] else p["ngl"] < p["layers"]
        if not heavy:
            best = p
            break
    if best is None and fitting:  # everything fits only with heavy offload: take the least offload
        best = max(fitting, key=lambda p: (p["ngl"] - p["cpu_moe"], p["kv_type"] == "f16"))
    adjusted: list[str] = []
    if best is None:  # even the smallest cache with the most offload does not fit: find the largest context that does
        lo, hi, found = 512, ctx, None
        while lo <= hi:
            mid = max(512, (lo + hi) // 2 // 256 * 256)
            p = propose(model, mid, learn=False, kv_type="q4_0")
            if p["fits"]:
                found, lo = p, mid + 256
            else:
                hi = mid - 256
        best = propose(model, found["ctx"] if found else 512, learn=learn, kv_type="q4_0")
        adjusted.append(f"Context limited to {best['ctx']}: the most this PC can hold")
    if best["kv_type"] != "f16" and not q4_named and not (q8_named and best["kv_type"] == "q8_0"):
        adjusted.append(f"KV cache: f16 -> {best['kv_type']}")
    if best["cpu_moe"]:
        adjusted.append(f"Expert layers on CPU: {best['cpu_moe']} of {best['layers']}")
    elif best["ngl"] < best["layers"]:
        adjusted.append(f"GPU layers: {best['ngl']} of {best['layers']}")
    return {**best, "adjusted": adjusted, "requested_ctx": ctx, "manual": False}
