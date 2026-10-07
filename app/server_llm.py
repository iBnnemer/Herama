"""Adapter that exposes a llama-server process through the small llama-cpp-python API Engine uses."""
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from app import monitor

_START_TIMEOUT = 900  # seconds; big models on slow disks take a while


_job = None


def _bind_to_parent(proc: subprocess.Popen) -> None:
    """Windows: put the child in a job object that kills it when this process dies, however it dies."""
    global _job
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if _job is None:
            _job = k32.CreateJobObjectW(None, None)
            info = Extended()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(wintypes.HANDLE(_job), 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(wintypes.HANDLE(_job), wintypes.HANDLE(int(proc._handle)))
    except Exception:  # best effort; the stale-process cleanup at startup is the backstop
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerLLM:
    def __init__(self, binary: Path, model: Path, n_ctx: int, mmproj: Path | None, log_path: Path, ngl: int | None = None,
                 cpu_moe: int = 0, expert_used: tuple[str, int] | None = None, kv_type: str = "f16", threads: int = 0,
                 draft: Path | None = None):
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        cmd = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(n_ctx), "--jinja"]
        if ngl is not None:  # explicit GPU layer count; otherwise llama-server picks one itself
            cmd += ["-ngl", str(ngl)]
        if kv_type != "f16":  # compressed KV cache needs flash attention
            cmd += ["-ctk", kv_type, "-ctv", kv_type, "-fa", "on"]
        if threads:
            cmd += ["-t", str(threads)]
        if cpu_moe:  # keep the experts of the first N layers in system RAM
            cmd += ["--n-cpu-moe", str(cpu_moe)]
        if expert_used:  # fewer active experts per token: faster, lower quality
            cmd += ["--override-kv", f"{expert_used[0]}.expert_used_count=int:{expert_used[1]}"]
        if draft:  # speculative decoding: a small draft model proposes tokens, the main model verifies them
            cmd += ["-md", str(draft), "-ngld", "999", "--draft-max", "16", "--draft-min", "1"]
        if mmproj:
            cmd += ["--mmproj", str(mmproj)]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path = log_path
        self._log = open(log_path, "wb")
        self.proc = subprocess.Popen(
            cmd, stdout=self._log, stderr=subprocess.STDOUT, cwd=str(binary.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        _bind_to_parent(self.proc)
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
        body["return_progress"] = True
        resp = self._open(path, body)
        last, usage, thinking, timings = None, None, False, None
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
                if obj.get("timings"):
                    timings = obj["timings"]
                if obj.get("prompt_progress"):
                    pp = obj["prompt_progress"]
                    monitor.progress(pp.get("processed", 0), pp.get("total", 0))
                if obj.get("choices"):
                    delta = obj["choices"][0].get("delta") or {}
                    think = delta.pop("reasoning_content", None)
                    if think:  # keep the model's reasoning visible instead of dropping it
                        delta["content"] = ("" if thinking else "<think>") + think
                        thinking = True
                    elif thinking and delta.get("content"):
                        delta["content"] = "</think>\n" + delta["content"]
                        thinking = False
                    last = obj
                    yield obj
            if last is not None and usage:
                last["usage"] = usage
            if last is not None and timings:
                last["timings"] = timings
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
