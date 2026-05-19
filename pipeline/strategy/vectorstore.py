"""Embed and store chunks + strategies into ChromaDB (Silver + Gold → Vector DB)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

import chromadb
from sentence_transformers import SentenceTransformer

from .models import Chunk, Strategy

_EMBEDDER: SentenceTransformer | None = None


def _get_embedder(model_name: str) -> SentenceTransformer:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = SentenceTransformer(model_name)
    return _EMBEDDER


def ingest_all(
    silver_dir: Path,
    gold_dir: Path,
    chroma_path: str,
    embed_model: str,
    log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    client = chromadb.PersistentClient(path=chroma_path)
    chunks_col = client.get_or_create_collection("chunks")
    strats_col = client.get_or_create_collection("strategies")
    embedder = _get_embedder(embed_model)

    silver_files = sorted(silver_dir.glob("*.json"))
    total = len(silver_files)
    n_chunks = 0

    for i, sf in enumerate(silver_files):
        if on_progress:
            on_progress(i, total * 2)
        with open(sf, encoding="utf-8") as f:
            chunk_dicts = json.load(f)
        chunks = [Chunk(**c) for c in chunk_dicts]
        if not chunks:
            continue
        ids = [c.chunk_id for c in chunks]
        texts = [c.text for c in chunks]
        metas = [{"video_id": c.video_id, "title": c.title, "date": c.date, "channel": c.channel} for c in chunks]
        embeddings = embedder.encode(texts, show_progress_bar=False).tolist()
        chunks_col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metas)
        n_chunks += len(chunks)
        log(f"  {sf.name}: {len(chunks)} chunks ingested")

    gold_files = sorted(gold_dir.glob("*_strategies.json"))
    n_strats = 0

    for i, gf in enumerate(gold_files):
        if on_progress:
            on_progress(total + i, total * 2)
        with open(gf, encoding="utf-8") as f:
            strat_dicts = json.load(f)
        strategies = [Strategy(**s) for s in strat_dicts]
        if not strategies:
            continue
        ids = [s.chunk_id for s in strategies]
        texts = [
            f"{s.strategy_name or 'strategy'}: "
            + " ".join(s.entry_conditions + s.exit_conditions + s.indicators)
            + (f" {s.source_quote}" if s.source_quote else "")
            for s in strategies
        ]
        metas = [
            {
                "video_id": s.video_id, "title": s.title, "date": s.date,
                "strategy_name": s.strategy_name or "",
                "timeframe": s.timeframe or "", "asset_class": s.asset_class or "",
                "strategy_type": s.strategy_type or "",
                "indicators": ", ".join(s.indicators), "confidence": s.confidence,
            }
            for s in strategies
        ]
        embeddings = embedder.encode(texts, show_progress_bar=False).tolist()
        strats_col.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metas)
        n_strats += len(strategies)
        log(f"  {gf.name}: {len(strategies)} strategies ingested")

    if on_progress:
        on_progress(total * 2, total * 2)
    return n_chunks, n_strats
