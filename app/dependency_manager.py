"""
Plug-and-Play dependency automation.

ensure_package(name)   — install if missing, blocking until done.
ensure_packages([...]) — parallel install of a list.
upgrade_packages_async([...]) — fire-and-forget upgrade to latest stable;
                                 called automatically by the GUI on startup.

The call blocks only until the install is *complete* (it joins the thread),
so callers that already run in a background thread (skills sandbox, hf_manager)
get a clean, non-blocking experience from the perspective of the CLI UI.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger("herama.deps")

# Path to requirements.txt relative to the package root (two levels up from
# this file: app/ → repo root).
_REQ_PATH = Path(__file__).resolve().parent.parent / "requirements.txt"

# Guards concurrent installs of the same package.
_install_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def _lock_for(package: str) -> threading.Lock:
    with _global_lock:
        if package not in _install_locks:
            _install_locks[package] = threading.Lock()
        return _install_locks[package]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_package(package_name: str, import_name: str | None = None) -> bool:
    """
    Ensure *package_name* is installed and importable.

    Parameters
    ----------
    package_name  : PyPI distribution name (e.g. "huggingface_hub")
    import_name   : module name used for the import check when it differs
                    from package_name (e.g. package "Pillow" → import "PIL")

    Returns True if the package is (or became) available, False on failure.
    The call blocks until the install finishes but runs under a per-package
    lock so two concurrent callers never double-install the same package.
    """
    mod_name = import_name or _canonical_import(package_name)

    if _is_importable(mod_name):
        return True

    lock = _lock_for(package_name)
    with lock:
        # re-check under lock in case another thread just installed it
        if _is_importable(mod_name):
            return True
        return _install(package_name, mod_name)


def ensure_packages(packages: list[str | tuple[str, str]]) -> dict[str, bool]:
    """
    Ensure multiple packages in parallel background threads, blocking until all
    are done.  Each element may be a plain name or a (package, import_name)
    tuple.  Returns {package_name: success}.
    """
    results: dict[str, bool] = {}
    threads: list[threading.Thread] = []

    def _worker(pkg, imp):
        results[pkg] = ensure_package(pkg, imp)

    for item in packages:
        if isinstance(item, tuple):
            pkg, imp = item
        else:
            pkg, imp = item, None
        t = threading.Thread(target=_worker, args=(pkg, imp), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _canonical_import(package_name: str) -> str:
    """Convert a PyPI name to a likely importable module name."""
    return package_name.replace("-", "_").lower()


def _is_importable(mod_name: str) -> bool:
    spec = importlib.util.find_spec(mod_name)
    return spec is not None


def _installed_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _install(package_name: str, mod_name: str) -> bool:
    """Run pip install synchronously; update requirements.txt on success."""
    log.info("Installing missing package: %s", package_name)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name, "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        log.error("pip install timed out for %s", package_name)
        return False

    if result.returncode != 0:
        log.error("pip install failed for %s:\n%s", package_name, result.stderr[:500])
        return False

    # invalidate importlib caches so the new package is discoverable
    importlib.invalidate_caches()

    if not _is_importable(mod_name):
        log.error("Package %s installed but %s still not importable", package_name, mod_name)
        return False

    version = _installed_version(package_name) or "unknown"
    log.info("Installed %s==%s", package_name, version)
    _append_to_requirements(package_name, version)
    return True


def upgrade_packages_async(
    packages: list[str | tuple[str, str]] | None = None,
    done_cb: Callable[[dict[str, bool]], None] | None = None,
) -> threading.Thread:
    """
    Silently upgrade packages to their latest stable versions in the background.

    When *packages* is None (the default), reads ``requirements.txt`` and
    runs ``pip install --upgrade --quiet -r requirements.txt`` in one pass —
    keeping the whole environment in sync with the pinned file.

    When *packages* is given, upgrades each named package individually.

    Never blocks the caller.
    """
    def _worker():
        results: dict[str, bool] = {}

        if packages is None:
            # upgrade everything listed in requirements.txt
            req = _REQ_PATH
            if req.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install",
                         "--upgrade", "--quiet", "-r", str(req)],
                        capture_output=True, text=True, timeout=300,
                    )
                    success = result.returncode == 0
                    if success:
                        importlib.invalidate_caches()
                        log.info("Upgraded all packages from requirements.txt")
                    else:
                        log.warning("requirements.txt upgrade failed: %s",
                                    result.stderr[:300])
                    results["requirements.txt"] = success
                except Exception as exc:
                    log.warning("requirements.txt upgrade exception: %s", exc)
                    results["requirements.txt"] = False
        else:
            for item in packages:
                pkg = item[0] if isinstance(item, tuple) else item
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install",
                         "--upgrade", "--quiet", pkg],
                        capture_output=True, text=True, timeout=120,
                    )
                    success = result.returncode == 0
                    if success:
                        importlib.invalidate_caches()
                        ver = _installed_version(pkg) or "unknown"
                        log.info("Upgraded %s → %s", pkg, ver)
                        _append_to_requirements(pkg, ver)
                    else:
                        log.warning("Upgrade failed for %s: %s", pkg,
                                    result.stderr[:200])
                    results[pkg] = success
                except Exception as exc:
                    log.warning("Upgrade exception for %s: %s", pkg, exc)
                    results[pkg] = False

        if done_cb:
            done_cb(results)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def _append_to_requirements(package_name: str, version: str) -> None:
    """Append 'package_name>=version' to requirements.txt if not already present."""
    line = f"{package_name}>={version}"
    try:
        text = _REQ_PATH.read_text("utf-8") if _REQ_PATH.exists() else ""
        # check whether any line already mentions this package (case-insensitive)
        pkg_lower = package_name.lower().replace("-", "_")
        for existing in text.splitlines():
            if existing.strip().lower().replace("-", "_").startswith(pkg_lower):
                log.debug("requirements.txt already contains %s, skipping append", package_name)
                return
        with _REQ_PATH.open("a", encoding="utf-8") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write(line + "\n")
        log.info("Added %s to requirements.txt", line)
    except OSError as e:
        log.warning("Could not update requirements.txt: %s", e)
