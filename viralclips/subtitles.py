"""Subtítulos estilo shorts: 2-3 palabras en pantalla, la palabra que suena resaltada."""

from __future__ import annotations

from pathlib import Path

from .models import Word

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,{margin},1
Style: Hook,{font},64,&H00000000,&H00000000,&H0000E6FF,&H0000E6FF,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = "&H0000E6FF&"  # amarillo (formato BGR de ASS)


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").strip()


def chunk_words(words: list[Word], max_words: int = 3, max_chars: int = 18) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        candidate = " ".join(x.text for x in cur + [w])
        if cur and (len(cur) >= max_words or len(candidate) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w.text.endswith((".", "?", "!", ",")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    hook: str = "",
    hook_seconds: float = 3.0,
    font: str = "Arial",
    size: int = 82,
    margin_v: int = 480,
    uppercase: bool = True,
) -> str:
    lines = [ASS_HEADER.format(font=font, size=size, margin=margin_v)]
    if hook:
        text = _clean(hook.upper() if uppercase else hook)
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(min(hook_seconds, clip_end - clip_start))},Hook,,0,0,0,,{text}")

    inside = [w for w in words if w.end > clip_start and w.start < clip_end]
    for chunk in chunk_words(inside):
        chunk_end = chunk[-1].end
        for i, w in enumerate(chunk):
            start = w.start
            end = chunk[i + 1].start if i + 1 < len(chunk) else chunk_end
            parts = []
            for k, x in enumerate(chunk):
                t = _clean(x.text.upper() if uppercase else x.text)
                parts.append(f"{{\\c{HIGHLIGHT}}}{t}{{\\c&H00FFFFFF&}}" if k == i else t)
            lines.append(
                f"Dialogue: 0,{_ts(start - clip_start)},{_ts(end - clip_start)},Sub,,0,0,0,,{' '.join(parts)}"
            )
    return "\n".join(lines) + "\n"


def build_srt(words: list[Word], clip_start: float, clip_end: float) -> str:
    inside = [w for w in words if w.end > clip_start and w.start < clip_end]
    out = []

    def fmt(t: float) -> str:
        t = max(0.0, t)
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    for n, chunk in enumerate(chunk_words(inside, max_words=7, max_chars=42), start=1):
        out.append(f"{n}\n{fmt(chunk[0].start - clip_start)} --> {fmt(chunk[-1].end - clip_start)}\n"
                   f"{' '.join(w.text for w in chunk)}\n")
    return "\n".join(out)


def write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
