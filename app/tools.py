"""Built-in tools every agent can call: files, web, shell, skills, memory and small utilities.

Each tool has a JSON schema (sent to the model), a `kind` the UI uses for permissions
(read / net / memory / write / exec) and a function that runs on the backend.
"""
import ast
import difflib
import fnmatch
import ipaddress
import json
import math
import operator
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from app import config

MAX_RESULT = 20000          # characters returned to the model per call
MAX_READ_BYTES = 400_000
MAX_LISTING = 500
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}
SECRET_RE = re.compile(r"(password|passwd|pwd|api[_ -]?key|secret|token)\s*[:=]|\bsk-[A-Za-z0-9]{16,}|\b[0-9a-f]{32,}\b", re.I)


class ToolError(Exception):
    """A problem the model should see and can react to."""


@dataclass
class Tool:
    name: str
    group: str
    kind: str
    desc: str
    props: dict
    required: list[str]
    fn: Callable[[dict, "Ctx"], str] = field(repr=False)

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.desc,
            "parameters": {"type": "object", "properties": self.props, "required": self.required}}}


@dataclass
class Ctx:
    dirs: list[Path]


REGISTRY: dict[str, Tool] = {}


def tool(name: str, group: str, kind: str, desc: str, props: dict | None = None, required: list[str] | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, group, kind, desc, props or {}, required or [], fn)
        return fn
    return deco


S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}


def _arr(item: dict) -> dict:
    return {"type": "array", "items": item}


# ── path safety ───────────────────────────────────────────────────────────────

def workspace() -> Path:
    p = config.ROOT / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_ctx(dirs: list[str] | None) -> Ctx:
    found = [Path(d).expanduser().resolve() for d in (dirs or []) if d and Path(d).expanduser().is_dir()]
    return Ctx(found or [workspace().resolve()])


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def safe(ctx: Ctx, path: str, must_exist: bool = True) -> Path:
    """Resolve `path` (relative paths start in the first allowed folder) and refuse anything outside the allowed folders."""
    if not path:
        raise ToolError("path is required")
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = ctx.dirs[0] / p
    p = p.resolve()
    if not any(_inside(p, d) for d in ctx.dirs):
        raise ToolError(f"{p} is outside the allowed folders: {', '.join(str(d) for d in ctx.dirs)}")
    if must_exist and not p.exists():
        raise ToolError(f"{p} does not exist")
    return p


def _read_text(p: Path) -> str:
    if not p.is_file():
        raise ToolError(f"{p} is not a file")
    data = p.read_bytes()[:MAX_READ_BYTES + 1]
    if b"\x00" in data[:4096]:
        raise ToolError(f"{p.name} looks like a binary file")
    text = data[:MAX_READ_BYTES].decode("utf-8", "replace")
    return text + ("\n[truncated]" if len(data) > MAX_READ_BYTES else "")


def _fmt_size(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return ""


# ── files ─────────────────────────────────────────────────────────────────────

@tool("workspace_folders", "Files", "read", "List the folders you are allowed to use. Relative paths start in the first one.")
def _workspace_folders(a, ctx):
    return "\n".join(str(d) for d in ctx.dirs)


@tool("list_files", "Files", "read", "List the files and sub-folders of a folder, with file sizes.",
      {"path": S, "sort": {"type": "string", "enum": ["name", "size"]}}, [])
def _list_files(a, ctx):
    p = safe(ctx, a.get("path") or ".")
    if not p.is_dir():
        raise ToolError(f"{p} is not a folder")
    rows = []
    for c in p.iterdir():
        try:
            rows.append((c.name, c.is_dir(), c.stat().st_size if c.is_file() else 0))
        except OSError:
            continue
    rows.sort(key=(lambda r: -r[2]) if a.get("sort") == "size" else (lambda r: (not r[1], r[0].lower())))
    out = [f"[DIR]  {n}/" if d else f"[FILE] {n}  ({_fmt_size(s)})" for n, d, s in rows[:MAX_LISTING]]
    return "\n".join(out) or "(empty folder)"


@tool("read_file", "Files", "read", "Read a text file. Use `head` or `tail` to read only the first or last lines.",
      {"path": S, "head": I, "tail": I}, ["path"])
def _read_file(a, ctx):
    text = _read_text(safe(ctx, a["path"]))
    lines = text.splitlines()
    if a.get("head"):
        return "\n".join(lines[:int(a["head"])])
    if a.get("tail"):
        return "\n".join(lines[-int(a["tail"]):])
    return text


@tool("read_files", "Files", "read", "Read several text files at once.", {"paths": _arr(S)}, ["paths"])
def _read_files(a, ctx):
    out = []
    for path in a["paths"][:20]:
        try:
            out.append(f"### {path}\n{_read_text(safe(ctx, path))}")
        except ToolError as e:
            out.append(f"### {path}\n[error] {e}")
    return "\n\n".join(out)


@tool("read_image", "Files", "read", "Load an image file and return its type, size and base64 data (up to 3 MB).", {"path": S}, ["path"])
def _read_image(a, ctx):
    import base64
    import mimetypes
    p = safe(ctx, a["path"])
    mime = mimetypes.guess_type(p.name)[0] or ""
    if not mime.startswith("image/"):
        raise ToolError(f"{p.name} is not an image")
    if p.stat().st_size > 3_000_000:
        raise ToolError("image is larger than 3 MB")
    return json.dumps({"mime": mime, "bytes": p.stat().st_size, "base64": base64.b64encode(p.read_bytes()).decode()})


@tool("write_file", "Files", "write", "Create a file or replace it completely. Missing folders are created.",
      {"path": S, "content": S}, ["path", "content"])
def _write_file(a, ctx):
    p = safe(ctx, a["path"], must_exist=False)
    if p.is_dir():
        raise ToolError(f"{p} is a folder")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a["content"], "utf-8")
    return f"Wrote {len(a['content'])} characters to {p}"


@tool("edit_file", "Files", "write",
      "Change a text file by replacing exact snippets. Each edit is {old, new}; `old` must appear exactly once. Returns a diff. Use dry_run to preview.",
      {"path": S, "edits": _arr({"type": "object", "properties": {"old": S, "new": S}, "required": ["old", "new"]}), "dry_run": B},
      ["path", "edits"])
def _edit_file(a, ctx):
    p = safe(ctx, a["path"])
    before = _read_text(p)
    text = before
    for i, e in enumerate(a["edits"], 1):
        n = text.count(e["old"])
        if n != 1:
            raise ToolError(f"edit {i}: the text to replace was found {n} times (it must be found exactly once)")
        text = text.replace(e["old"], e["new"], 1)
    diff = "".join(difflib.unified_diff(before.splitlines(True), text.splitlines(True), p.name, p.name))
    if not a.get("dry_run"):
        p.write_text(text, "utf-8")
    return (diff or "(no changes)") + ("\n[dry run, nothing written]" if a.get("dry_run") else "")


@tool("make_folder", "Files", "write", "Create a folder (and any missing parent folders).", {"path": S}, ["path"])
def _make_folder(a, ctx):
    p = safe(ctx, a["path"], must_exist=False)
    p.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {p}"


@tool("copy_path", "Files", "write", "Copy a file or folder to a new place.", {"source": S, "destination": S}, ["source", "destination"])
def _copy_path(a, ctx):
    src, dst = safe(ctx, a["source"]), safe(ctx, a["destination"], must_exist=False)
    if dst.exists():
        raise ToolError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return f"Copied {src} to {dst}"


@tool("move_path", "Files", "write", "Move or rename a file or folder.", {"source": S, "destination": S}, ["source", "destination"])
def _move_path(a, ctx):
    src, dst = safe(ctx, a["source"]), safe(ctx, a["destination"], must_exist=False)
    if dst.exists():
        raise ToolError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {src} to {dst}"


@tool("delete_path", "Files", "write", "Delete a file or folder. It is moved to the trash folder, so it can be restored.", {"path": S}, ["path"])
def _delete_path(a, ctx):
    p = safe(ctx, a["path"])
    if p in ctx.dirs:
        raise ToolError("an allowed folder itself cannot be deleted")
    trash = config.ROOT / ".trash" / time.strftime("%Y%m%d-%H%M%S")
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(trash / p.name))
    return f"Moved {p} to {trash / p.name}"


def _walk(root: Path, skip: set[str], limit: int):
    n = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        for f in sorted(files):
            n += 1
            if n > limit:
                return
            yield Path(dirpath) / f


@tool("folder_tree", "Files", "read", "Show a folder as an indented tree (up to 3 levels by default).",
      {"path": S, "depth": I}, [])
def _folder_tree(a, ctx):
    root = safe(ctx, a.get("path") or ".")
    depth = int(a.get("depth") or 3)
    lines: list[str] = []

    def rec(d: Path, level: int):
        if level > depth or len(lines) >= MAX_LISTING:
            return
        try:
            kids = sorted(d.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
        except OSError:
            return
        for c in kids:
            if c.name in SKIP_DIRS or len(lines) >= MAX_LISTING:
                continue
            lines.append("  " * (level - 1) + c.name + ("/" if c.is_dir() else ""))
            if c.is_dir():
                rec(c, level + 1)

    rec(root, 1)
    return "\n".join(lines) or "(empty folder)"


@tool("find_files", "Files", "read", "Find files by name anywhere under a folder. The pattern can use * and ? (for example *.py) or be part of a name.",
      {"pattern": S, "path": S}, ["pattern"])
def _find_files(a, ctx):
    root, pat = safe(ctx, a.get("path") or "."), a["pattern"].lower()
    glob = any(c in pat for c in "*?[")
    hits = [str(f) for f in _walk(root, SKIP_DIRS, 50000)
            if (fnmatch.fnmatch(f.name.lower(), pat) if glob else pat in f.name.lower())]
    return "\n".join(hits[:200]) or "No files found."


@tool("search_in_files", "Files", "read", "Search inside text files for a word or phrase (case-insensitive). Returns file:line: text.",
      {"query": S, "path": S, "glob": S}, ["query"])
def _search_in_files(a, ctx):
    root, q = safe(ctx, a.get("path") or "."), a["query"].lower()
    files = [root] if root.is_file() else _walk(root, SKIP_DIRS, 5000)
    out: list[str] = []
    for f in files:
        if a.get("glob") and not fnmatch.fnmatch(f.name, a["glob"]):
            continue
        try:
            if f.stat().st_size > 1_000_000:
                continue
            raw = f.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        for i, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            if q in line.lower():
                out.append(f"{f}:{i}: {line.strip()[:200]}")
                if len(out) >= 100:
                    return "\n".join(out) + "\n[more matches not shown]"
    return "\n".join(out) or "No matches."


@tool("file_info", "Files", "read", "Size, type and dates of a file or folder.", {"path": S}, ["path"])
def _file_info(a, ctx):
    p = safe(ctx, a["path"])
    st = p.stat()
    return json.dumps({"path": str(p), "type": "folder" if p.is_dir() else "file", "size": st.st_size,
                       "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                       "created": datetime.fromtimestamp(st.st_ctime).isoformat(timespec="seconds")})


# ── web ───────────────────────────────────────────────────────────────────────

_UA = {"User-Agent": "Mozilla/5.0 (compatible; herama)"}


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _check_public(url: str) -> None:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ToolError("only http and https addresses are allowed")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except OSError as e:
        raise ToolError(f"cannot resolve {u.hostname}: {e}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ToolError("addresses on this computer or local network are blocked")


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str, limit: int = 2_000_000, data: bytes | None = None, timeout: int = 20) -> tuple[bytes, str]:
    _check_public(url)
    opener = urllib.request.build_opener(_Redirects)
    try:
        with opener.open(urllib.request.Request(url, data=data, headers=_UA), timeout=timeout) as r:
            return r.read(limit), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise ToolError(f"the site answered {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ToolError(f"could not reach the site: {e}") from None


def parse_search(html: str, limit: int) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', html, re.S):
        href = m.group(1)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q["uddg"][0] if "uddg" in q else href
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
        out.append({"title": html_to_text(m.group(2)), "url": url, "snippet": html_to_text(snip.group(1)) if snip else ""})
        if len(out) >= limit:
            break
    return out


@tool("web_search", "Web", "net", "Search the web. Returns titles, addresses and short snippets. Open a result with open_url.",
      {"query": S, "max_results": I}, ["query"])
def _web_search(a, ctx):
    body = urllib.parse.urlencode({"q": a["query"]}).encode()
    raw, _ = _fetch("https://html.duckduckgo.com/html/", data=body)
    hits = parse_search(raw.decode("utf-8", "replace"), max(1, min(int(a.get("max_results") or 6), 15)))
    return "\n\n".join(f"{i}. {h['title']}\n{h['url']}\n{h['snippet']}" for i, h in enumerate(hits, 1)) or "No results."


@tool("open_url", "Web", "net", "Download a web page and return its readable text.", {"url": S, "max_chars": I}, ["url"])
def _open_url(a, ctx):
    raw, ctype = _fetch(a["url"])
    text = raw.decode("utf-8", "replace")
    if "html" in ctype.lower() or text.lstrip().startswith("<"):
        text = html_to_text(text)
    limit = max(500, min(int(a.get("max_chars") or 8000), MAX_RESULT))
    return text[:limit] + ("\n[truncated]" if len(text) > limit else "")


@tool("download_file", "Web", "write", "Download a file from the web into an allowed folder.", {"url": S, "path": S}, ["url", "path"])
def _download_file(a, ctx):
    dest = safe(ctx, a["path"], must_exist=False)
    raw, _ = _fetch(a["url"], limit=50_000_000, timeout=60)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return f"Saved {_fmt_size(len(raw))} to {dest}"


# ── shell ─────────────────────────────────────────────────────────────────────

@tool("run_command", "Shell", "exec", "Run a shell command inside an allowed folder and return its output. Stops after `timeout` seconds (default 60).",
      {"command": S, "folder": S, "timeout": I}, ["command"])
def _run_command(a, ctx):
    cwd = safe(ctx, a.get("folder") or ".")
    try:
        r = subprocess.run(a["command"], shell=True, cwd=cwd, capture_output=True, text=True, errors="replace",
                           timeout=max(1, min(int(a.get("timeout") or 60), 600)),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ToolError("the command timed out") from None
    out = (r.stdout or "") + (f"\n[stderr]\n{r.stderr}" if r.stderr else "")
    return f"[exit code {r.returncode}]\n{out}".strip()


# ── skills ────────────────────────────────────────────────────────────────────

@tool("list_skills", "Skills", "read", "List the saved skills (small Python programs) and what each does.")
def _list_skills(a, ctx):
    from app.skills import registry
    idx = registry.list_skills()
    return "\n".join(f"{n}: {v.get('desc', '')}" for n, v in idx.items()) or "No skills saved yet."


@tool("show_skill", "Skills", "read", "Show the source code of a saved skill.", {"name": S}, ["name"])
def _show_skill(a, ctx):
    from app.skills import registry
    if a["name"] not in registry.list_skills():
        raise ToolError("unknown skill")
    return (config.SKILLS_DIR / f"{a['name']}.py").read_text("utf-8")


@tool("run_skill", "Skills", "exec", "Run a saved skill with keyword arguments and return its result.",
      {"name": S, "args": {"type": "object"}}, ["name"])
def _run_skill(a, ctx):
    from app.skills import registry
    try:
        return json.dumps(registry.run(a["name"], a.get("args") or {}), ensure_ascii=False, default=str)
    except registry.SkillError as e:
        raise ToolError(str(e)) from None


@tool("create_skill", "Skills", "write",
      "Save a new skill: Python code that defines run(**kwargs) and returns a JSON-friendly value. Name: lowercase letters, digits and underscores.",
      {"name": S, "code": S, "description": S}, ["name", "code"])
def _create_skill(a, ctx):
    from app.skills import registry
    try:
        r = registry.save(a["name"], a["code"], a.get("description", ""))
    except registry.SkillError as e:
        raise ToolError(str(e)) from None
    return f"Saved skill {r['name']}"


# ── memory ────────────────────────────────────────────────────────────────────

@tool("remember", "Memory", "memory",
      "Remember one short, lasting fact about the user or their work (a preference, a name, a project path, a decision) so it is known in later conversations. One fact per call. Never save passwords, keys or other secrets.",
      {"fact": S}, ["fact"])
def _remember(a, ctx):
    from app.memory.store import memory
    fact = (a.get("fact") or "").strip()
    if not fact:
        raise ToolError("fact is empty")
    if len(fact) > 300:
        raise ToolError("keep the fact under 300 characters")
    if SECRET_RE.search(fact):
        raise ToolError("this looks like a secret, so it was not saved")
    return f"Remembered as #{memory.add(fact, kind='fact', tags='agent')}"


@tool("recall", "Memory", "memory", "Search the remembered facts by words. Each result shows its number (#n).", {"query": S}, ["query"])
def _recall(a, ctx):
    from app.memory.store import memory
    rows = memory.search(a["query"], 10) or []
    return "\n".join(f"#{r['id']} {r['content']}" for r in rows) or "Nothing remembered about that."


@tool("forget", "Memory", "memory", "Delete a remembered fact by its number (shown as #n in what you remember).", {"id": I}, ["id"])
def _forget(a, ctx):
    from app.memory.store import memory
    memory.delete(int(a["id"]))
    return f"Forgot #{int(a['id'])}"


# ── utilities ─────────────────────────────────────────────────────────────────

@tool("get_time", "Utilities", "read", "Current local date, time and time zone of the user's computer.")
def _get_time(a, ctx):
    n = datetime.now().astimezone()
    return f"{n.strftime('%A %Y-%m-%d %H:%M:%S')} ({n.tzname()}, UTC{n.strftime('%z')})"


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
          "tan": math.tan, "log": math.log, "log10": math.log10,
          "abs": abs, "round": round, "min": min, "max": max}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(n):
    if isinstance(n, ast.Expression):
        return _eval(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.Name) and n.id in _CONSTS:
        return _CONSTS[n.id]
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        l, r = _eval(n.left), _eval(n.right)
        if isinstance(n.op, ast.Pow) and abs(r) > 1000:
            raise ToolError("exponent too large")
        return _OPS[type(n.op)](l, r)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_eval(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
        return _FUNCS[n.func.id](*[_eval(x) for x in n.args])
    raise ToolError("unsupported expression")


@tool("calculate", "Utilities", "read", "Evaluate a math expression exactly, for example (12.5*8)/3 or sqrt(2)**2. Supports + - * / // % **, pi, e, sqrt, sin, cos, tan, log, log10, abs, round, min, max.",
      {"expression": S}, ["expression"])
def _calculate(a, ctx):
    try:
        return str(_eval(ast.parse(a["expression"], mode="eval")))
    except ToolError:
        raise
    except (SyntaxError, ZeroDivisionError, ValueError, TypeError, OverflowError) as e:
        raise ToolError(f"cannot calculate: {e}") from None


@tool("system_info", "Utilities", "read", "Facts about this computer: system, processor, memory, graphics card and free disk space.")
def _system_info(a, ctx):
    import psutil
    from app import runtime
    vm = psutil.virtual_memory()
    disk = shutil.disk_usage(ctx.dirs[0])
    return json.dumps({"system": f"{platform.system()} {platform.release()}", "cpu": platform.processor() or platform.machine(),
                       "threads": psutil.cpu_count(logical=True), "ram_gb": round(vm.total / 1e9, 1),
                       "ram_free_gb": round(vm.available / 1e9, 1), "gpus": runtime.gpu_names(),
                       "disk_free_gb": round(disk.free / 1e9, 1)})


# ── client-side tools (handled by the app, not run here) ─────────────────────

CLIENT_TOOLS = [
    Tool("ask_user", "Utilities", "ui", "Ask the user a question when you need a decision or missing detail, then stop and wait for the answer.",
         {"question": S}, ["question"], lambda a, c: ""),
    Tool("update_plan", "Utilities", "ui",
         "Show or update your step-by-step plan for a multi-step task. Send the full list every time; status is pending, doing or done.",
         {"steps": _arr({"type": "object", "properties": {"text": S, "status": {"type": "string", "enum": ["pending", "doing", "done"]}}, "required": ["text"]})},
         ["steps"], lambda a, c: ""),
]
for _t in CLIENT_TOOLS:
    REGISTRY[_t.name] = _t


def listing() -> list[dict]:
    return [{"name": t.name, "group": t.group, "kind": t.kind, "description": t.desc, "schema": t.schema(),
             "client": t in CLIENT_TOOLS} for t in REGISTRY.values()]


def run(name: str, args: dict, dirs: list[str] | None = None) -> dict:
    """Run one tool. Returns {"ok": bool, "result": str}; problems come back as text for the model to read."""
    t = REGISTRY.get(name)
    if t is None or t in CLIENT_TOOLS:
        return {"ok": False, "result": f"unknown tool: {name}"}
    try:
        out = t.fn(args if isinstance(args, dict) else {}, make_ctx(dirs))
        ok = True
    except ToolError as e:
        out, ok = str(e), False
    except KeyError as e:
        out, ok = f"missing argument: {e}", False
    except Exception as e:  # a bug or OS error inside a tool must not break the chat
        out, ok = f"{type(e).__name__}: {e}", False
    out = str(out)
    return {"ok": ok, "result": out[:MAX_RESULT] + ("\n[output truncated]" if len(out) > MAX_RESULT else "")}
