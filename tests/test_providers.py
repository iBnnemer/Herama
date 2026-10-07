import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

if "llama_cpp" not in sys.modules:
    lm = types.ModuleType("llama_cpp")
    lm.Llama = type("Llama", (), {"__init__": lambda s, **k: None})
    sys.modules["llama_cpp"] = lm

import app.config as cfg
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SEEN = {}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN["auth"], SEEN["body"] = self.headers.get("Authorization"), body
        if self.headers.get("Authorization") != "Bearer sk-secret-key":
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"bad key sk-secret-key"}'); return
        self.send_response(200)
        if body.get("stream"):
            self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for ch in ({"choices": [{"delta": {"content": "Hel"}}]}, {"choices": [{"delta": {"content": "lo"}}]},
                       {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "f", "arguments": "{}"}}]}}]},
                       {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}):
                self.wfile.write(b"data: " + json.dumps(ch).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode())


def _server():
    s = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}/v1"


def test_save_test_list_and_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MEMORY_DIR", tmp_path)
    srv, base = _server()
    try:
        entry = {"provider": "Custom", "model": "m1", "base_url": base, "api_key": "sk-secret-key", "label": "mine"}
        assert client.post("/api/providers/test", json=entry).json()["ok"]
        bad = client.post("/api/providers/test", json={**entry, "api_key": "sk-wrong-key"}).json()
        assert not bad["ok"] and "401" in bad["detail"]
        assert client.post("/api/providers", json={**entry, "base_url": "ftp://x"}).status_code == 400
        saved = client.post("/api/providers", json=entry).json()
        assert saved["has_key"] and "api_key" not in saved
        assert "sk-secret-key" not in json.dumps(client.get("/api/providers").json())
        assert any(m["name"] == "api:mine" for m in client.get("/api/tags").json()["models"])
        # editing without a new key keeps the stored one, and test reuses it
        assert client.post("/api/providers/test", json={**entry, "id": saved["id"], "api_key": ""}).json()["ok"]
        r = client.post("/api/chat", json={"model": "api:mine", "messages": [{"role": "user", "content": "hi"}],
                                           "options": {"temperature": 0.3}})
        lines = [json.loads(x) for x in r.text.splitlines() if x]
        assert "".join(x["message"]["content"] for x in lines if not x["done"]) == "Hello"
        final = lines[-1]
        assert final["done"] and final["eval_count"] == 2 and final["message"]["tool_calls"][0]["function"]["name"] == "f"
        assert SEEN["body"]["model"] == "m1" and SEEN["body"]["temperature"] == 0.3
        assert client.delete(f"/api/providers/{saved['id']}").status_code == 200
        assert not any(m["name"] == "api:mine" for m in client.get("/api/tags").json()["models"])
    finally:
        srv.shutdown()
