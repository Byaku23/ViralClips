"""Estructuras de datos compartidas por todo el pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Sentence:
    """Una frase de la transcripción: la unidad mínima para cortar sin partir ideas."""

    index: int
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text.strip() for w in self.words).strip()


@dataclass
class Candidate:
    """Un posible clip: un rango continuo de frases."""

    first: int  # índice de la primera frase
    last: int  # índice de la última frase (incluida)
    start: float
    end: float
    text: str
    signals: dict[str, float] = field(default_factory=dict)
    heuristic: float = 0.0  # 0-100
    llm: Optional[float] = None  # 0-100, si se usó IA
    score: float = 0.0  # puntaje final 0-100
    title: str = ""
    hook: str = ""
    reason: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        return d


@dataclass
class Source:
    """Un video listo para procesar."""

    path: str
    title: str
    origin: str  # ruta local o URL original
    heatmap: list[dict] = field(default_factory=list)  # [{start_time, end_time, value}]
    width: int = 0
    height: int = 0
    duration: float = 0.0
