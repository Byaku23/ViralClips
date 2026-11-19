"""Señales baratas de viralidad: retención de YouTube, audio y texto."""

from __future__ import annotations

import re
import unicodedata
import wave
from pathlib import Path

import numpy as np

from .models import Candidate, Sentence

# Palabras y giros que suelen abrir un buen gancho (español e inglés).
HOOK_PATTERNS = [
    r"\bpor qu[eé]\b", r"\bsab[ií]as\b", r"\bnadie\b", r"\bnunca\b", r"\bsecreto",
    r"\bverdad\b", r"\bmentira", r"\bimagina", r"\bincre[ií]ble", r"\bincluso\b",
    r"\bel mayor\b", r"\bla mayor\b", r"\bel peor\b", r"\bla peor\b", r"\bpero\b",
    r"\blo que\b", r"\bresulta que\b", r"\bdato\b", r"\berror\b",
    r"\bmuri[oó]\b", r"\bmuerte\b", r"\bguerra\b", r"\bprohibid", r"\bolvidad",
    r"\bmisterio", r"\bnadie sabe\b", r"\bpoca gente\b", r"\bjam[aá]s\b",
    r"\bwhy\b", r"\bnobody\b", r"\bnever\b", r"\bsecret", r"\btruth\b", r"\bimagine\b",
    r"\bcrazy\b", r"\binsane\b", r"\bthe biggest\b", r"\bthe worst\b",
]
_HOOK_RE = re.compile("|".join(HOOK_PATTERNS), re.I)
_NUMBER_RE = re.compile(r"\d")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def text_signals(cand: Candidate, sentences: list[Sentence]) -> dict[str, float]:
    first = sentences[cand.first].text
    body = cand.text
    n_words = max(1, len(body.split()))
    hook_first = 0.0
    if "?" in first or "¿" in first:
        hook_first += 0.5
    if _HOOK_RE.search(first) or _HOOK_RE.search(_strip_accents(first)):
        hook_first += 0.4
    if _NUMBER_RE.search(first):
        hook_first += 0.2
    density = (len(_HOOK_RE.findall(body)) + len(_NUMBER_RE.findall(body)) * 0.3) / n_words * 20
    last = sentences[cand.last].text
    closes = 1.0 if last.endswith((".", "!", "?")) else 0.4
    rate = n_words / max(cand.duration, 1.0)  # palabras por segundo
    return {
        "gancho_inicio": min(hook_first, 1.0),
        "densidad_ganchos": min(density, 1.0),
        "cierre": closes,
        "ritmo": float(np.clip((rate - 1.5) / 2.0, 0.0, 1.0)),
    }


class AudioEnergy:
    """Energía RMS en ventanas de 0.5 s, normalizada contra todo el video."""

    def __init__(self, wav_path: Path, window: float = 0.5):
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        hop = max(1, int(sr * window))
        n = len(samples) // hop
        if n == 0:
            self.rms = np.zeros(1)
        else:
            frames = samples[: n * hop].reshape(n, hop)
            self.rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
        self.window = window
        self.p50 = float(np.percentile(self.rms, 50)) if len(self.rms) else 0.0
        self.p95 = float(np.percentile(self.rms, 95)) if len(self.rms) else 1.0

    def score(self, start: float, end: float) -> float:
        a, b = int(start / self.window), max(int(end / self.window), int(start / self.window) + 1)
        seg = self.rms[a:b]
        if len(seg) == 0 or self.p95 <= self.p50:
            return 0.0
        peak = float(np.percentile(seg, 90))
        return float(np.clip((peak - self.p50) / (self.p95 - self.p50), 0.0, 1.0))


def heatmap_score(heatmap: list[dict], start: float, end: float) -> float | None:
    """Promedio del mapa de calor "Más repetidos" de YouTube (0 a 1) en el rango."""
    if not heatmap:
        return None
    total, weight = 0.0, 0.0
    for h in heatmap:
        a, b = float(h["start_time"]), float(h["end_time"])
        inter = max(0.0, min(b, end) - max(a, start))
        if inter > 0:
            total += float(h["value"]) * inter
            weight += inter
    return total / weight if weight else 0.0


WEIGHTS = {
    "retencion": 0.30,
    "gancho_inicio": 0.25,
    "energia": 0.15,
    "densidad_ganchos": 0.12,
    "cierre": 0.10,
    "ritmo": 0.08,
}


def heuristic_score(signals: dict[str, float]) -> float:
    """Combina señales 0-1 en un puntaje 0-100. Sin mapa de calor, reparte su peso."""
    weights = dict(WEIGHTS)
    if "retencion" not in signals:
        weights.pop("retencion")
    total = sum(weights.values())
    return round(100 * sum(signals.get(k, 0.0) * w for k, w in weights.items()) / total, 1)
