"""Hardware-aware llama.cpp runtime: picks, downloads and caches the right llama-server build."""
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tarfile
import threading
import urllib.request
import zipfile
from pathlib import Path

from app import config

log = logging.getLogger("herama")

RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15"
RUNTIME_DIR = Path(os.getenv("HERAMA_RUNTIME_DIR", config.ROOT / "runtime"))
CHAIN = {"cuda": ["cuda", "vulkan", "cpu"], "vulkan": ["vulkan", "cpu"], "metal": ["metal", "cpu"], "cpu": ["cpu"]}
LABELS = {"cuda": "CUDA", "vulkan": "Vulkan", "metal": "Metal", "cpu": "CPU only"}

_lock = threading.RLock()
_thread: threading.Thread | None = None
_state = {"state": "idle", "backend": "", "progress": 0.0, "error": ""}


# ── hardware detection ────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def nvidia_cuda_version() -> str | None:
    """CUDA version supported by the installed NVIDIA driver, or None without an NVIDIA GPU."""
    exe = shutil.which("nvidia-smi") or next((p for p in (
        r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
        if os.path.exists(p)), None)
    if not exe:
        return None
    m = re.search(r"CUDA Version:\s*([\d.]+)", _run([exe]))
    return m.group(1) if m else None


_IGNORED_ADAPTERS = ("microsoft basic", "remote", "virtual", "parsec", "displaylink")


def gpu_names() -> list[str]:
    system = platform.system()
    if system == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }"], 15)
        names = [ln.strip() for ln in out.splitlines() if ln.strip()]
    elif system == "Linux":
        names = [ln for ln in _run(["lspci"]).splitlines() if re.search(r"VGA|3D|Display", ln)]
    else:
        names = []
    return [n for n in names if not any(x in n.lower() for x in _IGNORED_ADAPTERS)]


def detect_backend() -> str:
    forced = os.getenv("HERAMA_BACKEND", "").lower()
    if forced in CHAIN:
        return forced
    system = platform.system()
    if system == "Darwin":
        return "metal"
    if nvidia_cuda_version() and system == "Windows":
        return "cuda"
    return "vulkan" if gpu_names() else "cpu"


# ── release asset selection ───────────────────────────────────────────────────

def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s))


def pick_assets(names: list[str], backend: str, system: str, machine: str, cuda: str | None = None) -> list[str] | None:
    """Names of the release files to download for this backend, or None if the release has no match."""
    low = {n.lower(): n for n in names if n.lower().endswith((".zip", ".tar.gz")) and "llama" in n.lower()}
    arm = machine.lower() in ("arm64", "aarch64")
    arch_re = r"arm64|aarch64" if arm else r"x64|x86_64|amd64"
    os_re = {"Windows": r"win|windows", "Linux": r"ubuntu|linux", "Darwin": r"macos|darwin"}.get(system, "$^")

    def find(*must: str, exclude: tuple[str, ...] = ()) -> list[str]:
        return [n for n in low if re.search(rf"[-_.]({os_re})[-_.]", n) and re.search(rf"[-_.]({arch_re})[-_.]", n)
                and all(m in n for m in must) and not any(x in n for x in exclude)]

    if backend == "cuda":
        if system != "Windows" or not cuda:
            return None
        usable = []
        for n in find("cuda-", exclude=("cudart",)):
            m = re.search(r"cuda-([\d.]+)-", n)
            if m and _ver(m.group(1)) <= _ver(cuda):
                usable.append((_ver(m.group(1)), n, m.group(1)))
        if not usable:
            return None
        _, main, ver = max(usable)
        rt = [n for n in low if "cudart" in n and f"cuda-{ver}-" in n and re.search(arch_re, n)]
        return [low[main]] + [low[n] for n in rt[:1]]
    if backend == "vulkan":
        hit = find("vulkan")
    elif backend == "metal":
        hit = find()
    else:
        hit = find("cpu") or find("avx2") or ([n for n in find("") if not any(
            k in n for k in ("cuda", "vulkan", "hip", "sycl", "opencl", "kompute", "rocm"))])
    return [low[hit[0]]] if hit else None


# ── install ───────────────────────────────────────────────────────────────────

def _manifest() -> Path:
    return RUNTIME_DIR / "installed.json"


def _installed() -> dict | None:
    try:
        info = json.loads(_manifest().read_text("utf-8"))
        if (RUNTIME_DIR / info["binary"]).exists():
            return info
    except (OSError, ValueError, KeyError):
        pass
    return None


def _http(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "herama"}), timeout=60)


def _find_binary(root: Path) -> Path | None:
    name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    return next(iter(sorted(root.rglob(name))), None)


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest)


def _install(backend: str) -> dict:
    """Download and extract the llama-server build for `backend`. Raises RuntimeError on failure."""
    system, machine = platform.system(), platform.machine()
    with _http(RELEASE_API) as r:
        releases = json.load(r)
    cuda = nvidia_cuda_version()
    picked, rel, sizes = None, {}, {}
    for rel in releases:
        sizes = {a["name"]: a for a in rel.get("assets", [])}
        for b in CHAIN[backend]:
            picked = pick_assets(list(sizes), b, system, machine, cuda)
            if picked:
                backend = b
                break
        if picked:
            break
    if not picked:
        seen = ", ".join(sorted({a["name"] for r_ in releases[:2] for a in r_.get("assets", [])})[:15])
        raise RuntimeError(f"no llama.cpp build found for {system}/{machine}; releases: "
                           f"{[r_.get('tag_name') for r_ in releases[:3]]}; assets: {seen}")

    with _lock:
        _state.update(state="downloading", backend=backend, progress=0.0, error="")
    dest = RUNTIME_DIR / f"{backend}-{rel['tag_name']}"
    dl = RUNTIME_DIR / "downloads"
    dl.mkdir(parents=True, exist_ok=True)
    total = sum(sizes[n]["size"] for n in picked) or 1
    done = 0
    for name in picked:
        target = dl / name
        with _http(sizes[name]["browser_download_url"]) as r, open(target, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                with _lock:
                    _state["progress"] = min(0.99, done / total)
        _extract(target, dest)
        target.unlink(missing_ok=True)
    binary = _find_binary(dest)
    if binary is None:
        raise RuntimeError("llama-server was not found in the downloaded archive")
    if platform.system() != "Windows":
        binary.chmod(0o755)
    info = {"backend": backend, "tag": rel["tag_name"], "binary": str(binary.relative_to(RUNTIME_DIR))}
    _manifest().write_text(json.dumps(info), "utf-8")
    log.info("llama.cpp runtime ready: %s %s", backend, rel["tag_name"])
    return info


def _install_safe(backend: str) -> None:
    try:
        info = _install(backend)
        with _lock:
            _state.update(state="ready", backend=info["backend"], progress=1.0, error="")
    except Exception as e:  # network down, rate limit, unsupported platform
        log.warning("runtime install failed: %s", e)
        with _lock:
            _state.update(state="error", error=str(e))


def disabled() -> bool:
    return os.getenv("HERAMA_RUNTIME", "auto").lower() == "off"


def start_background() -> None:
    """Begin downloading the matching runtime without blocking the server start."""
    global _thread
    if disabled() or "PYTEST_CURRENT_TEST" in os.environ:
        return
    with _lock:
        info = _installed()
        if info:
            _state.update(state="ready", backend=info["backend"], progress=1.0)
            return
        if _thread and _thread.is_alive():
            return
        backend = detect_backend()
        log.info("runtime: detected backend=%s cuda=%s gpus=%s", backend, nvidia_cuda_version(), gpu_names())
        _state.update(state="downloading", backend=backend, progress=0.0, error="")
        _thread = threading.Thread(target=_install_safe, args=(_state["backend"],), daemon=True)
        _thread.start()


def ensure_binary() -> Path | None:
    """Path to llama-server, waiting for an in-progress download; None if unavailable."""
    if disabled():
        return None
    info = _installed()
    if info:
        with _lock:
            _state.update(state="ready", backend=info["backend"], progress=1.0)
        return RUNTIME_DIR / info["binary"]
    start_background()
    t = _thread
    if t:
        t.join()
    info = _installed()
    return RUNTIME_DIR / info["binary"] if info else None


def current_backend() -> str:
    info = _installed()
    return info["backend"] if info else ""


def fallback() -> Path | None:
    """Switch to the next-best build after the current one failed to start."""
    info = _installed()
    cur = info["backend"] if info else "cpu"
    rest = CHAIN.get(cur, ["cpu"])[1:]
    for b in rest:
        try:
            new = _install(b)
            with _lock:
                _state.update(state="ready", backend=new["backend"], progress=1.0, error="")
            return RUNTIME_DIR / new["binary"]
        except Exception as e:
            log.warning("fallback to %s failed: %s", b, e)
    return None


def status() -> dict:
    with _lock:
        return dict(_state)


def label() -> tuple[str, bool | None]:
    """(text for the UI, accelerated?) describing the engine currently in use."""
    st = status()
    if st["state"] == "error" and not current_backend():
        return "engine download failed", False
    if st["state"] == "downloading":
        return f"downloading runtime {int(st['progress'] * 100)}%", None
    b = current_backend()
    if b:
        return LABELS.get(b, b), b != "cpu"
    return "", None
