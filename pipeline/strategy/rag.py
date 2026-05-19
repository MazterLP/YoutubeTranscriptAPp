"""Semantic search over ChromaDB chunks and strategies."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

_EMBEDDER: SentenceTransformer | None = None


def _get_embedder(model_name: str) -> SentenceTransformer:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = SentenceTransformer(model_name)
    return _EMBEDDER


@dataclass
class SearchResult:
    id: str
    text: str
    metadata: dict
    distance: float
    collection: str


def search(
    query: str,
    chroma_path: str,
    embed_model: str,
    n_results: int = 5,
    collections: list[str] | None = None,
) -> list[SearchResult]:
    if collections is None:
        collections = ["chunks", "strategies"]
    embedder = _get_embedder(embed_model)
    query_vec = embedder.encode([query])[0].tolist()
    client = chromadb.PersistentClient(path=chroma_path)
    results: list[SearchResult] = []
    for col_name in collections:
        try:
            col = client.get_collection(col_name)
        except Exception:
            continue
        res = col.query(query_embeddings=[query_vec], n_results=n_results)
        for doc_id, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            results.append(SearchResult(id=doc_id, text=doc, metadata=meta, distance=dist, collection=col_name))
    results.sort(key=lambda r: r.distance)
    return results


def fetch_top_strategies(
    query: str,
    chroma_path: str,
    embed_model: str,
    gold_dir: Path,
    n_results: int = 5,
) -> list[dict]:
    sr = search(query, chroma_path, embed_model, n_results, collections=["strategies"])
    top_ids = [r.id for r in sr]
    id_rank = {cid: idx for idx, cid in enumerate(top_ids)}
    matched: list[dict] = []
    for gf in gold_dir.glob("*_strategies.json"):
        with open(gf, encoding="utf-8") as f:
            for s in json.load(f):
                if s.get("chunk_id") in id_rank:
                    matched.append(s)
    matched.sort(key=lambda s: id_rank.get(s.get("chunk_id", ""), 9999))
    return matched[:n_results]
