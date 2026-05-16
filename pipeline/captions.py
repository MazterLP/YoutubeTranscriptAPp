"""Phase 2: fetch existing YouTube captions for a single video AND its
metadata in one call. Returns (transcript_text_or_None, info_dict).

We use `extract_info(url, download=True)` instead of `download([url])`
because the return value gives us upload_date and title — which lets
phase 1 stay as a flat (fast) listing and saves a separate metadata fetch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yt_dlp

from .utils import parse_vtt


def fetch_captions(
    video_id: str,
    output_dir: Path,
    cookies: Optional[Path] = None,
    sleep_min: int = 8,
    sleep_max: int = 15,
) -> tuple[Optional[str], dict]:
    """Download VTT captions + grab info_dict.

    Returns:
        (transcript_text, info_dict) — transcript is None if no captions
        exist or the text is too short; info_dict is {} on extractor errors.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    tmp = Path(output_dir) / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "vtt",
        "outtmpl": str(tmp / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "sleep_interval": sleep_min,
        "max_sleep_interval": sleep_max,
        "sleep_interval_requests": 3,
        "retries": 5,
        "retry_sleep_functions": {
            "http": lambda n: min(30 * 2 ** n, 300),
        },
    }
    if cookies and Path(cookies).exists():
        ydl_opts["cookiefile"] = str(cookies)

    info: dict = {}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            raw = ydl.extract_info(url, download=True)
            info = raw or {}
    except Exception:
        _cleanup(tmp, video_id)
        return None, info

    vtt_files = list(tmp.glob(f"{video_id}*.vtt"))
    if not vtt_files:
        _cleanup(tmp, video_id)
        return None, info

    try:
        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
    finally:
        _cleanup(tmp, video_id)

    return parse_vtt(vtt_text), info


def _cleanup(tmp: Path, video_id: str) -> None:
    for f in tmp.glob(f"{video_id}*"):
        f.unlink(missing_ok=True)
