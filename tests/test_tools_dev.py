import json
import shutil
import socket
import sys
import time

import pytest

from app import tools, tools_dev


def ws(tmp_path):
    return [str(tmp_path)]


def test_condense_keeps_errors_and_tail():
    lines = [f"line {i}" for i in range(500)]
    lines[250] = "ERROR something broke"
    out = tools_dev.condense("\n".join(lines))
    assert "ERROR something broke" in out and "line 499" in out and len(out.splitlines()) < 100
    assert tools_dev.condense("short\ntext") == "short\ntext"


def test_detect_checks(tmp_path):
    assert tools_dev.detect_checks(tmp_path) == []
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "x", "lint": "y"}}))
    labels = [c[1] for c in tools_dev.detect_checks(tmp_path)]
    assert labels == ["pytest", "npm test", "npm run lint"]


def test_run_checks_reports_failure(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_bad():\n    assert 1 == 2\n")
    r = tools.run("run_checks", {"what": "tests"}, ws(tmp_path))
    assert r["ok"] and "FAILED" in r["result"] and "assert" in r["result"]


def test_background_process_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_dev.config, "ROOT", tmp_path)
    cmd = f'"{sys.executable}" -u -c "import time; print(\'ready\', flush=True); time.sleep(30)"'
    r = tools.run("start_process", {"command": cmd}, ws(tmp_path))
    assert r["ok"], r
    pid = r["result"].split()[2]
    out = tools.run("process_output", {"id": pid}, ws(tmp_path))["result"]
    assert "running" in out and "ready" in out
    assert "running" in tools.run("list_processes", {}, ws(tmp_path))["result"]
    assert tools.run("stop_process", {"id": pid}, ws(tmp_path))["ok"]
    assert "exited" in tools.run("process_output", {"id": pid}, ws(tmp_path))["result"]


def test_check_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        assert "in use" in tools.run("check_port", {"port": port})["result"]
    assert "free" in tools.run("check_port", {"port": port})["result"]
    assert not tools.run("check_port", {"port": 0})["ok"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_commit_flow_and_clone_guard(tmp_path):
    d = ws(tmp_path)
    for cmd in ("init -q", "config user.email t@t", "config user.name t"):
        assert tools_dev._git(tmp_path, *cmd.split()) is not None
    (tmp_path / "a.txt").write_text("hi")
    assert "a.txt" in tools.run("git_status", {}, d)["result"]
    assert "Committed 1" in tools.run("git_commit", {"message": "add a"}, d)["result"]
    (tmp_path / "a.txt").write_text("hello")
    assert "hello" in tools.run("git_diff", {}, d)["result"]
    (tmp_path / "id_rsa").write_text("secret")
    bad = tools.run("git_commit", {"message": "oops"}, d)
    assert not bad["ok"] and "sensitive" in bad["result"]
    assert not tools.run("git_clone", {"url": "https://evil.example/x/y"}, d)["ok"]
    assert not tools.run("git_clone", {"url": "file:///etc"}, d)["ok"]


def test_shell_argv_for_each_shell(monkeypatch):
    monkeypatch.setattr(tools_dev, "available_shells", lambda: ["pwsh", "powershell", "cmd"])
    monkeypatch.setattr(tools_dev.shutil, "which", lambda n: f"C:/bin/{n}.exe")
    ps = tools_dev.shell_argv("Get-Date")
    assert ps[0].endswith("pwsh.exe") and "-NoProfile" in ps and ps[-1].endswith("Get-Date") and "UTF8" in ps[-1]
    assert tools_dev.shell_argv("dir", "cmd")[1:3] == ["/d", "/c"]
    assert tools_dev.shell_argv("x", "powershell")[0].endswith("powershell.exe")
    with pytest.raises(tools.ToolError):
        tools_dev.shell_argv("ls", "bash")


def test_run_command_with_shell_choice(tmp_path):
    r = tools.run("run_command", {"command": "echo hello"}, ws(tmp_path))
    assert r["ok"] and "hello" in r["result"]
    bad = tools.run("run_command", {"command": "echo hi", "shell": "zsh-nope"}, ws(tmp_path))
    assert not bad["ok"] and "not available" in bad["result"]


def test_environment_facts_list_real_versions():
    text = tools_dev.environment_facts(refresh=True)
    assert "Operating system:" in text and "python:" in text and "Shells you can choose" in text
