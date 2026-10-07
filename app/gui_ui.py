"""Herama Desktop GUI — Claude Code-inspired terminal workspace (customtkinter)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Auto-install & silent upgrade on launch
# ---------------------------------------------------------------------------
from app.dependency_manager import ensure_packages, upgrade_packages_async

_GUI_DEPS = ["customtkinter", "requests", "psutil"]
ensure_packages(_GUI_DEPS)
upgrade_packages_async()

import customtkinter as ctk
import requests
import psutil

# ---------------------------------------------------------------------------
# Claude Code palette — terminal aesthetic
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG          = "#0a0a0a"   # near-black canvas
SURFACE     = "#111111"   # slightly lifted surface
SURFACE2    = "#1a1a1a"   # card / panel bg
BORDER      = "#2a2a2a"   # subtle dividers
BORDER2     = "#333333"   # stronger borders
TEXT        = "#e5e5e5"   # primary text
TEXT_DIM    = "#666666"   # muted / metadata
TEXT_MID    = "#999999"   # secondary text
ACCENT      = "#f97316"   # orange — Claude orange
ACCENT_DIM  = "#7c3a10"   # muted orange
GREEN       = "#22c55e"
RED         = "#ef4444"
BLUE        = "#3b82f6"
PURPLE      = "#a855f7"
YELLOW      = "#eab308"

MONO        = "Cascadia Code"   # monospace font used everywhere
MONO_SZ     = 12
SANS        = "Segoe UI"
SANS_SZ     = 12

API_BASE    = "http://127.0.0.1:11434"
POLL_MS     = 2000


# ---------------------------------------------------------------------------
# Shared live state
# ---------------------------------------------------------------------------
class _State:
    connected    : bool       = False
    active_model : str        = ""
    local_models : list[str]  = []
    skills       : dict       = {}
    tps          : float      = 0.0
    token_count  : int        = 0
    agents       : list[dict] = []
    gguf_models  : list[str]  = []
    sessions     : list[str]  = ["herama (current)"]

state = _State()


# ---------------------------------------------------------------------------
# GGUF model discovery
# ---------------------------------------------------------------------------
def _find_local_gguf() -> list[str]:
    search_roots = [
        Path.home() / "herama_workspace",
        Path.home() / ".cache" / "huggingface",
        Path.home() / "ollama" / "models",
        Path("/opt/models"),
    ]
    found: list[str] = []
    seen: set[str] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("*.gguf"):
            if p.name not in seen:
                seen.add(p.name)
                found.append(p.name)
    return found


# ---------------------------------------------------------------------------
# Background poll loop
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
            r = requests.get(f"{API_BASE}/api/agents", timeout=2)
            state.agents = r.json().get("agents", [])
        except Exception:
            pass

        gguf = _find_local_gguf()
        state.gguf_models = list(dict.fromkeys(state.local_models + gguf))

        try:
            app_ref.after(0, app_ref._tick)
        except Exception:
            pass

        time.sleep(POLL_MS / 1000)


# ===========================================================================
# MODAL WINDOWS
# ===========================================================================

class _BaseModal(ctk.CTkToplevel):
    """Shared base for all modal dialogs."""
    def __init__(self, master, title: str, w: int, h: int):
        super().__init__(master)
        self.title(title)
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.grab_set()

    def _field(self, parent, label: str):
        ctk.CTkLabel(parent, text=label, font=(MONO, 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=20, pady=(10, 2))

    def _divider(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=BORDER,
                     corner_radius=0).pack(fill="x", padx=20, pady=6)

    def _btn_row(self, parent, cancel_cmd, save_text, save_cmd):
        row = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=0)
        row.pack(fill="x", padx=20, pady=(4, 18))
        ctk.CTkButton(row, text="cancel", width=80, height=30,
                      font=(MONO, 11), fg_color=SURFACE2, hover_color=BORDER2,
                      text_color=TEXT_DIM, corner_radius=4,
                      command=cancel_cmd).pack(side="right", padx=(6, 0))
        ctk.CTkButton(row, text=save_text, width=110, height=30,
                      font=(MONO, 11, "bold"), fg_color=ACCENT,
                      hover_color=ACCENT_DIM, text_color="white", corner_radius=4,
                      command=save_cmd).pack(side="right")


class AgentModal(_BaseModal):
    """Create or edit an agent."""

    def __init__(self, master, on_save: Callable[[dict], None],
                 agent: dict | None = None):
        super().__init__(master, "edit agent" if agent else "new agent", 500, 460)
        self._on_save = on_save
        self._agent = agent
        self._build()
        if agent:
            self._name.insert(0, agent.get("name", ""))
            self._prompt.insert("end", agent.get("system_prompt", ""))
            m = agent.get("model", "")
            if m:
                self._model_combo.set(m)

    def _build(self):
        # header
        hdr = ctk.CTkFrame(self, fg_color=SURFACE2, corner_radius=0, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        title = "Edit Agent" if self._agent else "New Agent"
        ctk.CTkLabel(hdr, text=title, font=(MONO, 12, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=16, pady=8)

        self._field(self, "agent name")
        self._name = ctk.CTkEntry(
            self, placeholder_text="e.g. code-reviewer",
            font=(MONO, MONO_SZ), fg_color=BG, text_color=TEXT,
            border_color=BORDER2, height=32, corner_radius=4,
        )
        self._name.pack(fill="x", padx=20, pady=(0, 4))

        self._field(self, "system prompt")
        self._prompt = ctk.CTkTextbox(
            self, height=120, font=(MONO, MONO_SZ),
            fg_color=BG, text_color=TEXT,
            border_color=BORDER2, border_width=1, corner_radius=4,
        )
        self._prompt.pack(fill="x", padx=20, pady=(0, 4))

        self._field(self, "model")
        vals = state.gguf_models or state.local_models or ["no models"]
        self._model_combo = ctk.CTkComboBox(
            self, values=vals, font=(MONO, MONO_SZ),
            fg_color=BG, text_color=TEXT,
            button_color=ACCENT, border_color=BORDER2,
            height=32, corner_radius=4,
        )
        self._model_combo.pack(fill="x", padx=20, pady=(0, 6))
        self._divider(self)
        self._btn_row(self, self.destroy, "save agent", self._submit)

    def _submit(self):
        name = self._name.get().strip()
        if not name:
            return
        payload: dict = {
            "name": name,
            "system_prompt": self._prompt.get("1.0", "end").strip(),
            "model": self._model_combo.get(),
        }
        if self._agent and "id" in self._agent:
            payload["id"] = self._agent["id"]
        self._on_save(payload)
        self.destroy()


class ModelSettingsModal(_BaseModal):
    """Context length and speed info for the active model."""

    def __init__(self, master, model_name: str,
                 on_apply: Callable[[str, int], None]):
        super().__init__(master, "model settings", 460, 340)
        self._model = model_name
        self._on_apply = on_apply
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=SURFACE2, corner_radius=0, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"model settings", font=(MONO, 12, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=16, pady=8)
        ctk.CTkLabel(hdr, text=self._model or "none", font=(MONO, 11),
                     text_color=TEXT_DIM).pack(side="left", padx=6)

        self._field(self, "context length  (tokens)")
        self._ctx_lbl = ctk.CTkLabel(self, text="4,096",
                                     font=(MONO, 14, "bold"), text_color=ACCENT,
                                     anchor="w")
        self._ctx_lbl.pack(fill="x", padx=20, pady=(0, 2))

        self._slider = ctk.CTkSlider(
            self, from_=512, to=262144, number_of_steps=511,
            progress_color=ACCENT, button_color=ACCENT,
            command=self._on_slide,
        )
        self._slider.set(4096)
        self._slider.pack(fill="x", padx=20, pady=(0, 10))

        self._divider(self)

        self._field(self, "last measured speed")
        tps_text = (f"{state.tps:.1f} tok/s" if state.tps > 0
                    else "—  run a query first")
        ctk.CTkLabel(self, text=tps_text, font=(MONO, 13),
                     text_color=GREEN, anchor="w").pack(fill="x", padx=20, pady=(0, 6))

        self._divider(self)
        self._btn_row(self, self.destroy, "apply", self._apply)

    def _on_slide(self, val: float):
        self._ctx_lbl.configure(text=f"{int(val):,}")

    def _apply(self):
        self._on_apply(self._model, int(self._slider.get()))
        self.destroy()


# ===========================================================================
# LEFT SIDEBAR — sessions + bots navigator
# ===========================================================================
class LeftSidebar(ctk.CTkFrame):

    def __init__(self, master,
                 on_section: Callable[[str], None],
                 on_agent_action: Callable[[str, dict | None], None], **kw):
        super().__init__(master, width=240, fg_color=SURFACE, corner_radius=0, **kw)
        self.on_section = on_section
        self.on_agent_action = on_agent_action
        self._build()

    def _build(self):
        self.pack_propagate(False)
        self.grid_propagate(False)

        # ── logo row ──
        logo = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=48)
        logo.pack(fill="x")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="◈  herama", font=(MONO, 13, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=14, pady=12)

        self._div()

        # ── tab bar ──
        tab_row = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        tab_row.pack(fill="x", padx=8, pady=(4, 0))

        self._tab_s = ctk.CTkButton(
            tab_row, text="sessions", font=(MONO, 10),
            fg_color=SURFACE2, hover_color=BORDER2,
            text_color=TEXT, corner_radius=4, height=26,
            command=lambda: self._activate_tab("SESSIONS"),
        )
        self._tab_s.pack(side="left", padx=(0, 3), pady=2, fill="x", expand=True)

        self._tab_b = ctk.CTkButton(
            tab_row, text="agents", font=(MONO, 10),
            fg_color=SURFACE, hover_color=BORDER2,
            text_color=TEXT_DIM, corner_radius=4, height=26,
            command=lambda: self._activate_tab("BOTS"),
        )
        self._tab_b.pack(side="left", padx=(3, 0), pady=2, fill="x", expand=True)

        # ── swappable content ──
        self._tab_area = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self._tab_area.pack(fill="x")
        self._build_sessions_view()

        self._div()

        # ── github clone ──
        ctk.CTkLabel(self, text="git clone", font=(MONO, 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=14, pady=(4, 2))
        self._clone_entry = ctk.CTkEntry(
            self, placeholder_text="https://github.com/...",
            font=(MONO, 10), fg_color=BG, text_color=TEXT,
            border_color=BORDER2, height=28, corner_radius=4,
        )
        self._clone_entry.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkButton(
            self, text="clone repo", font=(MONO, 10),
            fg_color=SURFACE2, hover_color=BORDER2, text_color=TEXT_DIM,
            height=26, corner_radius=4,
            command=self._do_clone,
        ).pack(fill="x", padx=8, pady=(0, 2))
        self._clone_status = ctk.CTkLabel(
            self, text="", font=(MONO, 9),
            text_color=TEXT_DIM, anchor="w", wraplength=210,
        )
        self._clone_status.pack(fill="x", padx=14)

        self._div()

        # ── local models ──
        ctk.CTkLabel(self, text="local models", font=(MONO, 10),
                     text_color=TEXT_DIM, anchor="w").pack(fill="x", padx=14, pady=(4, 2))
        self._models_frame = ctk.CTkScrollableFrame(
            self, fg_color=SURFACE, height=70, corner_radius=0,
        )
        self._models_frame.pack(fill="x", padx=4)

    # ------------------------------------------------------------------
    def _div(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                     corner_radius=0).pack(fill="x", pady=4)

    def _clear_tab_area(self):
        for w in self._tab_area.winfo_children():
            w.destroy()

    def _build_sessions_view(self):
        self._clear_tab_area()
        ctk.CTkButton(
            self._tab_area, text="+ new session", font=(MONO, 10),
            fg_color=SURFACE, hover_color=SURFACE2,
            text_color=TEXT_DIM, height=26, corner_radius=4,
            command=lambda: self.on_section("new"),
        ).pack(fill="x", padx=8, pady=(6, 2))

        self._sessions_scroll = ctk.CTkScrollableFrame(
            self._tab_area, fg_color=SURFACE, height=130, corner_radius=0,
        )
        self._sessions_scroll.pack(fill="x", padx=4, pady=(0, 4))
        self._render_sessions()

    def _render_sessions(self):
        if not hasattr(self, "_sessions_scroll"):
            return
        for w in self._sessions_scroll.winfo_children():
            w.destroy()
        for s in state.sessions:
            btn = ctk.CTkButton(
                self._sessions_scroll, text=s, anchor="w",
                font=(MONO, 10), fg_color=SURFACE, hover_color=SURFACE2,
                text_color=TEXT_MID, height=24, corner_radius=4,
                command=lambda ss=s: self.on_section(f"session:{ss}"),
            )
            btn.pack(fill="x", padx=2, pady=1)

    def _build_bots_view(self):
        self._clear_tab_area()
        ctk.CTkButton(
            self._tab_area, text="+ new agent", font=(MONO, 10),
            fg_color=ACCENT, hover_color=ACCENT_DIM, text_color="white",
            height=26, corner_radius=4,
            command=lambda: self.on_agent_action("create", None),
        ).pack(fill="x", padx=8, pady=(6, 4))
        self._agents_scroll = ctk.CTkScrollableFrame(
            self._tab_area, fg_color=SURFACE, height=150, corner_radius=0,
        )
        self._agents_scroll.pack(fill="x", padx=4, pady=(0, 4))
        self._render_agents(state.agents)
        threading.Thread(target=self._fetch_agents_async, daemon=True).start()

    def _fetch_agents_async(self):
        try:
            r = requests.get(f"{API_BASE}/api/agents", timeout=4)
            agents = r.json().get("agents", [])
            state.agents = agents
            try:
                self.after(0, lambda: self._render_agents(agents))
            except Exception:
                pass
        except Exception:
            pass

    def _render_agents(self, agents: list[dict]):
        if not hasattr(self, "_agents_scroll"):
            return
        for w in self._agents_scroll.winfo_children():
            w.destroy()
        if not agents:
            ctk.CTkLabel(self._agents_scroll, text="no agents yet",
                         font=(MONO, 10), text_color=TEXT_DIM).pack(pady=10)
            return
        for agent in agents:
            row = ctk.CTkFrame(self._agents_scroll, fg_color=SURFACE2, corner_radius=4)
            row.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(row, text=f"◆  {agent.get('name','?')}",
                         font=(MONO, 10), text_color=TEXT_MID,
                         anchor="w").pack(side="left", fill="x", expand=True,
                                          padx=8, pady=6)
            ctk.CTkButton(row, text="⚙", width=26, height=22,
                          font=(MONO, 11), fg_color=SURFACE,
                          hover_color=BORDER2, text_color=TEXT_DIM, corner_radius=3,
                          command=lambda a=agent: self.on_agent_action("edit", a),
                          ).pack(side="right", padx=4)

    def _activate_tab(self, name: str):
        is_s = name == "SESSIONS"
        self._tab_s.configure(fg_color=SURFACE2 if is_s else SURFACE,
                              text_color=TEXT if is_s else TEXT_DIM)
        self._tab_b.configure(fg_color=SURFACE2 if not is_s else SURFACE,
                              text_color=TEXT if not is_s else TEXT_DIM)
        if is_s:
            self._build_sessions_view()
        else:
            self._build_bots_view()

    def _do_clone(self):
        url = self._clone_entry.get().strip()
        if not url:
            return
        self._clone_status.configure(text="cloning…", text_color=YELLOW)
        workspace = Path.home() / "herama_workspace"
        from app.git_manager import clone_repo_async, CloneProgress

        def _prog(p: CloneProgress):
            msg = f"{p.phase} {p.pct:.0f}%" if not p.done else "done ✓"
            c = GREEN if p.done else (RED if p.error else YELLOW)
            try:
                self.after(0, lambda m=msg, col=c: self._clone_status.configure(
                    text=m, text_color=col))
            except Exception:
                pass

        def _done(path, err):
            if err:
                self.after(0, lambda: self._clone_status.configure(
                    text=f"error: {err[:50]}", text_color=RED))
            else:
                self.after(0, lambda: self._clone_status.configure(
                    text=f"→ {path.name}", text_color=GREEN))
                self.on_section(f"open_dir:{path}")

        clone_repo_async(url, workspace, _prog, _done)

    def refresh(self, connected: bool, models: list[str]):
        for w in self._models_frame.winfo_children():
            w.destroy()
        for m in models:
            ctk.CTkLabel(self._models_frame, text=f"  {m}",
                         font=(MONO, 10), text_color=TEXT_DIM,
                         anchor="w").pack(fill="x", padx=4, pady=1)


# ===========================================================================
# MESSAGE BLOCKS — Claude Code style
# ===========================================================================

class UserBlock(ctk.CTkFrame):
    """User message — right-leaning, simple."""
    def __init__(self, master, text: str, **kw):
        super().__init__(master, fg_color=SURFACE2, corner_radius=6, **kw)
        meta = ctk.CTkFrame(self, fg_color=SURFACE2, corner_radius=0)
        meta.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(meta, text="▶  you", font=(MONO, 10, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left")
        ctk.CTkLabel(meta, text=datetime.now().strftime("%H:%M"),
                     font=(MONO, 9), text_color=TEXT_DIM).pack(side="right")
        ctk.CTkLabel(self, text=text, font=(SANS, SANS_SZ),
                     text_color=TEXT, wraplength=580,
                     justify="left", anchor="w").pack(
            fill="x", padx=12, pady=(0, 10))


class AssistantBlock(ctk.CTkFrame):
    """Herama / assistant message — matches Claude Code assistant style."""
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=BG, corner_radius=0, **kw)
        meta = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        meta.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(meta, text="◈  herama", font=(MONO, 10, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left")
        self._ts = ctk.CTkLabel(meta, text=datetime.now().strftime("%H:%M"),
                                font=(MONO, 9), text_color=TEXT_DIM)
        self._ts.pack(side="right")
        self._body = ctk.CTkLabel(
            self, text="▋", font=(SANS, SANS_SZ),
            text_color=TEXT, wraplength=580, justify="left", anchor="w",
        )
        self._body.pack(fill="x", padx=12, pady=(0, 10))

    def set_text(self, txt: str):
        self._body.configure(text=txt or "▋")

    def finalize(self):
        self._body.configure(text=self._body.cget("text").rstrip("▋"))


class ToolBlock(ctk.CTkFrame):
    """Tool / task output block — Claude Code-style bordered box."""
    def __init__(self, master, label: str, status: str = "running", **kw):
        color = {"done": GREEN, "error": RED}.get(status, YELLOW)
        super().__init__(master, fg_color=SURFACE2,
                         border_color=color, border_width=1,
                         corner_radius=6, **kw)
        row = ctk.CTkFrame(self, fg_color=SURFACE2, corner_radius=0)
        row.pack(fill="x", padx=10, pady=(6, 6))
        dot = {"done": "●", "error": "✕", "running": "○"}.get(status, "○")
        ctk.CTkLabel(row, text=f"{dot}  {label}", font=(MONO, 10),
                     text_color=color, anchor="w").pack(side="left", fill="x", expand=True)
        ts = datetime.now().strftime("%H:%M:%S")
        ctk.CTkLabel(row, text=ts, font=(MONO, 9),
                     text_color=TEXT_DIM).pack(side="right")


# ===========================================================================
# CENTER PANEL
# ===========================================================================
class CenterPanel(ctk.CTkFrame):

    def __init__(self, master,
                 on_send: Callable[[str], None],
                 on_model_settings: Callable[[str], None], **kw):
        super().__init__(master, fg_color=BG, corner_radius=0, **kw)
        self.on_send = on_send
        self.on_model_settings = on_model_settings
        self._build()

    def _build(self):
        # ── top bar ──
        topbar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=40)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        ctk.CTkLabel(topbar, text="herama workspace", font=(MONO, 11, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left", padx=16)
        self._conn_dot = ctk.CTkLabel(topbar, text="● offline",
                                      font=(MONO, 10), text_color=RED)
        self._conn_dot.pack(side="right", padx=16)
        self._tps_lbl = ctk.CTkLabel(topbar, text="",
                                     font=(MONO, 10), text_color=TEXT_DIM)
        self._tps_lbl.pack(side="right", padx=8)

        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                     corner_radius=0).pack(fill="x")

        # ── scrollable conversation ──
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=BG, corner_radius=0,
            scrollbar_button_color=BORDER2,
        )
        self._scroll.pack(fill="both", expand=True)

        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                     corner_radius=0).pack(fill="x")

        # ── bottom input section ──
        bottom = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        bottom.pack(fill="x")

        # model selector bar
        mbar = ctk.CTkFrame(bottom, fg_color=SURFACE, corner_radius=0)
        mbar.pack(fill="x", padx=14, pady=(8, 0))

        ctk.CTkLabel(mbar, text="model:", font=(MONO, 10),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, 6))
        self._model_combo = ctk.CTkComboBox(
            mbar, values=["scanning…"],
            font=(MONO, 10), fg_color=BG, text_color=TEXT,
            button_color=ACCENT, border_color=BORDER2,
            height=26, width=220, corner_radius=4,
            command=self._on_model_selected,
        )
        self._model_combo.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            mbar, text="⚙  settings", width=90, height=26,
            font=(MONO, 10), fg_color=BG,
            hover_color=SURFACE2, text_color=TEXT_DIM, corner_radius=4,
            command=self._open_model_settings,
        ).pack(side="left")
        self._tok_lbl = ctk.CTkLabel(mbar, text="0 tokens",
                                     font=(MONO, 9), text_color=TEXT_DIM)
        self._tok_lbl.pack(side="right")

        # prompt row
        prow = ctk.CTkFrame(bottom, fg_color=SURFACE, corner_radius=0)
        prow.pack(fill="x", padx=14, pady=(6, 12))

        self._input = ctk.CTkTextbox(
            prow, height=52, font=(MONO, MONO_SZ),
            fg_color=BG, text_color=TEXT,
            border_color=BORDER2, border_width=1, corner_radius=4,
            scrollbar_button_color=BORDER2,
        )
        self._input.pack(fill="x", side="left", expand=True)
        self._input.bind("<Return>", self._on_return)

        ctk.CTkButton(
            prow, text="send", width=64, height=52,
            font=(MONO, 11, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_DIM, text_color="white",
            corner_radius=4, command=self._send,
        ).pack(side="right", padx=(6, 0))

    # ------------------------------------------------------------------
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
        self.add_user_message(text)
        self.on_send(text)

    def _on_model_selected(self, choice: str):
        state.active_model = choice

    def _open_model_settings(self):
        self.on_model_settings(self._model_combo.get())

    def add_user_message(self, text: str):
        UserBlock(self._scroll, text).pack(fill="x", padx=16, pady=(6, 2))
        self._scroll._parent_canvas.yview_moveto(1.0)

    def start_assistant_block(self) -> "AssistantBlock":
        blk = AssistantBlock(self._scroll)
        blk.pack(fill="x", padx=0, pady=(2, 2))
        self._scroll._parent_canvas.yview_moveto(1.0)
        return blk

    def add_tool_block(self, label: str, status: str = "running"):
        ToolBlock(self._scroll, label, status).pack(
            fill="x", padx=16, pady=(2, 2))
        self._scroll._parent_canvas.yview_moveto(1.0)

    def update_models(self, models: list[str]):
        if not models:
            return
        current = self._model_combo.get()
        self._model_combo.configure(values=models)
        if current not in models:
            self._model_combo.set(models[0])
            state.active_model = models[0]

    def get_selected_model(self) -> str:
        return self._model_combo.get()

    def update_status(self, connected: bool, tps: float, tokens: int):
        self._conn_dot.configure(
            text="● online" if connected else "● offline",
            text_color=GREEN if connected else RED,
        )
        if tps > 0:
            self._tps_lbl.configure(text=f"{tps:.1f} tok/s")
        self._tok_lbl.configure(text=f"{tokens:,} tokens")


# ===========================================================================
# RIGHT SIDEBAR — Plan / Files / Tasks
# ===========================================================================

class PlanPanel(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=SURFACE, corner_radius=0, **kw)
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="plan", font=(MONO, 10, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=12, pady=6)
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")
        self._text = ctk.CTkTextbox(
            self, font=(MONO, 10),
            fg_color=BG, text_color=TEXT_MID,
            border_width=0, corner_radius=0,
            scrollbar_button_color=BORDER2,
        )
        self._text.pack(fill="both", expand=True)
        self._text.insert("end", "# no active plan\n\nstart a conversation to\ngenerate a task plan.")
        self._text.configure(state="disabled")

    def set_plan(self, text: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("end", text or "# no active plan")
        self._text.configure(state="disabled")


class FilesPanel(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=SURFACE, corner_radius=0, **kw)
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="files", font=(MONO, 10, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=12, pady=6)
        ctk.CTkButton(hdr, text="open", width=44, height=22,
                      font=(MONO, 9), fg_color=SURFACE2,
                      hover_color=BORDER2, text_color=TEXT_DIM, corner_radius=3,
                      command=self._pick_folder).pack(side="right", padx=6)
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")
        self._path_lbl = ctk.CTkLabel(self, text="no folder open",
                                      font=(MONO, 9), text_color=TEXT_DIM,
                                      anchor="w", wraplength=300)
        self._path_lbl.pack(fill="x", padx=10, pady=(4, 2))
        self._tree = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0,
                                             scrollbar_button_color=BORDER2)
        self._tree.pack(fill="both", expand=True)
        ctk.CTkLabel(self._tree, text="open a folder or clone a repo",
                     font=(MONO, 10), text_color=TEXT_DIM).pack(pady=20)

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
            for w in self._tree.winfo_children():
                w.destroy()
            self._path_lbl.configure(text=str(path))
            parent_frame = self._tree
        if not path.exists() or not path.is_dir():
            return
        try:
            items = sorted(path.iterdir(),
                           key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        indent = "  " * depth
        for item in items:
            if item.name.startswith(".") and depth > 0:
                continue
            icon = "▸ " if item.is_dir() else "  "
            ctk.CTkLabel(parent_frame,
                         text=f"{indent}{icon}{item.name}",
                         font=(MONO, 10), text_color=TEXT_DIM,
                         anchor="w", cursor="hand2").pack(
                fill="x", padx=4, pady=1)
            if item.is_dir() and depth < 2:
                self.load_directory(item, depth + 1, parent_frame)


class BgTasksPanel(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color=SURFACE, corner_radius=0, **kw)
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="tasks", font=(MONO, 10, "bold"),
                     text_color=ACCENT, anchor="w").pack(side="left", padx=12, pady=6)
        self._cnt = ctk.CTkLabel(hdr, text="", font=(MONO, 9), text_color=TEXT_DIM)
        self._cnt.pack(side="right", padx=8)
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")
        self._log = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0,
                                            scrollbar_button_color=BORDER2)
        self._log.pack(fill="both", expand=True)
        self._n = 0
        self._seen_ids: set = set()

    def add_task(self, label: str, status: str = "running"):
        color = {"done": GREEN, "error": RED, "running": YELLOW}.get(status, TEXT_DIM)
        dot   = {"done": "●", "error": "✕", "running": "○"}.get(status, "○")
        ts = datetime.now().strftime("%H:%M:%S")
        row = ctk.CTkFrame(self._log, fg_color=BG, corner_radius=0)
        row.pack(fill="x", padx=4, pady=1)
        ctk.CTkLabel(row, text=ts, font=(MONO, 9),
                     text_color=TEXT_DIM, width=58).pack(side="left")
        ctk.CTkLabel(row, text=f"{dot}", font=(MONO, 10),
                     text_color=color, width=14).pack(side="left")
        ctk.CTkLabel(row, text=label, font=(MONO, 10),
                     text_color=TEXT_MID, anchor="w").pack(
            side="left", fill="x", expand=True, padx=4)
        self._n += 1
        self._cnt.configure(text=f"{self._n}")
        self._log._parent_canvas.yview_moveto(1.0)

    def ingest_event(self, event: dict):
        eid = event.get("id")
        if eid and eid in self._seen_ids:
            return
        if eid:
            self._seen_ids.add(eid)
        self.add_task(event.get("label", "event"), event.get("status", "running"))


class RightSidebar(ctk.CTkFrame):
    PANEL_NAMES = ("Plan", "Files", "Tasks")

    def __init__(self, master, on_toggle: Callable[[str], None], **kw):
        super().__init__(master, width=320, fg_color=SURFACE,
                         corner_radius=0, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._btns: dict[str, ctk.CTkButton] = {}
        self._on_toggle = on_toggle

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # button bar
        bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=40)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        ctk.CTkFrame(bar, width=1, fg_color=BORDER,
                     corner_radius=0).pack(side="left", fill="y")

        for name in self.PANEL_NAMES:
            btn = ctk.CTkButton(
                bar, text=name.lower(), font=(MONO, 10),
                fg_color=SURFACE, hover_color=SURFACE2,
                text_color=TEXT_DIM, corner_radius=0,
                height=40, width=80, border_spacing=0,
                command=lambda n=name: self._on_toggle(n),
            )
            btn.pack(side="left")
            ctk.CTkFrame(bar, width=1, fg_color=BORDER,
                         corner_radius=0).pack(side="left", fill="y")
            self._btns[name] = btn

        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                     corner_radius=0).grid(row=0, column=0, sticky="sew")

        self.container = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)

    def update_buttons(self, active_panels: dict[str, bool]):
        for name, btn in self._btns.items():
            btn.configure(
                fg_color=SURFACE2 if active_panels.get(name) else SURFACE,
                text_color=ACCENT if active_panels.get(name) else TEXT_DIM,
            )


# ===========================================================================
# Main application
# ===========================================================================
class HeramaApp(ctk.CTk):
    _PANEL_ORDER = ("Plan", "Files", "Tasks")

    def __init__(self):
        super().__init__()
        self.title("herama")
        self.geometry("1440x900")
        self.minsize(1100, 620)
        self.configure(fg_color=BG)

        self._history: list[dict] = []
        self._active_context_length: int = 4096

        self.active_panels: dict[str, bool] = {
            "Plan":  True,
            "Files": False,
            "Tasks": False,
        }

        self._build_layout()
        self.after(POLL_MS, self._tick)

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        self._left = LeftSidebar(
            self, on_section=self._on_nav,
            on_agent_action=self._on_agent_action,
        )
        self._left.grid(row=0, column=0, sticky="nsew")

        # vertical divider
        ctk.CTkFrame(self, width=1, fg_color=BORDER,
                     corner_radius=0).grid(row=0, column=0, sticky="nse")

        self._center = CenterPanel(
            self, on_send=self._on_send,
            on_model_settings=self._on_model_settings,
        )
        self._center.grid(row=0, column=1, sticky="nsew")

        self._right = RightSidebar(self, on_toggle=self.toggle_panel)
        self._right.grid(row=0, column=2, sticky="nsew")

        self._panels: dict[str, ctk.CTkFrame] = {
            "Plan":  PlanPanel(self._right.container),
            "Files": FilesPanel(self._right.container),
            "Tasks": BgTasksPanel(self._right.container),
        }

        self.refresh_right_sidebar()
        self._panels["Tasks"].add_task("herama workspace started", "done")

    # ------------------------------------------------------------------
    def toggle_panel(self, name: str) -> None:
        self.active_panels[name] = not self.active_panels[name]
        if not any(self.active_panels.values()):
            self.active_panels[name] = True
        self.refresh_right_sidebar()

    def refresh_right_sidebar(self) -> None:
        container = self._right.container
        for panel in self._panels.values():
            panel.grid_forget()
        for i in range(len(self._PANEL_ORDER)):
            container.grid_rowconfigure(i, weight=0)
        active = [n for n in self._PANEL_ORDER if self.active_panels.get(n)]
        for idx, name in enumerate(active):
            container.grid_rowconfigure(idx, weight=1)
            self._panels[name].grid(row=idx, column=0, sticky="nsew",
                                    padx=0, pady=0)
        self._right.update_buttons(self.active_panels)

    # ------------------------------------------------------------------
    def _on_nav(self, section: str):
        if section.startswith("open_dir:"):
            path = Path(section.split(":", 1)[1])
            self._panels["Files"].load_directory(path)
            self._panels["Tasks"].add_task(f"opened: {path.name}", "done")
        elif section == "new":
            self._center.add_tool_block("new session created", "done")
        else:
            self._panels["Tasks"].add_task(section, "done")

    def _on_agent_action(self, action: str, agent: dict | None):
        if action == "create":
            AgentModal(self, on_save=self._save_agent)
        elif action == "edit":
            AgentModal(self, on_save=self._save_agent, agent=agent)

    def _save_agent(self, payload: dict):
        def _worker():
            try:
                if "id" in payload:
                    requests.patch(f"{API_BASE}/api/agents/{payload['id']}",
                                   json=payload, timeout=8)
                    label = f"agent updated: {payload['name']}"
                else:
                    requests.post(f"{API_BASE}/api/agents",
                                  json=payload, timeout=8)
                    label = f"agent created: {payload['name']}"
                state.agents = []
                try:
                    self.after(0, lambda l=label: self._panels["Tasks"].add_task(
                        l, "done"))
                except Exception:
                    pass
            except Exception as exc:
                try:
                    self.after(0, lambda e=str(exc): self._panels["Tasks"].add_task(
                        f"agent error: {e[:50]}", "error"))
                except Exception:
                    pass
        threading.Thread(target=_worker, daemon=True).start()

    def _on_model_settings(self, model_name: str):
        ModelSettingsModal(self, model_name=model_name,
                           on_apply=self._apply_model_settings)

    def _apply_model_settings(self, model: str, ctx: int):
        self._active_context_length = ctx
        state.active_model = model
        self._panels["Tasks"].add_task(
            f"model: {model}  ctx: {ctx:,}", "done")

    # ------------------------------------------------------------------
    def _tick(self):
        models = state.gguf_models or state.local_models
        if models:
            self._center.update_models(models)
        self._center.update_status(state.connected, state.tps, state.token_count)
        self._left.refresh(state.connected, state.local_models)
        self.after(POLL_MS, self._tick)

    # ------------------------------------------------------------------
    def _on_send(self, text: str):
        self._history.append({"role": "user", "content": text})

        if text.strip().startswith("https://github.com/"):
            self._clone_repo(text.strip())
            return

        short = (text[:50] + "…") if len(text) > 50 else text
        self._panels["Tasks"].add_task(f"chat → {short}", "running")

        if not state.connected:
            blk = self._center.start_assistant_block()
            blk.set_text("⚠  backend offline — run `python launcher.py` first")
            return

        model = self._center.get_selected_model()
        if not model or model in ("scanning…", "no models"):
            blk = self._center.start_assistant_block()
            blk.set_text("⚠  no model selected — place a .gguf file in ~/herama_workspace")
            return

        blk = self._center.start_assistant_block()
        threading.Thread(target=self._stream_generate,
                         args=(model, text, blk), daemon=True).start()

    def _clone_repo(self, url: str):
        from app.git_manager import clone_repo_async, CloneProgress
        workspace = Path.home() / "herama_workspace"
        self._panels["Tasks"].add_task(f"clone: {url}", "running")
        blk = self._center.start_assistant_block()
        blk.set_text(f"cloning {url} …")

        def _prog(p: CloneProgress):
            msg = f"{p.phase}  {p.pct:.0f}%" if not p.done else "clone complete ✓"
            self.after(0, lambda m=msg: blk.set_text(m))

        def _done(path, err):
            if err:
                self.after(0, lambda e=err: blk.set_text(f"error: {e[:100]}"))
                self.after(0, lambda e=err: self._panels["Tasks"].add_task(
                    f"clone error: {e[:50]}", "error"))
            else:
                self.after(0, lambda p=path: blk.set_text(
                    f"cloned →  {p}\nfiles loaded in the files panel"))
                self.after(0, lambda p=path: self._panels["Files"].load_directory(p))
                self.after(0, lambda p=path: self._panels["Tasks"].add_task(
                    f"cloned: {p.name}", "done"))

        clone_repo_async(url, workspace, _prog, _done)

    def _stream_generate(self, model: str, prompt: str, blk: "AssistantBlock"):
        buf = ""
        t0 = time.monotonic()
        n = 0
        try:
            with requests.post(
                f"{API_BASE}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True,
                      "options": {"num_ctx": self._active_context_length}},
                stream=True, timeout=180,
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue
                    tok = chunk.get("response", "")
                    buf += tok
                    if tok:
                        n += 1
                    captured = buf
                    self.after(0, lambda t=captured: blk.set_text(t))
                    if chunk.get("done"):
                        break

            elapsed = time.monotonic() - t0
            if elapsed > 0 and n > 0:
                state.tps = n / elapsed
            state.token_count += n

            self._history.append({"role": "assistant", "content": buf})
            self.after(0, blk.finalize)
            short = (buf[:50] + "…") if len(buf) > 50 else buf
            self.after(0, lambda s=short: self._panels["Tasks"].add_task(
                f"chat ← {s}", "done"))
        except Exception as exc:
            self.after(0, lambda e=str(exc): blk.set_text(f"error: {e}"))
            self.after(0, lambda e=str(exc): self._panels["Tasks"].add_task(
                f"chat error: {e[:50]}", "error"))


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    app = HeramaApp()
    threading.Thread(target=_poll, args=(app,), daemon=True).start()
    app.mainloop()


if __name__ == "__main__":
    main()
