"""
Herama GUI — Production AI Infrastructure Dashboard.

Layout:
  ┌──────────────────────────────────────────────────────────┐
  │  TOP: [Token Speed] [RAM] [VRAM] [Active Experts]        │
  ├────────────────────────┬─────────────────────────────────┤
  │  LEFT SIDEBAR          │  DASHBOARD                      │
  │  • Model Management    │  [Context Fill donut] [Requests]│
  │  • HF Search           ├─────────────────────────────────┤
  │  • Context Slider      │  CHAT / TASK PLANNER TABS       │
  └────────────────────────┴─────────────────────────────────┘

Run:  python -m app.gui_ui
Requires: customtkinter >= 5.2, matplotlib >= 3.7 (auto-installed)
"""
from __future__ import annotations

# ── auto-install dependencies ─────────────────────────────────────────────────
from app.dependency_manager import ensure_packages
ensure_packages(["customtkinter", "matplotlib", "requests"])

# ── stdlib ────────────────────────────────────────────────────────────────────
import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

# ── third-party ───────────────────────────────────────────────────────────────
import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import requests as _requests

# ── project ───────────────────────────────────────────────────────────────────
from app import config

# ─────────────────────────────────────────────────────────────────────────────
# Theme & Palette
# ─────────────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG          = "#121214"
PANEL       = "#1a1a1f"
CARD        = "#1e1e26"
CARD2       = "#16161c"
BORDER      = "#2a2a38"
ACCENT_ORG  = "#f97316"   # orange — active / VRAM
ACCENT_GRN  = "#22c55e"   # green  — healthy / RAM
ACCENT_BLU  = "#3b82f6"   # blue   — info / speed
ACCENT_PRP  = "#a855f7"   # purple — experts
TEXT        = "#e2e8f0"
DIM         = "#64748b"
DIM2        = "#475569"
RED         = "#ef4444"
YELLOW      = "#eab308"

# matplotlib style to match dark theme
_MPL_STYLE = {
    "figure.facecolor": CARD,
    "axes.facecolor":   CARD,
    "axes.edgecolor":   BORDER,
    "axes.labelcolor":  DIM,
    "text.color":       TEXT,
    "xtick.color":      DIM,
    "ytick.color":      DIM,
    "grid.color":       BORDER,
    "lines.linewidth":  1.6,
}
for k, v in _MPL_STYLE.items():
    plt.rcParams[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL       = "http://127.0.0.1:11434"
VRAM_TOTAL_GB  = 10.8
RAM_TOTAL_GB   = 31.2
POLL_MS        = 500    # hardware poll interval
HISTORY_LEN    = 60     # data points kept for sparklines


# ─────────────────────────────────────────────────────────────────────────────
# Shared live metrics (updated from background thread)
# ─────────────────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self.lock           = threading.Lock()
        self.connected      = False
        self.active_model   = None
        self.tps            = 0.0
        self.tps_history    = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.ram_used_gb    = 0.0
        self.vram_used_gb   = 0.0
        self.cpu_layers     = 0
        self.gpu_layers     = 0
        self.n_ctx          = 0
        self.context_tokens = 0
        self.skills: dict   = {}
        self.requests: list = []   # recent API calls [(time, status, tok/s, ms)]
        self.local_models: list = []


metrics = Metrics()


# ─────────────────────────────────────────────────────────────────────────────
# Background poller
# ─────────────────────────────────────────────────────────────────────────────

def _poll_loop(app_ref):
    import psutil
    while True:
        try:
            health = _requests.get(f"{BASE_URL}/health", timeout=2).json()
            connected = True
            model = health.get("model")
        except Exception:
            connected = False
            model = None
            health = {}

        try:
            ram_used = (psutil.virtual_memory().total -
                        psutil.virtual_memory().available) / 1024 ** 3
        except Exception:
            ram_used = 0.0

        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            mi = pynvml.nvmlDeviceGetMemoryInfo(h)
            vram_used = (mi.total - mi.free) / 1024 ** 3
        except Exception:
            vram_used = 0.0

        # model info (gpu/cpu layers)
        gpu_layers = cpu_layers = n_ctx = 0
        if model:
            try:
                ps_data = _requests.get(f"{BASE_URL}/api/ps", timeout=2).json()
                ms_list = ps_data.get("models", [])
                if ms_list:
                    det = ms_list[0].get("details", {})
                    gpu_layers = det.get("n_gpu_layers", 0) or 0
                    cpu_layers = max(0, (det.get("block_count", 32) or 32) - gpu_layers)
                    n_ctx = det.get("context_length", 0) or 0
            except Exception:
                pass

        try:
            skills = _requests.get(f"{BASE_URL}/api/skills", timeout=2).json()
        except Exception:
            skills = {}

        try:
            tags = _requests.get(f"{BASE_URL}/api/tags", timeout=2).json()
            local_models = [m["name"] for m in tags.get("models", [])]
        except Exception:
            local_models = []

        with metrics.lock:
            metrics.connected    = connected
            metrics.active_model = model
            metrics.ram_used_gb  = ram_used
            metrics.vram_used_gb = vram_used
            metrics.gpu_layers   = gpu_layers
            metrics.cpu_layers   = cpu_layers
            metrics.n_ctx        = n_ctx
            metrics.skills       = skills
            metrics.local_models = local_models

        time.sleep(POLL_MS / 1000)


# ─────────────────────────────────────────────────────────────────────────────
# Reusable widget utilities
# ─────────────────────────────────────────────────────────────────────────────

def _label(parent, text="", font_size=10, bold=False, color=TEXT, **kw):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text,
                        font=("Segoe UI", font_size, weight),
                        text_color=color, **kw)


def _divider(parent, row, padx=8):
    ctk.CTkFrame(parent, height=1, fg_color=BORDER).grid(
        row=row, column=0, columnspan=99, sticky="ew", padx=padx, pady=4)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Cards (top row)
# ─────────────────────────────────────────────────────────────────────────────

class SparkCard(ctk.CTkFrame):
    """Card A — Token Speed with mini sparkline."""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(0, weight=1)

        _label(self, "TOKEN SPEED", 9, color=DIM).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        self._val = ctk.StringVar(value="— tok/s")
        _label(self, font_size=22, bold=True, color=ACCENT_BLU,
               textvariable=self._val).grid(row=1, column=0, sticky="w", padx=14)
        _label(self, "Decode / Prefill", 9, color=DIM2).grid(row=2, column=0, sticky="w", padx=14)

        # sparkline
        fig, self._ax = plt.subplots(figsize=(2.6, 0.7))
        fig.patch.set_facecolor(CARD)
        self._ax.set_facecolor(CARD)
        self._ax.set_xticks([]); self._ax.set_yticks([])
        for sp in self._ax.spines.values():
            sp.set_visible(False)
        self._line, = self._ax.plot([], [], color=ACCENT_BLU, linewidth=1.6)
        self._fill = self._ax.fill_between([], [], alpha=0.18, color=ACCENT_BLU)
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.get_tk_widget().configure(bg=CARD, highlightthickness=0)
        canvas.get_tk_widget().grid(row=3, column=0, sticky="ew", padx=6, pady=(2, 10))
        self._canvas = canvas
        self._fig = fig

    def update(self, tps: float, history: list):
        self._val.set(f"{tps:.1f} tok/s")
        xs = list(range(len(history)))
        ys = list(history)
        self._line.set_data(xs, ys)
        # rebuild fill
        for coll in self._ax.collections:
            coll.remove()
        self._ax.fill_between(xs, ys, alpha=0.15, color=ACCENT_BLU)
        self._ax.set_xlim(0, max(1, len(xs) - 1))
        self._ax.set_ylim(0, max(1, max(ys) * 1.2))
        try:
            self._canvas.draw_idle()
        except Exception:
            pass


class GaugeCard(ctk.CTkFrame):
    """Generic linear gauge card (RAM, VRAM)."""

    def __init__(self, parent, title: str, total_gb: float,
                 color: str, unit: str = "GB", **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.total_gb = total_gb
        self.color = color
        self.columnconfigure(0, weight=1)

        _label(self, title, 9, color=DIM).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        self._val_var = ctk.StringVar(value=f"0.0 / {total_gb:.1f} {unit}")
        _label(self, font_size=18, bold=True, color=color,
               textvariable=self._val_var).grid(row=1, column=0, sticky="w", padx=14, pady=(2, 0))

        self._pct_var = ctk.StringVar(value="0 %")
        _label(self, font_size=10, color=DIM2,
               textvariable=self._pct_var).grid(row=2, column=0, sticky="w", padx=14)

        self._bar = ctk.CTkProgressBar(self, height=8, corner_radius=4,
                                       progress_color=color, fg_color=BORDER)
        self._bar.set(0)
        self._bar.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 14))

    def update(self, used_gb: float):
        pct = min(1.0, used_gb / self.total_gb) if self.total_gb else 0
        self._bar.set(pct)
        self._val_var.set(f"{used_gb:.1f} / {self.total_gb:.1f} GB")
        self._pct_var.set(f"{pct * 100:.0f} %")


class ExpertsCard(ctk.CTkFrame):
    """Card D — Active Experts (MoE CPU vs GPU layers)."""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(0, weight=1)

        _label(self, "ACTIVE EXPERTS", 9, color=DIM).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 0))

        self._gpu_var = ctk.StringVar(value="GPU  0")
        self._cpu_var = ctk.StringVar(value="CPU  0")

        _label(self, font_size=18, bold=True, color=ACCENT_PRP,
               textvariable=self._gpu_var).grid(row=1, column=0, sticky="w", padx=14, pady=(2, 0))
        _label(self, font_size=12, color=DIM,
               textvariable=self._cpu_var).grid(row=2, column=0, sticky="w", padx=14)

        self._detail_var = ctk.StringVar(value="layers")
        _label(self, font_size=9, color=DIM2,
               textvariable=self._detail_var).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 14))

    def update(self, gpu: int, cpu: int, model: str | None):
        self._gpu_var.set(f"GPU  {gpu}")
        self._cpu_var.set(f"CPU  {cpu}")
        total = gpu + cpu
        self._detail_var.set(f"{total} total layers" + (f" · {model}" if model else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Context Fill donut
# ─────────────────────────────────────────────────────────────────────────────

class ContextDonut(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        _label(self, "CONTEXT FILL", 9, color=DIM).grid(
            row=0, column=0, padx=14, pady=(12, 0), sticky="w")

        fig, self._ax = plt.subplots(figsize=(2.2, 2.2))
        fig.patch.set_facecolor(CARD)
        self._pct_text = self._ax.text(0, 0, "0 %", ha="center", va="center",
                                       fontsize=16, fontweight="bold", color=TEXT)
        self._tok_text = self._ax.text(0, -0.28, "0 tok", ha="center", va="center",
                                       fontsize=8, color=DIM)
        self._ax.set_aspect("equal"); self._ax.axis("off")
        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.get_tk_widget().configure(bg=CARD, highlightthickness=0)
        canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._canvas = canvas
        self._fig = fig
        self._drawn = False
        self._wedge_fill = None
        self._wedge_bg = None
        self._draw_donut(0)

    def _draw_donut(self, pct: float):
        self._ax.clear()
        self._ax.set_aspect("equal"); self._ax.axis("off")
        filled = max(0.001, pct)
        empty  = max(0.001, 1 - pct)
        wedges, _ = self._ax.pie(
            [filled, empty],
            startangle=90,
            wedgeprops={"width": 0.32, "edgecolor": CARD, "linewidth": 2},
            colors=[ACCENT_ORG, BORDER],
        )
        p_str = f"{pct * 100:.0f} %"
        self._ax.text(0, 0.06, p_str, ha="center", va="center",
                      fontsize=16, fontweight="bold", color=TEXT)
        return wedges

    def update(self, used_tokens: int, n_ctx: int):
        pct = min(1.0, used_tokens / n_ctx) if n_ctx > 0 else 0
        self._draw_donut(pct)
        self._ax.text(0, -0.22, f"{used_tokens:,} / {n_ctx:,}", ha="center", va="center",
                      fontsize=8, color=DIM)
        try:
            self._canvas.draw_idle()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Recent Requests table
# ─────────────────────────────────────────────────────────────────────────────

class RequestsTable(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        _label(self, "RECENT SYSTEM REQUESTS", 9, color=DIM).grid(
            row=0, column=0, padx=14, pady=(12, 4), sticky="w")

        # header row
        hdr = ctk.CTkFrame(self, fg_color=CARD2, corner_radius=0)
        hdr.grid(row=1, column=0, sticky="ew", padx=8)
        for i, (col, w) in enumerate([("Time", 60), ("Status", 60),
                                       ("Prompt", 120), ("Tok/s", 55), ("ms", 55)]):
            _label(hdr, col, 9, bold=True, color=DIM2,
                   width=w, anchor="w").grid(row=0, column=i, padx=4, pady=3)

        self._rows_frame = ctk.CTkScrollableFrame(self, fg_color=CARD,
                                                  corner_radius=0, height=140)
        self._rows_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._rows_frame.columnconfigure(list(range(5)), weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._records: list[dict] = []

    def add_request(self, status: str, prompt: str, tps: float, ms: float):
        ts = time.strftime("%H:%M:%S")
        self._records.insert(0, {"ts": ts, "status": status,
                                  "prompt": prompt[:30], "tps": tps, "ms": ms})
        self._records = self._records[:50]
        self._render()

    def _render(self):
        for w in self._rows_frame.winfo_children():
            w.destroy()
        for rec in self._records[:20]:
            ok = rec["status"] == "200"
            sc = ACCENT_GRN if ok else RED
            row_data = [
                (rec["ts"],         DIM,    60),
                (rec["status"],     sc,     60),
                (rec["prompt"],     TEXT,   120),
                (f"{rec['tps']:.1f}", ACCENT_BLU, 55),
                (f"{rec['ms']:.0f}", DIM,   55),
            ]
            for col, (val, color, w) in enumerate(row_data):
                _label(self._rows_frame, val, 9, color=color,
                       width=w, anchor="w").grid(row=len(self._rows_frame.winfo_children()), column=col,
                                                  padx=4, pady=1)


# ─────────────────────────────────────────────────────────────────────────────
# LEFT SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

class LeftSidebar(ctk.CTkFrame):
    def __init__(self, parent, app: "HeramaApp", **kw):
        super().__init__(parent, width=260, fg_color=PANEL,
                         corner_radius=0, **kw)
        self.app = app
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        # branding
        _label(self, "⚡ HERAMA", 15, bold=True, color=ACCENT_ORG).grid(
            row=0, column=0, sticky="w", padx=14, pady=(16, 2))
        _label(self, "Local LLM Infrastructure", 9, color=DIM).grid(
            row=1, column=0, sticky="w", padx=14)

        _divider(self, 2)

        # status pill
        self._status_var = ctk.StringVar(value="● Offline")
        self._status_lbl = ctk.CTkLabel(self, textvariable=self._status_var,
                                        font=("Segoe UI", 10, "bold"),
                                        text_color=RED)
        self._status_lbl.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 4))

        # model display
        _label(self, "ACTIVE MODEL", 8, color=DIM).grid(row=4, column=0, sticky="w", padx=14, pady=(8, 0))
        self._model_var = ctk.StringVar(value="None")
        _label(self, font_size=11, bold=True, color=TEXT,
               textvariable=self._model_var, wraplength=230, anchor="w").grid(
            row=5, column=0, sticky="w", padx=14)

        _divider(self, 6)

        # local models
        _label(self, "LOCAL MODELS", 8, color=DIM).grid(row=7, column=0, sticky="w", padx=14, pady=(4, 2))
        self._models_box = ctk.CTkScrollableFrame(self, height=90, fg_color=BG, corner_radius=6)
        self._models_box.grid(row=8, column=0, padx=8, sticky="ew")
        self._models_box.columnconfigure(0, weight=1)

        ctk.CTkButton(self, text="↺  Refresh", height=26,
                      font=("Segoe UI", 10), fg_color=CARD2, hover_color=BORDER,
                      command=self._refresh_models).grid(
            row=9, column=0, padx=8, pady=(4, 0), sticky="ew")

        _divider(self, 10)

        # HF search
        _label(self, "SEARCH HUGGING FACE", 8, color=DIM).grid(
            row=11, column=0, sticky="w", padx=14, pady=(4, 2))
        self._hf_entry = ctk.CTkEntry(self, placeholder_text="mistral 7b Q4…",
                                      font=("Segoe UI", 11), height=32)
        self._hf_entry.grid(row=12, column=0, padx=8, sticky="ew")
        self._hf_entry.bind("<Return>", lambda _: self._hf_search())
        ctk.CTkButton(self, text="Search  ↗", height=30,
                      font=("Segoe UI", 10, "bold"),
                      fg_color=ACCENT_ORG, hover_color="#ea6a0a",
                      text_color=BG,
                      command=self._hf_search).grid(
            row=13, column=0, padx=8, pady=(4, 0), sticky="ew")

        self._hf_results = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=6, height=180)
        self._hf_results.grid(row=14, column=0, padx=8, pady=(4, 0), sticky="ew")
        self._hf_results.columnconfigure(0, weight=1)

        _divider(self, 15)

        # context slider
        _label(self, "CONTEXT LENGTH", 8, color=DIM).grid(
            row=16, column=0, sticky="w", padx=14, pady=(4, 0))
        self._ctx_label_var = ctk.StringVar(value="4,096 tokens")
        _label(self, font_size=12, bold=True, color=ACCENT_BLU,
               textvariable=self._ctx_label_var).grid(row=17, column=0, sticky="w", padx=14)
        self._ctx_slider = ctk.CTkSlider(self, from_=512, to=262144,
                                         number_of_steps=511,
                                         command=self._on_ctx,
                                         button_color=ACCENT_ORG,
                                         progress_color=ACCENT_ORG,
                                         fg_color=BORDER)
        self._ctx_slider.set(4096)
        self._ctx_slider.grid(row=18, column=0, padx=8, pady=(0, 8), sticky="ew")

        self.grid_rowconfigure(19, weight=1)

        # skills badge at bottom
        _divider(self, 20)
        _label(self, "ACQUIRED SKILLS", 8, color=DIM).grid(
            row=21, column=0, sticky="w", padx=14, pady=(4, 2))
        self._skills_box = ctk.CTkScrollableFrame(self, height=80, fg_color=BG, corner_radius=6)
        self._skills_box.grid(row=22, column=0, padx=8, pady=(0, 12), sticky="ew")
        self._skills_box.columnconfigure(0, weight=1)

    # ── callbacks ──

    def _refresh_models(self):
        def _w():
            try:
                d = _requests.get(f"{BASE_URL}/api/tags", timeout=5).json()
                models = [m["name"] for m in d.get("models", [])]
            except Exception:
                models = []
            self.after(0, lambda: self._fill_models(models))
        threading.Thread(target=_w, daemon=True).start()

    def _fill_models(self, models):
        for w in self._models_box.winfo_children():
            w.destroy()
        if not models:
            _label(self._models_box, "No local models", 9, color=DIM).grid(pady=4)
            return
        for name in models:
            ctk.CTkButton(
                self._models_box, text=name, height=24,
                font=("Segoe UI", 10), anchor="w",
                fg_color=CARD2, hover_color=ACCENT_ORG,
                text_color=TEXT,
                command=lambda n=name: self.app.load_model(n),
            ).grid(sticky="ew", padx=2, pady=1)

    def _hf_search(self):
        q = self._hf_entry.get().strip()
        if not q:
            return
        self.app.log(f"Searching HF: {q}…")
        for w in self._hf_results.winfo_children():
            w.destroy()
        _label(self._hf_results, "Searching…", 9, color=YELLOW).grid(pady=4)

        def _w():
            try:
                from app.hf_manager import search_gguf, estimate_performance
                cards = [estimate_performance(c, VRAM_TOTAL_GB, RAM_TOTAL_GB)
                         for c in search_gguf(q, limit=15)]
            except Exception as e:
                cards = []
                self.after(0, lambda: self.app.log(f"Search error: {e}"))
            self.after(0, lambda: self._fill_results(cards))
        threading.Thread(target=_w, daemon=True).start()

    def _fill_results(self, cards):
        for w in self._hf_results.winfo_children():
            w.destroy()
        if not cards:
            _label(self._hf_results, "No results.", 9, color=DIM).grid(pady=4)
            return
        for card in cards[:15]:
            f = ctk.CTkFrame(self._hf_results, fg_color=CARD2, corner_radius=6)
            f.grid(sticky="ew", padx=2, pady=2)
            f.columnconfigure(0, weight=1)
            sc = ACCENT_GRN if card.estimated_tps >= 20 else YELLOW if card.estimated_tps >= 5 else RED
            repo = card.repo_id.split("/")[-1][:24]
            fname = Path(card.filename).name[:26]
            _label(f, repo, 9, bold=True, anchor="w").grid(row=0, column=0, sticky="w", padx=6, pady=(4, 0))
            _label(f, fname, 8, color=DIM, anchor="w").grid(row=1, column=0, sticky="w", padx=6)
            inf = ctk.CTkFrame(f, fg_color="transparent")
            inf.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 0))
            _label(inf, f"{card.size_gb:.1f}GB", 9, color=DIM2).pack(side="left", padx=(0, 6))
            _label(inf, card.quantization, 9, color=YELLOW).pack(side="left", padx=(0, 6))
            _label(inf, f"~{card.estimated_tps:.0f} t/s", 9, bold=True, color=sc).pack(side="left")
            ctk.CTkButton(f, text="⬇", width=28, height=22, font=("Segoe UI", 10),
                          fg_color=CARD, hover_color=ACCENT_GRN,
                          command=lambda c=card: self.app.download_model(c),
                          ).grid(row=0, column=1, rowspan=3, padx=6, pady=4)

    def _on_ctx(self, val):
        v = max(512, (int(float(val)) // 256) * 256)
        self._ctx_label_var.set(f"{v:,} tokens")
        self.app.context_length = v

    def set_status(self, connected, model):
        if connected:
            self._status_var.set("● Connected")
            self._status_lbl.configure(text_color=ACCENT_GRN)
        else:
            self._status_var.set("● Offline")
            self._status_lbl.configure(text_color=RED)
        if model:
            self._model_var.set(model)
        else:
            self._model_var.set("None")

    def update_skills(self, skills: dict):
        for w in self._skills_box.winfo_children():
            w.destroy()
        if not skills:
            _label(self._skills_box, "No skills yet.", 9, color=DIM).grid(pady=2)
            return
        for name in list(skills.keys())[:20]:
            _label(self._skills_box, f"⚙ {name}", 9, color=TEXT, anchor="w").grid(sticky="w", padx=4, pady=1)


# ─────────────────────────────────────────────────────────────────────────────
# CHAT + TASK area (bottom of main panel)
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceArea(ctk.CTkFrame):
    def __init__(self, parent, app: "HeramaApp", **kw):
        super().__init__(parent, fg_color=PANEL, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._tabs = ctk.CTkTabview(self, fg_color=PANEL,
                                    segmented_button_selected_color=ACCENT_ORG,
                                    segmented_button_unselected_color=CARD2,
                                    text_color=TEXT,
                                    corner_radius=10)
        self._tabs.grid(row=0, column=0, sticky="nsew", padx=0, pady=0, rowspan=2)

        self._tabs.add("  Hermes Chat  ")
        self._tabs.add("  Task Board  ")

        self._build_chat(self._tabs.tab("  Hermes Chat  "))
        self._build_tasks(self._tabs.tab("  Task Board  "))

    # ── Chat ──────────────────────────────────────────────────────────────────

    def _build_chat(self, frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._chat_box = ctk.CTkTextbox(frame, font=("Consolas", 11),
                                        fg_color=BG, text_color=TEXT,
                                        wrap="word", state="disabled",
                                        corner_radius=8, border_width=1,
                                        border_color=BORDER)
        self._chat_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        bar.columnconfigure(0, weight=1)

        self._chat_entry = ctk.CTkEntry(bar, placeholder_text="Type a prompt…",
                                        font=("Segoe UI", 12), height=36,
                                        fg_color=CARD2, border_color=BORDER)
        self._chat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._chat_entry.bind("<Return>", lambda _: self._send())

        self._send_btn = ctk.CTkButton(bar, text="Send ▶", width=80, height=36,
                                       font=("Segoe UI", 11, "bold"),
                                       fg_color=ACCENT_ORG, hover_color="#ea6a0a",
                                       text_color=BG, command=self._send)
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
            self._append_chat("[System] No model loaded.\n\n")
            return
        self._chat_entry.delete(0, "end")
        self._send_btn.configure(state="disabled")
        self._append_chat(f"\nYou › {text}\n")
        self._append_chat("Hermes › ")
        self._history.append({"role": "user", "content": text})
        t0 = time.perf_counter()
        tok_count = [0]

        def on_tok(t: str):
            tok_count[0] += len(t.split())
            self.after(0, lambda: self._append_chat(t))

        def on_done():
            elapsed = time.perf_counter() - t0
            tps = tok_count[0] / elapsed if elapsed > 0 else 0
            with metrics.lock:
                metrics.tps = tps
                metrics.tps_history.append(tps)
            self.app.requests_table.add_request("200", text, tps, elapsed * 1000)
            self.after(0, lambda: self._append_chat("\n"))
            self.after(0, lambda: self._send_btn.configure(state="normal"))

        def _stream_worker():
            try:
                r = _requests.post(
                    f"{BASE_URL}/api/chat",
                    json={"model": model,
                          "messages": list(self._history),
                          "stream": True},
                    stream=True, timeout=120,
                )
                r.raise_for_status()
                full = []
                for line in r.iter_lines():
                    if line:
                        try:
                            c = json.loads(line)
                            tok = c.get("message", {}).get("content", "")
                            if tok:
                                full.append(tok)
                                on_tok(tok)
                        except json.JSONDecodeError:
                            pass
                self._history.append({"role": "assistant", "content": "".join(full)})
                with metrics.lock:
                    metrics.context_tokens = sum(len(m["content"].split())
                                                  for m in self._history)
            except Exception as e:
                on_tok(f"\n[Error: {e}]")
                self.app.requests_table.add_request("ERR", text, 0, 0)
            on_done()

        threading.Thread(target=_stream_worker, daemon=True).start()

    # ── Task Board ────────────────────────────────────────────────────────────

    def _build_tasks(self, frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self._task_scroll = ctk.CTkScrollableFrame(frame, fg_color=BG, corner_radius=8)
        self._task_scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        self._task_scroll.columnconfigure(0, weight=1)

        add_row = ctk.CTkFrame(frame, fg_color="transparent")
        add_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        add_row.columnconfigure(0, weight=1)
        self._task_entry = ctk.CTkEntry(add_row, placeholder_text="New task…",
                                        font=("Segoe UI", 11), height=32,
                                        fg_color=CARD2, border_color=BORDER)
        self._task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(add_row, text="+ Add", width=70, height=32,
                      fg_color=ACCENT_ORG, hover_color="#ea6a0a",
                      text_color=BG, font=("Segoe UI", 10, "bold"),
                      command=self._add_task).grid(row=0, column=1)

        self._tasks = [
            {"label": "Connect to Herama backend", "state": "done"},
            {"label": "Load a GGUF model",         "state": "todo"},
            {"label": "Test streaming chat",        "state": "todo"},
        ]
        self._render_tasks()

    def _add_task(self):
        t = self._task_entry.get().strip()
        if t:
            self._tasks.append({"label": t, "state": "todo"})
            self._task_entry.delete(0, "end")
            self._render_tasks()

    def _render_tasks(self):
        for w in self._task_scroll.winfo_children():
            w.destroy()
        cfg = {
            "done":        (ACCENT_GRN, "✓", "Done"),
            "in_progress": (YELLOW,     "⟳", "In Progress"),
            "todo":        (DIM,        "○", "Todo"),
        }
        for i, task in enumerate(self._tasks):
            color, icon, lbl = cfg[task["state"]]
            card = ctk.CTkFrame(self._task_scroll, fg_color=CARD2, corner_radius=8)
            card.grid(sticky="ew", padx=4, pady=3)
            card.columnconfigure(1, weight=1)
            _label(card, icon, 13, bold=True, color=color, width=26).grid(
                row=0, column=0, padx=(10, 4), pady=8)
            _label(card, task["label"], 11, anchor="w").grid(row=0, column=1, sticky="w")
            _label(card, lbl, 9, color=color).grid(row=0, column=2, padx=6)
            ctk.CTkButton(card, text="▶", width=26, height=26,
                          fg_color="transparent", hover_color=ACCENT_ORG,
                          command=lambda idx=i: self._cycle(idx)).grid(
                row=0, column=3, padx=(0, 8))

    def _cycle(self, idx):
        s = ["todo", "in_progress", "done"]
        cur = self._tasks[idx]["state"]
        self._tasks[idx]["state"] = s[(s.index(cur) + 1) % len(s)]
        self._render_tasks()


# ─────────────────────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────────────────────

class HeramaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Herama  —  Local LLM Infrastructure")
        self.geometry("1440x900")
        self.minsize(1100, 700)
        self.configure(fg_color=BG)

        self.active_model: str | None = None
        self.context_length: int = 4096

        # ── layout grid ──
        # col 0: left sidebar | col 1: main dashboard (weight)
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # left sidebar
        self._left = LeftSidebar(self, app=self)
        self._left.grid(row=0, column=0, sticky="nsew")

        # main area (right of sidebar)
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=1)

        # ── TOP ROW CARDS ──
        cards_row = ctk.CTkFrame(main, fg_color="transparent")
        cards_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 6))
        for i in range(4):
            cards_row.columnconfigure(i, weight=1)

        self._spark_card   = SparkCard(cards_row)
        self._ram_card     = GaugeCard(cards_row, "RAM FOOTPRINT", RAM_TOTAL_GB,  ACCENT_GRN)
        self._vram_card    = GaugeCard(cards_row, "VRAM FOOTPRINT", VRAM_TOTAL_GB, ACCENT_ORG)
        self._experts_card = ExpertsCard(cards_row)

        for col, card in enumerate([self._spark_card, self._ram_card,
                                     self._vram_card, self._experts_card]):
            card.grid(row=0, column=col, sticky="nsew", padx=5)

        # ── MIDDLE ROW: donut + requests ──
        mid = ctk.CTkFrame(main, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        mid.columnconfigure(0, weight=0, minsize=210)
        mid.columnconfigure(1, weight=1)

        self._donut  = ContextDonut(mid)
        self._donut.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.requests_table = RequestsTable(mid)
        self.requests_table.grid(row=0, column=1, sticky="nsew")

        # ── WORKSPACE (chat + tasks) ──
        self._workspace = WorkspaceArea(main, app=self)
        self._workspace.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # start polling
        self._left._refresh_models()
        self._tick()

    # ── periodic UI refresh (runs on main thread via after()) ──

    def _tick(self):
        with metrics.lock:
            connected   = metrics.connected
            model       = metrics.active_model
            ram         = metrics.ram_used_gb
            vram        = metrics.vram_used_gb
            tps         = metrics.tps
            history     = list(metrics.tps_history)
            gpu         = metrics.gpu_layers
            cpu         = metrics.cpu_layers
            n_ctx       = metrics.n_ctx
            ctx_toks    = metrics.context_tokens
            skills      = dict(metrics.skills)

        if model:
            self.active_model = model

        self._left.set_status(connected, model)
        self._left.update_skills(skills)
        self._spark_card.update(tps, history)
        self._ram_card.update(ram)
        self._vram_card.update(vram)
        self._experts_card.update(gpu, cpu, model)
        self._donut.update(ctx_toks, n_ctx or self.context_length)

        self.after(POLL_MS, self._tick)

    # ── public helpers ──

    def log(self, msg: str):
        pass  # no standalone log panel; requests_table + status pill cover it

    def load_model(self, name: str):
        def _w():
            try:
                _requests.post(f"{BASE_URL}/api/generate",
                               json={"model": name, "prompt": "", "stream": False},
                               timeout=60)
                self.active_model = name
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()

    def download_model(self, card):
        def _w():
            from app.hf_manager import download_model, DownloadProgress
            try:
                download_model(card.repo_id, card.filename, config.MODELS_DIR)
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────

def main():
    # start hardware poll in background
    app = HeramaApp()
    t = threading.Thread(target=_poll_loop, args=(app,), daemon=True)
    t.start()
    app.mainloop()


if __name__ == "__main__":
    main()
