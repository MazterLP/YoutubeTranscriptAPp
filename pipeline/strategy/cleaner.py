"""Normalize and chunk transcript JSON files (Bronze → Silver)."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Callable

from .models import Chunk


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_id": raw.get("id") or raw.get("video_id", "unknown"),
        "title": raw.get("title", ""),
        "date": raw.get("published_at") or raw.get("publish_date", ""),
        "channel": raw.get("channel", ""),
        "transcript": raw.get("transcript", ""),
        "segments": raw.get("segments", []),
    }


def _chunk_by_segments(segments: list[dict], max_words: int, overlap_words: int) -> list[dict]:
    chunks: list[dict] = []
    current_texts: list[str] = []
    current_words = 0
    current_start = 0.0
    current_end = 0.0
    first = True
    for seg in segments:
        text = seg.get("text", "").strip()
        words = len(text.split())
        if first:
            current_start = seg.get("start", 0.0)
            first = False
        if current_words + words > max_words and current_texts:
            chunks.append({"text": " ".join(current_texts), "start_sec": current_start, "end_sec": current_end})
            overlap_text = " ".join(" ".join(current_texts).split()[-overlap_words:])
            current_texts = [overlap_text] if overlap_text else []
            current_words = len(current_texts[0].split()) if current_texts else 0
            current_start = seg.get("start", 0.0)
        current_texts.append(text)
        current_words += words
        current_end = seg.get("end", 0.0)
    if current_texts:
        chunks.append({"text": " ".join(current_texts), "start_sec": current_start, "end_sec": current_end})
    return chunks


def _chunk_by_words(text: str, max_words: int, overlap_words: int) -> list[dict]:
    words = text.split()
    chunks: list[dict] = []
    i = 0
    while i < len(words):
        chunks.append({"text": " ".join(words[i: i + max_words]), "start_sec": None, "end_sec": None})
        i += max_words - overlap_words
    return chunks


def clean_all(
    bronze_dir: Path,
    silver_dir: Path,
    max_words: int = 300,
    overlap_words: int = 50,
    log: Callable[[str], None] = print,
) -> list[Chunk]:
    silver_dir.mkdir(parents=True, exist_ok=True)
    all_chunks: list[Chunk] = []

    json_files = sorted(bronze_dir.glob("*.json"))
    if not json_files:
        log(f"No JSON files found in {bronze_dir}")
        return []

    for json_file in json_files:
        try:
            with open(json_file, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            log(f"  SKIP {json_file.name}: {e}")
            continue

        norm = _normalize(raw)
        video_id = re.sub(r"[^\w-]", "_", norm["video_id"])

        raw_chunks = (
            _chunk_by_segments(norm["segments"], max_words, overlap_words)
            if norm["segments"]
            else _chunk_by_words(norm["transcript"], max_words, overlap_words)
        )

        chunks = [
            Chunk(
                chunk_id=f"{video_id}-{idx}",
                video_id=video_id,
                title=norm["title"],
                date=norm["date"],
                channel=norm["channel"],
                chunk_index=idx,
                text=rc["text"],
                start_sec=rc.get("start_sec"),
                end_sec=rc.get("end_sec"),
            )
            for idx, rc in enumerate(raw_chunks)
        ]

        out_path = silver_dir / f"{video_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in chunks], f, ensure_ascii=False, indent=2)

        log(f"  {json_file.name} → {len(chunks)} chunks")
        all_chunks.extend(chunks)

    return all_chunks
