"""
Herama GUI — LM Studio-inspired desktop app.

Layout:
  ┌──────────────┬──────────────────────────┬──────────────┐
  │  LEFT        │  MIDDLE (tabs)           │  RIGHT       │
  │  Model Mgmt  │  Task Planner / Chat     │  HW Monitor  │
  │  HF Search   │                          │  Skills      │
  │  Ctx Slider  │                          │              │
  └──────────────┴──────────────────────────┴──────────────┘

Run:  python -m app.gui_ui
Requires:  customtkinter >= 5.2   (auto-installed via dependency_manager)
"""
from __future__ import annotations

# ── auto-install GUI dependency ───────────────────────────────────────────────
from app.dependency_manager import ensure_package
ensure_package("customtkinter")
ensure_package("requests")

# ── stdlib ────────────────────────────────────────────────────────────────────
import json
import threading
import time
from pathlib import Path
from typing import Any

# ── third-party ───────────────────────────────────────────────────────────────
import customtkinter as ctk
import requests

# ── project ───────────────────────────────────────────────────────────────────
from app import config

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:11434"
VRAM_TOTAL_GB = float(config.__dict__.get("VRAM_TOTAL_GB", 10.8))
RAM_TOTAL_GB = float(config.__dict__.get("RAM_TOTAL_GB", 31.2))
POLL_INTERVAL = 5  # seconds

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colour palette
C_BG        = "#1a1a2e"
C_PANEL     = "#16213e"
C_CARD      = "#0f3460"
C_ACCENT    = "#e94560"
C_TEXT      = "#e0e0e0"
C_DIM       = "#888888"
C_GREEN     = "#00b894"
C_YELLOW    = "#fdcb6e"
C_RED       = "#e17055"


# ─────────────────────────────────────────────────────────────────────────────
# Backend helpers  (run in background threads)
# ─────────────────────────────────────────────────────────────────────────────

def _get(path: str, timeout: int = 5) -> dict | list | None:
    try:
        r = requests.get(f"{BASE_URL}{path}", timeout=timeout)
        return r.json() if r.ok else None
    except Exception:
        return None


def _post(path: str, payload: dict, timeout: int = 60) -> dict | None:
    try:
        r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=timeout)
        return r.json() if r.ok else None
    except Exception:
        return None


def _stream_chat(model: str, messages: list[dict], on_token, on_done):
    """Stream /api/chat and call on_token(str) for each token, on_done() at end."""
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
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        on_token(tok)
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        on_token(f"\n[Error: {e}]")
    on_done()


# ─────────────────────────────────────────────────────────────────────────────
# Reusable components
# ─────────────────────────────────────────────────────────────────────────────

class SectionLabel(ctk.CTkLabel):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, text=text, font=("Segoe UI", 11, "bold"),
                         text_color=C_ACCENT, **kw)


class HWBar(ctk.CTkFrame):
    """Labelled progress bar for VRAM / RAM."""

    def __init__(self, parent, label: str, total_gb: float, color: str, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.total_gb = total_gb
        self.columnconfigure(0, weight=1)

        self._label_var = ctk.StringVar(value=f"{label}  0.0 / {total_gb:.1f} GB")
        ctk.CTkLabel(self, textvariable=self._label_var,
                     font=("Segoe UI", 10), text_color=C_DIM,
                     anchor="w").grid(row=0, column=0, sticky="w")

        self._bar = ctk.CTkProgressBar(self, height=10,
                                       progress_color=color,
                                       fg_color="#2a2a4a")
        self._bar.set(0)
        self._bar.grid(row=1, column=0, sticky="ew", pady=(2, 6))

    def update(self, used_gb: float):
        pct = min(1.0, used_gb / self.total_gb) if self.total_gb else 0
        total = self.total_gb
        self._bar.set(pct)
        self._label_var.set(
            f"{self._label_var.get().split('  ')[0]}  {used_gb:.1f} / {total:.1f} GB"
        )


# ─────────────────────────────────────────────────────────────────────────────
# LEFT SIDEBAR — Model Management
# ─────────────────────────────────────────────────────────────────────────────

class LeftSidebar(ctk.CTkFrame):
    def __init__(self, parent, app: "HeramaApp", **kw):
        super().__init__(parent, width=280, fg_color=C_PANEL,
                         corner_radius=0, **kw)
        self.app = app
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        # ── title ──
        ctk.CTkLabel(self, text="⚡  HERAMA", font=("Segoe UI", 16, "bold"),
                     text_color=C_ACCENT).grid(row=0, column=0, pady=(16, 4), padx=12, sticky="w")
        ctk.CTkLabel(self, text="Local LLM Engine", font=("Segoe UI", 10),
                     text_color=C_DIM).grid(row=1, column=0, padx=12, sticky="w")

        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=2, column=0, sticky="ew", padx=8, pady=8)

        # ── connection status ──
        self._status_var = ctk.StringVar(value="● Connecting…")
        ctk.CTkLabel(self, textvariable=self._status_var,
                     font=("Segoe UI", 10, "bold"),
                     text_color=C_YELLOW).grid(row=3, column=0, padx=12, sticky="w")

        # ── active model ──
        SectionLabel(self, text="ACTIVE MODEL").grid(row=4, column=0, padx=12, pady=(12, 2), sticky="w")
        self._model_var = ctk.StringVar(value="None")
        ctk.CTkLabel(self, textvariable=self._model_var,
                     font=("Segoe UI", 11), text_color=C_TEXT,
                     wraplength=240).grid(row=5, column=0, padx=12, sticky="w")

        # ── local models list ──
        SectionLabel(self, text="LOCAL MODELS").grid(row=6, column=0, padx=12, pady=(14, 2), sticky="w")
        self._models_box = ctk.CTkScrollableFrame(self, height=80, fg_color=C_BG,
                                                  corner_radius=6)
        self._models_box.grid(row=7, column=0, padx=8, sticky="ew")
        self._models_box.columnconfigure(0, weight=1)

        ctk.CTkButton(self, text="Refresh Models", height=28,
                      command=self._refresh_models,
                      fg_color=C_CARD, hover_color=C_ACCENT,
                      font=("Segoe UI", 10)).grid(row=8, column=0, padx=8, pady=4, sticky="ew")

        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=9, column=0, sticky="ew", padx=8, pady=8)

        # ── HF search ──
        SectionLabel(self, text="SEARCH HUGGING FACE").grid(row=10, column=0, padx=12, pady=(4, 2), sticky="w")
        self._hf_entry = ctk.CTkEntry(self, placeholder_text="e.g. mistral 7b Q4",
                                      font=("Segoe UI", 11))
        self._hf_entry.grid(row=11, column=0, padx=8, pady=(0, 4), sticky="ew")
        self._hf_entry.bind("<Return>", lambda _: self._hf_search())
        ctk.CTkButton(self, text="Search", height=28,
                      command=self._hf_search,
                      fg_color=C_ACCENT, hover_color="#c73652",
                      font=("Segoe UI", 10, "bold")).grid(row=12, column=0, padx=8, sticky="ew")

        self._hf_results = ctk.CTkScrollableFrame(self, height=200, fg_color=C_BG,
                                                  corner_radius=6)
        self._hf_results.grid(row=13, column=0, padx=8, pady=(4, 0), sticky="ew")
        self._hf_results.columnconfigure(0, weight=1)

        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=14, column=0, sticky="ew", padx=8, pady=8)

        # ── context slider ──
        SectionLabel(self, text="CONTEXT LENGTH").grid(row=15, column=0, padx=12, pady=(4, 2), sticky="w")
        self._ctx_var = ctk.IntVar(value=4096)
        self._ctx_label = ctk.CTkLabel(self, text="4096 tokens",
                                       font=("Segoe UI", 10), text_color=C_TEXT)
        self._ctx_label.grid(row=16, column=0, padx=12, sticky="w")
        self._ctx_slider = ctk.CTkSlider(self, from_=512, to=262144,
                                         variable=self._ctx_var,
                                         command=self._on_ctx_change,
                                         button_color=C_ACCENT,
                                         progress_color=C_ACCENT)
        self._ctx_slider.grid(row=17, column=0, padx=8, pady=(0, 4), sticky="ew")

        # grid spacer
        self.grid_rowconfigure(18, weight=1)

    # ── callbacks ──

    def _refresh_models(self):
        def _worker():
            data = _get("/api/tags")
            models = [m["name"] for m in (data or {}).get("models", [])]
            self.after(0, lambda: self._populate_models(models))
        threading.Thread(target=_worker, daemon=True).start()

    def _populate_models(self, models: list[str]):
        for w in self._models_box.winfo_children():
            w.destroy()
        if not models:
            ctk.CTkLabel(self._models_box, text="No models found",
                         text_color=C_DIM, font=("Segoe UI", 10)).grid(pady=4)
            return
        for name in models:
            btn = ctk.CTkButton(
                self._models_box, text=name,
                font=("Segoe UI", 10), height=26,
                fg_color=C_CARD, hover_color=C_ACCENT,
                anchor="w",
                command=lambda n=name: self._load_model(n),
            )
            btn.grid(sticky="ew", padx=2, pady=1)

    def _load_model(self, name: str):
        self.app.log(f"Loading model: {name}…")
        def _worker():
            _post("/api/generate", {"model": name, "prompt": "", "stream": False})
            self.after(0, lambda: self._set_active_model(name))
        threading.Thread(target=_worker, daemon=True).start()

    def _set_active_model(self, name: str):
        self._model_var.set(name)
        self.app.active_model = name
        self.app.log(f"Model ready: {name}")

    def _hf_search(self):
        query = self._hf_entry.get().strip()
        if not query:
            return
        self.app.log(f"Searching HuggingFace: {query}…")
        for w in self._hf_results.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._hf_results, text="Searching…",
                     text_color=C_YELLOW, font=("Segoe UI", 10)).grid(pady=4)

        def _worker():
            try:
                from app.hf_manager import search_gguf, estimate_performance
                cards = search_gguf(query, limit=15)
                cards = [estimate_performance(c, VRAM_TOTAL_GB, RAM_TOTAL_GB) for c in cards]
            except Exception as e:
                cards = []
                self.after(0, lambda: self.app.log(f"Search failed: {e}"))
            self.after(0, lambda: self._show_results(cards))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_results(self, cards):
        for w in self._hf_results.winfo_children():
            w.destroy()
        if not cards:
            ctk.CTkLabel(self._hf_results, text="No results.",
                         text_color=C_DIM, font=("Segoe UI", 10)).grid(pady=4)
            return
        for card in cards[:15]:
            f = ctk.CTkFrame(self._hf_results, fg_color=C_CARD, corner_radius=6)
            f.grid(sticky="ew", padx=2, pady=2)
            f.columnconfigure(0, weight=1)

            repo_short = card.repo_id.split("/")[-1][:26]
            fname_short = Path(card.filename).name[:28]
            speed_color = C_GREEN if card.estimated_tps >= 20 else C_YELLOW if card.estimated_tps >= 5 else C_RED

            ctk.CTkLabel(f, text=repo_short, font=("Segoe UI", 9, "bold"),
                         text_color=C_TEXT, anchor="w").grid(row=0, column=0, padx=6, pady=(4, 0), sticky="w")
            ctk.CTkLabel(f, text=fname_short, font=("Segoe UI", 8),
                         text_color=C_DIM, anchor="w").grid(row=1, column=0, padx=6, sticky="w")

            info_frame = ctk.CTkFrame(f, fg_color="transparent")
            info_frame.grid(row=2, column=0, padx=6, pady=(2, 4), sticky="ew")
            ctk.CTkLabel(info_frame, text=f"{card.size_gb:.1f} GB",
                         font=("Segoe UI", 9), text_color=C_DIM).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(info_frame, text=card.quantization,
                         font=("Segoe UI", 9), text_color=C_YELLOW).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(info_frame, text=f"~{card.estimated_tps:.0f} t/s",
                         font=("Segoe UI", 9, "bold"), text_color=speed_color).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(info_frame, text=card.fit_label,
                         font=("Segoe UI", 8), text_color=C_DIM).pack(side="left")

            ctk.CTkButton(f, text="⬇ Download", height=22,
                          font=("Segoe UI", 9),
                          fg_color="#1a1a2e", hover_color=C_GREEN,
                          command=lambda c=card: self._download(c),
                          ).grid(row=3, column=0, padx=6, pady=(0, 4), sticky="e")

    def _download(self, card):
        self.app.log(f"Downloading {card.filename}…")
        def _worker():
            from app.hf_manager import download_model, DownloadProgress
            def on_prog(p: DownloadProgress):
                if not p.done:
                    self.after(0, lambda: self.app.log(
                        f"↓ {p.filename[:30]}  {p.pct:.1f}%  {p.speed_bps/1024/1024:.1f} MB/s"
                    ))
            try:
                dest = download_model(card.repo_id, card.filename,
                                      config.MODELS_DIR, on_prog)
                self.after(0, lambda: self.app.log(f"✓ Saved: {dest.name}"))
                self.after(0, self._refresh_models)
            except Exception as e:
                self.after(0, lambda: self.app.log(f"✗ Download failed: {e}"))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_ctx_change(self, val):
        v = int(float(val))
        # snap to nearest 256
        v = max(512, (v // 256) * 256)
        self._ctx_label.configure(text=f"{v:,} tokens")
        self.app.context_length = v

    def set_status(self, connected: bool, model: str | None):
        if connected:
            self._status_var.set("● Connected")
            # status label colour is set at creation; update dynamically
        else:
            self._status_var.set("● Offline")
        if model:
            self._model_var.set(model)


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLE — Tab Planner + Chat
# ─────────────────────────────────────────────────────────────────────────────

class MiddleArea(ctk.CTkFrame):
    def __init__(self, parent, app: "HeramaApp", **kw):
        super().__init__(parent, fg_color=C_BG, corner_radius=0, **kw)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._tabs = ctk.CTkTabview(self, fg_color=C_PANEL,
                                    segmented_button_selected_color=C_ACCENT,
                                    segmented_button_unselected_color=C_CARD,
                                    text_color=C_TEXT)
        self._tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=8, rowspan=2)
        self._tabs.columnconfigure(0, weight=1)

        self._tabs.add("  Task Planner  ")
        self._tabs.add("  Hermes Chat  ")

        self._build_planner(self._tabs.tab("  Task Planner  "))
        self._build_chat(self._tabs.tab("  Hermes Chat  "))

    # ── Task Planner tab ──────────────────────────────────────────────────────

    def _build_planner(self, frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Pipeline & Task Board",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C_TEXT).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self._task_scroll = ctk.CTkScrollableFrame(frame, fg_color=C_BG, corner_radius=6)
        self._task_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._task_scroll.columnconfigure(0, weight=1)

        # add task controls
        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))
        bottom.columnconfigure(0, weight=1)
        self._task_entry = ctk.CTkEntry(bottom, placeholder_text="New task…",
                                        font=("Segoe UI", 11))
        self._task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(bottom, text="Add", width=60, height=32,
                      fg_color=C_ACCENT, hover_color="#c73652",
                      command=self._add_task).grid(row=0, column=1)

        self._tasks: list[dict] = [
            {"label": "Connect to Herama backend", "state": "done"},
            {"label": "Load a GGUF model", "state": "todo"},
            {"label": "Chat with Hermes", "state": "todo"},
        ]
        self._render_tasks()

    def _add_task(self):
        label = self._task_entry.get().strip()
        if label:
            self._tasks.append({"label": label, "state": "todo"})
            self._task_entry.delete(0, "end")
            self._render_tasks()

    def _render_tasks(self):
        for w in self._task_scroll.winfo_children():
            w.destroy()
        state_cfg = {
            "done":        (C_GREEN,  "✓", "Done"),
            "in_progress": (C_YELLOW, "⟳", "In Progress"),
            "todo":        (C_DIM,    "○", "Todo"),
        }
        for i, task in enumerate(self._tasks):
            color, icon, label = state_cfg[task["state"]]
            card = ctk.CTkFrame(self._task_scroll, fg_color=C_CARD, corner_radius=8)
            card.grid(sticky="ew", padx=4, pady=3)
            card.columnconfigure(1, weight=1)

            ctk.CTkLabel(card, text=icon, font=("Segoe UI", 14, "bold"),
                         text_color=color, width=28).grid(row=0, column=0, padx=(8, 4), pady=8)
            ctk.CTkLabel(card, text=task["label"], font=("Segoe UI", 11),
                         text_color=C_TEXT, anchor="w").grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(card, text=label, font=("Segoe UI", 9),
                         text_color=color).grid(row=0, column=2, padx=8)

            # cycle state on click
            ctk.CTkButton(card, text="▶", width=28, height=28,
                          fg_color="transparent", hover_color=C_ACCENT,
                          font=("Segoe UI", 10),
                          command=lambda idx=i: self._cycle_task(idx),
                          ).grid(row=0, column=3, padx=(0, 6))

    def _cycle_task(self, idx: int):
        states = ["todo", "in_progress", "done"]
        cur = self._tasks[idx]["state"]
        self._tasks[idx]["state"] = states[(states.index(cur) + 1) % len(states)]
        self._render_tasks()

    # ── Chat tab ──────────────────────────────────────────────────────────────

    def _build_chat(self, frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._chat_box = ctk.CTkTextbox(frame, font=("Consolas", 11),
                                        fg_color=C_BG, text_color=C_TEXT,
                                        wrap="word", state="disabled",
                                        corner_radius=8)
        self._chat_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        input_row = ctk.CTkFrame(frame, fg_color="transparent")
        input_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        input_row.columnconfigure(0, weight=1)

        self._chat_entry = ctk.CTkEntry(input_row,
                                        placeholder_text="Type a message…",
                                        font=("Segoe UI", 12), height=36)
        self._chat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._chat_entry.bind("<Return>", lambda _: self._send())

        self._send_btn = ctk.CTkButton(input_row, text="Send ▶", width=80, height=36,
                                       fg_color=C_ACCENT, hover_color="#c73652",
                                       font=("Segoe UI", 11, "bold"),
                                       command=self._send)
        self._send_btn.grid(row=0, column=1)

        self._history: list[dict] = []

    def _append_chat(self, text: str):
        self._chat_box.configure(state="normal")
        self._chat_box.insert("end", text)
        self._chat_box.see("end")
        self._chat_box.configure(state="disabled")

    def _send(self):
        text = self._chat_entry.get().strip()
        if not text:
            return
        model = self.app.active_model
        if not model:
            self._append_chat("[System] No model loaded. Use the left panel.\n\n")
            return
        self._chat_entry.delete(0, "end")
        self._send_btn.configure(state="disabled")
        self._append_chat(f"You: {text}\n")
        self._append_chat("Hermes: ")
        self._history.append({"role": "user", "content": text})

        def on_token(tok: str):
            self.after(0, lambda: self._append_chat(tok))

        def on_done():
            full = self._chat_box.get("1.0", "end")
            # extract last assistant turn
            self._history.append({"role": "assistant", "content": ""})
            self.after(0, lambda: self._append_chat("\n\n"))
            self.after(0, lambda: self._send_btn.configure(state="normal"))

        threading.Thread(
            target=_stream_chat,
            args=(model, list(self._history), on_token, on_done),
            daemon=True,
        ).start()


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT SIDEBAR — Hardware Monitor + Skills
# ─────────────────────────────────────────────────────────────────────────────

class RightSidebar(ctk.CTkFrame):
    def __init__(self, parent, app: "HeramaApp", **kw):
        super().__init__(parent, width=240, fg_color=C_PANEL,
                         corner_radius=0, **kw)
        self.app = app
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        SectionLabel(self, text="HARDWARE MONITOR").grid(
            row=0, column=0, padx=12, pady=(14, 4), sticky="w")

        self._vram_bar = HWBar(self, "VRAM", VRAM_TOTAL_GB, C_ACCENT)
        self._vram_bar.grid(row=1, column=0, padx=10, sticky="ew")

        self._ram_bar = HWBar(self, "RAM", RAM_TOTAL_GB, C_GREEN)
        self._ram_bar.grid(row=2, column=0, padx=10, sticky="ew")

        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=3, column=0, sticky="ew", padx=8, pady=8)

        # model info
        SectionLabel(self, text="LOADED MODEL INFO").grid(
            row=4, column=0, padx=12, pady=(4, 2), sticky="w")
        self._info_var = ctk.StringVar(value="No model loaded")
        ctk.CTkLabel(self, textvariable=self._info_var,
                     font=("Segoe UI", 10), text_color=C_DIM,
                     wraplength=210, justify="left").grid(row=5, column=0, padx=12, sticky="w")

        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=6, column=0, sticky="ew", padx=8, pady=8)

        # skills
        SectionLabel(self, text="ACQUIRED SKILLS").grid(
            row=7, column=0, padx=12, pady=(4, 2), sticky="w")
        self._skills_scroll = ctk.CTkScrollableFrame(self, fg_color=C_BG,
                                                     corner_radius=6)
        self._skills_scroll.grid(row=8, column=0, padx=8, sticky="ew")
        self._skills_scroll.columnconfigure(0, weight=1)
        self.grid_rowconfigure(8, weight=1)

        # log area
        ctk.CTkFrame(self, height=1, fg_color=C_CARD).grid(
            row=9, column=0, sticky="ew", padx=8, pady=8)
        SectionLabel(self, text="ACTIVITY LOG").grid(
            row=10, column=0, padx=12, pady=(4, 2), sticky="w")
        self._log_box = ctk.CTkTextbox(self, height=130, font=("Consolas", 9),
                                       fg_color=C_BG, text_color=C_DIM,
                                       wrap="word", state="disabled",
                                       corner_radius=6)
        self._log_box.grid(row=11, column=0, padx=8, pady=(0, 8), sticky="ew")

    def update_hw(self, vram_used: float, ram_used: float):
        self._vram_bar.update(vram_used)
        self._ram_bar.update(ram_used)

    def update_skills(self, skills: dict):
        for w in self._skills_scroll.winfo_children():
            w.destroy()
        if not skills:
            ctk.CTkLabel(self._skills_scroll, text="No skills yet.",
                         text_color=C_DIM, font=("Segoe UI", 10)).grid(pady=4)
            return
        for name, meta in skills.items():
            f = ctk.CTkFrame(self._skills_scroll, fg_color=C_CARD, corner_radius=6)
            f.grid(sticky="ew", padx=2, pady=2)
            ctk.CTkLabel(f, text=f"⚙ {name}", font=("Segoe UI", 10, "bold"),
                         text_color=C_TEXT).grid(row=0, column=0, padx=8, pady=(4, 0), sticky="w")
            desc = (meta.get("desc") or "")[:40]
            if desc:
                ctk.CTkLabel(f, text=desc, font=("Segoe UI", 9),
                             text_color=C_DIM).grid(row=1, column=0, padx=8, pady=(0, 4), sticky="w")

    def update_model_info(self, info: str):
        self._info_var.set(info)

    def append_log(self, msg: str):
        self._log_box.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self._log_box.insert("end", f"{ts}  {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────────────────────

class HeramaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Herama — Local LLM Engine")
        self.geometry("1280x800")
        self.minsize(960, 600)
        self.configure(fg_color=C_BG)

        self.active_model: str | None = None
        self.context_length: int = 4096

        # layout
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._left = LeftSidebar(self, app=self)
        self._left.grid(row=0, column=0, sticky="nsew")

        self._middle = MiddleArea(self, app=self)
        self._middle.grid(row=0, column=1, sticky="nsew")

        self._right = RightSidebar(self, app=self)
        self._right.grid(row=0, column=2, sticky="nsew")

        # kick off polling
        self._poll()
        self._left._refresh_models()

    def log(self, msg: str):
        self.after(0, lambda: self._right.append_log(msg))

    def _poll(self):
        threading.Thread(target=self._poll_worker, daemon=True).start()
        self.after(POLL_INTERVAL * 1000, self._poll)

    def _poll_worker(self):
        # health
        health = _get("/health")
        connected = health is not None
        model = (health or {}).get("model")
        if model:
            self.active_model = model

        # vram / ram via psutil + optional pynvml
        try:
            import psutil
            ram_used = (psutil.virtual_memory().total -
                        psutil.virtual_memory().available) / 1024 ** 3
        except Exception:
            ram_used = 0.0
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            m = pynvml.nvmlDeviceGetMemoryInfo(h)
            vram_used = (m.total - m.free) / 1024 ** 3
        except Exception:
            vram_used = 0.0

        # skills
        skills_data = _get("/api/skills") or {}

        # model info
        if model:
            ps = _get("/api/ps") or {}
            ms = ps.get("models", [])
            if ms:
                m0 = ms[0]
                info = (f"{m0.get('name','?')}\n"
                        f"ctx: {m0.get('details', {}).get('context_length', '?')}\n"
                        f"gpu layers: {m0.get('details', {}).get('n_gpu_layers', '?')}")
            else:
                info = model
        else:
            info = "No model loaded"

        self.after(0, lambda: self._left.set_status(connected, model))
        self.after(0, lambda: self._right.update_hw(vram_used, ram_used))
        self.after(0, lambda: self._right.update_skills(skills_data))
        self.after(0, lambda: self._right.update_model_info(info))


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = HeramaApp()
    app.mainloop()


if __name__ == "__main__":
    main()
