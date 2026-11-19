"""Entrada de videos: archivos locales, carpetas y links (YouTube, Drive, Dropbox, enlaces directos).

Las descargas se hacen con yt-dlp desde tu propia computadora. Úsalo solo con videos
propios o para los que tengas permiso.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .models import Source

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".flv", ".ts"}


def is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), re.I))


def normalize_url(url: str) -> str:
    """Ajusta links de servicios de nube para que apunten al archivo y no a la página."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if "dropbox.com" in host:
        query = parse_qs(parsed.query)
        query["dl"] = ["1"]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    return url.strip()


def expand_inputs(inputs: list[str]) -> list[str]:
    """Convierte carpetas en la lista de videos que contienen; deja links y archivos tal cual."""
    out: list[str] = []
    for item in inputs:
        if is_url(item):
            out.append(item)
            continue
        p = Path(item).expanduser()
        if p.is_dir():
            out.extend(str(f) for f in sorted(p.rglob("*")) if f.suffix.lower() in VIDEO_EXTS)
        elif p.is_file():
            out.append(str(p))
        else:
            raise FileNotFoundError(f"No encuentro el archivo o carpeta: {item}")
    return out


def probe(path: str) -> tuple[int, int, float]:
    """Devuelve (ancho, alto, duración en segundos) usando ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    duration = float(data.get("format", {}).get("duration") or 0)
    return int(stream.get("width") or 0), int(stream.get("height") or 0), duration


def _download(url: str, cache_dir: Path, cookies_from_browser: str | None) -> Source:
    import yt_dlp  # import tardío: solo hace falta para links

    url = normalize_url(url)
    key = hashlib.sha1(url.encode()).hexdigest()[:12]
    target = cache_dir / "descargas" / key
    target.mkdir(parents=True, exist_ok=True)
    meta_file = target / "info.json"

    existing = [f for f in target.iterdir() if f.suffix.lower() in VIDEO_EXTS]
    if existing and meta_file.exists():
        info = json.loads(meta_file.read_text())
        path = str(existing[0])
    else:
        opts = {
            "outtmpl": str(target / "video.%(ext)s"),
            # Hasta 1080p es suficiente para un short de 1080x1920.
            "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        if cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        files = [f for f in target.iterdir() if f.suffix.lower() in VIDEO_EXTS]
        if not files:
            raise RuntimeError(f"La descarga de {url} no produjo un archivo de video.")
        path = str(files[0])
        keep = {k: info.get(k) for k in ("title", "heatmap", "duration", "webpage_url", "uploader")}
        meta_file.write_text(json.dumps(keep, ensure_ascii=False))
        info = keep

    w, h, d = probe(path)
    return Source(
        path=path,
        title=info.get("title") or Path(path).stem,
        origin=url,
        heatmap=info.get("heatmap") or [],
        width=w,
        height=h,
        duration=d,
    )


def load_source(item: str, cache_dir: Path, cookies_from_browser: str | None = None) -> Source:
    if is_url(item):
        return _download(item, cache_dir, cookies_from_browser)
    w, h, d = probe(item)
    return Source(path=item, title=Path(item).stem, origin=item, width=w, height=h, duration=d)
