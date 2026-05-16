"""YouTube Transcript Downloader — Tkinter GUI.

Run:
    python app.py

The GUI runs on the main thread; the pipeline runs in a background thread
inside `pipeline.orchestrator.Orchestrator`. Communication is via a
`queue.Queue` that this module drains every 100ms.
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
APP_ICON = APP_DIR / "icons8-youtube-studio-100.ico"

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
DEVICES = ["auto", "cuda", "cpu"]
WORKER_OPTIONS = ["1", "2", "3", "4"]


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.orch = Orchestrator()
        root.title("YouTube Transcript Downloader")
        root.geometry("820x640")

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
            "January","February","March","April","May","June",
            "July","August","September","October","November","December"
        ]
        self.var_date_enabled = BooleanVar(value=False)
        self.var_from_year  = StringVar(value=str(now.year - 2))
        self.var_from_month = StringVar(value="January")
        self.var_to_year    = StringVar(value=str(now.year))
        self.var_to_month   = StringVar(value=months[now.month - 1])
        self._year_options  = years
        self._month_options = months

        self.var_url.trace_add("write", self._on_url_change)

        self._build_ui()
        if APP_ICON.exists():
            root.iconbitmap(str(APP_ICON))
        self.root.after(100, self._drain_events)

    # ── UI layout ─────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        pad = {"padx": 6, "pady": 4}

        # Inputs frame
        inputs = ttk.LabelFrame(self.root, text="Channel & paths")
        inputs.pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(inputs, text="Channel URL:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_url, width=70).grid(
            row=0, column=1, columnspan=2, sticky="we", **pad
        )

        ttk.Label(inputs, text="Channel name:").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_channel, width=40).grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Label(inputs, text="Output folder:").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_output, width=55).grid(
            row=2, column=1, sticky="we", **pad
        )
        ttk.Button(inputs, text="Browse", command=self._pick_output).grid(
            row=2, column=2, **pad
        )

        ttk.Label(inputs, text="Cookies file:").grid(row=3, column=0, sticky="e", **pad)
        ttk.Entry(inputs, textvariable=self.var_cookies, width=55).grid(
            row=3, column=1, sticky="we", **pad
        )
        ttk.Button(inputs, text="Browse", command=self._pick_cookies).grid(
            row=3, column=2, **pad
        )

        inputs.columnconfigure(1, weight=1)

        # Whisper settings
        whisper = ttk.LabelFrame(self.root, text="Whisper")
        whisper.pack(fill="x", padx=10, pady=4)

        ttk.Label(whisper, text="Model:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Combobox(
            whisper, textvariable=self.var_model, values=WHISPER_MODELS,
            state="readonly", width=12,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(whisper, text="Device:").grid(row=0, column=2, sticky="e", **pad)
        ttk.Combobox(
            whisper, textvariable=self.var_device, values=DEVICES,
            state="readonly", width=8,
        ).grid(row=0, column=3, sticky="w", **pad)

        ttk.Label(whisper, text="Workers:").grid(row=0, column=4, sticky="e", **pad)
        ttk.Combobox(
            whisper, textvariable=self.var_workers, values=WORKER_OPTIONS,
            state="readonly", width=4,
        ).grid(row=0, column=5, sticky="w", **pad)

        ttk.Label(whisper, text="Sleep between captions (sec):").grid(
            row=1, column=0, columnspan=2, sticky="e", **pad
        )
        ttk.Entry(whisper, textvariable=self.var_sleep_min, width=5).grid(
            row=1, column=2, sticky="w", **pad
        )
        ttk.Label(whisper, text="to").grid(row=1, column=3, sticky="w")
        ttk.Entry(whisper, textvariable=self.var_sleep_max, width=5).grid(
            row=1, column=4, sticky="w", **pad
        )

        # Date filter
        date_frm = ttk.LabelFrame(self.root, text="Date filter")
        date_frm.pack(fill="x", padx=10, pady=4)

        ttk.Checkbutton(
            date_frm, text="Only download videos between:",
            variable=self.var_date_enabled,
            command=self._toggle_date_filter,
        ).grid(row=0, column=0, columnspan=7, sticky="w", **pad)

        ttk.Label(date_frm, text="From:").grid(row=1, column=0, sticky="e", **pad)
        self._cb_from_year = ttk.Combobox(
            date_frm, textvariable=self.var_from_year,
            values=self._year_options, state=DISABLED, width=7,
        )
        self._cb_from_year.grid(row=1, column=1, sticky="w", **pad)
        self._cb_from_month = ttk.Combobox(
            date_frm, textvariable=self.var_from_month,
            values=self._month_options, state=DISABLED, width=11,
        )
        self._cb_from_month.grid(row=1, column=2, sticky="w", **pad)

        ttk.Label(date_frm, text="To:").grid(row=1, column=3, sticky="e", **pad)
        self._cb_to_year = ttk.Combobox(
            date_frm, textvariable=self.var_to_year,
            values=self._year_options, state=DISABLED, width=7,
        )
        self._cb_to_year.grid(row=1, column=4, sticky="w", **pad)
        self._cb_to_month = ttk.Combobox(
            date_frm, textvariable=self.var_to_month,
            values=self._month_options, state=DISABLED, width=11,
        )
        self._cb_to_month.grid(row=1, column=5, sticky="w", **pad)

        # Controls
        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=10, pady=6)
        self.btn_start = ttk.Button(controls, text="Start", command=self._start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(
            controls, text="Stop", command=self._stop, state=DISABLED
        )
        self.btn_stop.pack(side="left", padx=4)

        # Progress
        prog = ttk.LabelFrame(self.root, text="Progress")
        prog.pack(fill="x", padx=10, pady=4)
        self.lbl_phase = ttk.Label(prog, text="Phase: idle")
        self.lbl_phase.grid(row=0, column=0, sticky="w", **pad)
        self.pbar = ttk.Progressbar(prog, orient=HORIZONTAL, mode="determinate")
        self.pbar.grid(row=0, column=1, sticky="we", **pad)
        self.lbl_counter = ttk.Label(prog, text="0 / 0")
        self.lbl_counter.grid(row=0, column=2, sticky="e", **pad)
        self.lbl_stats = ttk.Label(
            prog, text="Captions: 0   Whisper: 0   Skipped: 0   Failed: 0"
        )
        self.lbl_stats.grid(row=1, column=0, columnspan=3, sticky="w", **pad)
        prog.columnconfigure(1, weight=1)

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=(4, 10))
        self.log = ScrolledText(log_frame, height=15, state=DISABLED, wrap="word")
        self.log.pack(fill=BOTH, expand=True, padx=4, pady=4)

    # ── button handlers ───────────────────────────────────────────────
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
        for cb in (self._cb_from_year, self._cb_from_month,
                   self._cb_to_year, self._cb_to_month):
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
            self._log_line(
                f"WARN: cookies file not found at {cookies_path} — continuing without."
            )
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
            self._log_line(
                f"Date filter: {date_from or 'any'} -> {date_to or 'any'}"
            )
        self.orch.start(cfg)

    def _stop(self) -> None:
        self.orch.stop()
        self.btn_stop.configure(state=DISABLED)

    # ── event pump ────────────────────────────────────────────────────
    def _drain_events(self) -> None:
        try:
            while True:
                evt = self.orch.events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass

        if not self.orch.is_running():
            self.btn_start.configure(state=NORMAL)
            self.btn_stop.configure(state=DISABLED)

        self.root.after(100, self._drain_events)

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
