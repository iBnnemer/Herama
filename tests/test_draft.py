from app import server_llm


def _cmd(monkeypatch, tmp_path, draft):
    seen = {}
    monkeypatch.setattr(server_llm.subprocess, "Popen", lambda cmd, **k: seen.setdefault("cmd", cmd) and type("P", (), {})())
    monkeypatch.setattr(server_llm, "_bind_to_parent", lambda p: None)
    monkeypatch.setattr(server_llm.ServerLLM, "_wait_ready", lambda self: None)
    server_llm.ServerLLM(tmp_path / "llama-server", tmp_path / "big.gguf", 4096, None, tmp_path / "log", draft=draft)
    return seen["cmd"]


def test_draft_flags(monkeypatch, tmp_path):
    cmd = _cmd(monkeypatch, tmp_path, tmp_path / "small.gguf")
    assert cmd[cmd.index("-md") + 1].endswith("small.gguf") and "--draft-max" in cmd


def test_no_draft_by_default(monkeypatch, tmp_path):
    assert "-md" not in _cmd(monkeypatch, tmp_path, None)
