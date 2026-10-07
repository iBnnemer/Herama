"""Tests for /api/agents CRUD and CORS."""
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


def test_agents_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path)
    assert client.get("/api/agents").json() == []
    a = client.post("/api/agents", json={"name": "coder", "system_prompt": "be brief"}).json()
    assert a["name"] == "coder" and a["id"]
    assert client.patch(f"/api/agents/{a['id']}", json={"model": "m1"}).json()["model"] == "m1"
    assert len(client.get("/api/agents").json()) == 1
    assert client.delete(f"/api/agents/{a['id']}").status_code == 200
    assert client.delete(f"/api/agents/{a['id']}").status_code == 404


def test_agent_requires_name(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path)
    assert client.post("/api/agents", json={"name": " "}).status_code == 400


def test_cors_preflight():
    r = client.options("/api/agents", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"
