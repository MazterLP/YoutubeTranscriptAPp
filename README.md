# YouTube Transcript Downloader

A desktop GUI app that downloads every video transcript from a YouTube channel and saves them as structured JSON files — ready for ChromaDB, AI search, or any NLP pipeline.

**How it works:**
1. Fetches the full video list from a channel (one fast request)
2. Tries YouTube's own captions first (seconds per video)
3. Falls back to local [Whisper](https://github.com/SYSTRAN/faster-whisper) transcription for videos without captions (downloads audio → GPU/CPU transcription)

All output is saved in `output/{ChannelName}/` as JSON files. Re-running is safe — already-downloaded videos are skipped.

---

## Quick Install

### Windows (PowerShell one-liner)

```powershell
irm https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.ps1 | iex
```

Creates a virtual environment in `~/YoutubeTranscriptAPp/.venv`, installs all dependencies, and adds a desktop shortcut.

### Ubuntu / Linux (Bash one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.sh | bash
```

Auto-installs `python3-tk` if missing, creates `.venv`, installs dependencies, and registers a `.desktop` launcher.

---

## Manual Install (any OS)

**Prerequisites:**
- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) on PATH (needed for Whisper audio extraction)
- GPU optional: CUDA toolkit if you want GPU-accelerated transcription

```bash
git clone https://github.com/MazterLP/YoutubeTranscriptAPp.git
cd YoutubeTranscriptAPp

# Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

> **Ubuntu only:** if Tkinter is missing run `sudo apt install python3-tk` before `pip install`.

---

## Usage

### Tab 1 — Transcript Downloader

1. Launch the app (`python app.py` or desktop shortcut)
2. Paste the channel URL (e.g. `https://www.youtube.com/@SomeChannel`)
3. Set a channel name for the output folder
4. (Optional) point to a `cookies.txt` file — **strongly recommended**, see below
5. Choose Whisper model and workers, click **Start**

Output lands in `output/{ChannelName}/`:

```
output/
└── SomeChannel/
    ├── videos.csv                  ← full video list
    ├── _failed.csv                 ← videos with no YouTube captions
    └── 2024-03-15_ep-350-title_abc123XYZde.json
```

### JSON schema

```json
{
  "video_id":     "abc123XYZde",
  "episode":      "350",
  "channel":      "Some Channel",
  "title":        "Full episode title",
  "url":          "https://www.youtube.com/watch?v=abc123XYZde",
  "publish_date": "2024-03-15",
  "word_count":   12540,
  "transcript":   "Full cleaned transcript text..."
}
```

Videos transcribed via Whisper include two extra fields: `language`, `metadata` (model/device/confidence), and `segments` (timestamped word-level array).

---

### Tab 2 — Strategy Pipeline

Turns downloaded transcripts into searchable trading strategies and generates Pine Script v6 code.

**Four phases (run individually or as a full pipeline):**

1. **Clean** — chunks transcripts into overlapping text windows → `output/silver/`
2. **Extract** — sends each chunk to an LLM, extracts structured strategy data → `output/gold/`
3. **Ingest** — embeds chunks and strategies into a local ChromaDB vector store → `output/chroma/`
4. **Generate** — enter a query → RAG search → LLM generates a Pine Script → `output/strategies/`

**LLM backends** (select via radio button in the GUI):

| Backend | Requirements |
|---|---|
| **Ollama** (default) | [Ollama](https://ollama.com) running locally; default model `qwen3:14b` |
| **Claude API** | `ANTHROPIC_API_KEY` (see below); default model `claude-sonnet-4-6` |

**Setting your API key**

Either paste it directly into the GUI, or create a `.env` file at the project root — the app loads it automatically on startup:

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

### Importing from an existing database

If your transcripts are stored in a SQLite database (`raw_documents` table), use the included migration script to convert them to the bronze JSON format the pipeline expects:

```powershell
.\.venv\Scripts\python.exe export_db_to_bronze.py
```

Edit the `DB_PATH` constant at the top of the script to point to your database. Already-exported files are skipped (idempotent).

---

## cookies.txt (highly recommended)

Without a session cookie YouTube heavily rate-limits anonymous requests. With it, the same channel list downloads ~5–10× faster and you avoid the 1-hour ban.

1. Install the Chrome extension **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)**
2. Go to `youtube.com` while logged into your Google account
3. Click the extension → Export → save as `cookies.txt`
4. Drop the file into the app folder (`~/YoutubeTranscriptAPp/cookies.txt`)
5. Pick it in the GUI or leave it in the default path — it's auto-detected

`cookies.txt` is in `.gitignore` and will never be committed.

---

## Whisper model sizes

| Model | VRAM | Speed | Quality |
|-------|------|-------|---------|
| tiny | ~1 GB | fastest | lower |
| base | ~1 GB | fast | decent |
| small | ~2 GB | fast | good |
| **medium** | ~5 GB | moderate | **recommended** |
| large-v2 | ~10 GB | slow | best |

Falls back to CPU automatically if no CUDA GPU is detected.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `429 Too Many Requests` | Add `cookies.txt`; increase sleep range in GUI |
| `CUDA not available` | Set Device → `cpu` in the GUI |
| `No transcript / empty text` | Video has no captions → Whisper phase will handle it |
| `ffmpeg not found` | Install FFmpeg and add to PATH |
| `python3-tk` not found (Linux) | `sudo apt install python3-tk` |
| Channel shows 0 videos | Try appending `/videos` to the channel URL |

---

## Architecture

```
app.py                           Tkinter GUI — polls a queue every 100ms
pipeline/
  orchestrator.py                Tab 1: background thread, drives phases 1–3
  channel.py                     Phase 1: flat channel listing (1 HTTP request)
  captions.py                    Phase 2: yt-dlp VTT fetch + info_dict
  whisper_worker.py              Phase 3: faster-whisper GPU/CPU transcription
  utils.py                       Shared helpers (slugify, dates, VTT parsing)
  strategy/
    orchestrator.py              Tab 2: background thread, drives strategy phases
    cleaner.py                   Phase 1: Bronze JSON → chunked Silver JSON
    extractor.py                 Phase 2: Silver → Gold strategies via LLM
    vectorstore.py               Phase 3: Silver + Gold → ChromaDB
    rag.py                       Semantic search over ChromaDB
    pinegen.py                   RAG → LLM → Pine Script v6
    models.py                    Pydantic models (Chunk, Strategy, PineResult)
export_db_to_bronze.py           SQLite → bronze JSON migration utility
```
