"""Frases, clips candidatos, modo cobertura completa y eliminación de duplicados."""

from __future__ import annotations

from .models import Candidate, Sentence, Word

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")


def build_sentences(words: list[Word], max_gap: float = 0.8, max_len: float = 15.0) -> list[Sentence]:
    """Agrupa palabras en frases por puntuación, silencios largos o longitud máxima."""
    sentences: list[Sentence] = []
    current: list[Word] = []
    for i, w in enumerate(words):
        if current:
            gap = w.start - current[-1].end
            too_long = w.end - current[0].start > max_len
            if gap > max_gap or too_long:
                sentences.append(Sentence(len(sentences), current))
                current = []
        current.append(w)
        if w.text.endswith(SENTENCE_END):
            sentences.append(Sentence(len(sentences), current))
            current = []
    if current:
        sentences.append(Sentence(len(sentences), current))
    return sentences


def _make(sentences: list[Sentence], first: int, last: int) -> Candidate:
    return Candidate(
        first=first,
        last=last,
        start=sentences[first].start,
        end=sentences[last].end,
        text=" ".join(s.text for s in sentences[first : last + 1]),
    )


def sliding_candidates(
    sentences: list[Sentence], min_len: float = 20.0, max_len: float = 60.0
) -> list[Candidate]:
    """Todas las ventanas de frases completas cuya duración cae entre min_len y max_len."""
    out: list[Candidate] = []
    n = len(sentences)
    for i in range(n):
        for j in range(i, n):
            dur = sentences[j].end - sentences[i].start
            if dur > max_len:
                break
            if dur >= min_len:
                out.append(_make(sentences, i, j))
    return out


def coverage_segments(
    sentences: list[Sentence], target: float = 45.0, min_len: float = 20.0, max_len: float = 75.0
) -> list[Candidate]:
    """Parte el video completo en segmentos seguidos, sin descartar nada.

    Corta en la frontera de frase con el silencio más largo dentro de la zona
    [min_len, max_len], prefiriendo cortes cercanos a `target`.
    """
    out: list[Candidate] = []
    n = len(sentences)
    i = 0
    while i < n:
        best_j, best_cost = None, float("inf")
        j = i
        while j < n:
            dur = sentences[j].end - sentences[i].start
            if dur > max_len and best_j is not None:
                break
            if dur >= min_len:
                gap = (sentences[j + 1].start - sentences[j].end) if j + 1 < n else 2.0
                # Costo bajo = cerca del objetivo y con una pausa natural larga.
                cost = abs(dur - target) / target - min(gap, 2.0) * 0.5
                if cost < best_cost:
                    best_j, best_cost = j, cost
            j += 1
        if best_j is None:  # lo que queda es más corto que min_len
            if out and sentences[n - 1].end - out[-1].start <= max_len * 1.3:
                prev = out.pop()
                out.append(_make(sentences, prev.first, n - 1))
            else:
                out.append(_make(sentences, i, n - 1))
            break
        out.append(_make(sentences, i, best_j))
        i = best_j + 1
    return out


def overlap_ratio(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shorter = min(a.duration, b.duration) or 1e-9
    return inter / shorter


def non_max_suppression(cands: list[Candidate], key: str = "score", max_overlap: float = 0.5,
                        limit: int | None = None) -> list[Candidate]:
    """Se queda con el mejor de cada grupo de clips que se solapan."""
    ranked = sorted(cands, key=lambda c: getattr(c, key), reverse=True)
    kept: list[Candidate] = []
    for c in ranked:
        if all(overlap_ratio(c, k) <= max_overlap for k in kept):
            kept.append(c)
            if limit and len(kept) >= limit:
                break
    return kept
