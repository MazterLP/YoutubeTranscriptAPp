"""Export Trading Research SQLite transcripts to bronze JSON format.

Usage:
    python export_db_to_bronze.py

Reads from:
    Trading Research/db/trading_research.db  (raw_documents table)

Writes to:
    output/bronze/<id>_<slug>.json  (one file per transcript)

The output format is compatible with pipeline/strategy/cleaner.py.
Already-exported files are skipped (idempotent).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / "Documents/Fede_Projects/Trading Research/db/trading_research.db"
BRONZE_DIR = Path(__file__).parent / "output" / "bronze"


def _slug(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^\w]+", "_", text)[:max_len].strip("_").lower()


def export(db_path: Path = DB_PATH, bronze_dir: Path = BRONZE_DIR) -> int:
    bronze_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source_channel, title, raw_content, metadata_json FROM raw_documents"
    )
    rows = cur.fetchall()
    conn.close()

    exported = skipped = 0
    for row in rows:
        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        doc = {
            "video_id": meta.get("video_id") or str(row["id"]),
            "title": row["title"] or meta.get("title", ""),
            "channel": row["source_channel"] or meta.get("channel", ""),
            "transcript": row["raw_content"] or "",
            "publish_date": meta.get("publish_date", ""),
            "url": meta.get("url", ""),
            "segments": [],
        }

        fname = f"{row['id']:04d}_{_slug(doc['title'])}.json"
        out = bronze_dir / fname
        if out.exists():
            skipped += 1
            continue

        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        exported += 1

    print(f"Exported {exported} transcripts to {bronze_dir}  ({skipped} already existed)")
    return exported


if __name__ == "__main__":
    export()
