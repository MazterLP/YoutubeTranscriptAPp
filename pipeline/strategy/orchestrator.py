"""Background orchestrator for the strategy pipeline.

Emits the same event schema as pipeline.orchestrator so the GUI can reuse
its _drain_events logic: {"kind": "log"|"phase"|"progress"|"done", "payload": ...}
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class StrategyConfig:
    bronze_dir: Path
    silver_dir: Path
    gold_dir: Path
    chroma_path: str
    strategies_dir: Path
    template_path: Path
    ollama_model: str = "qwen3:14b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_temperature: float = 0.1
    ollama_timeout: int = 600
    embed_model: str = "all-MiniLM-L6-v2"
    max_words: int = 300
    overlap_words: int = 50
    min_confidence: float = 0.6
    backend: str = "ollama"          # "ollama" or "claude"
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"


class StrategyOrchestrator:
    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start_pipeline(self, cfg: StrategyConfig) -> None:
        if self._thread and self._thread.is_alive():
            self._emit("log", "Pipeline already running.")
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run_pipeline, args=(cfg,), daemon=True)
        self._thread.start()

    def start_generate(self, cfg: StrategyConfig, query: str) -> None:
        if self._thread and self._thread.is_alive():
            self._emit("log", "Pipeline already running.")
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run_generate, args=(cfg, query), daemon=True)
        self._thread.start()

    def start_search(self, cfg: StrategyConfig, query: str) -> None:
        if self._thread and self._thread.is_alive():
            self._emit("log", "Already running.")
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run_search, args=(cfg, query), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._emit("log", "Stop requested...")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, kind: str, payload) -> None:
        self.events.put({"kind": kind, "payload": payload})

    def _log(self, msg: str) -> None:
        self._emit("log", msg)

    def _run_pipeline(self, cfg: StrategyConfig) -> None:
        try:
            from .cleaner import clean_all
            from .extractor import extract_all
            from .vectorstore import ingest_all

            # Step 1: Clean
            self._emit("phase", "Clean")
            self._log(f"Chunking transcripts from {cfg.bronze_dir} ...")
            chunks = clean_all(
                bronze_dir=cfg.bronze_dir,
                silver_dir=cfg.silver_dir,
                max_words=cfg.max_words,
                overlap_words=cfg.overlap_words,
                log=self._log,
            )
            self._log(f"Total: {len(chunks)} chunks in {cfg.silver_dir}")
            if self.stop_event.is_set():
                self._emit("done", "stopped")
                return

            # Step 2: Extract
            lm = cfg.claude_model if cfg.backend == "claude" else cfg.ollama_model
            self._emit("phase", "Extract")
            self._log(f"Extracting strategies with {cfg.backend}:{lm} ...")
            strategies = extract_all(
                silver_dir=cfg.silver_dir,
                gold_dir=cfg.gold_dir,
                model=lm,
                base_url=cfg.ollama_base_url,
                temperature=cfg.ollama_temperature,
                timeout=cfg.ollama_timeout,
                min_confidence=cfg.min_confidence,
                log=self._log,
                on_progress=lambda d, t: self._emit("progress", {"done": d, "total": t}),
                stop_check=self.stop_event.is_set,
                backend=cfg.backend,
                claude_api_key=cfg.claude_api_key,
            )
            self._log(f"Total: {len(strategies)} strategies saved")
            if self.stop_event.is_set():
                self._emit("done", "stopped")
                return

            # Step 3: Ingest
            self._emit("phase", "Ingest")
            self._log("Embedding and storing in ChromaDB ...")
            n_chunks, n_strats = ingest_all(
                silver_dir=cfg.silver_dir,
                gold_dir=cfg.gold_dir,
                chroma_path=cfg.chroma_path,
                embed_model=cfg.embed_model,
                log=self._log,
                on_progress=lambda d, t: self._emit("progress", {"done": d, "total": t}),
            )
            self._log(f"Ingested {n_chunks} chunks + {n_strats} strategies into ChromaDB")
            self._emit("done", "ok")

        except Exception as e:
            self._log(f"FATAL: {e}")
            self._emit("done", "error")

    def _run_generate(self, cfg: StrategyConfig, query: str) -> None:
        try:
            from .pinegen import generate
            lm = cfg.claude_model if cfg.backend == "claude" else cfg.ollama_model
            self._emit("phase", "Generate")
            self._log(f"Generating Pine Script for: '{query}' ({cfg.backend}:{lm}) ...")
            result = generate(
                query=query,
                chroma_path=cfg.chroma_path,
                embed_model=cfg.embed_model,
                gold_dir=cfg.gold_dir,
                strategies_dir=cfg.strategies_dir,
                template_path=cfg.template_path,
                model=lm,
                base_url=cfg.ollama_base_url,
                temperature=cfg.ollama_temperature,
                timeout=cfg.ollama_timeout,
                log=self._log,
                backend=cfg.backend,
                claude_api_key=cfg.claude_api_key,
            )
            if result.source_strategies:
                self._log(f"Based on: {', '.join(result.source_strategies)}")
            self._log("─" * 50)
            self._log(result.pine_code)
            self._log("─" * 50)
            self._log(f"Saved to: {result.output_path}")
            self._emit("done", result.output_path)
        except Exception as e:
            self._log(f"FATAL: {e}")
            self._emit("done", "error")

    def _run_search(self, cfg: StrategyConfig, query: str) -> None:
        try:
            from .rag import search
            self._emit("phase", "Search")
            self._log(f"Searching: '{query}' ...")
            results = search(
                query=query,
                chroma_path=cfg.chroma_path,
                embed_model=cfg.embed_model,
                n_results=5,
            )
            if not results:
                self._log("No results — run the pipeline first (Clean → Extract → Ingest).")
            for i, r in enumerate(results, 1):
                meta = r.metadata
                self._log(
                    f"[{i}] [{r.collection}] {meta.get('title', '')[:50]} | "
                    f"{meta.get('date', '')} | dist={r.distance:.3f}"
                )
                self._log(f"    {r.text[:200]}...")
            self._emit("done", "ok")
        except Exception as e:
            self._log(f"FATAL: {e}")
            self._emit("done", "error")
