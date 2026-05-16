"""Pure helpers shared across pipeline phases: slugify, date parsing,
filename formatting, video-id extraction, VTT cleaning."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pandas as pd


def fix_encoding(text: str) -> str:
    """Best-effort mojibake repair via latin-1 round-trip.
    Handles the common case of utf-8 bytes mis-decoded as latin-1
    (e.g. 'Ã©' -> 'é', '\\u00e2\\u0080\\u0099' -> ''')."""
    if not isinstance(text, str):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def slugify(text: str) -> str:
    if not text:
        return "untitled"
    text = fix_encoding(text).lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] or "untitled"


def parse_date(raw) -> dict:
    """Return both representations: filename (YYYY-MM-DD for sortability) and iso."""
    empty = {"iso": "", "filename": "0000-00-00"}
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return empty
    raw = str(raw).strip().split(".")[0]
    if not raw or raw.lower() == "nan":
        return empty

    if re.match(r"^\d{8}$", raw):
        try:
            dt = datetime.strptime(raw, "%Y%m%d")
            iso = dt.strftime("%Y-%m-%d")
            return {"iso": iso, "filename": iso}
        except ValueError:
            return empty

    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            iso = dt.strftime("%Y-%m-%d")
            return {"iso": iso, "filename": iso}
        except ValueError:
            return empty

    return empty


def extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else (url or "").split("/")[-1]


_EPISODE_PATTERNS = [
    r"(?i)\bEp(?:isode)?\.?\s*#?(\d+)\b",
    r"(?<!\d)#(\d{2,4})(?!\d)",
    r"(?<!\d)(\d{3,4})(?!\d)",
]


def extract_episode(title: str, fallback: str = "") -> str:
    if fallback and str(fallback).strip() not in ("nan", ""):
        return str(fallback).strip()
    for pat in _EPISODE_PATTERNS:
        m = re.search(pat, title or "")
        if m:
            return m.group(1)
    return ""


def make_filename(date_filename: str, title: str, video_id: str) -> str:
    return f"{date_filename or '0000-00-00'}_{slugify(title)}_{video_id}.json"


def parse_vtt(vtt_text: str) -> Optional[str]:
    """Strip WEBVTT headers, timestamps, HTML tags; dedupe consecutive lines.
    Returns cleaned text or None if under 100 characters."""
    lines = vtt_text.splitlines()
    seen: list[str] = []
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(x) for x in ("WEBVTT", "NOTE", "Kind:", "Language:")):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        if seen and seen[-1] == line:
            continue
        seen.append(line)
        out.append(line)
    text = re.sub(r"\s+", " ", " ".join(out)).strip()
    return text if len(text) > 100 else None


def channel_folder_name(channel_url: str, fallback: str = "Channel") -> str:
    """Derive a filesystem-safe folder name from a channel URL or title."""
    if channel_url:
        m = re.search(r"@([A-Za-z0-9_\-.]+)", channel_url)
        if m:
            return m.group(1)
        m = re.search(r"/(?:channel|c|user)/([A-Za-z0-9_\-.]+)", channel_url)
        if m:
            return m.group(1)
    return slugify(fallback)
