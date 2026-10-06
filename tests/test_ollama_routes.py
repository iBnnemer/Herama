"""Smoke tests for Ollama-compatible routes using a fake engine."""
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient


# ── fake llama-cpp so import succeeds without the native library ──────────────
llama_mod = types.ModuleType("llama_cpp")


class _FakeLlama:
    def __init__(self, **kw): pass

    def __call__(self, prompt, stream=False, **kw):
        token = {"choices": [{"text": "hi", "finish_reason": "stop"}], "usage": {}}
        if stream:
            return iter([token])
        return token

    def create_chat_completion(self, messages, stream=False, **kw):
        token = {"choices": [{"message": {"role": "assistant", "content": "hi"},
                               "delta": {"content": "hi"}, "finish_reason": "stop"}], "usage": {}}
        if stream:
            return iter([token])
        return token

    def create_embedding(self, text):
        return {"data": [{"embedding": [0.1, 0.2]}]}


llama_mod.Llama = _FakeLlama
sys.modules["llama_cpp"] = llama_mod

# ── fake pynvml ───────────────────────────────────────────────────────────────
pynvml_mod = types.ModuleType("pynvml")
pynvml_mod.nvmlInit = lambda: None
pynvml_mod.nvmlDeviceGetHandleByIndex = lambda i: None
pynvml_mod.nvmlDeviceGetMemoryInfo = lambda h: type("M", (), {"free": 0})()
sys.modules["pynvml"] = pynvml_mod

from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_models(tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path / ".memory")
    monkeypatch.setattr(cfg, "SKILLS_DIR", tmp_path / "skills")
    # create a fake GGUF file (4-byte magic only — enough for path resolution)
    (tmp_path / "testmodel.gguf").write_bytes(b"GGUF" + b"\x00" * 28)
    yield


def test_tags():
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert "models" in r.json()


def test_version():
    assert client.get("/api/version").status_code == 200


def test_ps_empty():
    r = client.get("/api/ps")
    assert r.json()["models"] == []


def test_show():
    r = client.post("/api/show", json={"name": "testmodel"})
    assert r.status_code == 200
    assert r.json()["model"] == "testmodel"


def test_show_not_found():
    assert client.post("/api/show", json={"name": "nope"}).status_code == 404


def test_generate_no_stream():
    r = client.post("/api/generate", json={"model": "testmodel", "prompt": "hello", "stream": False})
    assert r.status_code == 200
    assert "response" in r.json()


def test_chat_no_stream():
    r = client.post("/api/chat", json={
        "model": "testmodel",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    })
    assert r.status_code == 200
    assert r.json()["message"]["role"] == "assistant"


def test_embeddings():
    r = client.post("/api/embeddings", json={"model": "testmodel", "prompt": "hello"})
    assert r.status_code == 200
    assert isinstance(r.json()["embedding"], list)


def test_pull_stub():
    r = client.post("/api/pull", json={"name": "somemodel", "stream": False})
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_delete_not_found():
    assert client.request("DELETE", "/api/delete", json={"name": "nope"}).status_code == 404
