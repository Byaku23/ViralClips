"""Línea de comandos: `viralclips ENTRADA [ENTRADA...] [opciones]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ingest, llm
from .pipeline import Options, process


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="viralclips",
        description="Convierte videos largos en clips verticales 9:16 con subtítulos y puntaje de viralidad.",
    )
    p.add_argument("entradas", nargs="+",
                   help="Archivos de video, carpetas o links (YouTube, Google Drive, Dropbox, enlace directo).")
    p.add_argument("-o", "--salida", default="clips", help="Carpeta de salida (por defecto: clips).")
    p.add_argument("--modo", choices=["mejores", "completo"], default="mejores",
                   help="mejores: solo los N clips con más potencial. completo: parte todo el video por temas.")
    p.add_argument("-n", "--cantidad", type=int, default=None,
                   help="Cuántos clips sacar (por defecto 10 en modo mejores, todos en modo completo).")
    p.add_argument("--min", type=float, default=20.0, help="Duración mínima de un clip en segundos.")
    p.add_argument("--max", type=float, default=60.0, help="Duración máxima de un clip en segundos.")
    p.add_argument("--objetivo", type=float, default=45.0, help="Duración ideal en modo completo.")
    p.add_argument("--idioma", default=None, help="Idioma del video (es, en...). Si no, se detecta solo.")
    p.add_argument("--whisper", default="small",
                   help="Modelo de Whisper: tiny, base, small, medium, large-v3 (más grande = más preciso y lento).")
    p.add_argument("--dispositivo", default="auto", help="auto, cpu o cuda.")
    p.add_argument("--nicho", default="", help='Tema del canal, p. ej. "historia y curiosidades".')
    p.add_argument("--sin-ia", action="store_true", help="No usar Claude; solo señales de texto, audio y retención.")
    p.add_argument("--sin-refinar", action="store_true", help="No volver a juzgar los mejores con el modelo fino.")
    p.add_argument("--modelo-juez", default=llm.JUDGE_MODEL, help="Modelo que puntúa todos los candidatos.")
    p.add_argument("--modelo-fino", default=llm.REFINE_MODEL, help="Modelo que afina los mejores.")
    p.add_argument("--encuadre", choices=["auto", "recorte", "ajuste"], default="auto",
                   help="recorte: centra la cara. ajuste: video completo sobre fondo desenfocado. auto: decide solo.")
    p.add_argument("--sin-subtitulos", action="store_true", help="No quemar subtítulos (igual se guarda el .srt).")
    p.add_argument("--sin-gancho", action="store_true", help="No mostrar el texto de gancho al inicio.")
    p.add_argument("--solo-analizar", action="store_true", help="Solo calcular y listar clips, sin renderizar.")
    p.add_argument("--cookies-navegador", default=None,
                   help="Usar las cookies de tu navegador para descargar (chrome, firefox, safari, edge).")
    p.add_argument("--cache", default=".viralclips_cache", help="Carpeta de caché de descargas y transcripciones.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    count = args.cantidad if args.cantidad is not None else (10 if args.modo == "mejores" else None)
    opts = Options(
        out_dir=Path(args.salida),
        cache_dir=Path(args.cache),
        mode=args.modo,
        count=count,
        min_len=args.min,
        max_len=args.max,
        target_len=args.objetivo,
        language=args.idioma,
        whisper_model=args.whisper,
        device=args.dispositivo,
        use_ai=not args.sin_ia,
        refine=not args.sin_refinar,
        judge_model=args.modelo_juez,
        refine_model=args.modelo_fino,
        niche=args.nicho,
        framing=args.encuadre,
        burn_subtitles=not args.sin_subtitulos,
        show_hook=not args.sin_gancho,
        analyze_only=args.solo_analizar,
        cookies_from_browser=args.cookies_navegador,
    )
    if opts.min_len >= opts.max_len:
        print("Error: --min debe ser menor que --max.", file=sys.stderr)
        return 2

    try:
        items = ingest.expand_inputs(args.entradas)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if not items:
        print("No encontré videos en las entradas indicadas.", file=sys.stderr)
        return 2

    if opts.use_ai:
        try:
            import anthropic

            client = anthropic.Anthropic()
        except Exception as e:  # sin credenciales: seguir sin IA en vez de fallar
            print(f"Aviso: no pude iniciar Claude ({e}). Sigo solo con señales; usa --sin-ia para ocultar este aviso.",
                  file=sys.stderr)
            client, opts.use_ai = None, False
    else:
        client = None

    failures = 0
    for item in items:
        try:
            process(item, opts, client=client)
        except Exception as e:  # un video malo no debe frenar el lote
            failures += 1
            print(f"  Error con {item}: {e}", file=sys.stderr)
    return 1 if failures == len(items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
