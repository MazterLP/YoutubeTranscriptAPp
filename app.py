"""YouTube Transcript Downloader — Tkinter GUI.

Run:
    python app.py

Two tabs:
  1. Transcript Downloader — download captions / Whisper transcripts from YouTube channels.
  2. Strategy Pipeline   — chunk → extract strategies → embed → search → generate PineScript.
"""

from __future__ import annotations

import calendar
import queue
import sys
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    BooleanVar,
    DISABLED,
    END,
    HORIZONTAL,
    NORMAL,
    StringVar,
    Tk,
    filedialog,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

from pipeline.orchestrator import Config, Orchestrator
from pipeline.utils import channel_folder_name

APP_DIR = Path(__file__).parent.resolve()
DEFAULT_OUTPUT = APP_DIR / "output"
DEFAULT_COOKIES = APP_DIR / "cookies.txt"
DEFAULT_SILVER = APP_DIR / "output" / "silver"
DEFAULT_GOLD = APP_DIR / "output" / "gold"
DEFAULT_CHROMA = str(APP_DIR / "output" / "chroma")
DEFAULT_STRATEGIES = APP_DIR / "output" / "strategies"
TEMPLATE_PATH = APP_DIR / "templates" / "strategy_skeleton.pine"
APP_ICON = APP_DIR / "icons8-youtube-studio-100.ico"

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
DEVICES = ["auto", "cuda", "cpu"]
WORKER_OPTIONS = ["1", "2", "3", "4"]


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.orch = Orchestrator()
        root.title("YouTube Transcript Downloader")
        root.geometry("860x720")

        # ── Transcript tab vars ───────────────────────────────────────────────
        self.var_url = StringVar()
        self.var_output = StringVar(value=str(DEFAULT_OUTPUT))
        self.var_cookies = StringVar(value=str(DEFAULT_COOKIES))
        self.var_channel = StringVar(value="")
        self.var_model = StringVar(value="medium")
        self.var_device = StringVar(value="auto")
        self.var_workers = StringVar(value="1")
        self.var_sleep_min = StringVar(value="8")
        self.var_sleep_max = StringVar(value="15")

        now = datetime.now()
        years = [str(y) for y in range(2005, now.year + 2)]
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        self.var_date_enabled = BooleanVar(value=False)
        self.var_from_year = StringVar(value=str(now.year - 2))
        self.var_from_month = StringVar(value="January")
        self.var_to_year = StringVar(value=str(now.year))
        self.var_to_month = StringVar(value=months[now.month - 1])
        self._year_options = years
        self._month_options = months

        self.var_url.trace_add("write", self._on_url_change)

        # ── Strategy tab vars ─────────────────────────────────────────────────
        self.var_bronze = StringVar(value=str(DEFAULT_OUTPUT))
        self.var_silver = StringVar(value=str(DEFAULT_SILVER))
        self.var_gold = StringVar(value=str(DEFAULT_GOLD))
        self.var_chroma = StringVar(value=DEFAULT_CHROMA)
        self.var_strat_out = StringVar(value=str(DEFAULT_STRATEGIES))
        self.var_ollama_model = StringVar(value="qwen3:14b")
        self.var_ollama_url = StringVar(value="http://localhost:11434")
        self.var_confidence = StringVar(value="0.6")
        self.var_embed_model = StringVar(value="all-MiniLM-L6-v2")
        self.var_query = StringVar()

        self._build_ui()
        if APP_ICON.exists():
            try:
                root.iconbitmap(str(APP_ICON))
            except Exception:
                pass
        self.root.after(100, self._drain_events)

    # ── UI layout ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        nb = ttk.Notebook(self.root)
        nb.pack(fill=BOTH, expand=True, padx=6, pady=6)

        tab1 = ttk.Frame(nb)
        tab2 = ttk.Frame(nb)
        nb.add(tab1, text="  Transcript Downloader  ")
        nb.add(tab2, text="  Strategy Pipeline  ")

        self._build_transcript_tab(tab1)
        self._build_strategy_tab(tab2)

    # ── Tab 1: Transcript Downloader ──────────────────────────────────────────
    def _build_transcript_tab(self, parent: ttk.Frame) -> None:
        pad = {"padx": 6, "pady": 4}

        inputs = ttk.LabelFrame(parent, text="Channel & paths")
        inputs.pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(inputs, text="Channel URL:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_url, width=70).grid(
            row=0, column=1, columnspan=2, sticky="we", **pad)

        ttk.Label(inputs, text="Channel name:").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_channel, width=40).grid(
            row=1, column=1, sticky="w", **pad)

        ttk.Label(inputs, text="Output folder:").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_output, width=55).grid(
            row=2, column=1, sticky="we", **pad)
        ttk.Button(inputs, text="Browse", command=self._pick_output).grid(row=2, column=2, **pad)

        ttk.Label(inputs, text="Cookies file:").grid(row=3, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_cookies, width=55).grid(
            row=3, column=1, sticky="we", **pad)
        ttk.Button(inputs, text="Browse", command=self._pick_cookies).grid(row=3, column=2, **pad)
        inputs.columnconfigure(1, weight=1)

        whisper = ttk.LabelFrame(parent, text="Whisper")
        whisper.pack(fill="x", padx=10, pady=4)

        ttk.Label(whisper, text="Model:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Combobox(whisper, textvariable=self.var_model, values=WHISPER_MODELS,
                     state="readonly", width=12).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(whisper, text="Device:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(whisper, textvariable=self.var_device, values=DEVICES,
                     state="readonly", width=8).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(whisper, text="Workers:").grid(row=0, column=4, sticky="e", **pad)
        ttk.Combobox(whisper, textvariable=self.var_workers, values=WORKER_OPTIONS,
                     state="readonly", width=4).grid(row=0, column=5, sticky="w", **pad)
        ttk.Label(whisper, text="Sleep between captions (sec):").grid(
            row=1, column=0, columnspan=2, sticky="e", **pad)
        ttk.Entry(whisper, textvariable=self.var_sleep_min, width=5).grid(
            row=1, column=2, sticky="w", **pad)
        ttk.Label(whisper, text="to").grid(row=1, column=3, sticky="w")
        ttk.Entry(whisper, textvariable=self.var_sleep_max, width=5).grid(
            row=1, column=4, sticky="w", **pad)

        date_frm = ttk.LabelFrame(parent, text="Date filter")
        date_frm.pack(fill="x", padx=10, pady=4)
        ttk.Checkbutton(date_frm, text="Only download videos between:",
                        variable=self.var_date_enabled,
                        command=self._toggle_date_filter).grid(
            row=0, column=0, columnspan=7, sticky="w", **pad)
        ttk.Label(date_frm, text="From:").grid(row=1, column=0, sticky="e", **pad)
        self._cb_from_year = ttk.Combobox(date_frm, textvariable=self.var_from_year,
                                           values=self._year_options, state=DISABLED, width=7)
        self._cb_from_year.grid(row=1, column=1, sticky="w", **pad)
        self._cb_from_month = ttk.Combobox(date_frm, textvariable=self.var_from_month,
                                            values=self._month_options, state=DISABLED, width=11)
        self._cb_from_month.grid(row=1, column=2, sticky="w", **pad)
        ttk.Label(date_frm, text="To:").grid(row=1, column=3, sticky="e", **pad)
        self._cb_to_year = ttk.Combobox(date_frm, textvariable=self.var_to_year,
                                         values=self._year_options, state=DISABLED, width=7)
        self._cb_to_year.grid(row=1, column=4, sticky="w", **pad)
        self._cb_to_month = ttk.Combobox(date_frm, textvariable=self.var_to_month,
                                          values=self._month_options, state=DISABLED, width=11)
        self._cb_to_month.grid(row=1, column=5, sticky="w", **pad)

        controls = ttk.Frame(parent)
        controls.pack(fill="x", padx=10, pady=6)
        self.btn_start = ttk.Button(controls, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(controls, text="Stop", command=self._stop, state=DISABLED)
        self.btn_stop.pack(side="left", padx=4)

        prog = ttk.LabelFrame(parent, text="Progress")
        prog.pack(fill="x", padx=10, pady=4)
        self.lbl_phase = ttk.Label(prog, text="Phase: idle")
        self.lbl_phase.grid(row=0, column=0, sticky="w", **pad)
        self.pbar = ttk.Progressbar(prog, orient=HORIZONTAL, mode="determinate")
        self.pbar.grid(row=0, column=1, sticky="we", **pad)
        self.lbl_counter = ttk.Label(prog, text="0 / 0")
        self.lbl_counter.grid(row=0, column=2, sticky="e", **pad)
        self.lbl_stats = ttk.Label(prog, text="Captions: 0   Whisper: 0   Skipped: 0   Failed: 0")
        self.lbl_stats.grid(row=1, column=0, columnspan=3, sticky="w", **pad)
        prog.columnconfigure(1, weight=1)

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=(4, 10))
        self.log = ScrolledText(log_frame, height=12, state=DISABLED, wrap="word")
        self.log.pack(fill=BOTH, expand=True, padx=4, pady=4)

    # ── Tab 2: Strategy Pipeline ──────────────────────────────────────────────
    def _build_strategy_tab(self, parent: ttk.Frame) -> None:
        from pipeline.strategy.orchestrator import StrategyConfig, StrategyOrchestrator
        self._strat_orch = StrategyOrchestrator()
        pad = {"padx": 6, "pady": 4}

        # Paths
        paths_frm = ttk.LabelFrame(parent, text="Folders")
        paths_frm.pack(fill="x", padx=10, pady=(10, 4))

        def _row(frm, label, var, row, browse_fn=None):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="e", **pad)
            ttk.Entry(frm, textvariable=var, width=55).grid(row=row, column=1, sticky="we", **pad)
            if browse_fn:
                ttk.Button(frm, text="Browse", command=browse_fn).grid(row=row, column=2, **pad)

        _row(paths_frm, "Transcripts (bronze):", self.var_bronze, 0,
             lambda: self._pick_dir(self.var_bronze))
        _row(paths_frm, "Silver chunks:", self.var_silver, 1,
             lambda: self._pick_dir(self.var_silver))
        _row(paths_frm, "Gold strategies:", self.var_gold, 2,
             lambda: self._pick_dir(self.var_gold))
        _row(paths_frm, "ChromaDB folder:", self.var_chroma, 3,
             lambda: self._pick_dir(self.var_chroma))
        _row(paths_frm, "Pine output folder:", self.var_strat_out, 4,
             lambda: self._pick_dir(self.var_strat_out))
        paths_frm.columnconfigure(1, weight=1)

        # Ollama settings
        ollama_frm = ttk.LabelFrame(parent, text="Ollama / Embeddings")
        ollama_frm.pack(fill="x", padx=10, pady=4)

        ttk.Label(ollama_frm, text="Model:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(ollama_frm, textvariable=self.var_ollama_model, width=18).grid(
            row=0, column=1, sticky="w", **pad)
        ttk.Label(ollama_frm, text="URL:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Entry(ollama_frm, textvariable=self.var_ollama_url, width=28).grid(
            row=0, column=3, sticky="w", **pad)
        ttk.Label(ollama_frm, text="Min confidence:").grid(row=0, column=4, sticky="e", **pad)
        ttk.Entry(ollama_frm, textvariable=self.var_confidence, width=6).grid(
            row=0, column=5, sticky="w", **pad)

        ttk.Label(ollama_frm, text="Embed model:").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(ollama_frm, textvariable=self.var_embed_model, width=28).grid(
            row=1, column=1, columnspan=2, sticky="w", **pad)

        # Pipeline buttons
        pipeline_frm = ttk.LabelFrame(parent, text="Pipeline")
        pipeline_frm.pack(fill="x", padx=10, pady=4)

        self.btn_clean = ttk.Button(pipeline_frm, text="1. Clean", command=self._strat_clean)
        self.btn_clean.pack(side="left", padx=6, pady=6)
        self.btn_extract = ttk.Button(pipeline_frm, text="2. Extract", command=self._strat_extract)
        self.btn_extract.pack(side="left", padx=6, pady=6)
        self.btn_ingest = ttk.Button(pipeline_frm, text="3. Ingest", command=self._strat_ingest)
        self.btn_ingest.pack(side="left", padx=6, pady=6)
        self.btn_pipeline = ttk.Button(pipeline_frm, text="▶  Full Pipeline",
                                        command=self._strat_pipeline)
        self.btn_pipeline.pack(side="left", padx=12, pady=6)
        self.btn_strat_stop = ttk.Button(pipeline_frm, text="Stop",
                                          command=self._strat_stop, state=DISABLED)
        self.btn_strat_stop.pack(side="left", padx=6, pady=6)

        # Search / Generate
        gen_frm = ttk.LabelFrame(parent, text="Search & Generate PineScript")
        gen_frm.pack(fill="x", padx=10, pady=4)

        ttk.Label(gen_frm, text="Query:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(gen_frm, textvariable=self.var_query, width=52).grid(
            row=0, column=1, sticky="we", **pad)
        ttk.Button(gen_frm, text="Search", command=self._strat_search).grid(
            row=0, column=2, **pad)
        ttk.Button(gen_frm, text="Generate .pine", command=self._strat_generate).grid(
            row=0, column=3, **pad)
        gen_frm.columnconfigure(1, weight=1)

        # Progress
        sprog = ttk.LabelFrame(parent, text="Progress")
        sprog.pack(fill="x", padx=10, pady=4)
        self.lbl_strat_phase = ttk.Label(sprog, text="Phase: idle")
        self.lbl_strat_phase.grid(row=0, column=0, sticky="w", **pad)
        self.strat_pbar = ttk.Progressbar(sprog, orient=HORIZONTAL, mode="determinate")
        self.strat_pbar.grid(row=0, column=1, sticky="we", **pad)
        self.lbl_strat_counter = ttk.Label(sprog, text="")
        self.lbl_strat_counter.grid(row=0, column=2, sticky="e", **pad)
        sprog.columnconfigure(1, weight=1)

        # Log
        slog_frame = ttk.LabelFrame(parent, text="Log")
        slog_frame.pack(fill=BOTH, expand=True, padx=10, pady=(4, 10))
        self.strat_log = ScrolledText(slog_frame, height=12, state=DISABLED, wrap="word")
        self.strat_log.pack(fill=BOTH, expand=True, padx=4, pady=4)

    # ── strategy tab helpers ──────────────────────────────────────────────────
    def _make_strat_cfg(self):
        from pipeline.strategy.orchestrator import StrategyConfig
        try:
            conf = float(self.var_confidence.get())
        except ValueError:
            conf = 0.6
        bronze = Path(self.var_bronze.get())
        if not bronze.exists():
            self._strat_log_line(f"ERROR: bronze folder not found: {bronze}")
            return None
        return StrategyConfig(
            bronze_dir=bronze,
            silver_dir=Path(self.var_silver.get()),
            gold_dir=Path(self.var_gold.get()),
            chroma_path=self.var_chroma.get(),
            strategies_dir=Path(self.var_strat_out.get()),
            template_path=TEMPLATE_PATH,
            ollama_model=self.var_ollama_model.get(),
            ollama_base_url=self.var_ollama_url.get(),
            min_confidence=conf,
            embed_model=self.var_embed_model.get(),
        )

    def _strat_set_running(self, running: bool) -> None:
        state_run = DISABLED if running else NORMAL
        state_stop = NORMAL if running else DISABLED
        for btn in (self.btn_clean, self.btn_extract, self.btn_ingest, self.btn_pipeline):
            btn.configure(state=state_run)
        self.btn_strat_stop.configure(state=state_stop)

    def _strat_clean(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        self._strat_set_running(True)
        self._strat_log_line("=== Clean ===")
        from pipeline.strategy.orchestrator import StrategyOrchestrator
        self._strat_orch = StrategyOrchestrator()

        def _run():
            from pipeline.strategy.cleaner import clean_all
            chunks = clean_all(cfg.bronze_dir, cfg.silver_dir,
                               cfg.max_words, cfg.overlap_words,
                               log=lambda m: self._strat_orch.events.put({"kind": "log", "payload": m}))
            self._strat_orch.events.put({"kind": "log", "payload": f"Total: {len(chunks)} chunks"})
            self._strat_orch.events.put({"kind": "done", "payload": "ok"})

        import threading
        self._strat_orch._thread = threading.Thread(target=_run, daemon=True)
        self._strat_orch._thread.start()

    def _strat_extract(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        self._strat_set_running(True)
        self._strat_log_line("=== Extract ===")
        from pipeline.strategy.orchestrator import StrategyOrchestrator

        def _run():
            from pipeline.strategy.extractor import extract_all
            strats = extract_all(
                silver_dir=cfg.silver_dir, gold_dir=cfg.gold_dir,
                model=cfg.ollama_model, base_url=cfg.ollama_base_url,
                temperature=cfg.ollama_temperature, timeout=cfg.ollama_timeout,
                min_confidence=cfg.min_confidence,
                log=lambda m: self._strat_orch.events.put({"kind": "log", "payload": m}),
                on_progress=lambda d, t: self._strat_orch.events.put({"kind": "progress", "payload": {"done": d, "total": t}}),
                stop_check=self._strat_orch.stop_event.is_set,
            )
            self._strat_orch.events.put({"kind": "log", "payload": f"Total: {len(strats)} strategies"})
            self._strat_orch.events.put({"kind": "done", "payload": "ok"})

        import threading
        self._strat_orch._thread = threading.Thread(target=_run, daemon=True)
        self._strat_orch._thread.start()

    def _strat_ingest(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        self._strat_set_running(True)
        self._strat_log_line("=== Ingest ===")
        from pipeline.strategy.orchestrator import StrategyOrchestrator

        def _run():
            from pipeline.strategy.vectorstore import ingest_all
            n_c, n_s = ingest_all(
                silver_dir=cfg.silver_dir, gold_dir=cfg.gold_dir,
                chroma_path=cfg.chroma_path, embed_model=cfg.embed_model,
                log=lambda m: self._strat_orch.events.put({"kind": "log", "payload": m}),
                on_progress=lambda d, t: self._strat_orch.events.put({"kind": "progress", "payload": {"done": d, "total": t}}),
            )
            self._strat_orch.events.put({"kind": "log", "payload": f"Done: {n_c} chunks + {n_s} strategies in ChromaDB"})
            self._strat_orch.events.put({"kind": "done", "payload": "ok"})

        import threading
        self._strat_orch._thread = threading.Thread(target=_run, daemon=True)
        self._strat_orch._thread.start()

    def _strat_pipeline(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        self._strat_set_running(True)
        self._strat_log_line("=== Full Pipeline ===")
        from pipeline.strategy.orchestrator import StrategyOrchestrator
        self._strat_orch = StrategyOrchestrator()
        self._strat_orch.start_pipeline(cfg)

    def _strat_search(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        query = self.var_query.get().strip()
        if not query:
            self._strat_log_line("ERROR: enter a query first.")
            return
        self._strat_set_running(True)
        from pipeline.strategy.orchestrator import StrategyOrchestrator
        self._strat_orch = StrategyOrchestrator()
        self._strat_orch.start_search(cfg, query)

    def _strat_generate(self) -> None:
        cfg = self._make_strat_cfg()
        if not cfg:
            return
        query = self.var_query.get().strip()
        if not query:
            self._strat_log_line("ERROR: enter a query first.")
            return
        self._strat_set_running(True)
        from pipeline.strategy.orchestrator import StrategyOrchestrator
        self._strat_orch = StrategyOrchestrator()
        self._strat_orch.start_generate(cfg, query)

    def _strat_stop(self) -> None:
        self._strat_orch.stop()
        self.btn_strat_stop.configure(state=DISABLED)

    def _pick_dir(self, var: StringVar) -> None:
        chosen = filedialog.askdirectory(initialdir=var.get() or str(APP_DIR))
        if chosen:
            var.set(chosen)

    # ── event pump (shared, drains both orchestrators) ────────────────────────
    def _drain_events(self) -> None:
        # Transcript orchestrator
        try:
            while True:
                evt = self.orch.events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass
        if not self.orch.is_running():
            self.btn_start.configure(state=NORMAL)
            self.btn_stop.configure(state=DISABLED)

        # Strategy orchestrator
        if hasattr(self, "_strat_orch"):
            try:
                while True:
                    evt = self._strat_orch.events.get_nowait()
                    self._handle_strat_event(evt)
            except queue.Empty:
                pass
            if not self._strat_orch.is_running():
                self._strat_set_running(False)

        self.root.after(100, self._drain_events)

    def _handle_strat_event(self, evt: dict) -> None:
        kind = evt["kind"]
        payload = evt["payload"]
        if kind == "log":
            self._strat_log_line(str(payload))
        elif kind == "phase":
            self.lbl_strat_phase.configure(text=f"Phase: {payload}")
            self.strat_pbar.configure(value=0, maximum=100)
            self.lbl_strat_counter.configure(text="")
            self._strat_log_line(f"--- {payload} ---")
        elif kind == "progress":
            done = payload.get("done", 0)
            total = max(payload.get("total", 1), 1)
            self.strat_pbar.configure(maximum=total, value=done)
            self.lbl_strat_counter.configure(text=f"{done} / {total}")
        elif kind == "done":
            self.lbl_strat_phase.configure(text="Phase: done")

    def _strat_log_line(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.strat_log.configure(state=NORMAL)
        self.strat_log.insert(END, f"[{ts}] {msg}\n")
        self.strat_log.see(END)
        self.strat_log.configure(state=DISABLED)

    # ── Transcript tab helpers ────────────────────────────────────────────────
    def _pick_output(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.var_output.get() or str(APP_DIR))
        if chosen:
            self.var_output.set(chosen)

    def _pick_cookies(self) -> None:
        chosen = filedialog.askopenfilename(
            initialdir=str(APP_DIR),
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if chosen:
            self.var_cookies.set(chosen)

    def _toggle_date_filter(self) -> None:
        state = "readonly" if self.var_date_enabled.get() else DISABLED
        for cb in (self._cb_from_year, self._cb_from_month, self._cb_to_year, self._cb_to_month):
            cb.configure(state=state)

    def _on_url_change(self, *_) -> None:
        url = self.var_url.get().strip()
        if not url:
            return
        name = channel_folder_name(url)
        if name and name != "channel":
            self.var_channel.set(name)

    def _start(self) -> None:
        url = self.var_url.get().strip()
        if not url:
            self._log_line("ERROR: please enter a channel URL.")
            return
        try:
            sleep_min = int(self.var_sleep_min.get())
            sleep_max = int(self.var_sleep_max.get())
            workers = int(self.var_workers.get())
        except ValueError:
            self._log_line("ERROR: sleep values and workers must be integers.")
            return
        if sleep_min < 0 or sleep_max < sleep_min:
            self._log_line("ERROR: invalid sleep range.")
            return

        cookies_path = Path(self.var_cookies.get()) if self.var_cookies.get() else None
        if cookies_path and not cookies_path.exists():
            self._log_line(f"WARN: cookies file not found at {cookies_path} — continuing without.")
            cookies_path = None

        date_from: "Date | None" = None
        date_to:   "Date | None" = None
        if self.var_date_enabled.get():
            try:
                from_y = int(self.var_from_year.get())
                from_m = self._month_options.index(self.var_from_month.get()) + 1
                date_from = Date(from_y, from_m, 1)
                to_y = int(self.var_to_year.get())
                to_m = self._month_options.index(self.var_to_month.get()) + 1
                last_day = calendar.monthrange(to_y, to_m)[1]
                date_to = Date(to_y, to_m, last_day)
                if date_from > date_to:
                    self._log_line("ERROR: 'From' date is after 'To' date.")
                    return
            except (ValueError, IndexError):
                self._log_line("ERROR: invalid date range selection.")
                return

        cfg = Config(
            channel_url=url,
            output_root=Path(self.var_output.get()),
            cookies=cookies_path,
            whisper_model=self.var_model.get(),
            whisper_device=self.var_device.get(),
            whisper_workers=workers,
            sleep_min=sleep_min,
            sleep_max=sleep_max,
            channel_name=self.var_channel.get() or "Channel",
            date_from=date_from,
            date_to=date_to,
        )
        self.btn_start.configure(state=DISABLED)
        self.btn_stop.configure(state=NORMAL)
        self._log_line("=" * 60)
        self._log_line(f"Starting pipeline for: {url}")
        if date_from or date_to:
            self._log_line(f"Date filter: {date_from or 'any'} -> {date_to or 'any'}")
        self.orch.start(cfg)

    def _stop(self) -> None:
        self.orch.stop()
        self.btn_stop.configure(state=DISABLED)

    def _handle_event(self, evt: dict) -> None:
        kind = evt["kind"]
        payload = evt["payload"]
        if kind == "log":
            self._log_line(str(payload))
        elif kind == "phase":
            self.lbl_phase.configure(text=f"Phase: {payload}")
            self.pbar.configure(value=0, maximum=100)
            self.lbl_counter.configure(text="0 / 0")
            self._log_line(f"--- Phase: {payload} ---")
        elif kind == "progress":
            done = payload.get("done", 0)
            total = max(payload.get("total", 1), 1)
            self.pbar.configure(maximum=total, value=done)
            self.lbl_counter.configure(text=f"{done} / {total}")
        elif kind == "stats":
            s = payload
            self.lbl_stats.configure(
                text=(
                    f"Captions: {s.captions_saved}   "
                    f"Whisper: {s.whisper_saved}   "
                    f"Skipped: {s.skipped}   "
                    f"Failed: {s.failed}"
                )
            )
        elif kind == "done":
            s = payload
            self.lbl_phase.configure(text="Phase: done")
            self._log_line(
                "=" * 60 + "\n"
                f"DONE — captions: {s.captions_saved}, whisper: {s.whisper_saved}, "
                f"skipped: {s.skipped}, failed: {s.failed}"
            )

    def _log_line(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state=NORMAL)
        self.log.insert(END, f"[{ts}] {msg}\n")
        self.log.see(END)
        self.log.configure(state=DISABLED)


def main() -> None:
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
