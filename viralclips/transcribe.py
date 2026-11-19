"""Transcripción con tiempos por palabra (faster-whisper, corre en tu computadora)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import Word


def extract_audio(video: str, out_wav: Path) -> Path:
    """Audio mono a 16 kHz: lo que necesita Whisper y el análisis de energía."""
    if not out_wav.exists():
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
             "-c:a", "pcm_s16le", str(out_wav)],
            check=True,
        )
    return out_wav


def transcribe(
    audio: Path,
    cache_file: Path,
    model_size: str = "small",
    language: str | None = None,
    device: str = "auto",
) -> list[Word]:
    if cache_file.exists():
        return [Word(**w) for w in json.loads(cache_file.read_text())]

    from faster_whisper import WhisperModel  # import tardío: carga pesada

    compute_type = "int8" if device in ("cpu", "auto") else "float16"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text=text, start=float(w.start), end=float(w.end)))

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False))
    return words
