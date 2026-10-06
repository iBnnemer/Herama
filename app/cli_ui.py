"""Herama CLI — rich 3-panel terminal dashboard with HF model search."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import requests
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn, DownloadColumn, Progress, SpinnerColumn,
    TextColumn, TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

BASE_URL = "http://127.0.0.1:11434"
POLL_INTERVAL = 5  # seconds

console = Console()


# ── shared state ──────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.health: dict = {}
        self.skills: dict = {}
        self.logs: list[str] = []
        self.tokens: list[str] = []
        self.connected = False
        self.active_model: str | None = None
        # search screen
        self.screen = "chat"          # "chat" | "search"
        self.search_results: list[Any] = []
        self.search_query = ""
        self.search_busy = False
        self.dl_progress: Any | None = None  # DownloadProgress | None
        self.tasks: list[dict] = [
            {"label": "Connect to Herama backend", "done": False},
            {"label": "Load a model", "done": False},
            {"label": "Chat with the model", "done": False},
        ]

    def log(self, msg: str):
        with self.lock:
            ts = time.strftime("%H:%M:%S")
            self.logs.append(f"[dim]{ts}[/dim] {msg}")
            if len(self.logs) > 200:
                self.logs = self.logs[-200:]

    def add_token(self, t: str):
        with self.lock:
            self.tokens.append(t)

    def clear_tokens(self):
        with self.lock:
            self.tokens.clear()

    def set_task_done(self, label: str):
        with self.lock:
            for t in self.tasks:
                if t["label"] == label:
                    t["done"] = True


state = State()


# ── background poller ────────────────────────────────────────────────────────

def _poll():
    while True:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=3)
            if r.status_code == 200:
                with state.lock:
                    state.health = r.json()
                    state.connected = True
                    if state.health.get("model"):
                        state.active_model = state.health["model"]
                state.set_task_done("Connect to Herama backend")
            else:
                with state.lock:
                    state.connected = False
        except Exception:
            with state.lock:
                state.connected = False

        try:
            r = requests.get(f"{BASE_URL}/api/skills", timeout=3)
            if r.status_code == 200:
                with state.lock:
                    state.skills = r.json()
        except Exception:
            pass

        time.sleep(POLL_INTERVAL)


# ── panel builders ────────────────────────────────────────────────────────────

def _build_tasks_panel() -> Panel:
    lines = Text()
    with state.lock:
        tasks = list(state.tasks)
        connected = state.connected
        active_model = state.active_model
        avail = state.health.get("models_available", "?")
        screen = state.screen

    for t in tasks:
        icon = "[green]✓[/green]" if t["done"] else "[yellow]○[/yellow]"
        lines.append(f" {icon} ", style="")
        lines.append(t["label"] + "\n")

    status_color = "green" if connected else "red"
    status_label = "CONNECTED" if connected else "OFFLINE"
    mode_label = "[cyan]SEARCH[/cyan]" if screen == "search" else "[green]CHAT[/green]"
    header = Text(f"● {status_label}  mode: ", style=status_color + " bold")
    header.append_text(Text.from_markup(mode_label))
    header.append("\n\n")

    if active_model:
        header.append(f"Model: {active_model}\n", style="cyan")
    header.append(f"Available models: {avail}\n\n", style="dim")
    header.append_text(lines)

    return Panel(
        header,
        title="[bold]Active Tasks[/bold]",
        border_style="blue",
        padding=(0, 1),
    )


def _build_skills_panel() -> Panel:
    with state.lock:
        skills = dict(state.skills)

    if not skills:
        body = Text("No skills registered yet.\n\nUse :skill to generate one.", style="dim")
        return Panel(body, title="[bold]Skills Registry[/bold]", border_style="magenta")

    tbl = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    tbl.add_column("Name", style="cyan", no_wrap=True)
    tbl.add_column("Description", style="white")
    tbl.add_column("Created", style="dim", no_wrap=True)

    for name, meta in skills.items():
        desc = (meta.get("desc") or "—")[:60]
        ts = meta.get("ts")
        created = time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "?"
        tbl.add_row(name, desc, created)

    return Panel(tbl, title="[bold]Skills Registry[/bold]", border_style="magenta")


def _build_main_panel() -> Panel:
    with state.lock:
        screen = state.screen
        logs = list(state.logs[-30:])
        tokens = list(state.tokens)

    if screen == "search":
        return _build_search_panel()

    body = Text()

    if tokens:
        body.append("─── Response ───\n", style="bold cyan")
        body.append("".join(tokens) + "\n\n", style="white")

    body.append("─── Logs ───\n", style="bold dim")
    for line in logs[-20:]:
        body.append(line + "\n")

    return Panel(
        body,
        title="[bold]Execution Log[/bold]",
        border_style="green",
        padding=(0, 1),
    )


def _build_search_panel() -> Panel:
    with state.lock:
        results = list(state.search_results)
        query = state.search_query
        busy = state.search_busy
        dl = state.dl_progress

    body = Text()

    # header
    body.append("─── Hugging Face Model Search ───\n", style="bold cyan")
    if query:
        body.append(f"Query: {query}\n", style="dim")
    if busy:
        body.append("Searching…\n", style="yellow")
    body.append("\n")

    # download progress
    if dl is not None:
        if dl.done and not dl.error:
            body.append(f"[green]✓ Download complete:[/green] {dl.filename}\n\n")
        elif dl.error:
            body.append(f"[red]✗ Download failed:[/red] {dl.error}\n\n")
        else:
            pct = dl.pct
            bar_w = 30
            filled = int(bar_w * pct / 100)
            bar = "█" * filled + "░" * (bar_w - filled)
            speed_mb = dl.speed_bps / 1024 / 1024
            body.append(
                f"[cyan]↓[/cyan] {dl.filename[:40]}  [{bar}]  "
                f"{pct:.1f}%  {speed_mb:.1f} MB/s\n\n",
            )

    if not results and not busy:
        body.append("Type  :search <query>  to search Hugging Face for GGUF models.\n", style="dim")
        body.append("Example:  :search mistral 7b\n", style="dim")
        return Panel(body, title="[bold]Search & Download Models[/bold]",
                     border_style="cyan", padding=(0, 1))

    # results table
    tbl = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    tbl.add_column("#", style="dim", no_wrap=True, width=3)
    tbl.add_column("Model / File", style="white", no_wrap=False)
    tbl.add_column("Quant", style="yellow", no_wrap=True)
    tbl.add_column("Size", style="white", no_wrap=True)
    tbl.add_column("Est. Speed", style="green", no_wrap=True)
    tbl.add_column("Fit", style="cyan", no_wrap=False)
    tbl.add_column("VRAM", style="magenta", no_wrap=True)
    tbl.add_column("RAM", style="blue", no_wrap=True)

    for i, card in enumerate(results[:15], 1):
        repo_short = card.repo_id.split("/")[-1][:25]
        fname_short = Path(card.filename).name[:30]
        label = f"{repo_short}\n[dim]{fname_short}[/dim]"
        tbl.add_row(
            str(i),
            label,
            card.quantization,
            f"{card.size_gb:.1f} GB",
            f"~{card.estimated_tps:.0f} t/s",
            card.fit_label,
            f"{card.vram_used_gb:.1f}",
            f"{card.ram_used_gb:.1f}",
        )

    body_renderable = body  # Text so far
    # Return a panel combining both Text and Table via a Group
    from rich.console import Group
    content = Group(body_renderable, tbl)

    return Panel(
        content,
        title="[bold]Search & Download Models[/bold]",
        border_style="cyan",
        padding=(0, 1),
    )


def _build_layout() -> Layout:
    layout = Layout()
    layout.split_row(
        Layout(name="sidebar", ratio=1),
        Layout(name="main", ratio=3),
    )
    layout["sidebar"].split_column(
        Layout(name="tasks", ratio=3),
        Layout(name="skills", ratio=2),
    )
    return layout


# ── chat ──────────────────────────────────────────────────────────────────────

def _stream_chat(model: str, messages: list[dict]) -> float:
    t0 = time.perf_counter()
    state.clear_tokens()
    try:
        r = requests.post(
            f"{BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": True},
            stream=True,
            timeout=120,
        )
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        state.add_token(content)
                except json.JSONDecodeError:
                    pass
    except requests.RequestException as e:
        state.log(f"[red]Chat error: {e}[/red]")
    return time.perf_counter() - t0


# ── HF search / download helpers ─────────────────────────────────────────────

def _do_search(query: str):
    """Run in background thread."""
    from app.hf_manager import search_gguf, estimate_performance, VRAM_TOTAL_BYTES, RAM_TOTAL_BYTES
    try:
        state.log(f"Searching HuggingFace for [cyan]{query}[/cyan]…")
        cards = search_gguf(query, limit=20)
        vfree = VRAM_TOTAL_BYTES / 1024 ** 3
        rfree = RAM_TOTAL_BYTES / 1024 ** 3
        cards = [estimate_performance(c, vfree, rfree) for c in cards]
        with state.lock:
            state.search_results = cards
            state.search_busy = False
        state.log(f"[green]Found {len(cards)} GGUF files[/green] matching '{query}'.")
    except Exception as e:
        with state.lock:
            state.search_busy = False
        state.log(f"[red]Search failed: {e}[/red]")


def _do_download(repo_id: str, filename: str):
    """Run in background thread."""
    from app.hf_manager import download_model, DownloadProgress
    from app import config

    def on_progress(prog: DownloadProgress):
        with state.lock:
            state.dl_progress = prog

    try:
        state.log(f"Downloading [cyan]{filename}[/cyan] from {repo_id}…")
        dest = download_model(repo_id, filename, config.MODELS_DIR, on_progress)
        state.log(f"[green]Saved to {dest}[/green]")
    except Exception as e:
        with state.lock:
            if state.dl_progress:
                state.dl_progress.error = str(e)
        state.log(f"[red]Download failed: {e}[/red]")


# ── commands ──────────────────────────────────────────────────────────────────

HELP_TEXT = """
[bold]Commands — Chat Mode[/bold]
  :model [name]      — load a model (or show current)
  :models            — list local models
  :skills            — refresh skills panel
  :clear             — clear response area
  :search <query>    — switch to Search screen and search HF
  :quit / :exit      — exit Herama CLI

[bold]Commands — Search Mode[/bold]
  :search <query>    — new search
  :download <#>      — download result by number (e.g. :download 3)
  :chat              — return to Chat screen
  :help              — show this help

[bold]Chatting[/bold]
  Type any message and press Enter to chat with the loaded model.
"""


def _handle_command(cmd: str, model_ref: list) -> bool:
    """Return True to quit."""
    parts = cmd.strip().split(None, 1)
    verb = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in (":quit", ":exit"):
        return True

    if verb == ":help":
        console.print(HELP_TEXT)

    elif verb == ":clear":
        state.clear_tokens()
        state.log("Response cleared.")

    elif verb == ":chat":
        with state.lock:
            state.screen = "chat"
        state.log("Switched to Chat screen.")

    elif verb == ":models":
        try:
            r = requests.get(f"{BASE_URL}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            state.log("Local models: " + (", ".join(models) or "none"))
        except Exception as e:
            state.log(f"[red]Error: {e}[/red]")

    elif verb == ":skills":
        state.log("Refreshing skills…")
        try:
            r = requests.get(f"{BASE_URL}/api/skills", timeout=5)
            with state.lock:
                state.skills = r.json()
            state.log(f"Skills refreshed — {len(state.skills)} registered.")
        except Exception as e:
            state.log(f"[red]Error: {e}[/red]")

    elif verb == ":model":
        if arg:
            state.log(f"Loading model [cyan]{arg}[/cyan]…")
            try:
                r = requests.post(
                    f"{BASE_URL}/api/generate",
                    json={"model": arg, "prompt": "", "stream": False},
                    timeout=60,
                )
                if r.status_code == 200:
                    model_ref[0] = arg
                    with state.lock:
                        state.active_model = arg
                    state.set_task_done("Load a model")
                    state.log(f"[green]Model loaded: {arg}[/green]")
                else:
                    state.log(f"[red]Failed: {r.text[:120]}[/red]")
            except Exception as e:
                state.log(f"[red]Error: {e}[/red]")
        else:
            state.log(f"Current model: [cyan]{state.active_model or 'none'}[/cyan]")

    elif verb == ":search":
        if not arg:
            state.log("[yellow]Usage: :search <query>[/yellow]")
        else:
            with state.lock:
                state.screen = "search"
                state.search_query = arg
                state.search_results = []
                state.search_busy = True
                state.dl_progress = None
            threading.Thread(target=_do_search, args=(arg,), daemon=True).start()

    elif verb == ":download":
        with state.lock:
            results = list(state.search_results)
        if not arg.isdigit():
            state.log("[yellow]Usage: :download <number> — pick from search results[/yellow]")
        else:
            idx = int(arg) - 1
            if 0 <= idx < len(results):
                card = results[idx]
                with state.lock:
                    state.dl_progress = None
                threading.Thread(
                    target=_do_download,
                    args=(card.repo_id, card.filename),
                    daemon=True,
                ).start()
            else:
                state.log(f"[yellow]No result #{arg}[/yellow]")

    else:
        state.log(f"[yellow]Unknown command: {verb}. Type :help[/yellow]")

    return False


# ── main loop ─────────────────────────────────────────────────────────────────

def main():
    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    time.sleep(0.5)

    model_ref = [state.active_model or ""]
    history: list[dict] = []

    layout = _build_layout()
    state.log("Herama CLI started. Type :help for commands.")

    with Live(layout, console=console, refresh_per_second=4, screen=True):
        while True:
            with state.lock:
                cur_model = state.active_model or model_ref[0]
                screen = state.screen

            layout["tasks"].update(_build_tasks_panel())
            layout["skills"].update(_build_skills_panel())
            layout["main"].update(_build_main_panel())

            mode = "search" if screen == "search" else cur_model or "no model"
            try:
                user_input = Prompt.ask(
                    f"[cyan]{mode}[/cyan] »", console=console
                ).strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue

            if user_input.startswith(":"):
                if _handle_command(user_input, model_ref):
                    break
                continue

            # chat message (only in chat screen)
            if screen == "search":
                state.log("[dim]Tip: type :chat to return to chat mode.[/dim]")
                continue

            if not cur_model:
                state.log("[yellow]No model loaded. Use :model [name] first.[/yellow]")
                continue

            history.append({"role": "user", "content": user_input})
            state.log(f"[dim]You:[/dim] {user_input[:80]}")
            state.log("Streaming response…")
            layout["main"].update(_build_main_panel())

            elapsed = _stream_chat(cur_model, history)
            full_response = "".join(state.tokens)
            history.append({"role": "assistant", "content": full_response})
            state.set_task_done("Chat with the model")

            tps = len(full_response.split()) / elapsed if elapsed > 0 else 0
            state.log(
                f"[green]Done[/green] — {len(full_response)} chars, "
                f"{elapsed:.1f}s, ~{tps:.1f} words/s"
            )

    console.print("\n[bold green]Goodbye from Herama CLI.[/bold green]")


if __name__ == "__main__":
    main()
