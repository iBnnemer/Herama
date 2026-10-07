"""Adapter that exposes a llama-server process through the small llama-cpp-python API Engine uses."""
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

_START_TIMEOUT = 900  # seconds; big models on slow disks take a while


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerLLM:
    def __init__(self, binary: Path, model: Path, n_ctx: int, mmproj: Path | None, log_path: Path):
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        cmd = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(n_ctx), "--jinja"]
        if mmproj:
            cmd += ["--mmproj", str(mmproj)]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = log_path
        self._log = open(log_path, "wb")
        self.proc = subprocess.Popen(
            cmd, stdout=self._log, stderr=subprocess.STDOUT, cwd=str(binary.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        try:
            self._wait_ready()
        except Exception:
            self.close()
            raise

    def _tail(self) -> str:
        try:
            return self._log_path.read_text("utf-8", "replace")[-600:].strip()
        except OSError:
            return ""

    def _wait_ready(self) -> None:
        deadline = time.time() + _START_TIMEOUT
        while time.time() < deadline:
            code = self.proc.poll()
            if code is not None:
                raise RuntimeError(f"llama-server exited with code {code}: {self._tail()}")
            try:
                with urllib.request.urlopen(f"{self.base}/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        raise RuntimeError("llama-server did not become ready in time")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._log.close()

    # ── requests ──────────────────────────────────────────────────────────────

    def _open(self, path: str, body: dict):
        req = urllib.request.Request(f"{self.base}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"llama-server {e.code}: {detail}") from None

    @staticmethod
    def _body(kw: dict, **extra) -> dict:
        body = {k: v for k, v in kw.items() if v is not None}
        body.update(extra)
        return body

    def _json(self, path: str, body: dict) -> dict:
        with self._open(path, body) as r:
            return json.load(r)

    def _stream(self, path: str, body: dict):
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        resp = self._open(path, body)
        last, usage = None, None
        try:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                if obj.get("error"):
                    raise RuntimeError(str(obj["error"]))
                if obj.get("usage"):
                    usage = obj["usage"]
                if obj.get("choices"):
                    last = obj
                    yield obj
            if last is not None and usage:
                last["usage"] = usage
        finally:
            resp.close()

    # ── llama-cpp-python style API ────────────────────────────────────────────

    def __call__(self, prompt: str, stream: bool = False, **kw):
        body = self._body(kw, prompt=prompt)
        return self._stream("/v1/completions", body) if stream else self._json("/v1/completions", body)

    def create_chat_completion(self, messages: list[dict], stream: bool = False, **kw):
        body = self._body(kw, messages=messages)
        return self._stream("/v1/chat/completions", body) if stream else self._json("/v1/chat/completions", body)

    def create_embedding(self, text: str) -> dict:
        raise RuntimeError("embeddings are not available with the llama-server runtime")
