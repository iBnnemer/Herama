"""Herama Desktop GUI — 3-column workspace layout (customtkinter)."""
from __future__ import annotations

import threading
import time
import queue
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Auto-install dependencies
# ---------------------------------------------------------------------------
from app.dependency_manager import ensure_packages

ensure_packages(["customtkinter", "requests", "psutil"])

import customtkinter as ctk
import requests
import psutil

# ---------------------------------------------------------------------------
# Theme / palette
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG         = "#1a1a1f"   # app background
SIDEBAR_BG = "#141417"   # left + right sidebar
PANEL_BG   = "#1e1e26"   # sub-panels
CARD_BG    = "#16161c"   # card / item background
BORDER     = "#2a2a35"   # dividers
TEXT       = "#e2e8f0"   # primary text
TEXT_DIM   = "#6b7280"   # secondary text
ACCENT     = "#3b82f6"   # blue accent
ACCENT_GRN = "#22c55e"   # green
ACCENT_ORG = "#f97316"   # orange
ACCENT_PRP = "#a855f7"   # purple
ACCENT_RED = "#ef4444"   # error

API_BASE   = "http://127.0.0.1:11434"
POLL_MS    = 2000        # sidebar polls every 2 s

# ---------------------------------------------------------------------------
# Shared live state (updated by background thread, read by _tick)
# ---------------------------------------------------------------------------
class _State:
    connected       : bool       = False
    active_model    : str        = ""
    local_models    : list[str]  = []
    skills          : dict       = {}
    bg_tasks        : deque      = deque(maxlen=100)  # (time_str, label, status)
    project_files   : list[str]  = []   # placeholder
    plan_text       : str        = ""   # placeholder markdown plan
    tps             : float      = 0.0

state = _State()
_ui_queue: queue.Queue = queue.Queue()   # (func, *args) dispatched to main thread

# ---------------------------------------------------------------------------
# Background poll
# ---------------------------------------------------------------------------
def _poll(app_ref):
    while True:
        try:
            r = requests.get(f"{API_BASE}/health", timeout=2)
            state.connected = r.status_code == 200
        except Exception:
            state.connected = False

        try:
            r = requests.get(f"{API_BASE}/api/tags", timeout=2)
            state.local_models = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass

        try:
            r = requests.get(f"{API_BASE}/api/skills", timeout=2)
            state.skills = r.json()
        except Exception:
            pass

        try:
            app_ref.after(0, app_ref._tick)
        except Exception:
            pass

        time.sleep(POLL_MS / 1000)


# ===========================================================================
# LEFT SIDEBAR
# ===========================================================================
class LeftSidebar(ctk.CTkFrame):
    """Navigation sidebar — Sessions / Projects / Bots / Artifacts / Routines."""

    def __init__(self, master, on_section: Callable[[str], None], **kw):
        super().__init__(master, width=220, fg_color=SIDEBAR_BG, corner_radius=0, **kw)
        self.on_section = on_section
        self._active_section = "Sessions"
        self._build()

    def _build(self):
        self.pack_propagate(False)
        self.grid_propagate(False)

        # ── top tab row: SESSIONS / BOTS ──
        tab_row = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        tab_row.pack(fill="x", padx=0, pady=(8, 0))

        self._tab_sessions = ctk.CTkButton(
            tab_row, text="SESSIONS", font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG, hover_color=BORDER, text_color=TEXT,
            corner_radius=6, height=28,
            command=lambda: self._show_section("Sessions"),
        )
        self._tab_sessions.pack(side="left", padx=(8, 2), pady=2)

        self._tab_bots = ctk.CTkButton(
            tab_row, text="BOTS", font=("Segoe UI", 11, "bold"),
            fg_color=SIDEBAR_BG, hover_color=BORDER, text_color=TEXT_DIM,
            corner_radius=6, height=28,
            command=lambda: self._show_section("Bots"),
        )
        self._tab_bots.pack(side="left", padx=(2, 8), pady=2)

        # ── "+ New" button ──
        ctk.CTkButton(
            self, text="+ New", font=("Segoe UI", 12),
            fg_color=CARD_BG, hover_color=BORDER, text_color=TEXT,
            height=30, corner_radius=6,
            command=lambda: self.on_section("new"),
        ).pack(fill="x", padx=8, pady=(8, 4))

        # ── nav items ──
        nav_items = [
            ("Projects", "Beta"),
            ("Artifacts", ""),
            ("Routines", ""),
            ("Customize", ""),
        ]
        for label, badge in nav_items:
            row = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
            row.pack(fill="x", padx=8, pady=1)
            btn = ctk.CTkButton(
                row, text=label, anchor="w",
                font=("Segoe UI", 12), fg_color=SIDEBAR_BG,
                hover_color=CARD_BG, text_color=TEXT_DIM,
                height=28, corner_radius=4,
                command=lambda l=label: self.on_section(l),
            )
            btn.pack(side="left", fill="x", expand=True)
            if badge:
                ctk.CTkLabel(
                    row, text=badge, font=("Segoe UI", 9),
                    fg_color=ACCENT, text_color="white",
                    corner_radius=4, padx=4, pady=1,
                ).pack(side="right", padx=(0, 4))

        self._divider()

        # ── Pinned section ──
        ctk.CTkLabel(
            self, text="Pinned", font=("Segoe UI", 10),
            text_color=TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 2))

        for label in ["Herama", "Task Monitor"]:
            self._nav_item(label, icon="◆")

        self._divider()

        # ── Models section ──
        ctk.CTkLabel(
            self, text="Local Models", font=("Segoe UI", 10),
            text_color=TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 2))

        self._models_frame = ctk.CTkScrollableFrame(
            self, fg_color=SIDEBAR_BG, height=120, corner_radius=0,
        )
        self._models_frame.pack(fill="x", padx=4)

        self._divider()

        # ── Status chip ──
        self._status_lbl = ctk.CTkLabel(
            self, text="⬤  Offline", font=("Segoe UI", 11),
            text_color=ACCENT_RED, anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=12, pady=(4, 4))

    def _divider(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(
            fill="x", padx=0, pady=4
        )

    def _nav_item(self, label: str, icon: str = "•"):
        btn = ctk.CTkButton(
            self, text=f"  {icon}  {label}", anchor="w",
            font=("Segoe UI", 12), fg_color=SIDEBAR_BG,
            hover_color=CARD_BG, text_color=TEXT,
            height=28, corner_radius=4,
            command=lambda: self.on_section(label),
        )
        btn.pack(fill="x", padx=4, pady=1)
        return btn

    def _show_section(self, name: str):
        self._active_section = name
        is_s = name == "Sessions"
        self._tab_sessions.configure(
            fg_color=CARD_BG if is_s else SIDEBAR_BG,
            text_color=TEXT if is_s else TEXT_DIM,
        )
        self._tab_bots.configure(
            fg_color=CARD_BG if not is_s else SIDEBAR_BG,
            text_color=TEXT if not is_s else TEXT_DIM,
        )

    def refresh(self):
        # update model list
        for w in self._models_frame.winfo_children():
            w.destroy()
        for m in state.local_models:
            ctk.CTkLabel(
                self._models_frame, text=m, font=("Segoe UI", 11),
                text_color=TEXT_DIM, anchor="w",
            ).pack(fill="x", padx=4, pady=1)

        # update status chip
        if state.connected:
            self._status_lbl.configure(text="⬤  Backend online", text_color=ACCENT_GRN)
        else:
            self._status_lbl.configure(text="⬤  Offline", text_color=ACCENT_RED)


# ===========================================================================
# CENTER PANEL — chat area
# ===========================================================================
class ChatBubble(ctk.CTkFrame):
    """Single message bubble (user or assistant)."""

    def __init__(self, master, role: str, text: str, **kw):
        is_user = role == "user"
        super().__init__(
            master,
            fg_color=CARD_BG if is_user else PANEL_BG,
            corner_radius=10,
            **kw,
        )
        header = "You" if is_user else "Herama"
        clr = ACCENT if is_user else ACCENT_PRP
        ctk.CTkLabel(
            self, text=header, font=("Segoe UI", 10, "bold"),
            text_color=clr, anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(
            self, text=text, font=("Segoe UI", 12),
            text_color=TEXT, wraplength=580, justify="left", anchor="w",
        ).pack(fill="x", padx=10, pady=(2, 8))


class CenterPanel(ctk.CTkFrame):
    """Main chat execution panel."""

    def __init__(self, master, on_send: Callable[[str], None], **kw):
        super().__init__(master, fg_color=BG, corner_radius=0, **kw)
        self.on_send = on_send
        self._stream_bubble: ctk.CTkLabel | None = None
        self._build()

    def _build(self):
        # ── header bar ──
        hdr = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="New session", font=("Segoe UI", 13, "bold"),
            text_color=TEXT, anchor="w",
        ).pack(side="left", padx=16, pady=10)

        self._model_lbl = ctk.CTkLabel(
            hdr, text="Default", font=("Segoe UI", 11),
            text_color=TEXT_DIM,
        )
        self._model_lbl.pack(side="left", padx=8)

        # ── scrollable message history ──
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=BG, corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── input area ──
        input_bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        input_bar.pack(fill="x", pady=(0, 0))

        self._input = ctk.CTkTextbox(
            input_bar, height=60, font=("Segoe UI", 13),
            fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, border_width=1, corner_radius=8,
        )
        self._input.pack(fill="x", padx=12, pady=10, side="left", expand=True)
        self._input.bind("<Return>", self._on_return)
        self._input.bind("<Shift-Return>", lambda e: None)

        ctk.CTkButton(
            input_bar, text="Send", width=70, height=40,
            font=("Segoe UI", 12, "bold"),
            fg_color=ACCENT, hover_color="#2563eb", text_color="white",
            corner_radius=8, command=self._send,
        ).pack(side="right", padx=(0, 12), pady=10)

    def _on_return(self, event):
        if event.state & 0x1:   # Shift held → newline
            return
        self._send()
        return "break"

    def _send(self):
        text = self._input.get("1.0", "end").strip()
        if not text:
            return
        self._input.delete("1.0", "end")
        self.add_message("user", text)
        self.on_send(text)

    def add_message(self, role: str, text: str):
        bubble = ChatBubble(self._scroll, role, text)
        bubble.pack(fill="x", padx=16, pady=4)
        self._scroll._parent_canvas.yview_moveto(1.0)

    def start_stream(self) -> ctk.CTkLabel:
        """Create a streaming placeholder bubble; return its text label."""
        frame = ctk.CTkFrame(self._scroll, fg_color=PANEL_BG, corner_radius=10)
        frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(
            frame, text="Herama", font=("Segoe UI", 10, "bold"),
            text_color=ACCENT_PRP, anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 0))
        lbl = ctk.CTkLabel(
            frame, text="▋", font=("Segoe UI", 12),
            text_color=TEXT, wraplength=580, justify="left", anchor="w",
        )
        lbl.pack(fill="x", padx=10, pady=(2, 8))
        self._stream_bubble = lbl
        self._scroll._parent_canvas.yview_moveto(1.0)
        return lbl

    def update_model(self, model: str):
        self._model_lbl.configure(text=model or "No model loaded")


# ===========================================================================
# RIGHT SIDEBAR — Plan / Files / Background Tasks
# ===========================================================================
class PlanPanel(ctk.CTkFrame):
    """Sub-panel A: Plan Tracker (markdown scaffold with todo/done)."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=8, **kw)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            hdr, text="Plan", font=("Segoe UI", 12, "bold"),
            text_color=TEXT, anchor="w",
        ).pack(side="left")

        self._text = ctk.CTkTextbox(
            self, font=("Cascadia Code", 11),
            fg_color=CARD_BG, text_color=TEXT,
            border_width=0, corner_radius=6,
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._text.insert("end", "No active plan.\n\nStart a conversation to generate a task plan.")
        self._text.configure(state="disabled")

    def set_plan(self, text: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("end", text or "No active plan.")
        self._text.configure(state="disabled")


class FilesPanel(ctk.CTkFrame):
    """Sub-panel B: Files Browser."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=8, **kw)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            hdr, text="Files", font=("Segoe UI", 12, "bold"),
            text_color=TEXT, anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="Open folder", width=90, height=24,
            font=("Segoe UI", 10), fg_color=CARD_BG,
            hover_color=BORDER, text_color=TEXT_DIM, corner_radius=4,
            command=self._open_folder,
        ).pack(side="right")

        self._tree = ctk.CTkScrollableFrame(
            self, fg_color=CARD_BG, corner_radius=6,
        )
        self._tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._placeholder = ctk.CTkLabel(
            self._tree,
            text="Open files appear here\n\nPick a file in the tree,\nor click a file path in\nthe conversation.",
            font=("Segoe UI", 11), text_color=TEXT_DIM, justify="center",
        )
        self._placeholder.pack(expand=True, pady=30)

    def _open_folder(self):
        try:
            import tkinter.filedialog as fd
            path = fd.askdirectory()
            if path:
                self.load_directory(path)
        except Exception:
            pass

    def load_directory(self, path: str):
        for w in self._tree.winfo_children():
            w.destroy()
        p = Path(path)
        if not p.exists():
            return
        for item in sorted(p.iterdir()):
            icon = "📁" if item.is_dir() else "📄"
            ctk.CTkLabel(
                self._tree,
                text=f"  {icon}  {item.name}",
                font=("Segoe UI", 11), text_color=TEXT_DIM, anchor="w",
            ).pack(fill="x", padx=4, pady=1)

    def refresh_files(self, files: list[str]):
        for w in self._tree.winfo_children():
            w.destroy()
        if not files:
            ctk.CTkLabel(
                self._tree, text="No files loaded.",
                font=("Segoe UI", 11), text_color=TEXT_DIM,
            ).pack(pady=20)
            return
        for f in files:
            ctk.CTkLabel(
                self._tree, text=f"  📄  {f}",
                font=("Segoe UI", 11), text_color=TEXT_DIM, anchor="w",
            ).pack(fill="x", padx=4, pady=1)


class BgTasksPanel(ctk.CTkFrame):
    """Sub-panel C: Background Tasks Log."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=8, **kw)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            hdr, text="Background tasks", font=("Segoe UI", 12, "bold"),
            text_color=TEXT, anchor="w",
        ).pack(side="left")
        self._count_lbl = ctk.CTkLabel(
            hdr, text="", font=("Segoe UI", 10),
            text_color=TEXT_DIM,
        )
        self._count_lbl.pack(side="right")

        self._log = ctk.CTkScrollableFrame(
            self, fg_color=CARD_BG, corner_radius=6,
        )
        self._log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._placeholder = ctk.CTkLabel(
            self._log, text="No background tasks running.",
            font=("Segoe UI", 11), text_color=TEXT_DIM,
        )
        self._placeholder.pack(expand=True, pady=20)

    def add_task(self, label: str, status: str = "running"):
        for w in self._log.winfo_children():
            if isinstance(w, ctk.CTkLabel) and "No background" in w.cget("text"):
                w.destroy()
                break
        color = {
            "done": ACCENT_GRN,
            "error": ACCENT_RED,
            "running": ACCENT_ORG,
        }.get(status, TEXT_DIM)
        ts = datetime.now().strftime("%H:%M:%S")
        row = ctk.CTkFrame(self._log, fg_color=CARD_BG, corner_radius=4)
        row.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(
            row, text=f"[{ts}]", font=("Cascadia Code", 10),
            text_color=TEXT_DIM, width=60,
        ).pack(side="left", padx=4)
        ctk.CTkLabel(
            row, text=label, font=("Segoe UI", 11),
            text_color=TEXT, anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkLabel(
            row, text=status, font=("Segoe UI", 10, "bold"),
            text_color=color,
        ).pack(side="right", padx=6)
        count = len([w for w in self._log.winfo_children() if isinstance(w, ctk.CTkFrame)])
        self._count_lbl.configure(text=f"Finished {count} ›")
        self._log._parent_canvas.yview_moveto(1.0)


# ===========================================================================
# RIGHT SIDEBAR container — tabbed sub-panels
# ===========================================================================
class RightSidebar(ctk.CTkFrame):
    """Dynamic right sidebar with Plan / Files / Tasks sub-panels."""

    def __init__(self, master, **kw):
        super().__init__(master, width=340, fg_color=SIDEBAR_BG, corner_radius=0, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._build()

    def _build(self):
        # ── tab bar ──
        tab_bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        tab_bar.pack(fill="x", padx=8, pady=(8, 4))

        self._tabs: dict[str, ctk.CTkButton] = {}
        for name in ("Plan", "Files", "Tasks"):
            btn = ctk.CTkButton(
                tab_bar, text=name, font=("Segoe UI", 11),
                fg_color=CARD_BG, hover_color=BORDER,
                text_color=TEXT_DIM, corner_radius=6,
                height=26, width=70,
                command=lambda n=name: self._show_tab(n),
            )
            btn.pack(side="left", padx=2)
            self._tabs[name] = btn

        # ── panels ──
        self._panels: dict[str, ctk.CTkFrame] = {}

        self._plan   = PlanPanel(self)
        self._files  = FilesPanel(self)
        self._tasks  = BgTasksPanel(self)

        self._panels["Plan"]  = self._plan
        self._panels["Files"] = self._files
        self._panels["Tasks"] = self._tasks

        self._show_tab("Plan")

    def _show_tab(self, name: str):
        for n, panel in self._panels.items():
            panel.pack_forget()
        for n, btn in self._tabs.items():
            btn.configure(
                fg_color=ACCENT if n == name else CARD_BG,
                text_color=TEXT if n == name else TEXT_DIM,
            )
        self._panels[name].pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # convenience proxies
    @property
    def plan(self)  -> PlanPanel:    return self._plan
    @property
    def files(self) -> FilesPanel:   return self._files
    @property
    def tasks(self) -> BgTasksPanel: return self._tasks


# ===========================================================================
# Main application
# ===========================================================================
class HeramaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Herama  —  Local LLM Workspace")
        self.geometry("1400x860")
        self.minsize(1100, 600)
        self.configure(fg_color=BG)

        self._history: list[dict] = []          # [{role, content}]
        self._stream_label: ctk.CTkLabel | None = None
        self._stream_buf: str = ""

        self._build_layout()
        self.after(POLL_MS, self._tick)

    # ------------------------------------------------------------------
    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # left  sidebar  — fixed
        self.grid_columnconfigure(1, weight=1)   # center panel   — fills
        self.grid_columnconfigure(2, weight=0)   # right sidebar  — fixed

        self._left  = LeftSidebar(self, on_section=self._on_nav)
        self._left.grid(row=0, column=0, sticky="nsew")

        self._center = CenterPanel(self, on_send=self._on_send)
        self._center.grid(row=0, column=1, sticky="nsew")

        self._right = RightSidebar(self)
        self._right.grid(row=0, column=2, sticky="nsew")

        # seed background task log with welcome entry
        self._right.tasks.add_task("Herama workspace launched", "done")

    # ------------------------------------------------------------------
    def _on_nav(self, section: str):
        """Handle left-sidebar navigation clicks."""
        if section == "new":
            self._center.add_message("system_info", "New session started.")
        else:
            self._right.tasks.add_task(f"Navigated to: {section}", "done")

    # ------------------------------------------------------------------
    def _tick(self):
        """Periodic UI refresh (runs on main thread via after())."""
        self._left.refresh()
        if state.active_model:
            self._center.update_model(state.active_model)
        self.after(POLL_MS, self._tick)

    # ------------------------------------------------------------------
    def _on_send(self, text: str):
        """Handle user message send."""
        self._history.append({"role": "user", "content": text})
        self._right.tasks.add_task(f"Chat → {text[:40]}…" if len(text) > 40 else f"Chat → {text}", "running")

        if not state.connected:
            self._center.add_message("assistant", "⚠ Backend is offline. Start `herama` server first.")
            return

        if not state.local_models:
            self._center.add_message("assistant", "⚠ No models loaded. Use the sidebar to download one.")
            return

        model = state.active_model or state.local_models[0]
        stream_lbl = self._center.start_stream()
        self._stream_label = stream_lbl
        self._stream_buf = ""

        threading.Thread(
            target=self._stream_generate,
            args=(model, text, stream_lbl),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    def _stream_generate(self, model: str, prompt: str, lbl: ctk.CTkLabel):
        """Run /api/generate streaming in background thread."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
        }
        buf = ""
        try:
            with requests.post(
                f"{API_BASE}/api/generate", json=payload, stream=True, timeout=120
            ) as resp:
                import json as _json
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = _json.loads(line)
                    except Exception:
                        continue
                    token = chunk.get("response", "")
                    buf += token
                    captured = buf
                    self.after(0, lambda t=captured: lbl.configure(text=t))
                    if chunk.get("done"):
                        break
            self._history.append({"role": "assistant", "content": buf})
            self.after(0, lambda: self._right.tasks.add_task(
                f"Chat ← {buf[:40]}…" if len(buf) > 40 else f"Chat ← {buf}", "done"
            ))
        except Exception as exc:
            msg = f"Error: {exc}"
            self.after(0, lambda m=msg: lbl.configure(text=m, text_color=ACCENT_RED))
            self.after(0, lambda: self._right.tasks.add_task(f"Chat error: {exc}", "error"))

    def load_model(self, name: str):
        state.active_model = name
        self._center.update_model(name)
        self._right.tasks.add_task(f"Load model: {name}", "running")


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    app = HeramaApp()
    threading.Thread(target=_poll, args=(app,), daemon=True).start()
    app.mainloop()


if __name__ == "__main__":
    main()
