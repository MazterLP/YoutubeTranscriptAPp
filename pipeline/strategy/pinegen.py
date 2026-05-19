"""Generate PineScript v6 strategies using RAG + Ollama."""
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path
from typing import Callable

import ollama

from .models import PineResult
from .rag import fetch_top_strategies, search

_SYSTEM = """You are an expert Pine Script v6 programmer for TradingView. Write clean, correct, complete Pine Script v6 strategies.

RULES:
- First line MUST be: //@version=6
- Use strategy() with overlay, qty, capital, commission settings
- Use input.int() / input.float() for all parameters
- Use ta.ema(), ta.rsi(), ta.atr(), ta.crossover(), ta.crossunder()
- strategy.entry() to open, strategy.exit() with stop= and limit= to close
- All variable names in snake_case
- Return ONLY Pine Script code. No markdown, no explanation."""

_USER_TPL = """Generate a complete Pine Script v6 strategy based on these extracted strategies:

## REQUEST
{query}

## EXTRACTED STRATEGIES
{strategies}

## TRANSCRIPT CONTEXT
{context}

## TEMPLATE (follow this structure)
{skeleton}

Write the complete Pine Script v6 strategy now."""


def _validate(code: str) -> tuple[bool, str]:
    issues = []
    if "//@version=6" not in code:
        issues.append("missing //@version=6")
    if "strategy(" not in code:
        issues.append("missing strategy()")
    if "strategy.entry(" not in code:
        issues.append("missing strategy.entry()")
    return not issues, "; ".join(issues)


def generate(
    query: str,
    chroma_path: str,
    embed_model: str,
    gold_dir: Path,
    strategies_dir: Path,
    template_path: Path,
    model: str,
    base_url: str,
    temperature: float,
    timeout: int,
    log: Callable[[str], None] = print,
) -> PineResult:
    skeleton = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    strategies = fetch_top_strategies(query, chroma_path, embed_model, gold_dir)
    raw_chunks = search(query, chroma_path, embed_model, n_results=3, collections=["chunks"])
    context = "\n\n---\n\n".join(
        f"[{r.metadata.get('title', '')} | {r.metadata.get('date', '')}]\n{r.text}"
        for r in raw_chunks
    )

    client = ollama.Client(host=base_url, timeout=timeout)
    resp = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _USER_TPL.format(
                query=query,
                strategies=json.dumps(strategies, indent=2, ensure_ascii=False),
                context=context,
                skeleton=skeleton,
            )},
        ],
        options={"temperature": temperature},
    )
    pine_code = resp["message"]["content"].strip()
    pine_code = re.sub(r"^```(?:pine|pinescript)?\s*", "", pine_code)
    pine_code = re.sub(r"\s*```$", "", pine_code).strip()

    valid, issues = _validate(pine_code)
    if not valid:
        log(f"  Warning: {issues}")

    today = date.today().isoformat()
    slug = re.sub(r"\W+", "_", query.lower())[:40].strip("_")
    strategies_dir.mkdir(parents=True, exist_ok=True)
    out_path = strategies_dir / f"{slug}_{today}.pine"
    out_path.write_text(pine_code, encoding="utf-8")

    source_names = [s.get("strategy_name", "") for s in strategies if s.get("strategy_name")]
    log(f"  Saved: {out_path.name}")
    return PineResult(
        query=query,
        pine_code=pine_code,
        source_strategies=source_names,
        output_path=str(out_path),
    )
