"""Measured generation speeds per model and settings, used to correct the speed estimates."""
import json
import threading

from app import config

_lock = threading.Lock()


def _file():
    return config.MEMORY_DIR / "calibration.json"


def _load() -> dict:
    try:
        return json.loads(_file().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def record(model: str, ctx: int, ngl: int, cpu_moe: int, top_k: int, tps: float, kv: str = "f16") -> None:
    """Remember a measured speed; repeated runs with the same settings are averaged."""
    key = f"{ctx}|{ngl}|{cpu_moe}|{top_k}|{kv}"
    with _lock:
        data = _load()
        e = data.setdefault(model, {}).get(key)
        if e:
            e["tps"] = round(e["tps"] * 0.6 + tps * 0.4, 2)
            e["n"] += 1
        else:
            data[model][key] = {"ctx": ctx, "ngl": ngl, "cpu_moe": cpu_moe, "top_k": top_k, "kv": kv, "tps": round(tps, 2), "n": 1}
        try:
            config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            _file().write_text(json.dumps(data), "utf-8")
        except OSError:
            pass


def entries(model: str) -> list[dict]:
    return list(_load().get(model, {}).values())
