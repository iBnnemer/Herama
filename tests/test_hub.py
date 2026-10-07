"""Tests for the Hugging Face hub helpers (network mocked)."""
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

from fastapi.testclient import TestClient

import app.config as cfg
from app import hub
from app.main import app

client = TestClient(app)
GB = 1024 ** 3
HW = {"gpu": "NVIDIA GeForce RTX 3080 Ti", "vram_total_gb": 12.0, "vram_free_gb": 11.0,
      "gpu_bandwidth": 912, "ram_total_gb": 32.0, "ram_free_gb": 20.0}


def test_estimate_full_gpu_matches_measurement():
    e = hub.estimate(int(7 * GB), HW)
    assert e["fit"] == "gpu" and 60 < e["tps"] < 80  # measured 70.8 t/s on this card


def test_estimate_split_and_cpu():
    e = hub.estimate(int(20 * GB), HW)
    assert e["fit"] == "split" and e["tps"] < 20
    cpu = {**HW, "vram_total_gb": 0, "vram_free_gb": 0, "gpu_bandwidth": 0}
    e = hub.estimate(int(7 * GB), cpu)
    assert e["fit"] == "cpu" and 5 < e["tps"] < 10
    assert hub.estimate(int(100 * GB), cpu)["fit"] == "too_big"


def test_files_filters_and_sorts(monkeypatch):
    tree = [
        {"type": "file", "path": "m-Q8_0.gguf", "lfs": {"size": 8 * GB}},
        {"type": "file", "path": "m-Q4_K_M.gguf", "lfs": {"size": 4 * GB}},
        {"type": "file", "path": "mmproj-m.gguf", "lfs": {"size": GB}},
        {"type": "file", "path": "big-00001-of-00003.gguf", "lfs": {"size": GB}},
        {"type": "file", "path": "README.md", "size": 10},
    ]
    monkeypatch.setattr(hub, "_get_json", lambda url: tree)
    monkeypatch.setattr(hub, "hardware", lambda: HW)
    out = hub.files("a/b")
    assert [f["file"] for f in out] == ["m-Q4_K_M.gguf", "m-Q8_0.gguf"]
    assert out[0]["quant"] == "Q4_K_M" and out[0]["tps"] > out[1]["tps"]


def test_search_route(monkeypatch):
    monkeypatch.setattr(hub, "_get_json", lambda url: [{"id": "a/b", "downloads": 5, "likes": 1}])
    assert client.get("/api/hub/search?q=x").json() == [{"id": "a/b", "downloads": 5, "likes": 1}]


def test_download_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MODELS_DIR", tmp_path)

    class Resp:
        headers = {"Content-Length": "6"}
        def __init__(self): self.parts = [b"abc", b"def", b""]
        def read(self, n): return self.parts.pop(0)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(hub.urllib.request, "urlopen", lambda *a, **k: Resp())
    job = hub.start_download("a/b", "sub/m.gguf", 6)
    for _ in range(100):
        if job["state"] != "downloading":
            break
        import time; time.sleep(0.02)
    assert job["state"] == "done" and (tmp_path / "m.gguf").read_bytes() == b"abcdef"
    assert client.post("/api/hub/download", json={"repo": "a/b", "file": "x.txt"}).status_code == 400
