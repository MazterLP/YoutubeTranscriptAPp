"""Phase 1: list every video on a YouTube channel as fast as possible.

Uses extract_flat="in_playlist" so yt-dlp makes one request per playlist/tab
and returns lightweight entries (id, title, url) — no per-video HTTP.

Channel-root URLs (e.g. https://www.youtube.com/@handle) return TABS
(Videos / Live / Shorts) rather than videos with flat extraction. We detect
that case and recurse one level into each tab, deduping by video id.

This is the critical performance fix vs. extract_flat=False, which would
hit N+1 video URLs and get the IP rate-limited fast when anonymous.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from .utils import extract_episode


_TAB_SUFFIXES = ("videos", "live", "shorts", "streams", "podcasts", "releases")


def _normalize_channel_url(url: str) -> str:
    """Channel-root URLs return tabs with flat extraction. Appending /videos
    makes yt-dlp return the actual video list directly. We do this for any
    URL that doesn't already end in a known tab name."""
    url = (url or "").rstrip("/")
    if not url:
        return url
    # Already pointing at a tab? leave it alone.
    last = url.rsplit("/", 1)[-1].lower()
    if last in _TAB_SUFFIXES:
        return url
    # Looks like a channel root (@handle, /channel/UC..., /c/Name, /user/Name)?
    if (
        "/@" in url
        or "/channel/" in url
        or "/c/" in url
        or "/user/" in url
    ):
        return url + "/videos"
    return url


def _tab_url(tab: dict, channel_url: str) -> Optional[str]:
    """Find the best URL for a tab entry: prefer `url`, then `webpage_url`,
    then construct from the tab id + channel root."""
    for key in ("url", "webpage_url", "original_url"):
        val = tab.get(key)
        if val:
            return val
    tab_id = tab.get("id")
    if tab_id and channel_url:
        return channel_url.rstrip("/") + "/" + tab_id
    return None


def _is_video_entry(entry: dict) -> bool:
    """Heuristic: does this flat entry point at an actual video?"""
    if not entry:
        return False
    eid = entry.get("id", "") or ""
    url = entry.get("url", "") or ""
    if "watch?v=" in url or "youtu.be/" in url:
        return True
    if len(eid) == 11 and "/" not in eid and eid.lower() not in _TAB_SUFFIXES:
        return True
    return False


def _flat_entries(ydl: "yt_dlp.YoutubeDL", url: str) -> list[dict]:
    info = ydl.extract_info(url, download=False)
    if not info:
        return []
    return [e for e in (info.get("entries") or []) if e]


def fetch_channel_csv(
    channel_url: str,
    output_csv: Path,
    cookies: Optional[Path] = None,
    log: Callable[[str], None] = print,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> int:
    """Fetch the channel's video list (flat) and write a CSV. Returns row count.

    Idempotent: skips if the CSV already exists and is non-empty.
    """
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if output_csv.exists() and output_csv.stat().st_size > 0:
        with open(output_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        if "VideoID" in header and "UploadDate" in header and row_count > 0:
            log(f"  CSV already exists with {row_count} rows -> skipping channel fetch")
            return row_count
        log(f"  CSV has old/incomplete schema ({header}) -> regenerating")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
    }
    if cookies and Path(cookies).exists():
        ydl_opts["cookiefile"] = str(cookies)

    normalized = _normalize_channel_url(channel_url)
    if normalized != channel_url:
        log(f"  Normalised URL -> {normalized}")
    log(f"  Listing channel (flat) {normalized}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        entries = _flat_entries(ydl, normalized)

        if not entries:
            raise RuntimeError("Could not fetch channel info — check the URL and cookies.")

        # If we still got tabs (Videos / Live / Shorts), drill into each one.
        if not any(_is_video_entry(e) for e in entries):
            log(f"  Got {len(entries)} tabs at the URL, drilling in...")
            video_entries: list[dict] = []
            for tab in entries:
                tab_title = tab.get("title") or tab.get("id") or "?"
                tab_url = _tab_url(tab, normalized)
                if not tab_url:
                    log(f"    tab '{tab_title}': no URL field (keys: {list(tab.keys())})")
                    continue
                log(f"    tab '{tab_title}' -> {tab_url}")
                try:
                    sub = _flat_entries(ydl, tab_url)
                    sub = [e for e in sub if _is_video_entry(e)]
                    log(f"      {len(sub)} videos")
                    video_entries.extend(sub)
                except Exception as e:
                    log(f"      error ({e})")
            entries = video_entries

    # Dedupe by video id, preserving order.
    seen: set[str] = set()
    rows = []
    for entry in entries:
        vid = entry.get("id", "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = entry.get("title", "") or ""
        url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"

        # YouTube flat entries include a Unix timestamp — convert to YYYY-MM-DD.
        upload_date = ""
        ts = entry.get("timestamp")
        if ts:
            try:
                upload_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass
        if not upload_date:
            raw = entry.get("upload_date", "")
            if raw and len(raw) == 8:
                upload_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"

        rows.append(
            {
                "VideoID": vid,
                "URL": url,
                "Title": title,
                "Episode": extract_episode(title),
                "UploadDate": upload_date,
            }
        )

    total = len(rows)
    dated = sum(1 for r in rows if r["UploadDate"])
    log(f"  Found {total} unique videos ({dated} with known upload date)")
    if on_progress:
        on_progress(total, total)

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["VideoID", "URL", "Title", "Episode", "UploadDate"])
        writer.writeheader()
        writer.writerows(rows)

    log(f"  Saved {total} videos -> {output_csv}")
    return total
