"""Tests for API key middleware."""
import sys
import types

import pytest
from fastapi.testclient import TestClient

# ── stubs ─────────────────────────────────────────────────────────────────────
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
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_no_key_configured():
    """Without HERAMA_API_KEY all requests pass through."""
    cfg.API_KEY = ""
    r = client.get("/api/version")
    assert r.status_code == 200


def test_key_required_missing(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEY", "secret123")
    r = client.get("/api/version")
    assert r.status_code == 401


def test_key_bearer(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEY", "secret123")
    r = client.get("/api/version", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 200


def test_key_raw(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEY", "secret123")
    r = client.get("/api/version", headers={"Authorization": "secret123"})
    assert r.status_code == 200


def test_key_wrong(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEY", "secret123")
    r = client.get("/api/version", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
