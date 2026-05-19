"""Extract trading strategies from chunks using Ollama (Silver → Gold)."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Callable

import ollama

from .models import Chunk, Strategy

_SYSTEM = """You are a quantitative trading strategy analyst. Read transcript excerpts and extract concrete, actionable trading strategies.

RULES:
- Only extract strategies with specific, measurable rules (indicators, conditions, parameters).
- If no concrete strategy is present, return {"has_strategy": false}.
- Never invent details not found in the text.
- Respond ONLY with valid JSON. No markdown, no explanation.

OUTPUT FORMAT:
{
  "has_strategy": true,
  "strategy_name": "short descriptive name",
  "indicators": ["EMA 9", "RSI 14"],
  "entry_conditions": ["specific entry rule"],
  "exit_conditions": ["specific exit rule"],
  "stop_loss": "description or null",
  "take_profit": "description or null",
  "timeframe": "15m or null",
  "asset_class": "crypto|forex|stocks|futures|options|null",
  "strategy_type": "trend_following|mean_reversion|breakout|scalping|swing|other|null",
  "confidence": 0.0,
  "source_quote": "verbatim key sentence"
}

confidence: 0.9+ all rules explicit; 0.7-0.89 mostly explicit; 0.5-0.69 partial; below 0.5 vague"""

_USER_TPL = "Analyze this transcript excerpt:\n\n---\n{text}\n---"


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError("No JSON in response")


def extract_all(
    silver_dir: Path,
    gold_dir: Path,
    model: str,
    base_url: str,
    temperature: float,
    timeout: int,
    min_confidence: float,
    log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] | None = None,
    stop_check: Callable[[], bool] = lambda: False,
) -> list[Strategy]:
    gold_dir.mkdir(parents=True, exist_ok=True)
    client = ollama.Client(host=base_url, timeout=timeout)
    all_saved: list[Strategy] = []

    silver_files = sorted(silver_dir.glob("*.json"))
    total_files = len(silver_files)

    for file_idx, silver_file in enumerate(silver_files):
        if stop_check():
            break
        if on_progress:
            on_progress(file_idx, total_files)

        with open(silver_file, encoding="utf-8") as f:
            chunk_dicts = json.load(f)

        chunks = [Chunk(**c) for c in chunk_dicts]
        strategies: list[Strategy] = []
        video_id = chunks[0].video_id if chunks else silver_file.stem

        for chunk in chunks:
            if stop_check():
                break
            try:
                resp = client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": _USER_TPL.format(text=chunk.text)},
                    ],
                    options={"temperature": temperature},
                )
                data = _parse_json(resp["message"]["content"])
            except Exception as e:
                log(f"    chunk {chunk.chunk_id}: {e}")
                continue

            strat = Strategy(
                has_strategy=data.get("has_strategy", False),
                strategy_name=data.get("strategy_name"),
                indicators=data.get("indicators", []),
                entry_conditions=data.get("entry_conditions", []),
                exit_conditions=data.get("exit_conditions", []),
                stop_loss=data.get("stop_loss"),
                take_profit=data.get("take_profit"),
                timeframe=data.get("timeframe"),
                asset_class=data.get("asset_class"),
                strategy_type=data.get("strategy_type"),
                confidence=float(data.get("confidence", 0.0)),
                source_quote=data.get("source_quote"),
                chunk_id=chunk.chunk_id,
                video_id=chunk.video_id,
                title=chunk.title,
                date=chunk.date,
            )
            if strat.has_strategy and strat.confidence >= min_confidence:
                strategies.append(strat)

        log(f"  {silver_file.name} → {len(strategies)} strategies")
        out_path = gold_dir / f"{video_id}_strategies.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([s.model_dump() for s in strategies], f, ensure_ascii=False, indent=2)
        all_saved.extend(strategies)

    if on_progress:
        on_progress(total_files, total_files)
    return all_saved
