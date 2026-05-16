"""Phase 3: download a video's audio and transcribe it with faster-whisper.

The Whisper model is loaded once (GPU with float16, falling back to CPU/int8)
and shared across worker threads. faster-whisper allows concurrent .transcribe()
calls on a single GPU but they internally serialize on VRAM — the practical
benefit of >1 worker is overlapping the next audio download with the current
transcription, not true parallel inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp
from faster_whisper import WhisperModel


@dataclass
class TranscriptionResult:
    text: str
    language: str
    lang_prob: float
    segments: list[dict]


def load_model(model_size: str, device: str) -> tuple[WhisperModel, str]:
    """Load Whisper with the requested device, falling back to CPU/int8 if needed.
    Returns (model, actual_device)."""
    if device == "auto":
        device = "cuda"

    compute_type = "float16" if device == "cuda" else "int8"
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        return model, device
    except Exception:
        if device == "cpu":
            raise
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        return model, "cpu"


def download_audio(
    video_id: str,
    temp_dir: Path,
    cookies: Optional[Path] = None,
    audio_format: str = "mp3",
) -> Optional[Path]:
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(temp_dir / f"{video_id}.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "128",
            }
        ],
    }
    if cookies and Path(cookies).exists():
        ydl_opts["cookiefile"] = str(cookies)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception:
        return None

    audio_path = temp_dir / f"{video_id}.{audio_format}"
    return audio_path if audio_path.exists() else None


def transcribe(audio_path: Path, model: WhisperModel) -> TranscriptionResult:
    segments_gen, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    text_parts: list[str] = []
    segments: list[dict] = []
    for seg in segments_gen:
        text_parts.append(seg.text)
        segments.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
        )
    return TranscriptionResult(
        text=" ".join(p.strip() for p in text_parts).strip(),
        language=info.language,
        lang_prob=round(info.language_probability, 3),
        segments=segments,
    )
