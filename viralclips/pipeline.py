"""Une todas las piezas: entrada → transcripción → candidatos → puntaje → render."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import candidates as cand_mod
from . import ingest, llm, render, signals, subtitles, transcribe
from .models import Candidate, Sentence, Source, Word


@dataclass
class Options:
    out_dir: Path = Path("clips")
    cache_dir: Path = Path(".viralclips_cache")
    mode: str = "mejores"  # "mejores" | "completo"
    count: int | None = 10  # en modo completo, None = todos
    min_len: float = 20.0
    max_len: float = 60.0
    target_len: float = 45.0
    language: str | None = None
    whisper_model: str = "small"
    device: str = "auto"
    use_ai: bool = True
    refine: bool = True
    judge_model: str = llm.JUDGE_MODEL
    refine_model: str = llm.REFINE_MODEL
    niche: str = ""
    framing: str = "auto"  # "auto" | "recorte" | "ajuste"
    burn_subtitles: bool = True
    show_hook: bool = True
    analyze_only: bool = False
    cookies_from_browser: str | None = None


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:max_len].strip("-") or "video"


def _work_dir(src: Source, cache_dir: Path) -> Path:
    if ingest.is_url(src.origin):
        key = src.origin
    else:
        st = os.stat(src.path)
        key = f"{Path(src.path).resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return cache_dir / "trabajos" / hashlib.sha1(key.encode()).hexdigest()[:12]


def score_signals(c: Candidate, sentences: list[Sentence], energy: signals.AudioEnergy, src: Source) -> None:
    s = signals.text_signals(c, sentences)
    s["energia"] = energy.score(c.start, c.end)
    ret = signals.heatmap_score(src.heatmap, c.start, c.end)
    if ret is not None:
        s["retencion"] = ret
    c.signals = {k: round(v, 3) for k, v in s.items()}
    c.heuristic = signals.heuristic_score(s)


def combine(c: Candidate) -> None:
    c.score = round(0.65 * c.llm + 0.35 * c.heuristic, 1) if c.llm is not None else c.heuristic


def select(
    words: list[Word], src: Source, energy: signals.AudioEnergy, opts: Options, log=print, client=None
) -> tuple[list[Candidate], list[Sentence]]:
    sentences = cand_mod.build_sentences(words)
    if not sentences:
        return [], sentences

    if opts.mode == "completo":
        cands = cand_mod.coverage_segments(sentences, opts.target_len, opts.min_len, opts.max_len)
    else:
        cands = cand_mod.sliding_candidates(sentences, opts.min_len, opts.max_len)
        if not cands:  # video más corto que min_len: un solo clip con todo
            cands = cand_mod.coverage_segments(sentences, opts.target_len, 0, opts.max_len)
    log(f"  {len(sentences)} frases, {len(cands)} candidatos")

    for c in cands:
        score_signals(c, sentences, energy, src)
        combine(c)

    if opts.mode == "completo":
        pool = cands
    else:
        pool_size = max((opts.count or 10) * 3, 20)
        pool = cand_mod.non_max_suppression(cands, key="heuristic", limit=pool_size)

    if opts.use_ai:
        ai_ok = llm.judge(pool, sentences, opts.niche, opts.judge_model, client=client, log=log)
        for c in pool:
            score_signals(c, sentences, energy, src)  # el recorte de Claude cambia el rango
            combine(c)
        if ai_ok and opts.refine and opts.mode != "completo" and opts.refine_model:
            top = cand_mod.non_max_suppression(pool, limit=opts.count or 10)
            llm.judge(top, sentences, opts.niche, opts.refine_model, client=client, log=log)
            for c in top:
                score_signals(c, sentences, energy, src)
                combine(c)

    if opts.mode == "completo":
        chosen = sorted(pool, key=lambda c: c.score, reverse=True)
        if opts.count:
            chosen = chosen[: opts.count]
    else:
        chosen = cand_mod.non_max_suppression(pool, limit=opts.count or 10)
    return chosen, sentences


def _write_summary(folder: Path, src: Source, clips: list[dict]) -> None:
    lines = [
        f"# {src.title}",
        "",
        f"Origen: {src.origin}",
        "",
        "| # | Puntaje | IA | Señales | Inicio | Duración | Título |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, c in enumerate(clips, start=1):
        start = f"{int(c['start'] // 60)}:{int(c['start'] % 60):02d}"
        ia = "" if c["llm"] is None else f"{c['llm']:.0f}"
        title = (c["title"] or c["text"][:60]).replace("|", "/")
        lines.append(f"| {i} | {c['score']:.0f} | {ia} | {c['heuristic']:.0f} | {start} | {c['duration']:.0f} s | {title} |")
    (folder / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process(item: str, opts: Options, log=print, client=None) -> Path:
    log(f"▶ {item}")
    src = ingest.load_source(item, opts.cache_dir, opts.cookies_from_browser)
    log(f"  {src.title} ({src.duration / 60:.1f} min, {src.width}x{src.height})"
        + ("" if not src.heatmap else ", con mapa de retención de YouTube"))
    work = _work_dir(src, opts.cache_dir)
    wav = transcribe.extract_audio(src.path, work / "audio.wav")
    if not (work / "transcripcion.json").exists():
        log(f"  Transcribiendo con Whisper ({opts.whisper_model}), puede tardar unos minutos...")
    words = transcribe.transcribe(wav, work / "transcripcion.json", opts.whisper_model, opts.language, opts.device)
    if not words:
        raise RuntimeError("No se detectó voz en el video; por ahora el detector necesita narración o diálogo.")
    energy = signals.AudioEnergy(wav)

    chosen, _ = select(words, src, energy, opts, log=log, client=client)

    folder = opts.out_dir / slugify(src.title)
    folder.mkdir(parents=True, exist_ok=True)
    pad_before, pad_after = 0.15, 0.35
    results = []
    for rank, c in enumerate(chosen, start=1):
        start = max(0.0, c.start - pad_before)
        end = min(src.duration or c.end + pad_after, c.end + pad_after)
        name = f"{rank:03d}_{int(c.score):02d}_{slugify(c.title or c.text, 40)}"
        d = c.to_dict()
        d.update(file=f"{name}.mp4", clip_start=round(start, 3), clip_end=round(end, 3))
        if not opts.analyze_only:
            ass = None
            if opts.burn_subtitles:
                ass = subtitles.write(
                    folder / f"{name}.ass",
                    subtitles.build_ass(words, start, end, hook=c.hook if opts.show_hook else ""),
                )
            subtitles.write(folder / f"{name}.srt", subtitles.build_srt(words, start, end))
            log(f"  Render {rank}/{len(chosen)}: {name}.mp4")
            d["framing"] = render.render_clip(src.path, folder / f"{name}.mp4", start, end,
                                              src.width, src.height, opts.framing, ass)
            if ass is not None:
                ass.unlink(missing_ok=True)
        results.append(d)

    (folder / "clips.json").write_text(
        json.dumps({"source": src.origin, "title": src.title, "clips": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary(folder, src, results)
    log(f"  Listo: {len(results)} clips en {folder}")
    return folder
