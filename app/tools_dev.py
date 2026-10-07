"""Developer tools: background processes, ports, project checks and git. Registered into app.tools."""
import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil

from app import config
from app.tools import B, I, S, ToolError, _arr, _sensitive, safe, tool

MAX_PROCS = 8
_PROCS: dict[str, dict] = {}
_ERR_LINE = re.compile(r"(error|exception|traceback|fail(ed|ure)?|assert|warning:|\bE\s{2,}|^\s*\^)", re.I)


def condense(text: str, head: int = 5, tail: int = 30, errors: int = 40) -> str:
    """Shorten long tool output: the first lines, every error-looking line and the last lines."""
    lines = text.splitlines()
    if len(lines) <= head + tail + errors:
        return text
    mid = lines[head:len(lines) - tail]
    hits = [l for l in mid if _ERR_LINE.search(l)][:errors]
    cut = len(mid) - len(hits)
    return "\n".join([*lines[:head], f"[... {cut} lines left out ...]", *hits, "[...]", *lines[-tail:]])


# -- shells and the machine's own versions --------------------------------------

def available_shells() -> list[str]:
    """Shell names usable here, the preferred (default) one first."""
    if os.name == "nt":
        out = []
        if shutil.which("pwsh"):
            out.append("pwsh")
        if shutil.which("powershell"):
            out.append("powershell")
        return out + ["cmd"]
    return (["bash"] if shutil.which("bash") else []) + ["sh"]


def shell_argv(command: str, shell: str = "") -> list[str]:
    shells = available_shells()
    shell = (shell or shells[0]).lower()
    if shell == "powershell" and "powershell" not in shells and "pwsh" in shells:
        shell = "pwsh"
    if shell not in shells:
        raise ToolError(f"shell '{shell}' is not available here; use one of: {', '.join(shells)}")
    if shell in ("pwsh", "powershell"):
        prefix = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
        return [shutil.which(shell) or shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", prefix + command]
    if shell == "cmd":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", command]
    return [shutil.which(shell) or shell, "-c", command]


def _version(argv: list[str]) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=6,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[0][:80] if (r.stdout or r.stderr) else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


_ENV_CACHE: str | None = None


def environment_facts(refresh: bool = False) -> str:
    """What this computer really has, so commands are written for these versions (computed once, then cached)."""
    global _ENV_CACHE
    if _ENV_CACHE is not None and not refresh:
        return _ENV_CACHE
    import platform
    shells = available_shells()
    lines = [f"Operating system: {platform.system()} {platform.release()} (version {platform.version()}), {platform.machine()}"]
    lines.append(f"Shells you can choose in run_command (shell argument): {', '.join(shells)}. Default: {shells[0]}.")
    if os.name == "nt":
        for sh in ("pwsh", "powershell"):
            if sh in shells:
                v = _version([shutil.which(sh) or sh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"])
                lines.append(f"{sh} version: {v or 'unknown'}" + (" (Windows PowerShell 5.1: no '&&' between commands, use ';'; no ternary or null-coalescing operators)" if v.startswith("5.") else ""))
        lines.append("Paths use backslashes; the drive letters present: " + ", ".join(f"{c}:" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{c}:\\")))
    tools_seen = [("python", [sys.executable or "python", "--version"]), ("git", ["git", "--version"]), ("node", ["node", "--version"]), ("npm", ["npm", "--version"])]
    for name, argv in tools_seen:
        if argv[0] in (sys.executable, "python") or shutil.which(argv[0]):
            v = _version(argv if os.name != "nt" or argv[0] != "npm" else [shutil.which("npm") or "npm", "--version"])
            lines.append(f"{name}: {v or 'installed (version unknown)'}")
        else:
            lines.append(f"{name}: not installed")
    _ENV_CACHE = "\n".join(lines)
    return _ENV_CACHE


# -- background processes -----------------------------------------------------

def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(proc.pid)
        for ch in parent.children(recursive=True):
            ch.kill()
        parent.kill()
    except psutil.Error:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


@atexit.register
def _stop_all() -> None:
    for p in _PROCS.values():
        if p["proc"].poll() is None:
            _kill_tree(p["proc"])


def _proc(pid: str) -> dict:
    p = _PROCS.get(str(pid))
    if p is None:
        raise ToolError(f"no process {pid}; call list_processes")
    return p


def _state(p: dict) -> str:
    code = p["proc"].poll()
    return "running" if code is None else f"exited with code {code}"


def _tail(p: dict, lines: int) -> str:
    try:
        text = p["log"].read_text("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-max(1, min(lines, 400)):])


@tool("start_process", "Shell", "exec",
      "Start a long-running command in the background (a dev server, a watcher) and return its id. Read its output later with process_output; stop it with stop_process.",
      {"command": S, "folder": S, "shell": S}, ["command"])
def _start_process(a, ctx):
    running = [k for k, p in _PROCS.items() if p["proc"].poll() is None]
    if len(running) >= MAX_PROCS:
        raise ToolError(f"{MAX_PROCS} processes are already running; stop one first")
    cwd = safe(ctx, a.get("folder") or ".", write=True)
    pid = str(max((int(k) for k in _PROCS), default=0) + 1)
    log = config.ROOT / ".processes" / f"{pid}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "wb")
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(shell_argv(a["command"], a.get("shell", "")), cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
    _PROCS[pid] = {"proc": proc, "log": log, "command": a["command"], "started": time.time()}
    time.sleep(1.0)  # a command that fails at once should say so right away
    return f"Started process {pid} ({_state(_PROCS[pid])}).\n{_tail(_PROCS[pid], 20)}".strip()


@tool("process_output", "Shell", "read", "Show the latest output and status of a background process started with start_process.",
      {"id": S, "lines": I}, ["id"])
def _process_output(a, ctx):
    p = _proc(a["id"])
    return f"[{_state(p)}]\n{_tail(p, int(a.get('lines') or 60))}".strip()


@tool("list_processes", "Shell", "read", "List the background processes started with start_process and whether each one still runs.")
def _list_processes(a, ctx):
    return "\n".join(f"{k}: {_state(p)} - {p['command'][:80]}" for k, p in _PROCS.items()) or "No background processes."


@tool("stop_process", "Shell", "exec", "Stop a background process (and everything it started).", {"id": S}, ["id"])
def _stop_process(a, ctx):
    p = _proc(a["id"])
    if p["proc"].poll() is not None:
        return f"Process {a['id']} had already {_state(p)}."
    _kill_tree(p["proc"])
    return f"Stopped process {a['id']}."


@tool("check_port", "Shell", "read",
      "Check whether a local network port is in use and by what, so a server does not clash with another one. Also suggests a free port.",
      {"port": I}, ["port"])
def _check_port(a, ctx):
    port = int(a["port"])
    if not 1 <= port <= 65535:
        raise ToolError("port must be between 1 and 65535")

    def busy(n: int) -> bool:
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", n)) == 0

    if not busy(port):
        return f"Port {port} is free."
    who = ""
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN and c.pid:
                who = f" by {psutil.Process(c.pid).name()} (pid {c.pid})"
                break
    except (psutil.Error, OSError):
        pass
    free = next((n for n in range(port + 1, port + 200) if not busy(n)), None)
    return f"Port {port} is in use{who}." + (f" Port {free} is free." if free else "")


# -- project checks -----------------------------------------------------------

def detect_checks(folder: Path) -> list[tuple[str, str, list[str]]]:
    """(kind, label, command) for the tests and linters this project appears to use."""
    out: list[tuple[str, str, list[str]]] = []
    py = [sys.executable or "python", "-m"]
    has = lambda *names: any((folder / n).exists() for n in names)  # noqa: E731
    if has("pytest.ini", "tox.ini", "conftest.py", "tests") or any(folder.glob("test_*.py")):
        out.append(("tests", "pytest", [*py, "pytest", "-q", "--tb=short", "-x"]))
    if has("ruff.toml", ".ruff.toml"):
        out.append(("lint", "ruff", [*py, "ruff", "check", "."]))
    elif has(".flake8", "setup.cfg"):
        out.append(("lint", "flake8", [*py, "flake8", "."]))
    elif has("pyproject.toml") and "[tool.ruff" in (folder / "pyproject.toml").read_text("utf-8", errors="replace"):
        out.append(("lint", "ruff", [*py, "ruff", "check", "."]))
    pkg = folder / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text("utf-8")).get("scripts", {})
        except ValueError:
            scripts = {}
        npm = shutil.which("npm") or "npm"
        if "test" in scripts:
            out.append(("tests", "npm test", [npm, "test", "--silent"]))
        if "lint" in scripts:
            out.append(("lint", "npm run lint", [npm, "run", "lint", "--silent"]))
    return out


@tool("run_checks", "Shell", "exec",
      "Run the project's automated tests and linter (pytest, ruff or flake8, npm test and lint are detected by themselves) and return a short report with only the failures. Use it after changing code.",
      {"folder": S, "what": {"type": "string", "enum": ["all", "tests", "lint"]}}, [])
def _run_checks(a, ctx):
    cwd = safe(ctx, a.get("folder") or ".", write=True)
    want = a.get("what") or "all"
    checks = [c for c in detect_checks(cwd) if want in ("all", c[0])]
    if not checks:
        return "No tests or linter were detected in this folder. Run them yourself with run_command."
    report = []
    for kind, label, cmd in checks:
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=300,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = condense((r.stdout or "") + (r.stderr or ""))
            report.append(f"## {label}: {'passed' if r.returncode == 0 else f'FAILED (exit {r.returncode})'}\n{out.strip()}")
        except subprocess.TimeoutExpired:
            report.append(f"## {label}: timed out after 300 s")
        except FileNotFoundError:
            report.append(f"## {label}: the tool is not installed")
    return "\n\n".join(report)


# -- git ----------------------------------------------------------------------

_GITHUB = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$")


def _git(cwd: Path, *args: str, timeout: int = 120) -> str:
    if shutil.which("git") is None:
        raise ToolError("git is not installed")
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ToolError("the git command timed out") from None
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode:
        raise ToolError(out or f"git exited with code {r.returncode}")
    return out


@tool("git_clone", "Git", "write", "Download a GitHub repository (https://github.com/owner/name) into a folder of the workspace.",
      {"url": S, "folder": S}, ["url"])
def _git_clone(a, ctx):
    url = (a.get("url") or "").strip()
    if not _GITHUB.match(url):
        raise ToolError("only https://github.com/owner/name addresses can be cloned")
    name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    parent = safe(ctx, a.get("folder") or ".", write=True)
    dest = parent / name
    if dest.exists():
        raise ToolError(f"{dest} already exists")
    _git(parent, "clone", "--depth", "50", url, name, timeout=600)
    return f"Cloned into {dest}"


@tool("git_status", "Git", "read", "Show the branch and the changed files of a git project.", {"folder": S}, [])
def _git_status(a, ctx):
    return _git(safe(ctx, a.get("folder") or "."), "status", "--short", "--branch") or "Clean."


@tool("git_diff", "Git", "read", "Show the uncommitted changes of a git project (optionally one path, or the staged ones).",
      {"folder": S, "path": S, "staged": B}, [])
def _git_diff(a, ctx):
    args = ["diff", "--no-color"] + (["--staged"] if a.get("staged") else []) + (["--", a["path"]] if a.get("path") else [])
    out = _git(safe(ctx, a.get("folder") or "."), *args)
    return condense(out, head=200, tail=60, errors=0) if out else "No changes."


@tool("git_commit", "Git", "write", "Commit the changes of a git project locally with a clear message (all changes, or only the listed paths). Never pushes.",
      {"folder": S, "message": S, "paths": _arr(S)}, ["message"])
def _git_commit(a, ctx):
    cwd = safe(ctx, a.get("folder") or ".", write=True)
    msg = (a.get("message") or "").strip()
    if len(msg) < 3:
        raise ToolError("write a clear commit message")
    paths = [str(p) for p in a.get("paths") or []]
    _git(cwd, "add", *(paths or ["-A"]))
    staged = [p for p in _git(cwd, "diff", "--staged", "--name-only").splitlines() if p]
    bad = [p for p in staged if _sensitive(cwd / p)]
    if bad:
        _git(cwd, "reset", "-q")
        raise ToolError(f"refusing to commit sensitive files: {', '.join(bad)}")
    if not staged:
        return "Nothing to commit."
    _git(cwd, "commit", "-m", msg)
    return f"Committed {len(staged)} file(s): {msg}"


@tool("git_push", "Git", "exec",
      "Push the committed work to the remote repository using the user's own git login. The user is asked to confirm every push.",
      {"folder": S}, [])
def _git_push(a, ctx):
    return _git(safe(ctx, a.get("folder") or ".", write=True), "push", timeout=300) or "Pushed."
