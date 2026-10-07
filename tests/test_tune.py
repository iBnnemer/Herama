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
    orig = type(f).stat
    monkeypatch.setattr(type(f), "stat", lambda self, **k: types.SimpleNamespace(st_size=int(size_gb * GB))
                        if self == f else orig(self, **k))
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


def test_per_layer_metadata_arrays(tmp_path, monkeypatch):
    # 48 layers: every 6th is global, the rest slide over 1024 tokens; some layers have no attention (0 KV heads)
    meta = {**DENSE, "block_count": 48, "attention.head_count_kv": [8] * 40 + [0] * 8,
            "attention.sliding_window": 1024, "attention.sliding_window_pattern": [1, 1, 1, 1, 1, 0] * 8}
    f = _model(tmp_path, monkeypatch, 7, meta, "gemma-x-Q4_K_M.gguf")
    assert tune.propose(f, 65536)["kv_gb"] < 3


def test_calibration_learns_from_measurements(tmp_path, monkeypatch):
    import app.config as cfg
    from app import calib
    (tmp_path / "mem").mkdir()
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path / "mem")
    f = _model(tmp_path, monkeypatch, 7, DENSE, "calib-Q4_K_M.gguf")
    raw = tune.propose(f, 65536)
    assert raw["calibrated"] == ""
    calib.record(f.stem, 65536, raw["ngl"], raw["cpu_moe"], 0, raw["tps"] / 2)
    again = tune.propose(f, 65536)
    assert again["calibrated"] == "measured" and again["tps"] == round(raw["tps"] / 2, 2)
    other = tune.propose(f, 131072)            # not measured, but the model runs about half as fast as estimated
    assert other["calibrated"] == "learned" and 0.4 < other["tps"] / tune.propose(f, 131072, learn=False)["tps"] < 0.6
    calib.record(f.stem, 65536, raw["ngl"], raw["cpu_moe"], 0, raw["tps"] / 2)
    assert calib.entries(f.stem)[0]["n"] == 2


def test_auto_prefers_cpu_experts_then_kv_compression_then_context_cap(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 17, {**MOE, "context_length": 1_000_000}, "Qwen3-30B-A3B-Q4_K_M.gguf")
    short = tune.auto(f, 8192)
    assert short["kv_type"] == "f16" and short["cpu_moe"] > 0 and not short["adjusted"][0].startswith("Context")
    big = tune.auto(f, 98304)
    assert big["kv_type"] != "f16" and big["fits"] and big["ctx"] == 98304
    huge = tune.auto(f, 4_000_000)
    assert huge["kv_type"] == "q4_0" and huge["ctx"] < 4_000_000 and huge["fits"]
    assert any(a.startswith("Context limited") for a in huge["adjusted"])
    assert huge["requested_ctx"] == 4_000_000


def test_auto_small_dense_model_needs_no_adjustment(tmp_path, monkeypatch):
    f = _model(tmp_path, monkeypatch, 7, DENSE)
    a = tune.auto(f, 4096)
    assert a["kv_type"] == "f16" and a["ngl"] == a["layers"] and a["adjusted"] == []
