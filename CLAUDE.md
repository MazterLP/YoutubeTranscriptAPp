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

## Architecture

The app has two layers: a **Tkinter GUI** (`app.py`) that never blocks, and a **pipeline** (`pipeline/`) that runs in a background `threading.Thread` and communicates back via `queue.Queue`.

### Thread model
- `App._drain_events()` is scheduled with `root.after(100, ...)` — polls the queue every 100 ms and updates all widgets
- `Orchestrator.start(cfg)` spawns the daemon thread
- `Orchestrator.stop()` sets a `threading.Event`; the pipeline exits cooperatively between videos (never mid-transcription)

### Pipeline phases (all inside `pipeline/orchestrator.py`)

1. **Channel fetch** (`pipeline/channel.py`): one flat yt-dlp request returns the full video list → `videos.csv`. Automatically normalises channel root URLs to `/videos` tab and recurses into tabs if needed.
2. **Captions** (`pipeline/captions.py`): per-video, calls `extract_info(download=True)` to download VTT subtitles AND get `upload_date` in one call. Sleeps `random.uniform(sleep_min, sleep_max)` between videos — critical to avoid YouTube 429s. Failures go to in-memory `failed_videos` list.
3. **Whisper** (`pipeline/whisper_worker.py`): only runs when `failed_videos` is non-empty. Loads `faster-whisper` once (GPU → CPU fallback), uses `ThreadPoolExecutor` with user-configured workers. Each worker: download MP3 → transcribe → delete MP3 → write JSON.

### Key design decisions
- `extract_flat="in_playlist"` in channel.py is intentional — `extract_flat=False` makes N per-video requests and triggers rate-limits immediately on anonymous sessions.
- `captions.py` uses `extract_info(download=True)` not `download()` so we get `upload_date` back without a separate request.
- Idempotency: both the channel CSV check (header schema + row count) and the per-video glob `*_{video_id}.json` ensure safe re-runs.
- `cookies.txt` is gitignored; its path defaults to `APP_DIR/cookies.txt` and is optional — the app warns and continues without it.

### Output

```
output/{ChannelName}/
  videos.csv                              ← VideoID, URL, Title, Episode
  _failed.csv                             ← videos with no YouTube captions
  _failed_whisper_YYYYMMDD_HHMMSS.csv    ← videos that also failed Whisper
  YYYY-MM-DD_slug-title_videoID.json
```

JSON schema (captions): `video_id, episode, channel, title, url, publish_date, word_count, transcript`
JSON schema (Whisper adds): `language, metadata{whisper_model, device, lang_prob}, segments[{start, end, text}]`

## Files

| File | Purpose |
|---|---|
| `app.py` | Tkinter GUI + event drain loop |
| `pipeline/orchestrator.py` | Thread, queue, phases coordinator |
| `pipeline/channel.py` | Phase 1: flat channel listing |
| `pipeline/captions.py` | Phase 2: VTT fetch via yt-dlp |
| `pipeline/whisper_worker.py` | Phase 3: audio download + faster-whisper |
| `pipeline/utils.py` | Pure helpers: slugify, parse_date, VTT parse, etc. |
| `install.ps1` | Windows one-liner installer |
| `install.sh` | Linux/macOS installer |
