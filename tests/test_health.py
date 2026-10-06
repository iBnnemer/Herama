"""Tests for /health endpoint."""
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

import app.config as cfg
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_no_model(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(cfg, "API_KEY", "")
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model"] is None
    assert body["models_available"] == 0


def test_health_sees_gguf(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(cfg, "API_KEY", "")
    (tmp_path / "phi3.gguf").write_bytes(b"GGUF" + b"\x00" * 28)
    r = client.get("/health")
    assert r.json()["models_available"] == 1


def test_health_requires_auth(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEY", "tok")
    r = client.get("/health")
    assert r.status_code == 401
