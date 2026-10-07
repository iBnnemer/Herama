"""Herama Desktop GUI — 3-column adaptive workspace (customtkinter)."""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Auto-install & silent upgrade on launch
# ---------------------------------------------------------------------------
from app.dependency_manager import ensure_packages, upgrade_packages_async

_GUI_DEPS = ["customtkinter", "requests", "psutil"]
ensure_packages(_GUI_DEPS)
# Upgrade all packages in requirements.txt silently in the background
upgrade_packages_async()   # no args → reads requirements.txt

import customtkinter as ctk
import requests
import psutil

# ---------------------------------------------------------------------------
# Theme / palette
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG         = "#1a1a1f"
SIDEBAR_BG = "#141417"
PANEL_BG   = "#1e1e26"
CARD_BG    = "#16161c"
BORDER     = "#2a2a35"
TEXT       = "#e2e8f0"
TEXT_DIM   = "#6b7280"
ACCENT     = "#3b82f6"
ACCENT_GRN = "#22c55e"
ACCENT_ORG = "#f97316"
ACCENT_PRP = "#a855f7"
ACCENT_RED = "#ef4444"

API_BASE = "http://127.0.0.1:11434"
POLL_MS  = 2000


# ---------------------------------------------------------------------------
# Shared live state
# ---------------------------------------------------------------------------
class _State:
    connected    : bool      = False
    active_model : str       = ""
    local_models : list[str] = []
    skills       : dict      = {}
    tps          : float     = 0.0

state = _State()


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
    """Navigation sidebar — Sessions / Models / Clone repo."""

    def __init__(self, master, on_section: Callable[[str], None], **kw):
        super().__init__(master, width=220, fg_color=SIDEBAR_BG, corner_radius=0, **kw)
        self.on_section = on_section
        self._build()

    def _build(self):
        self.pack_propagate(False)
        self.grid_propagate(False)

        # ── tab row ──
        tab_row = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        tab_row.pack(fill="x", pady=(8, 0))

        self._tab_s = ctk.CTkButton(
            tab_row, text="SESSIONS", font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG, hover_color=BORDER, text_color=TEXT,
            corner_radius=6, height=28,
            command=lambda: self._activate_tab("SESSIONS"),
        )
        self._tab_s.pack(side="left", padx=(8, 2), pady=2)

        self._tab_b = ctk.CTkButton(
            tab_row, text="BOTS", font=("Segoe UI", 11, "bold"),
            fg_color=SIDEBAR_BG, hover_color=BORDER, text_color=TEXT_DIM,
            corner_radius=6, height=28,
            command=lambda: self._activate_tab("BOTS"),
        )
        self._tab_b.pack(side="left", padx=(2, 8), pady=2)

        # ── "+ New" ──
        ctk.CTkButton(
            self, text="+ New Session", font=("Segoe UI", 12),
            fg_color=CARD_BG, hover_color=BORDER, text_color=TEXT,
            height=30, corner_radius=6,
            command=lambda: self.on_section("new"),
        ).pack(fill="x", padx=8, pady=(8, 4))

        # ── nav list ──
        for label, badge in [("Projects", "Beta"), ("Artifacts", ""),
                              ("Routines", ""), ("Customize", "")]:
            row = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
            row.pack(fill="x", padx=8, pady=1)
            ctk.CTkButton(
                row, text=label, anchor="w",
                font=("Segoe UI", 12), fg_color=SIDEBAR_BG,
                hover_color=CARD_BG, text_color=TEXT_DIM,
                height=28, corner_radius=4,
                command=lambda l=label: self.on_section(l),
            ).pack(side="left", fill="x", expand=True)
            if badge:
                ctk.CTkLabel(
                    row, text=badge, font=("Segoe UI", 9),
                    fg_color=ACCENT, text_color="white",
                    corner_radius=4, padx=4, pady=1,
                ).pack(side="right", padx=(0, 4))

        self._div()

        # ── pinned ──
        ctk.CTkLabel(self, text="Pinned", font=("Segoe UI", 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=12, pady=(4, 2))
        for lbl in ["Herama", "Task Monitor"]:
            ctk.CTkButton(
                self, text=f"  ◆  {lbl}", anchor="w",
                font=("Segoe UI", 12), fg_color=SIDEBAR_BG,
                hover_color=CARD_BG, text_color=TEXT,
                height=28, corner_radius=4,
                command=lambda l=lbl: self.on_section(l),
            ).pack(fill="x", padx=4, pady=1)

        self._div()

        # ── GitHub clone ──
        ctk.CTkLabel(self, text="GitHub", font=("Segoe UI", 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=12, pady=(4, 2))

        self._clone_entry = ctk.CTkEntry(
            self, placeholder_text="https://github.com/owner/repo",
            font=("Segoe UI", 11), fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, height=28, corner_radius=6,
        )
        self._clone_entry.pack(fill="x", padx=8, pady=2)

        ctk.CTkButton(
            self, text="Clone Repo", font=("Segoe UI", 11),
            fg_color=ACCENT, hover_color="#2563eb", text_color="white",
            height=28, corner_radius=6,
            command=self._do_clone,
        ).pack(fill="x", padx=8, pady=(2, 4))

        self._clone_status = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 10),
            text_color=TEXT_DIM, anchor="w", wraplength=190,
        )
        self._clone_status.pack(fill="x", padx=12)

        self._div()

        # ── local models ──
        ctk.CTkLabel(self, text="Local Models", font=("Segoe UI", 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=12, pady=(4, 2))

        self._models_frame = ctk.CTkScrollableFrame(
            self, fg_color=SIDEBAR_BG, height=100, corner_radius=0,
        )
        self._models_frame.pack(fill="x", padx=4)

        self._div()

        # ── status ──
        self._status_lbl = ctk.CTkLabel(
            self, text="⬤  Offline", font=("Segoe UI", 11),
            text_color=ACCENT_RED, anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=12, pady=(4, 8))

    def _div(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(
            fill="x", pady=4)

    def _activate_tab(self, name: str):
        is_s = name == "SESSIONS"
        self._tab_s.configure(fg_color=CARD_BG if is_s else SIDEBAR_BG,
                              text_color=TEXT if is_s else TEXT_DIM)
        self._tab_b.configure(fg_color=CARD_BG if not is_s else SIDEBAR_BG,
                              text_color=TEXT if not is_s else TEXT_DIM)

    def _do_clone(self):
        url = self._clone_entry.get().strip()
        if not url:
            return
        self._clone_status.configure(text="Cloning…", text_color=ACCENT_ORG)
        workspace = Path.home() / "herama_workspace"

        from app.git_manager import clone_repo_async, CloneProgress

        def _progress(p: CloneProgress):
            msg = f"{p.phase} {p.pct:.0f}%" if not p.done else "Done ✓"
            color = ACCENT_GRN if p.done else (ACCENT_RED if p.error else ACCENT_ORG)
            try:
                self.after(0, lambda m=msg, c=color: self._clone_status.configure(
                    text=m, text_color=c))
            except Exception:
                pass

        def _done(path, err):
            if err:
                self.after(0, lambda: self._clone_status.configure(
                    text=f"Error: {err[:60]}", text_color=ACCENT_RED))
            else:
                self.after(0, lambda: self._clone_status.configure(
                    text=f"Cloned → {path.name}", text_color=ACCENT_GRN))
                self.on_section(f"open_dir:{path}")

        clone_repo_async(url, workspace, _progress, _done)

    def refresh(self):
        for w in self._models_frame.winfo_children():
            w.destroy()
        for m in state.local_models:
            ctk.CTkLabel(
                self._models_frame, text=m, font=("Segoe UI", 11),
                text_color=TEXT_DIM, anchor="w",
            ).pack(fill="x", padx=4, pady=1)
        self._status_lbl.configure(
            text="⬤  Backend online" if state.connected else "⬤  Offline",
            text_color=ACCENT_GRN if state.connected else ACCENT_RED,
        )


# ===========================================================================
# CENTER PANEL
# ===========================================================================
class ChatBubble(ctk.CTkFrame):
    def __init__(self, master, role: str, text: str, **kw):
        super().__init__(master,
                         fg_color=CARD_BG if role == "user" else PANEL_BG,
                         corner_radius=10, **kw)
        ctk.CTkLabel(
            self,
            text="You" if role == "user" else "Herama",
            font=("Segoe UI", 10, "bold"),
            text_color=ACCENT if role == "user" else ACCENT_PRP,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(
            self, text=text, font=("Segoe UI", 12),
            text_color=TEXT, wraplength=560, justify="left", anchor="w",
        ).pack(fill="x", padx=10, pady=(2, 8))


class CenterPanel(ctk.CTkFrame):
    def __init__(self, master, on_send: Callable[[str], None], **kw):
        super().__init__(master, fg_color=BG, corner_radius=0, **kw)
        self.on_send = on_send
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Herama Workspace", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left", padx=16, pady=10)
        self._model_lbl = ctk.CTkLabel(hdr, text="No model", font=("Segoe UI", 11),
                                       text_color=TEXT_DIM)
        self._model_lbl.pack(side="left", padx=8)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        bar.pack(fill="x")
        self._input = ctk.CTkTextbox(
            bar, height=60, font=("Segoe UI", 13),
            fg_color=CARD_BG, text_color=TEXT,
            border_color=BORDER, border_width=1, corner_radius=8,
        )
        self._input.pack(fill="x", padx=12, pady=10, side="left", expand=True)
        self._input.bind("<Return>", self._on_return)
        ctk.CTkButton(
            bar, text="Send", width=70, height=40,
            font=("Segoe UI", 12, "bold"),
            fg_color=ACCENT, hover_color="#2563eb", text_color="white",
            corner_radius=8, command=self._send,
        ).pack(side="right", padx=(0, 12), pady=10)

    def _on_return(self, event):
        if event.state & 0x1:
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
        ChatBubble(self._scroll, role, text).pack(fill="x", padx=16, pady=4)
        self._scroll._parent_canvas.yview_moveto(1.0)

    def start_stream(self) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(self._scroll, fg_color=PANEL_BG, corner_radius=10)
        frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(frame, text="Herama", font=("Segoe UI", 10, "bold"),
                     text_color=ACCENT_PRP, anchor="w").pack(fill="x", padx=10, pady=(6, 0))
        lbl = ctk.CTkLabel(frame, text="▋", font=("Segoe UI", 12),
                           text_color=TEXT, wraplength=560, justify="left", anchor="w")
        lbl.pack(fill="x", padx=10, pady=(2, 8))
        self._scroll._parent_canvas.yview_moveto(1.0)
        return lbl

    def update_model(self, model: str):
        self._model_lbl.configure(text=model or "No model")


# ===========================================================================
# RIGHT SIDEBAR — Adaptive Layout Container
# ===========================================================================

class PlanPanel(ctk.CTkFrame):
    """Plan Tracker — markdown/text scaffold."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=0, **kw)
        ctk.CTkLabel(self, text="Plan", font=("Segoe UI", 11, "bold"),
                     text_color=TEXT, anchor="w").pack(fill="x", padx=8, pady=(6, 2))
        self._text = ctk.CTkTextbox(
            self, font=("Cascadia Code", 11),
            fg_color=CARD_BG, text_color=TEXT,
            border_width=0, corner_radius=4,
        )
        self._text.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._text.insert("end", "No active plan.\n\nStart a conversation to generate a task plan.")
        self._text.configure(state="disabled")

    def set_plan(self, text: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("end", text or "No active plan.")
        self._text.configure(state="disabled")


class FilesPanel(ctk.CTkFrame):
    """Files Explorer — real directory tree with deep traversal."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=0, **kw)
        self._root_path: Path | None = None
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        hdr.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(hdr, text="Files Explorer", font=("Segoe UI", 11, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left")
        ctk.CTkButton(
            hdr, text="Open…", width=60, height=22,
            font=("Segoe UI", 10), fg_color=CARD_BG,
            hover_color=BORDER, text_color=TEXT_DIM, corner_radius=4,
            command=self._pick_folder,
        ).pack(side="right")
        self._path_lbl = ctk.CTkLabel(self, text="No folder open",
                                      font=("Segoe UI", 9), text_color=TEXT_DIM,
                                      anchor="w", wraplength=300)
        self._path_lbl.pack(fill="x", padx=8, pady=(0, 2))
        self._tree = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=4)
        self._tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        ctk.CTkLabel(self._tree, text="Open a folder or clone a repo",
                     font=("Segoe UI", 11), text_color=TEXT_DIM).pack(pady=20)

    def _pick_folder(self):
        try:
            import tkinter.filedialog as fd
            path = fd.askdirectory()
            if path:
                self.load_directory(Path(path))
        except Exception:
            pass

    def load_directory(self, path: Path, depth: int = 0, parent_frame=None):
        if depth == 0:
            self._root_path = path
            for w in self._tree.winfo_children():
                w.destroy()
            self._path_lbl.configure(text=str(path))
            parent_frame = self._tree

        if not path.exists() or not path.is_dir():
            return

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        indent = "  " * depth
        for item in items:
            if item.name.startswith(".") and depth > 0:
                continue   # skip hidden inside subdirs
            icon = "📁" if item.is_dir() else "📄"
            lbl = ctk.CTkLabel(
                parent_frame,
                text=f"{indent}{icon}  {item.name}",
                font=("Segoe UI", 11), text_color=TEXT_DIM, anchor="w",
                cursor="hand2",
            )
            lbl.pack(fill="x", padx=2, pady=1)
            if item.is_dir() and depth < 2:
                self.load_directory(item, depth + 1, parent_frame)


class BgTasksPanel(ctk.CTkFrame):
    """Background Tasks Log — timestamped entries with status badge."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=0, **kw)
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        hdr.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(hdr, text="Background Tasks", font=("Segoe UI", 11, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left")
        self._count_lbl = ctk.CTkLabel(hdr, text="", font=("Segoe UI", 10),
                                       text_color=TEXT_DIM)
        self._count_lbl.pack(side="right")
        self._log = ctk.CTkScrollableFrame(self, fg_color=CARD_BG, corner_radius=4)
        self._log.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._count = 0

    def add_task(self, label: str, status: str = "running"):
        color = {"done": ACCENT_GRN, "error": ACCENT_RED,
                 "running": ACCENT_ORG}.get(status, TEXT_DIM)
        ts = datetime.now().strftime("%H:%M:%S")
        row = ctk.CTkFrame(self._log, fg_color=CARD_BG, corner_radius=4)
        row.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(row, text=f"[{ts}]", font=("Cascadia Code", 10),
                     text_color=TEXT_DIM, width=62).pack(side="left", padx=4)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 11),
                     text_color=TEXT, anchor="w").pack(side="left", fill="x",
                                                       expand=True, padx=4)
        ctk.CTkLabel(row, text=status, font=("Segoe UI", 10, "bold"),
                     text_color=color).pack(side="right", padx=6)
        self._count += 1
        self._count_lbl.configure(text=f"Finished {self._count} ›")
        self._log._parent_canvas.yview_moveto(1.0)


class RightSidebar(ctk.CTkFrame):
    """
    Passive container for the right column.
    Owns the toggle-button bar and the panel-container frame.
    All state logic lives in HeramaApp; buttons call app.toggle_panel(name).
    """

    PANEL_NAMES = ("Plan", "Files", "Tasks")

    def __init__(self, master, on_toggle: Callable[[str], None], **kw):
        super().__init__(master, width=350, fg_color=SIDEBAR_BG,
                         corner_radius=0, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)

        self._btns: dict[str, ctk.CTkButton] = {}
        self._on_toggle = on_toggle

        # Row 0 = button bar (fixed); row 1 = panel container (expands)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── toggle button bar ──
        bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 4))

        for name in self.PANEL_NAMES:
            btn = ctk.CTkButton(
                bar, text=name, font=("Segoe UI", 11),
                fg_color=CARD_BG, hover_color=BORDER,
                text_color=TEXT_DIM, corner_radius=6,
                height=26, width=80,
                command=lambda n=name: self._on_toggle(n),
            )
            btn.pack(side="left", padx=3)
            self._btns[name] = btn

        # ── panel container — HeramaApp grids panels here ──
        self.container = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0)
        self.container.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.container.grid_columnconfigure(0, weight=1)

    def update_buttons(self, active_panels: dict[str, bool]):
        """Sync button highlight to the current active_panels state."""
        for name, btn in self._btns.items():
            btn.configure(
                fg_color=ACCENT if active_panels.get(name) else CARD_BG,
                text_color=TEXT if active_panels.get(name) else TEXT_DIM,
            )


# ===========================================================================
# Main application
# ===========================================================================
class HeramaApp(ctk.CTk):
    """
    Central application class.

    Panel state is owned here:
        self.active_panels = {"Plan": True, "Files": False, "Tasks": False}

    All layout mutations go through one master method:
        self.refresh_right_sidebar()
    """

    _PANEL_ORDER = ("Plan", "Files", "Tasks")

    def __init__(self):
        super().__init__()
        self.title("Herama  —  Local LLM Workspace")
        self.geometry("1440x880")
        self.minsize(1100, 600)
        self.configure(fg_color=BG)

        self._history: list[dict] = []

        # ── master panel state ──
        self.active_panels: dict[str, bool] = {
            "Plan":  True,
            "Files": False,
            "Tasks": False,
        }

        self._build_layout()
        self.after(POLL_MS, self._tick)

    # ------------------------------------------------------------------
    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # left sidebar — fixed
        self.grid_columnconfigure(1, weight=1)   # center        — fluid
        self.grid_columnconfigure(2, weight=0)   # right sidebar — fixed

        self._left = LeftSidebar(self, on_section=self._on_nav)
        self._left.grid(row=0, column=0, sticky="nsew")

        self._center = CenterPanel(self, on_send=self._on_send)
        self._center.grid(row=0, column=1, sticky="nsew")

        # right sidebar: pass the toggle callback
        self._right = RightSidebar(self, on_toggle=self.toggle_panel)
        self._right.grid(row=0, column=2, sticky="nsew")

        # build the three panel widgets inside the container (not placed yet)
        self._panels: dict[str, ctk.CTkFrame] = {
            "Plan":  PlanPanel(self._right.container),
            "Files": FilesPanel(self._right.container),
            "Tasks": BgTasksPanel(self._right.container),
        }

        # perform initial layout
        self.refresh_right_sidebar()

        # seed the task log
        self._panels["Tasks"].add_task("Herama workspace started", "done")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    def toggle_panel(self, name: str) -> None:
        """
        Flip the boolean for *name* in active_panels, then refresh.
        Ensures at least one panel is always visible.
        """
        self.active_panels[name] = not self.active_panels[name]

        # guard: if all panels are now False, re-enable the one just toggled off
        if not any(self.active_panels.values()):
            self.active_panels[name] = True

        self.refresh_right_sidebar()

    # ------------------------------------------------------------------
    def refresh_right_sidebar(self) -> None:
        """
        Master layout refresh for the right sidebar.

        Algorithm
        ---------
        1. grid_forget() every panel — clears the container completely.
        2. Reset every row weight on the container to 0.
        3. Collect the ordered list of active panel names.
        4. For each active panel: configure its container row with weight=1
           and grid() it into that row with sticky="nsew".
           → 1 panel active  → occupies 100 % of the height (weight=1/1)
           → 2 panels active → each 50 %                    (weight=1/2)
           → 3 panels active → each 33 %                    (weight=1/3)
        5. Sync toggle-button highlights to active_panels state.
        """
        container = self._right.container

        # step 1 — remove all panels from the grid
        for panel in self._panels.values():
            panel.grid_forget()

        # step 2 — zero out all row weights
        for i in range(len(self._PANEL_ORDER)):
            container.grid_rowconfigure(i, weight=0)

        # step 3 — ordered list of currently active names
        active_names = [n for n in self._PANEL_ORDER if self.active_panels.get(n)]

        # step 4 — re-grid each active panel with equal weight
        for row_idx, name in enumerate(active_names):
            container.grid_rowconfigure(row_idx, weight=1)
            self._panels[name].grid(
                row=row_idx, column=0, sticky="nsew", padx=0, pady=(0, 2)
            )

        # step 5 — sync button highlights
        self._right.update_buttons(self.active_panels)

    def _on_nav(self, section: str):
        if section.startswith("open_dir:"):
            path = Path(section.split(":", 1)[1])
            self._panels["Files"].load_directory(path)
            self._panels["Tasks"].add_task(f"Opened repo: {path.name}", "done")
        elif section == "new":
            self._center.add_message("assistant", "New session ready.")
        else:
            self._panels["Tasks"].add_task(f"Navigation: {section}", "done")

    def _tick(self):
        self._left.refresh()
        if state.active_model:
            self._center.update_model(state.active_model)
        self.after(POLL_MS, self._tick)

    def _on_send(self, text: str):
        self._history.append({"role": "user", "content": text})

        # ── GitHub URL shortcut: clone instead of chat ──
        if text.strip().startswith("https://github.com/"):
            self._clone_repo(text.strip())
            return

        short = (text[:40] + "…") if len(text) > 40 else text
        self._panels["Tasks"].add_task(f"Chat → {short}", "running")

        if not state.connected:
            self._center.add_message("assistant",
                                     "⚠ Backend offline. Run `python launcher.py` or `python -m app.main` first.")
            return
        if not state.local_models:
            self._center.add_message("assistant",
                                     "⚠ No models loaded. Paste a GitHub URL to clone a repo, or download a GGUF model.")
            return

        model = state.active_model or state.local_models[0]
        stream_lbl = self._center.start_stream()

        threading.Thread(target=self._stream_generate,
                         args=(model, text, stream_lbl), daemon=True).start()

    def _clone_repo(self, url: str):
        """Handle a GitHub URL pasted into the chat input."""
        from app.git_manager import clone_repo_async, CloneProgress

        workspace = Path.home() / "herama_workspace"
        self._center.add_message("user", url)
        self._center.add_message("assistant", f"Cloning {url} …")
        self._panels["Tasks"].add_task(f"Clone: {url}", "running")

        stream_lbl = self._center.start_stream()

        def _progress(p: CloneProgress):
            msg = f"Phase: {p.phase}  {p.pct:.0f}%" if not p.done else "Clone complete ✓"
            self.after(0, lambda m=msg: stream_lbl.configure(text=m))

        def _done(path, err):
            if err:
                self.after(0, lambda e=err: stream_lbl.configure(
                    text=f"Clone failed: {e[:120]}", text_color=ACCENT_RED))
                self.after(0, lambda e=err: self._panels["Tasks"].add_task(
                    f"Clone error: {e[:60]}", "error"))
            else:
                self.after(0, lambda p=path: stream_lbl.configure(
                    text=f"Cloned → {p}\n\nFiles loaded in the Files Explorer panel."))
                self.after(0, lambda p=path: self._panels["Files"].load_directory(p))
                self.after(0, lambda p=path: self._panels["Tasks"].add_task(
                    f"Cloned: {p.name}", "done"))

        clone_repo_async(url, workspace, _progress, _done)

    def _stream_generate(self, model: str, prompt: str, lbl: ctk.CTkLabel):
        buf = ""
        try:
            with requests.post(f"{API_BASE}/api/generate",
                               json={"model": model, "prompt": prompt, "stream": True},
                               stream=True, timeout=180) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    buf += chunk.get("response", "")
                    captured = buf
                    self.after(0, lambda t=captured: lbl.configure(text=t))
                    if chunk.get("done"):
                        break
            self._history.append({"role": "assistant", "content": buf})
            short = (buf[:40] + "…") if len(buf) > 40 else buf
            self.after(0, lambda s=short: self._panels["Tasks"].add_task(f"Chat ← {s}", "done"))
        except Exception as exc:
            self.after(0, lambda e=str(exc): lbl.configure(text=f"Error: {e}",
                                                            text_color=ACCENT_RED))
            self.after(0, lambda e=str(exc): self._panels["Tasks"].add_task(
                f"Chat error: {e[:50]}", "error"))


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    app = HeramaApp()
    threading.Thread(target=_poll, args=(app,), daemon=True).start()
    app.mainloop()


if __name__ == "__main__":
    main()
