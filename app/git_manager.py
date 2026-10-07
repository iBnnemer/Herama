"""GitHub repository cloner — downloads full repos via Git or ZIP fallback."""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class CloneProgress:
    repo_url: str
    dest: Path
    phase: str = "starting"    # starting / cloning / extracting / done
    pct: float = 0.0
    done: bool = False
    error: str = ""


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) from a GitHub URL, or None if unrecognised."""
    url = url.strip().rstrip("/").removesuffix(".git")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+)", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _clone_via_git(
    repo_url: str,
    dest: Path,
    progress_cb: Callable[[CloneProgress], None] | None,
) -> None:
    prog = CloneProgress(repo_url=repo_url, dest=dest, phase="cloning")
    if progress_cb:
        progress_cb(prog)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--recurse-submodules", repo_url, str(dest)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:500] or "git clone failed")

    prog.phase = "done"
    prog.pct = 100.0
    prog.done = True
    if progress_cb:
        progress_cb(prog)


def _clone_via_zip(
    owner: str,
    repo: str,
    dest: Path,
    progress_cb: Callable[[CloneProgress], None] | None,
) -> None:
    """Download the HEAD ZIP archive from GitHub and extract it."""
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
    # try 'master' fallback handled by urllib error
    prog = CloneProgress(repo_url=zip_url, dest=dest, phase="cloning")
    if progress_cb:
        progress_cb(prog)

    zip_path = dest.parent / f"_herama_dl_{repo}.zip"
    chunk = 1024 * 64

    def _download(url: str) -> bool:
        req = urllib.request.Request(url, headers={"User-Agent": "herama/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if total and progress_cb:
                            prog.pct = downloaded / total * 90
                            progress_cb(prog)
            return True
        except Exception:
            return False

    # try main → master
    if not _download(zip_url):
        master_url = zip_url.replace("/main.zip", "/master.zip")
        if not _download(master_url):
            raise RuntimeError("Could not download repository archive from GitHub")

    # extract
    prog.phase = "extracting"
    prog.pct = 90.0
    if progress_cb:
        progress_cb(prog)

    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        top = zf.namelist()[0].split("/")[0]
        zf.extractall(dest.parent / "_herama_extract_tmp")

    extracted = dest.parent / "_herama_extract_tmp" / top
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(extracted), str(dest))
    shutil.rmtree(dest.parent / "_herama_extract_tmp", ignore_errors=True)
    zip_path.unlink(missing_ok=True)

    prog.phase = "done"
    prog.pct = 100.0
    prog.done = True
    if progress_cb:
        progress_cb(prog)


def clone_repo(
    url: str,
    workspace: Path,
    progress_cb: Callable[[CloneProgress], None] | None = None,
) -> Path:
    """
    Clone a GitHub repository into *workspace/<repo_name>/*.

    Uses ``git clone --depth 1`` when git is available, otherwise downloads
    and extracts the ZIP archive directly via urllib.

    Returns the destination path.
    """
    parsed = _parse_github_url(url)
    if parsed is None:
        raise ValueError(f"Not a recognised GitHub URL: {url!r}")

    owner, repo = parsed
    dest = workspace / repo
    workspace.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        shutil.rmtree(dest)

    if _git_available():
        git_url = f"https://github.com/{owner}/{repo}.git"
        _clone_via_git(git_url, dest, progress_cb)
    else:
        _clone_via_zip(owner, repo, dest, progress_cb)

    return dest


def clone_repo_async(
    url: str,
    workspace: Path,
    progress_cb: Callable[[CloneProgress], None] | None = None,
    done_cb: Callable[[Path | None, str], None] | None = None,
) -> threading.Thread:
    """Start clone in a background thread. ``done_cb(path, error)`` on finish."""

    def _worker():
        try:
            path = clone_repo(url, workspace, progress_cb)
            if done_cb:
                done_cb(path, "")
        except Exception as exc:
            if progress_cb:
                p = CloneProgress(repo_url=url, dest=workspace, error=str(exc), done=True)
                progress_cb(p)
            if done_cb:
                done_cb(None, str(exc))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
