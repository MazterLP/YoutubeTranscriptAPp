# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```powershell
# Windows (no console window)
.\.venv\Scripts\pythonw.exe app.py

# Windows (with console for debugging)
.\.venv\Scripts\python.exe app.py

# Linux / macOS
./.venv/bin/python3 app.py
```

## Installing dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
# Ubuntu also needs: sudo apt install python3-tk ffmpeg
```

There is no test suite and no lint configuration in this project.

## Environment variables

`app.py` automatically loads a `.env` file at the project root on startup (key=value format, `#` comments ignored). The only env var the app reads is:

- `ANTHROPIC_API_KEY` — used when the Claude API backend is selected in the Strategy Pipeline tab. Can also be pasted directly into the GUI.

## Utility scripts

**`export_db_to_bronze.py`** — one-shot migration from a specific SQLite database (`~/Documents/Fede_Projects/Trading Research/db/trading_research.db`, table `raw_documents`) to bronze JSON files in `output/bronze/`. Idempotent — already-exported files are skipped. Run with:

```powershell
.\.venv\Scripts\python.exe export_db_to_bronze.py
```

---

## Architecture

The app has two tabs, each backed by its own pipeline running in a background `threading.Thread` and communicating back via `queue.Queue`.

### Thread model (shared by both tabs)
- `App._drain_events()` is scheduled with `root.after(100, ...)` — polls the queue every 100 ms and updates all widgets
- Both orchestrators emit the same event schema: `{"kind": "log"|"phase"|"progress"|"done", "payload": ...}`
- Each orchestrator exposes `start(cfg)` / `stop()` with a `threading.Event`; pipelines exit cooperatively between units of work (never mid-transcription or mid-chunk)

---

### Tab 1 — Transcript Downloader (`pipeline/orchestrator.py`)

Three sequential phases:

1. **Channel fetch** (`pipeline/channel.py`): one flat yt-dlp request returns the full video list → `videos.csv`. Automatically normalises channel root URLs to `/videos` tab and recurses into tabs if needed.
2. **Captions** (`pipeline/captions.py`): per-video, calls `extract_info(download=True)` to download VTT subtitles AND get `upload_date` in one call. Sleeps `random.uniform(sleep_min, sleep_max)` between videos — critical to avoid YouTube 429s. Failures go to in-memory `failed_videos` list.
3. **Whisper** (`pipeline/whisper_worker.py`): only runs when `failed_videos` is non-empty. Loads `faster-whisper` once (GPU → CPU fallback), uses `ThreadPoolExecutor` with user-configured workers. Each worker: download MP3 → transcribe → delete MP3 → write JSON.

**Key design decisions**
- `extract_flat="in_playlist"` in channel.py is intentional — `extract_flat=False` makes N per-video requests and triggers rate-limits immediately on anonymous sessions.
- `captions.py` uses `extract_info(download=True)` not `download()` so we get `upload_date` back without a separate request.
- Idempotency: both the channel CSV check (header schema + row count) and the per-video glob `*_{video_id}.json` ensure safe re-runs.
- `cookies.txt` is gitignored; its path defaults to `APP_DIR/cookies.txt` and is optional — the app warns and continues without it.

**Output**
```
output/{ChannelName}/
  videos.csv                              ← VideoID, URL, Title, Episode
  _failed.csv                             ← videos with no YouTube captions
  _failed_whisper_YYYYMMDD_HHMMSS.csv    ← videos that also failed Whisper
  YYYY-MM-DD_slug-title_videoID.json
```

JSON schema (captions): `video_id, episode, channel, title, url, publish_date, word_count, transcript`
JSON schema (Whisper adds): `language, metadata{whisper_model, device, lang_prob}, segments[{start, end, text}]`

---

### Tab 2 — Strategy Pipeline (`pipeline/strategy/`)

Four sequential phases driven by `pipeline/strategy/orchestrator.py` (`StrategyOrchestrator`):

1. **Clean** (`cleaner.py`): reads Bronze JSON transcripts, normalises fields, chunks text by word count (`max_words=300`, `overlap_words=50`) → writes Silver JSON files (`output/silver/{video_id}.json`).
2. **Extract** (`extractor.py`): sends each Silver chunk to an LLM with a structured prompt → parses JSON response → filters by confidence threshold → writes Gold JSON files (`output/gold/{video_id}_strategies.json`).
3. **Ingest** (`vectorstore.py`): embeds Silver chunks and Gold strategies with `sentence-transformers` → upserts into two ChromaDB collections (`chunks`, `strategies`) at `output/chroma/`.
4. **Generate / Search** (`pinegen.py`, `rag.py`): user enters a query → RAG search over ChromaDB → top strategies + transcript context sent to LLM → returns Pine Script v6 code → saved to `output/strategies/{slug}_{date}.pine`.

**LLM backends**

Both `extractor.py` and `pinegen.py` support two backends, selected via `StrategyConfig.backend`:
- `"ollama"` (default) — local Ollama instance at `http://localhost:11434`, model `qwen3:14b`
- `"claude"` — Anthropic API via `anthropic` SDK; requires `claude_api_key` and `claude_model` (default `claude-sonnet-4-6`)

The GUI exposes radio buttons to switch backends; `extractor.py` calls `_call_ollama()` or `_call_claude()` based on this flag.

**Data flow**
```
output/{ChannelName}/*.json  (Bronze)
  └─ cleaner.py ──→  output/silver/*.json
  └─ extractor.py ──→  output/gold/*_strategies.json
  └─ vectorstore.py ──→  output/chroma/  (ChromaDB)
  └─ pinegen.py + rag.py ──→  output/strategies/*.pine
```

**Key design decisions**
- ChromaDB is a local persistent store; `vectorstore.py` uses `upsert` — re-running ingest is safe and idempotent.
- `extractor.py` JSON parsing strips markdown fences before `json.loads` to handle models that wrap output in code blocks.
- The Pine Script skeleton in `templates/strategy_skeleton.pine` is injected into the generation prompt as a structural guide.

**Models (Pydantic, `models.py`)**
- `Chunk` — Silver unit: `chunk_id, video_id, title, date, channel, chunk_index, text, start_sec, end_sec`
- `Strategy` — Gold unit: all extraction fields + `confidence`, `chunk_id`, `video_id`, `title`, `date`
- `PineResult` — generation output: `query, pine_code, source_strategies, output_path`

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Tkinter GUI — two-tab layout, event drain loop |
| `export_db_to_bronze.py` | One-shot SQLite → bronze JSON migration utility |
| `pipeline/orchestrator.py` | Tab 1: thread, queue, transcript phases coordinator |
| `pipeline/channel.py` | Phase 1: flat channel listing |
| `pipeline/captions.py` | Phase 2: VTT fetch via yt-dlp |
| `pipeline/whisper_worker.py` | Phase 3: audio download + faster-whisper |
| `pipeline/utils.py` | Pure helpers: slugify, parse_date, VTT parse, etc. |
| `pipeline/strategy/orchestrator.py` | Tab 2: thread, queue, strategy phases coordinator |
| `pipeline/strategy/cleaner.py` | Phase 1: Bronze → Silver chunking |
| `pipeline/strategy/extractor.py` | Phase 2: Silver → Gold via Ollama or Claude API |
| `pipeline/strategy/vectorstore.py` | Phase 3: Gold + Silver → ChromaDB |
| `pipeline/strategy/rag.py` | Semantic search over ChromaDB |
| `pipeline/strategy/pinegen.py` | RAG → LLM → Pine Script v6 generation |
| `pipeline/strategy/models.py` | Pydantic models: Chunk, Strategy, PineResult |
| `templates/strategy_skeleton.pine` | Pine Script v6 template injected into generation prompt |
| `install.ps1` | Windows one-liner installer |
| `install.sh` | Linux/macOS installer |
