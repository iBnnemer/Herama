"""Tests for the per-model settings proposal."""
import sys
import types

if "llama_cpp" not in sys.modules:
    lm = types.ModuleType("llama_cpp")
    lm.Llama = type("Llama", (), {"__init__": lambda s, **k: None})
    sys.modules["llama_cpp"] = lm
if "pynvml" not in sys.modules:
    pm = types.ModuleType("pynvml")
    pm.nvmlInit = lambda: None
    pm.nvmlDeviceGetHandleByIndex = lambda i: None
    pm.nvmlDeviceGetMemoryInfo = lambda h: type("M", (), {"free": 0})()
    sys.modules["pynvml"] = pm

from app import hub, resources, tune

GB = 1024 ** 3
HW = {"gpu": "RTX 3080 Ti", "vram_total_gb": 12.0, "vram_free_gb": 12.0, "gpu_bandwidth": 912,
      "ram_total_gb": 32.0, "ram_free_gb": 20.0, "cpu_bandwidth": 80.0}


def _model(tmp_path, monkeypatch, size_gb, meta, name="m-Q4_K_M.gguf"):
    f = tmp_path / name
    f.write_bytes(b"\0")
    monkeypatch.setattr(type(f), "stat", lambda self, **k: types.SimpleNamespace(st_size=int(size_gb * GB)))
    monkeypatch.setattr(resources, "gguf_meta", lambda p: meta)
    monkeypatch.setattr(hub, "hardware", lambda: HW)
    return f


DENSE = {"block_count": 40, "context_length": 32768, "embedding_length": 5120,
         "attention.head_count": 40, "attention.head_count_kv": 8}
MOE = {**DENSE, "block_count": 48, "expert_count": 128}


def test_dense_fits_then_offloads_as_context_grows(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 7, DENSE)
    small = tune.propose(f, 4096)
    assert small["ngl"] == 40 and small["cpu_moe"] == 0 and small["fits"]
    huge = tune.propose(f, 32768)
    assert huge["kv_gb"] > small["kv_gb"] and huge["tps"] <= small["tps"]


def test_moe_moves_experts_to_cpu_when_context_grows(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 17, MOE, "Qwen3-30B-A3B-Q4_K_M.gguf")
    short = tune.propose(f, 4096)
    long = tune.propose(f, 32768)
    assert short["moe"] and short["cpu_moe"] > 0           # 17 GB cannot sit fully in 12 GB
    assert long["cpu_moe"] >= short["cpu_moe"] and long["fits"]
    assert short["tps"] > 15                                 # active experts keep it fast


def test_user_override_is_reestimated(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 17, MOE, "Qwen3-30B-A3B-Q4_K_M.gguf")
    base = tune.propose(f, 4096)
    more = tune.propose(f, 4096, cpu_moe=base["cpu_moe"] + 10)
    assert more["cpu_moe"] == base["cpu_moe"] + 10 and more["vram_gb"] < base["vram_gb"] and more["tps"] < base["tps"]


def test_sliding_window_model_has_small_kv(tmp_path, monkeypatch):
    gemma = {**DENSE, "block_count": 48, "context_length": 131072, "attention.head_count_kv": 8,
             "attention.sliding_window": 1024, "attention.sliding_window_pattern": 6}
    f = _model(tmp_path, monkeypatch, 7, gemma, "gemma-12b-Q4_K_M.gguf")
    sw = tune.propose(f, 65536)
    full = tune.propose(_model(tmp_path, monkeypatch, 7, {**DENSE, "block_count": 48}, "plain-Q4_K_M.gguf"), 65536)
    assert sw["kv_gb"] < full["kv_gb"] / 4 and sw["ngl"] == 48


def test_fewer_active_experts_is_faster(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 17, {**MOE, "expert_used_count": 8}, "Qwen3-30B-A3B-Q4_K_M.gguf")
    base = tune.propose(f, 4096)
    fast = tune.propose(f, 4096, top_k=4)
    assert base["top_k"] == 8 and fast["top_k"] == 4 and fast["tps"] > base["tps"]
