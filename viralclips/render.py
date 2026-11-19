"""Render vertical 9:16 con ffmpeg: recorte centrado en la cara o video completo sobre fondo desenfocado."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

OUT_W, OUT_H = 1080, 1920


def face_center(video: str, start: float, end: float, samples: int = 12) -> tuple[float | None, float]:
    """Centro horizontal típico de las caras (0 a 1) y fracción de muestras con cara."""
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(video)
    xs, weights, hits = [], [], 0
    times = np.linspace(start + 0.5, max(start + 0.6, end - 0.5), samples)
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 480 / max(w, 1)
        small = cv2.resize(frame, (480, int(h * scale))) if scale < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30))
        if len(faces):
            hits += 1
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])  # la cara más grande
            xs.append((fx + fw / 2) / small.shape[1])
            weights.append(fw * fh)
    cap.release()
    ratio = hits / max(len(times), 1)
    if not xs:
        return None, ratio
    order = np.argsort(xs)
    xs_sorted, w_sorted = np.array(xs)[order], np.array(weights)[order]
    cum = np.cumsum(w_sorted) / w_sorted.sum()
    return float(xs_sorted[np.searchsorted(cum, 0.5)]), ratio  # mediana ponderada


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_filter(src_w: int, src_h: int, mode: str, center_x: float | None, ass: Path | None) -> str:
    if src_h >= src_w * 1.5:  # ya es vertical
        base = (f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]")
    elif mode == "recorte":
        crop_w = min(src_w, int(src_h * 9 / 16)) // 2 * 2
        cx = (center_x if center_x is not None else 0.5) * src_w
        x = int(min(max(cx - crop_w / 2, 0), src_w - crop_w))
        base = f"[0:v]crop={crop_w}:{src_h}:{x}:0,scale={OUT_W}:{OUT_H},setsar=1[v]"
    else:  # "ajuste": video completo sobre una copia desenfocada
        base = (f"[0:v]split=2[a][b];"
                f"[a]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
                f"gblur=sigma=40,eq=brightness=-0.08[bg];"
                f"[b]scale={OUT_W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    if ass is not None:
        base = base[:-3] + f"[pre];[pre]ass='{_escape_filter_path(ass)}'[v]"
    return base


def render_clip(
    video: str,
    out: Path,
    start: float,
    end: float,
    src_w: int,
    src_h: int,
    mode: str = "auto",
    ass: Path | None = None,
) -> str:
    """Renderiza el clip y devuelve el modo de encuadre usado."""
    center, ratio = (None, 0.0)
    if src_h < src_w * 1.5 and mode in ("auto", "recorte"):
        center, ratio = face_center(video, start, end)
    if mode == "auto":
        mode = "recorte" if (center is not None and ratio >= 0.4) else "ajuste"
    filt = build_filter(src_w, src_h, mode, center, ass)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-i", video, "-t", f"{end - start:.3f}",
        "-filter_complex", filt, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return mode
