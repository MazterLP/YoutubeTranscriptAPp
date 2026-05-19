from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    video_id: str
    title: str
    date: str
    channel: str = ""
    chunk_index: int
    text: str
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None


class Strategy(BaseModel):
    has_strategy: bool
    strategy_name: Optional[str] = None
    indicators: list[str] = Field(default_factory=list)
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    stop_loss: Optional[str] = None
    take_profit: Optional[str] = None
    timeframe: Optional[str] = None
    asset_class: Optional[str] = None
    strategy_type: Optional[str] = None
    confidence: float = 0.0
    source_quote: Optional[str] = None
    chunk_id: str = ""
    video_id: str = ""
    title: str = ""
    date: str = ""


class PineResult(BaseModel):
    query: str
    pine_code: str
    source_strategies: list[str] = Field(default_factory=list)
    output_path: str = ""
