"""Herama CLI — rich 3-panel terminal dashboard."""
from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any

import requests
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

BASE_URL = "http://127.0.0.1:11434"
POLL_INTERVAL = 5  # seconds

console = Console()


# ── shared state ─────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.health: dict = {}
        self.skills: dict = {}
        self.logs: list[str] = []
        self.tokens: list[str] = []
        self.connected = False
        self.active_model: str | None = None
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


# ── background poller ─────────────────────────────────────────────────────────

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
    for t in state.tasks:
        icon = "[green]✓[/green]" if t["done"] else "[yellow]○[/yellow]"
        lines.append(f" {icon} ", style="")
        lines.append(t["label"] + "\n")

    status_color = "green" if state.connected else "red"
    status_label = "CONNECTED" if state.connected else "OFFLINE"
    header = Text(f"● {status_label}\n\n", style=status_color + " bold")

    if state.active_model:
        header.append(f"Model: {state.active_model}\n", style="cyan")
    avail = state.health.get("models_available", "?")
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
        logs = list(state.logs[-30:])
        tokens = list(state.tokens)

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
    elapsed = time.perf_counter() - t0
    return elapsed


# ── commands ──────────────────────────────────────────────────────────────────

HELP_TEXT = """
[bold]Commands[/bold]
  :model [name]    — load a model (or show current)
  :models          — list available models
  :skills          — refresh skills panel
  :clear           — clear response area
  :help            — show this help
  :quit / :exit    — exit Herama CLI

[bold]Chatting[/bold]
  Type any message and press Enter to chat with the loaded model.
"""


def _handle_command(cmd: str, model_ref: list) -> bool:
    """Return True to quit."""
    parts = cmd.strip().split(None, 1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb in (":quit", ":exit"):
        return True

    if verb == ":help":
        console.print(HELP_TEXT)

    elif verb == ":clear":
        state.clear_tokens()
        state.log("Response cleared.")

    elif verb == ":models":
        try:
            r = requests.get(f"{BASE_URL}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            state.log("Models: " + (", ".join(models) or "none"))
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
            current = state.active_model or "none"
            state.log(f"Current model: [cyan]{current}[/cyan]")

    else:
        state.log(f"[yellow]Unknown command: {verb}. Type :help[/yellow]")

    return False


# ── main loop ─────────────────────────────────────────────────────────────────

def main():
    # start background poller
    t = threading.Thread(target=_poll, daemon=True)
    t.start()

    # give it a moment to connect
    time.sleep(0.5)

    model_ref = [state.active_model or ""]
    history: list[dict] = []

    layout = _build_layout()
    state.log("Herama CLI started. Type :help for commands.")

    with Live(layout, console=console, refresh_per_second=4, screen=True):
        while True:
            with state.lock:
                cur_model = state.active_model or model_ref[0]

            layout["tasks"].update(_build_tasks_panel())
            layout["skills"].update(_build_skills_panel())
            layout["main"].update(_build_main_panel())

            # read input outside of Live refresh to avoid flicker
            try:
                prompt_str = f"[cyan]{cur_model or 'no model'}[/cyan] » "
                user_input = Prompt.ask(prompt_str, console=console).strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input:
                continue

            if user_input.startswith(":"):
                quit_flag = _handle_command(user_input, model_ref)
                if quit_flag:
                    break
                continue

            # chat message
            if not cur_model:
                state.log("[yellow]No model loaded. Use :model [name] first.[/yellow]")
                continue

            history.append({"role": "user", "content": user_input})
            state.log(f"[dim]You:[/dim] {user_input[:80]}")
            state.log("Streaming response…")

            # update layout before blocking call
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
