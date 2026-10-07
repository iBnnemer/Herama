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
import random
import re
import shutil
import socket
import ssl
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


class NeedsAccess(ToolError):
    """The path is outside the folders granted so far; the app can ask the user and retry."""

    def __init__(self, folder: str, write: bool):
        super().__init__(f"{folder} is not in the allowed folders yet; the user has to approve {'changes in' if write else 'reading'} it")
        self.folder, self.write = folder, write


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
    dirs: list[Path]                                       # read and write
    read_dirs: list[Path] = field(default_factory=list)    # read only (paths the user mentioned or approved)
    computer: bool = False                                 # the user approved searching the whole computer
    agent: str = ""                                        # id of the agent calling the tool (its own memory)
    model: str = ""                                        # model the caller is using (default for helper agents)
    group: str = ""                                        # agent group of the chat: limits who can be asked


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


def _paths(items: list[str] | None) -> list[Path]:
    out = []
    for d in items or []:
        try:
            p = Path(d).expanduser()
            if d and p.exists():
                out.append(p.resolve())
        except (OSError, RuntimeError):
            continue
    return out


def make_ctx(dirs: list[str] | None, read_dirs: list[str] | None = None, computer: bool = False,
             agent: str = "", model: str = "", group: str = "") -> Ctx:
    found = [d for d in _paths(dirs) if d.is_dir()]
    return Ctx(found or [workspace().resolve()], _paths(read_dirs), computer, agent, model, group)


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


SENSITIVE_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store"}
SENSITIVE_FILES = re.compile(r"^(id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|.*\.(pem|key|pfx|p12|kdbx)|login data|cookies|web data|\.netrc|credentials(\.json)?)$", re.I)


def _sensitive(p: Path) -> bool:
    return any(part.lower() in SENSITIVE_DIRS for part in p.parts) or bool(SENSITIVE_FILES.match(p.name))


def safe(ctx: Ctx, path: str, must_exist: bool = True, write: bool = False) -> Path:
    """Resolve `path` (relative paths start in the first allowed folder).

    Reading works in the allowed and read-only folders, changes only in the allowed ones; anything else
    raises NeedsAccess so the app can ask the user. Credential files and folders are always refused."""
    if not path:
        raise ToolError("path is required")
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = ctx.dirs[0] / p
    p = p.resolve()
    if _sensitive(p):
        raise ToolError(f"{p.name} looks like a credentials file or folder, so it is blocked")
    roots = ctx.dirs if write else ctx.dirs + ctx.read_dirs
    if not any(_inside(p, d) for d in roots):
        anchor = p if p.is_dir() else p.parent
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        raise NeedsAccess(str(anchor), write)
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

@tool("workspace_folders", "Files", "read", "List the folders you can use now. Relative paths start in the first one. Other folders need the user's approval, which is asked automatically when you try them.")
def _workspace_folders(a, ctx):
    out = [f"{d}  (read and write)" for d in ctx.dirs] + [f"{d}  (read only)" for d in ctx.read_dirs]
    return "\n".join(out)


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
    p = safe(ctx, a["path"], must_exist=False, write=True)
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
    p = safe(ctx, a["path"], write=not a.get("dry_run"))
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
    p = safe(ctx, a["path"], must_exist=False, write=True)
    p.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {p}"


@tool("copy_path", "Files", "write", "Copy a file or folder to a new place.", {"source": S, "destination": S}, ["source", "destination"])
def _copy_path(a, ctx):
    src, dst = safe(ctx, a["source"]), safe(ctx, a["destination"], must_exist=False, write=True)
    if dst.exists():
        raise ToolError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    return f"Copied {src} to {dst}"


@tool("move_path", "Files", "write", "Move or rename a file or folder.", {"source": S, "destination": S}, ["source", "destination"])
def _move_path(a, ctx):
    src, dst = safe(ctx, a["source"], write=True), safe(ctx, a["destination"], must_exist=False, write=True)
    if dst.exists():
        raise ToolError(f"{dst} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {src} to {dst}"


@tool("delete_path", "Files", "write", "Delete a file or folder. It is moved to the trash folder, so it can be restored.", {"path": S}, ["path"])
def _delete_path(a, ctx):
    p = safe(ctx, a["path"], write=True)
    if p in ctx.dirs or p in ctx.read_dirs:
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


SYSTEM_SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
               "appdata", "library", "proc", "sys", "dev", "run", "snap", "node_modules", ".git", "__pycache__", ".cache",
               ".venv", "venv", "site-packages", ".trash", "$windows.~bt", "recovery"}
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".csv", ".html", ".css", ".yml", ".yaml", ".toml", ".xml",
            ".log", ".ini", ".cfg", ".c", ".cpp", ".h", ".java", ".go", ".rs", ".sh", ".bat", ".ps1", ".sql", ".rtf", ".tex"}
SEARCH_SECONDS = 20


def search_roots(all_drives: bool) -> list[Path]:
    """Where "search my computer" looks: the user's own folders, or every drive when asked."""
    home = Path.home()
    if all_drives:
        if platform.system() == "Windows":
            import string
            return [Path(f"{c}:\\") for c in string.ascii_uppercase if Path(f"{c}:\\").exists()]
        return [Path("/")]
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive", "Projects", "source", "dev", "work"]
    roots = [home / n for n in names if (home / n).is_dir()]
    return roots or [home]


@tool("search_computer", "Files", "read",
      "Search the user's computer for files and folders by name, or by words inside text files (content=true). Looks in Desktop, Documents, Downloads and similar folders; "
      "set all_drives=true to look everywhere. Returns paths, newest first. Then use read_file on a file result, or analyze_folder on a folder result. The user is asked to approve the first search.",
      {"query": S, "content": B, "all_drives": B, "folder": S}, ["query"])
def _search_computer(a, ctx):
    if not ctx.computer:
        raise NeedsAccess("*computer*", False)
    q = a["query"].lower().strip()
    if not q:
        raise ToolError("query is empty")
    glob = any(c in q for c in "*?[")
    roots = [safe(ctx, a["folder"])] if a.get("folder") else search_roots(bool(a.get("all_drives")))
    deadline = time.time() + SEARCH_SECONDS
    hits: list[tuple[tuple[int, float], str, int]] = []
    scanned, timed_out = 0, False
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            if not a.get("content"):   # folders count too: "find the folder called nmr"
                for d in dirs:
                    if (fnmatch.fnmatch(d.lower(), q) if glob else q in d.lower()) and d.lower() not in SYSTEM_SKIP and not _sensitive(Path(dirpath) / d):
                        try:
                            hits.append(((int(d.lower() == q), (Path(dirpath) / d).stat().st_mtime), str(Path(dirpath) / d) + "/", 0))
                        except OSError:
                            pass
            dirs[:] = [d for d in dirs if d.lower() not in SYSTEM_SKIP and not d.startswith(".") and not _sensitive(Path(dirpath) / d)]
            for f in files:
                scanned += 1
                full = Path(dirpath) / f
                if time.time() > deadline:
                    timed_out = True
                    break
                if _sensitive(full):
                    continue
                if a.get("content"):
                    if full.suffix.lower() not in TEXT_EXT:
                        continue
                    try:
                        if full.stat().st_size > 1_000_000:
                            continue
                        if q not in full.read_bytes().decode("utf-8", "replace").lower():
                            continue
                    except OSError:
                        continue
                elif not (fnmatch.fnmatch(f.lower(), q) if glob else q in f.lower()):
                    continue
                try:
                    st = full.stat()
                    hits.append(((int(f.lower() == q), st.st_mtime), str(full), st.st_size))
                except OSError:
                    continue
            if timed_out or len(hits) >= 400:
                break
        if timed_out or len(hits) >= 400:
            break
    hits.sort(reverse=True)
    lines = [f"{p}  (folder, {datetime.fromtimestamp(m[1]).strftime('%Y-%m-%d')})" if p.endswith("/")
             else f"{p}  ({_fmt_size(sz)}, {datetime.fromtimestamp(m[1]).strftime('%Y-%m-%d')})" for m, p, sz in hits[:100]]
    note = f"\n[scanned {scanned} files{', stopped after ' + str(SEARCH_SECONDS) + 's - narrow the search' if timed_out else ''}]"
    return ("\n".join(lines) or "No matches.") + note


KEY_FILES = ("readme", "package.json", "pyproject.toml", "requirements.txt", "setup.py", "cargo.toml", "go.mod", "pom.xml",
             "makefile", "dockerfile", "main.py", "app.py", "index.js", "index.ts", "main.ts", "main.rs", "main.go")


@tool("analyze_folder", "Files", "read",
      "Get a full picture of a folder in ONE call: file tree, counts by file type, total size, and the contents of its key files (README, manifests, entry points) and a sample of other text files. "
      "Use this to understand or summarize a folder instead of listing sub-folders one by one.",
      {"path": S, "max_chars": I}, ["path"])
def _analyze_folder(a, ctx):
    root = safe(ctx, a["path"])
    if not root.is_dir():
        raise ToolError(f"{root} is not a folder")
    budget = max(3000, min(int(a.get("max_chars") or 14000), MAX_RESULT - 3000))
    files: list[tuple[Path, int, float]] = []
    tree: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not _sensitive(Path(dirpath) / d))
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth <= 3 and len(tree) < 150 and rel.parts:
            tree.append("  " * (depth - 1) + rel.parts[-1] + "/")
        for n in sorted(names):
            f = Path(dirpath) / n
            if _sensitive(f):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            files.append((f, st.st_size, st.st_mtime))
            if depth <= 3 and len(tree) < 150:
                tree.append("  " * depth + n)
        if len(files) > 20000:
            break
    by_ext: dict[str, list[int]] = {}
    for f, size, _ in files:
        e = by_ext.setdefault(f.suffix.lower() or "(none)", [0, 0])
        e[0] += 1
        e[1] += size
    summary = ", ".join(f"{e} x{c} ({_fmt_size(sz)})" for e, (c, sz) in sorted(by_ext.items(), key=lambda kv: -kv[1][0])[:12])
    out = [f"# {root}", f"{len(files)} files, {_fmt_size(sum(s for _, s, _ in files))} in total", f"Types: {summary or 'none'}",
           "", "## Tree" + (" (first 150 entries)" if len(tree) >= 150 else ""), "\n".join(tree) or "(empty)"]
    used = sum(len(x) for x in out)

    def add(f: Path, lines: int):
        nonlocal used
        if used >= budget or f.suffix.lower() not in TEXT_EXT and f.name.lower() not in KEY_FILES and not f.name.lower().startswith("readme"):
            return
        try:
            if f.stat().st_size > 400_000:
                return
            raw = f.read_bytes()
        except OSError:
            return
        if b"\x00" in raw[:4096]:
            return
        text = "\n".join(raw.decode("utf-8", "replace").splitlines()[:lines])[: max(0, min(2500, budget - used))]
        if text.strip():
            out.append(f"\n## {f.relative_to(root)}\n{text}")
            used += len(text) + 20

    key = [f for f, _, _ in files if f.name.lower() in KEY_FILES or f.name.lower().startswith("readme")]
    key.sort(key=lambda f: (len(f.relative_to(root).parts), f.name))
    for f in key[:8]:
        add(f, 80)
    rest = sorted((x for x in files if x[0] not in key and x[0].suffix.lower() in TEXT_EXT), key=lambda x: -x[2])
    for f, _, _ in rest[:10]:
        add(f, 25)
    return "\n".join(out)


@tool("file_info", "Files", "read", "Size, type and dates of a file or folder.", {"path": S}, ["path"])
def _file_info(a, ctx):
    p = safe(ctx, a["path"])
    st = p.stat()
    return json.dumps({"path": str(p), "type": "folder" if p.is_dir() else "file", "size": st.st_size,
                       "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                       "created": datetime.fromtimestamp(st.st_ctime).isoformat(timespec="seconds")})


# ── web ───────────────────────────────────────────────────────────────────────

_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


def _browser_headers() -> dict:
    """A realistic browser identity, a different one on each attempt."""
    return {"User-Agent": random.choice(_AGENTS), "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}


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


def _fetch(url: str, limit: int = 2_000_000, data: bytes | None = None, timeout: int = 10, headers: dict | None = None,
           retries: int = 2) -> tuple[bytes, str]:
    """Download a page. Timeouts, 429 and 5xx answers are retried with a growing pause (1 s, 2 s)."""
    _check_public(url)
    opener = urllib.request.build_opener(_Redirects)
    for attempt in range(retries + 1):
        try:
            with opener.open(urllib.request.Request(url, data=data, headers={**_browser_headers(), **(headers or {})}), timeout=timeout) as r:
                return r.read(limit), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < retries:
                time.sleep(1 + attempt)
                continue
            raise ToolError(f"the site answered {e.code}") from None
        except ssl.SSLError as e:
            raise ToolError(f"secure connection failed ({e}); a firewall or antivirus may be inspecting HTTPS") from None
        except (urllib.error.URLError, OSError) as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise ToolError(f"secure connection failed ({e.reason}); a firewall or antivirus may be inspecting HTTPS") from None
            if attempt < retries:
                time.sleep(1 + attempt)
                continue
            raise ToolError(f"could not reach the site: {e}") from None
    raise ToolError("could not reach the site")


def parse_search(html: str, limit: int) -> list[dict]:
    from app import websearch
    return websearch.parse_ddg_html(html, limit, html_to_text)


@tool("web_search", "Web", "net", "Search the web. Returns titles, addresses and short snippets. Open a result with open_url.",
      {"query": S, "max_results": I}, ["query"])
def _web_search(a, ctx):
    from app import websearch
    limit = max(1, min(int(a.get("max_results") or 6), 15))
    hits, provider, notes = websearch.search(a["query"], limit, _fetch, html_to_text)
    if not hits:
        raise ToolError("The web search failed (" + "; ".join(notes) + "). Tell the user; they can set HERAMA_SEARX_URL or BRAVE_API_KEY for a reliable search, "
                        "or you can open_url a page you already know.")
    return "\n\n".join(f"{i}. {h['title']}\n{h['url']}\n{h['snippet']}" for i, h in enumerate(hits, 1))


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
    dest = safe(ctx, a["path"], must_exist=False, write=True)
    raw, _ = _fetch(a["url"], limit=50_000_000, timeout=60)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return f"Saved {_fmt_size(len(raw))} to {dest}"


# ── shell ─────────────────────────────────────────────────────────────────────

@tool("run_command", "Shell", "exec", "Run a shell command inside an allowed folder and return its output. Stops after `timeout` seconds (default 60).",
      {"command": S, "folder": S, "timeout": I}, ["command"])
def _run_command(a, ctx):
    cwd = safe(ctx, a.get("folder") or ".", write=True)
    try:
        r = subprocess.run(a["command"], shell=True, cwd=cwd, capture_output=True, text=True, errors="replace",
                           timeout=max(1, min(int(a.get("timeout") or 60), 600)),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ToolError("the command timed out") from None
    out = (r.stdout or "") + (f"\n[stderr]\n{r.stderr}" if r.stderr else "")
    from app.tools_dev import condense
    return f"[exit code {r.returncode}]\n{condense(out)}".strip()


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
      "Remember one short, lasting fact about the user or their work (a preference, a name, a project path, a decision) so it is known in later conversations. "
      "By default the fact is private to you; set shared to true when other agents should know it too. One fact per call. Never save passwords, keys or other secrets.",
      {"fact": S, "shared": B}, ["fact"])
def _remember(a, ctx):
    from app.memory.store import memory
    fact = (a.get("fact") or "").strip()
    if not fact:
        raise ToolError("fact is empty")
    if len(fact) > 300:
        raise ToolError("keep the fact under 300 characters")
    if SECRET_RE.search(fact):
        raise ToolError("this looks like a secret, so it was not saved")
    owner = "" if a.get("shared") else ctx.agent
    fid = memory.add(fact, kind="fact", tags="agent", agent=owner)
    return f"Remembered as #{fid} ({'shared' if not owner else 'private'})"


@tool("recall", "Memory", "memory",
      "Search what you remember (your private facts and the shared ones) by words. Each result shows its number (#n).", {"query": S}, ["query"])
def _recall(a, ctx):
    from app.memory.store import memory
    rows = memory.search(a["query"], 10, ctx.agent or None) or []
    return "\n".join(f"#{r['id']} {r['content']}" + ("" if r.get("agent") else " [shared]") for r in rows) or "Nothing remembered about that."


@tool("forget", "Memory", "memory", "Delete a remembered fact by its number (shown as #n). You can delete your own and shared facts.", {"id": I}, ["id"])
def _forget(a, ctx):
    from app.memory.store import memory
    fid = int(a["id"])
    row = memory.get(fid)
    if row is None:
        raise ToolError(f"no fact #{fid}")
    if row.get("agent") and ctx.agent and row["agent"] != ctx.agent:
        raise ToolError(f"fact #{fid} belongs to another agent")
    memory.delete(fid)
    return f"Forgot #{fid}"


# ── agents (collaboration) ────────────────────────────────────────────────────

def _agents() -> list[dict]:
    from app.api import agents
    return agents._load()


def _team(ctx) -> list[dict]:
    """Agents the caller may ask: the other members of its group, or everyone outside a group."""
    me = ctx.agent or "default"
    rows = [ag for ag in _agents() if ag["id"] != me]
    if ctx.group:
        from app.api import groups
        g = groups.get(ctx.group)
        if g is None:
            raise ToolError("this group no longer exists")
        ids = {g["lead"], *g["members"]}
        rows = [ag for ag in rows if ag["id"] in ids]
    return rows


def _find_agent(who: str, ctx) -> dict:
    who = (who or "").strip().lower()
    for ag in _team(ctx):
        if who in (ag["id"].lower(), ag["name"].lower()):
            return ag
    raise ToolError(f"no agent named '{who}' that you can ask; call list_agents to see them")


@tool("list_agents", "Agents", "read", "List the other agents you can ask for help, with what each one is for.")
def _list_agents(a, ctx):
    rows = _team(ctx)
    return "\n".join(f"{ag['name']} (id {ag['id']}): {(ag.get('system_prompt') or '')[:160]}" for ag in rows) or "There are no other agents."


@tool("ask_agent", "Agents", "read",
      "Ask another agent to do a sub-task and get its answer back. It works alone with its own instructions and memory (and the shared facts), "
      "so give it everything it needs in the task text. Use list_agents first to see who is available.",
      {"agent": S, "task": S}, ["agent", "task"])
def _ask_agent(a, ctx):
    from app.engine import engine
    from app.memory.store import memory
    target = _find_agent(a.get("agent"), ctx)
    task = (a.get("task") or "").strip()
    if not task:
        raise ToolError("task is empty")
    if target["id"] == (ctx.agent or "default"):
        raise ToolError("you cannot ask yourself")
    model = target.get("model") or ctx.model
    if not model:
        raise ToolError("no model is set for that agent")
    system = (target.get("system_prompt") or "You are a helpful assistant.").strip()
    facts = memory.relevant(task, agent=target["id"])
    if facts:
        system += "\n\nKnown facts:\n" + "\n".join(f"- #{f['id']} {f['content']}" for f in facts)
    system += f"\n\nAnother agent ({ctx.agent or 'default'}) asked you for help. Answer the task directly and briefly."
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    try:
        gen = engine.chat(model, msgs, {"num_predict": 1500}, False)
        text = next(gen)
        list(gen)  # let the engine finish its bookkeeping
    except FileNotFoundError:
        raise ToolError(f"model '{model}' not found") from None
    return f"{target['name']} answered:\n{text.strip()}"


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
    Tool("use_tools", "Utilities", "ui",
         "Switch on more tools when the task needs them. Only a few tools are active at first. Groups: Files (read, write, search files), Web (search, open pages), "
         "Shell (run commands), Skills (saved programs), Memory (remember facts), Git (clone, status, commit, push), Agents (ask other agents for help), Utilities (time, calculator, computer info).",
         {"groups": _arr({"type": "string", "enum": ["Files", "Web", "Shell", "Skills", "Memory", "Agents", "Git", "Utilities"]})}, ["groups"], lambda a, c: ""),
    Tool("ask_user", "Utilities", "ui", "Ask the user a question when you need a decision or missing detail, then stop and wait for the answer.",
         {"question": S}, ["question"], lambda a, c: ""),
    Tool("update_plan", "Utilities", "ui",
         "Show or update your step-by-step plan for a multi-step task. Send the full list every time; status is pending, doing or done.",
         {"steps": _arr({"type": "object", "properties": {"text": S, "status": {"type": "string", "enum": ["pending", "doing", "done"]}}, "required": ["text"]})},
         ["steps"], lambda a, c: ""),
]
for _t in CLIENT_TOOLS:
    REGISTRY[_t.name] = _t


from app import tools_dev  # noqa: E402,F401  (registers the developer tools)


def listing() -> list[dict]:
    return [{"name": t.name, "group": t.group, "kind": t.kind, "description": t.desc, "schema": t.schema(),
             "client": t in CLIENT_TOOLS} for t in REGISTRY.values()]


def run(name: str, args: dict, dirs: list[str] | None = None, read_dirs: list[str] | None = None, computer: bool = False,
        agent: str = "", model: str = "", group: str = "") -> dict:
    """Run one tool. Returns {"ok": bool, "result": str}; problems come back as text for the model to read.

    When the tool needs a folder nobody approved yet, the answer also has "needs_access": {"folder", "write"}."""
    t = REGISTRY.get(name)
    if t is None or t in CLIENT_TOOLS:
        return {"ok": False, "result": f"unknown tool: {name}"}
    extra: dict = {}
    try:
        out = t.fn(args if isinstance(args, dict) else {}, make_ctx(dirs, read_dirs, computer, agent, model, group))
        ok = True
    except NeedsAccess as e:
        out, ok, extra = str(e), False, {"needs_access": {"folder": e.folder, "write": e.write}}
    except ToolError as e:
        out, ok = str(e), False
    except KeyError as e:
        out, ok = f"missing argument: {e}", False
    except Exception as e:  # a bug or OS error inside a tool must not break the chat
        out, ok = f"{type(e).__name__}: {e}", False
    out = str(out)
    return {"ok": ok, "result": out[:MAX_RESULT] + ("\n[output truncated]" if len(out) > MAX_RESULT else ""), **extra}
