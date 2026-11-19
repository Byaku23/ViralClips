# ViralClips

Convierte videos largos en clips verticales 9:16 listos para Shorts, TikTok y Reels. Busca los momentos con más potencial viral, les da un puntaje de 0 a 100, los recorta con el hablante centrado y les quema subtítulos palabra por palabra.

Esta es la **fase 0**: un programa que corre en tu computadora. La versión web vendrá después, cuando los clips sean buenos.

## Qué acepta

- Un archivo de video: `mi_video.mp4`, `.mov`, `.mkv`, `.webm`...
- Una carpeta entera con videos (los procesa todos).
- Un link: YouTube, Google Drive, Dropbox, enlaces directos a un archivo y los más de mil sitios que soporta [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Las descargas se hacen desde tu computadora. Úsalo con videos tuyos o para los que tengas permiso: las políticas de YouTube no permiten descargar contenido ajeno.

## Instalación

Necesitas Python 3.10 o más nuevo y [ffmpeg](https://ffmpeg.org/download.html).

```bash
# macOS
brew install python ffmpeg
# Windows (PowerShell)
winget install Python.Python.3.12 Gyan.FFmpeg

git clone https://github.com/Byaku23/ViralClips.git
cd ViralClips
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -e .
```

Para que Claude juzgue los clips, crea una clave en [console.anthropic.com](https://console.anthropic.com) y guárdala:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."      # en Windows: setx ANTHROPIC_API_KEY "sk-ant-..."
```

Sin clave el programa igual funciona, solo con las señales de texto, audio y retención.

## Uso

```bash
# Los 10 mejores clips de un video tuyo
viralclips mi_video.mp4 --nicho "historia y curiosidades" --idioma es

# Desde un link
viralclips "https://www.youtube.com/watch?v=..." -n 15

# Partir un directo largo en todos los clips posibles, ordenados por puntaje
viralclips directo.mp4 --modo completo --objetivo 45

# Una carpeta completa, solo analizar (sin renderizar) para revisar rápido
viralclips ~/Videos/atlas --solo-analizar
```

Los resultados quedan en `clips/<nombre-del-video>/`:

- `001_87_titulo.mp4`: el clip, con el puesto y el puntaje en el nombre.
- `001_87_titulo.srt`: los subtítulos por separado, por si quieres editarlos.
- `resumen.md`: tabla con todos los clips, su puntaje y dónde empiezan.
- `clips.json`: todo el detalle (señales, razón del puntaje, título y gancho propuestos).

### Opciones útiles

| Opción | Qué hace |
| --- | --- |
| `--modo mejores` / `--modo completo` | Solo los N mejores, o el video entero dividido por temas |
| `-n 20` | Cuántos clips sacar |
| `--min 20 --max 60` | Duración mínima y máxima de cada clip, en segundos |
| `--whisper large-v3` | Transcripción más precisa (más lenta). Por defecto `small` |
| `--encuadre recorte` / `ajuste` | Recortar centrando la cara, o mostrar el video completo sobre fondo desenfocado (mejor para mapas y pantallas). `auto` decide solo |
| `--sin-ia` | No usar Claude |
| `--sin-refinar` | No pasar los mejores por el segundo juez (más barato) |
| `--cookies-navegador chrome` | Usar tu sesión del navegador si YouTube pide verificar que no eres un bot |

## Cómo decide qué es viral

1. **Transcribe** el audio con Whisper, con el tiempo exacto de cada palabra.
2. **Arma candidatos** de frases completas que duren entre `--min` y `--max` segundos, para no cortar una idea a la mitad.
3. **Filtra con señales baratas:**
   - retención: el mapa de calor "Más repetidos" de YouTube, cuando el video lo tiene;
   - gancho: preguntas, números y palabras como "nadie", "secreto" o "nunca" en la primera frase;
   - energía del audio, ritmo al hablar y si el clip termina en una frase cerrada.
4. **Claude Haiku** juzga los mejores candidatos con una rúbrica (gancho, se entiende solo, remate, emoción, encaje con tu nicho). Puede recortar frases de relleno y propone título y texto de gancho.
5. **Claude Sonnet** vuelve a juzgar solo los finalistas para afinar el puntaje.
6. Quita los clips que se solapan más de la mitad y renderiza los ganadores.

El puntaje final es 65 % el de Claude y 35 % el de las señales. Procesar una hora de video con IA cuesta unos centavos de dólar.

## Pruebas

```bash
pip install -e ".[dev]"
pytest
```

Las pruebas no llaman a la API de Claude ni descargan nada.
