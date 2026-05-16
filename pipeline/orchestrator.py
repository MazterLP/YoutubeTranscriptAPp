"""Coordinates the three pipeline phases inside a worker thread.

The GUI thread instantiates `Orchestrator`, calls `start(...)` to launch
the pipeline in a daemon thread, and polls `events` (a queue.Queue) every
~100ms to update labels and the log textarea.

Stop is cooperative: setting `stop_event` causes the orchestrator to exit
at the next safe point — between videos in the captions phase, and after
each in-flight Whisper future completes.
"""

from __future__ import annotations

import json
import queue
import random
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Optional

import pandas as pd

from . import captions, channel, whisper_worker
from .utils import (
    channel_folder_name,
    extract_episode,
    extract_video_id,
    fix_encoding,
    make_filename,
    parse_date,
)


@dataclass
class Config:
    channel_url: str
    output_root: Path
    cookies: Optional[Path]
    whisper_model: str = "medium"
    whisper_device: str = "auto"
    whisper_workers: int = 1
    sleep_min: int = 8
    sleep_max: int = 15
    channel_name: str = "Channel"
    date_from: Optional[Date] = None   # inclusive lower bound (first day of month)
    date_to: Optional[Date] = None     # inclusive upper bound (last day of month)


def _in_date_range(date_str: str, cfg: "Config") -> Optional[bool]:
    """Check if a YYYY-MM-DD date string is within cfg.date_from/date_to.

    Returns:
        True  → in range (or no filter set)
        False → out of range → skip this video
        None  → date unknown → can't decide; caller should proceed and check later
    """
    if not cfg.date_from and not cfg.date_to:
        return True
    if not date_str:
        return None  # unknown — include tentatively
    try:
        video_date = Date.fromisoformat(date_str)
    except ValueError:
        return None
    if cfg.date_from and video_date < cfg.date_from:
        return False
    if cfg.date_to and video_date > cfg.date_to:
        return False
    return True


@dataclass
class Stats:
    total: int = 0
    captions_saved: int = 0
    whisper_saved: int = 0
    skipped: int = 0
    failed: int = 0
    failed_videos: list[dict] = field(default_factory=list)


class Orchestrator:
    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats = Stats()

    # ── public API ────────────────────────────────────────────────────
    def start(self, cfg: Config) -> None:
        if self._thread and self._thread.is_alive():
            self._emit("log", "Pipeline already running.")
            return
        self.stop_event.clear()
        self.stats = Stats()
        self._thread = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._emit("log", "Stop requested — finishing current video then exiting...")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── internals ─────────────────────────────────────────────────────
    def _emit(self, kind: str, payload) -> None:
        self.events.put({"kind": kind, "payload": payload})

    def _log(self, msg: str) -> None:
        self._emit("log", msg)

    def _run(self, cfg: Config) -> None:
        try:
            folder = channel_folder_name(cfg.channel_url, cfg.channel_name)
            channel_dir = Path(cfg.output_root) / folder
            channel_dir.mkdir(parents=True, exist_ok=True)
            csv_path = channel_dir / "videos.csv"

            self._emit("phase", "Channel metadata")
            self._log(f"Output folder: {channel_dir}")
            channel.fetch_channel_csv(
                channel_url=cfg.channel_url,
                output_csv=csv_path,
                cookies=cfg.cookies,
                log=self._log,
                on_progress=lambda done, total: self._emit(
                    "progress", {"done": done, "total": total}
                ),
            )
            if self.stop_event.is_set():
                self._log("Stopped after channel fetch.")
                return

            self._captions_phase(cfg, channel_dir, csv_path)
            if self.stop_event.is_set():
                self._log("Stopped after captions phase.")
                self._emit("done", self.stats)
                return

            if self.stats.failed_videos:
                self._whisper_phase(cfg, channel_dir)

            self._emit("done", self.stats)
        except Exception as e:
            self._log(f"FATAL: {e}")
            self._emit("done", self.stats)

    # ── phase 2 ───────────────────────────────────────────────────────
    def _captions_phase(self, cfg: Config, channel_dir: Path, csv_path: Path) -> None:
        self._emit("phase", "Captions")
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="latin-1")

        total = len(df)
        self.stats.total = total
        self._log(f"Loaded {total} videos from {csv_path.name}")

        for idx in range(1, total + 1):
            if self.stop_event.is_set():
                return

            row = df.iloc[idx - 1]
            url = str(row.get("URL", "")).strip()
            if not url:
                continue
            csv_title = fix_encoding(str(row.get("Title", "")))
            ep_raw = row.get("Episode", "")

            # Prefer the explicit VideoID column (new schema); fall back to
            # parsing it out of the URL for older CSVs.
            csv_vid = str(row.get("VideoID", "") or "").strip()
            video_id = csv_vid if csv_vid else extract_video_id(url)
            csv_date = str(row.get("UploadDate", "") or "").strip()

            self._emit("progress", {"done": idx, "total": total})

            # Date filter — if we already know the upload date from the CSV,
            # skip entirely (no YouTube request needed).
            date_check = _in_date_range(csv_date, cfg)
            if date_check is False:
                self.stats.skipped += 1
                self._emit("stats", self.stats)
                continue

            # Pre-check: if a JSON for this video_id already exists under any
            # date, skip without hitting YouTube at all.
            existing = next(channel_dir.glob(f"*_{video_id}.json"), None)
            if existing:
                self.stats.skipped += 1
                self._emit("stats", self.stats)
                continue

            self._log(f"[{idx}/{total}] captions: {csv_title[:60]}")
            text, info = captions.fetch_captions(
                video_id=video_id,
                output_dir=channel_dir,
                cookies=cfg.cookies,
                sleep_min=cfg.sleep_min,
                sleep_max=cfg.sleep_max,
            )

            # Prefer fresh info_dict values when available; fall back to CSV.
            title = fix_encoding(info.get("title") or csv_title)
            upload_date = info.get("upload_date", "") or csv_date
            date_info = parse_date(upload_date)
            episode = extract_episode(title, str(ep_raw))

            # Second date check using the fresh date from info_dict (covers
            # videos where the CSV had no UploadDate from flat extraction).
            if date_check is None and _in_date_range(date_info["iso"], cfg) is False:
                self.stats.skipped += 1
                self._log(f"    skipped (date {date_info['iso'] or '?'} out of range)")
                self._emit("stats", self.stats)
                if idx < total and not self.stop_event.is_set():
                    time.sleep(random.uniform(cfg.sleep_min, cfg.sleep_max))
                continue

            filename = make_filename(date_info["filename"], title, video_id)
            out_path = channel_dir / filename

            if text:
                payload = {
                    "video_id": video_id,
                    "episode": episode,
                    "channel": cfg.channel_name,
                    "title": title,
                    "url": url,
                    "publish_date": date_info["iso"],
                    "word_count": len(text.split()),
                    "transcript": text,
                }
                _write_json(out_path, payload)
                self.stats.captions_saved += 1
                self._log(f"    saved ({payload['word_count']:,} words)")
            else:
                self.stats.failed_videos.append(
                    {
                        "url": url,
                        "title": title,
                        "episode": episode,
                        "publish_date": date_info["iso"],
                        "filename": filename,
                        "reason": "No captions" if info else "Extractor error",
                    }
                )
                self._log("    no captions -> queued for Whisper")

            self._emit("stats", self.stats)

            if idx < total and not self.stop_event.is_set():
                time.sleep(random.uniform(cfg.sleep_min, cfg.sleep_max))

        if self.stats.failed_videos:
            failed_csv = channel_dir / "_failed.csv"
            pd.DataFrame(self.stats.failed_videos).to_csv(
                failed_csv, index=False, encoding="utf-8-sig"
            )
            self._log(f"Wrote {failed_csv.name} ({len(self.stats.failed_videos)} videos)")

    # ── phase 3 ───────────────────────────────────────────────────────
    def _whisper_phase(self, cfg: Config, channel_dir: Path) -> None:
        self._emit("phase", "Whisper")
        temp_dir = channel_dir / "_temp_audio"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self._log(f"Loading Whisper '{cfg.whisper_model}' on {cfg.whisper_device}...")
        try:
            model, actual_device = whisper_worker.load_model(
                cfg.whisper_model, cfg.whisper_device
            )
        except Exception as e:
            self._log(f"Could not load Whisper model: {e}")
            return
        self._log(f"Model ready on {actual_device}")

        failures = self.stats.failed_videos
        total = len(failures)
        self.stats.failed_videos = []  # will repopulate with still-failed items

        def work(item: dict) -> dict:
            url = item["url"]
            video_id = extract_video_id(url)
            out_path = channel_dir / item["filename"]
            if out_path.exists():
                return {"item": item, "status": "skipped"}

            audio = whisper_worker.download_audio(
                video_id=video_id, temp_dir=temp_dir, cookies=cfg.cookies
            )
            if not audio:
                return {"item": item, "status": "download_failed"}

            try:
                result = whisper_worker.transcribe(audio, model)
            except Exception as e:
                audio.unlink(missing_ok=True)
                return {"item": item, "status": "transcribe_failed", "error": str(e)}

            audio.unlink(missing_ok=True)

            date_info = parse_date(item.get("publish_date", ""))
            payload = {
                "video_id": video_id,
                "episode": item.get("episode", ""),
                "channel": cfg.channel_name,
                "title": item.get("title", ""),
                "url": url,
                "publish_date": date_info["iso"] or item.get("publish_date", ""),
                "word_count": len(result.text.split()),
                "transcript": result.text,
                "language": result.language,
                "metadata": {
                    "whisper_model": cfg.whisper_model,
                    "device": actual_device,
                    "lang_prob": result.lang_prob,
                },
                "segments": result.segments,
            }
            _write_json(out_path, payload)
            return {"item": item, "status": "ok", "words": payload["word_count"]}

        workers = max(1, int(cfg.whisper_workers))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(work, it): it for it in failures}
            done = 0
            for fut in as_completed(futures):
                if self.stop_event.is_set():
                    for f in futures:
                        f.cancel()
                    break
                done += 1
                self._emit("progress", {"done": done, "total": total})
                try:
                    r = fut.result()
                except Exception as e:
                    self._log(f"  worker error: {e}")
                    continue

                item = r["item"]
                title = item.get("title", "")[:60]
                status = r["status"]
                if status == "ok":
                    self.stats.whisper_saved += 1
                    self._log(f"  whisper OK ({r['words']:,} words) — {title}")
                elif status == "skipped":
                    self.stats.skipped += 1
                else:
                    self.stats.failed += 1
                    self.stats.failed_videos.append(
                        {**item, "reason": status + (": " + r.get("error", "") if r.get("error") else "")}
                    )
                    self._log(f"  whisper FAIL ({status}) — {title}")
                self._emit("stats", self.stats)

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        if self.stats.failed_videos:
            ts = time.strftime("%Y%m%d_%H%M%S")
            rp = channel_dir / f"_failed_whisper_{ts}.csv"
            pd.DataFrame(self.stats.failed_videos).to_csv(
                rp, index=False, encoding="utf-8-sig"
            )
            self._log(f"Still-failed report: {rp.name}")


def _write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
