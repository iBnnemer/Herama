"""llama.cpp runtime: asset selection and the llama-server adapter (against a fake server)."""
import json
import os
import stat
import sys
import types

if "llama_cpp" not in sys.modules:
    lm = types.ModuleType("llama_cpp")
    lm.Llama = type("Llama", (), {"__init__": lambda s, **k: None})
    sys.modules["llama_cpp"] = lm

import pytest

from app import runtime

ASSETS = [
    "llama-b9000-bin-win-cpu-x64.zip", "llama-b9000-bin-win-cpu-arm64.zip",
    "llama-b9000-bin-win-vulkan-x64.zip", "llama-b9000-bin-win-hip-radeon-x64.zip",
    "llama-b9000-bin-win-cuda-12.4-x64.zip", "llama-b9000-bin-win-cuda-13.1-x64.zip",
    "cudart-llama-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-13.1-x64.zip",
    "llama-b9000-bin-ubuntu-x64.tar.gz", "llama-b9000-bin-ubuntu-vulkan-x64.tar.gz",
    "llama-b9000-bin-macos-arm64.tar.gz", "llama-b9000-bin-macos-x64.tar.gz",
]


def test_pick_cuda_matches_driver_version():
    out = runtime.pick_assets(ASSETS, "cuda", "Windows", "AMD64", cuda="12.8")
    assert out == ["llama-b9000-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip"]
    out = runtime.pick_assets(ASSETS, "cuda", "Windows", "AMD64", cuda="13.2")
    assert out[0].endswith("cuda-13.1-x64.zip") and out[1].startswith("cudart")


def test_pick_cuda_too_old_driver_returns_none():
    assert runtime.pick_assets(ASSETS, "cuda", "Windows", "AMD64", cuda="11.8") is None


def test_pick_vulkan_cpu_and_unix():
    assert runtime.pick_assets(ASSETS, "vulkan", "Windows", "AMD64") == ["llama-b9000-bin-win-vulkan-x64.zip"]
    assert runtime.pick_assets(ASSETS, "cpu", "Windows", "AMD64") == ["llama-b9000-bin-win-cpu-x64.zip"]
    assert runtime.pick_assets(ASSETS, "cpu", "Linux", "x86_64") == ["llama-b9000-bin-ubuntu-x64.tar.gz"]
    assert runtime.pick_assets(ASSETS, "metal", "Darwin", "arm64") == ["llama-b9000-bin-macos-arm64.tar.gz"]


def test_forced_backend(monkeypatch):
    monkeypatch.setenv("HERAMA_BACKEND", "vulkan")
    assert runtime.detect_backend() == "vulkan"


FAKE_SERVER = r'''
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
port = int(args[args.index("--port") + 1])
open(sys.argv[0] + ".args", "w").write(" ".join(args))

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        if not body.get("stream"):
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                                         "usage": {"completion_tokens": 2}}).encode()); return
        self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        chunks = [{"choices": [{"delta": {"content": "Hel"}}]}, {"choices": [{"delta": {"content": "lo"}}]},
                  {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                  {"choices": [], "usage": {"completion_tokens": 2}}]
        for c in chunks:
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


@pytest.fixture
def fake_binary(tmp_path):
    (tmp_path / "fake_server.py").write_text(FAKE_SERVER)
    script = tmp_path / "llama-server"
    script.write_text(f'#!/bin/sh\nexec {sys.executable} {tmp_path / "fake_server.py"} "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.mark.skipif(os.name == "nt", reason="uses a shell script as fake binary")
def test_engine_chat_through_server(tmp_path, monkeypatch, fake_binary):
    import app.config as cfg
    from app.engine import Engine
    models = tmp_path / "models"
    models.mkdir()
    (models / "Gemma-X-Q4.gguf").write_bytes(b"GGUF")
    (models / "mmproj-Gemma-X-BF16.gguf").write_bytes(b"GGUF")
    monkeypatch.setattr(cfg, "MODELS_DIR", models)
    monkeypatch.setattr(runtime, "ensure_binary", lambda: fake_binary)
    monkeypatch.setattr(runtime, "current_backend", lambda: "vulkan")
    monkeypatch.setattr(runtime, "RUNTIME_DIR", tmp_path / "rt")

    eng = Engine()
    out = list(eng.chat("Gemma-X-Q4", [{"role": "user", "content": "hi"}], {"num_ctx": 2048}, True))
    try:
        assert out[:2] == ["Hel", "lo"]
        final = out[-1]
        assert final["choices"][0]["finish_reason"] == "stop"
        assert final["usage"]["completion_tokens"] == 2
        args = (tmp_path / "fake_server.py.args").read_text()
        assert "--mmproj" in args and "mmproj-Gemma-X-BF16.gguf" in args and "-c 2048" in args
        assert eng.ps()["n_gpu_layers"] == -1
        text = eng.chat("Gemma-X-Q4", [{"role": "user", "content": "hi"}], {"num_ctx": 2048}, False)
        assert next(text) == "Hello"
    finally:
        eng.unload()


def test_pick_assets_alt_naming():
    names = ["llama-v0.6.0-windows-x86_64-vulkan.zip", "llama-v0.6.0-windows-x86_64-cpu.zip", "notes.txt"]
    assert runtime.pick_assets(names, "vulkan", "Windows", "AMD64") == ["llama-v0.6.0-windows-x86_64-vulkan.zip"]
    assert runtime.pick_assets(names, "cpu", "Windows", "AMD64") == ["llama-v0.6.0-windows-x86_64-cpu.zip"]
