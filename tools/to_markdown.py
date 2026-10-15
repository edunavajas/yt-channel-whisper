#!/usr/bin/env python3
"""
Convierte el canal indexado + las transcripciones en Markdown listo para indexar.

Genera UN documento Markdown por vídeo, con frontmatter (título, fecha, URL,
duración), pensado para meterlo en una base de conocimiento vectorial.

Entrada:
  - Un JSONL de vídeos (salida de channel_index.py): data/videos.jsonl
  - Un directorio de transcripciones (salida de transcribe_channel.py): out/<video_id>/transcript.txt

Salida:
  - Un directorio con un .md por vídeo: markdown/<video_id>.md

Nota: el índice rápido (channel_index.py --flat-playlist) no trae la fecha de
subida ni el canal. Si faltan y tienes `yt-dlp` instalado, este script los pide
(un vídeo por consulta). Desactívalo con --no-enrich.

No usa dependencias externas (solo la librería estándar).

Ejemplo:
  python tools/to_markdown.py --in data/videos.jsonl --transcripts out --out markdown
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("to_markdown")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_videos(input_path: Path) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                videos.append(json.loads(line))
    return videos


def format_date(upload_date: Any) -> str:
    """yt-dlp entrega la fecha como YYYYMMDD; la pasamos a YYYY-MM-DD."""
    text = str(upload_date or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def yaml_escape(value: Any) -> str:
    """Escapa un valor para el frontmatter YAML (entre comillas dobles)."""
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", " ").strip()
    return f'"{text}"'


def fetch_metadata(url: str) -> dict[str, Any]:
    """Pide a yt-dlp fecha, canal y duración de un vídeo concreto."""
    if not url or not shutil.which("yt-dlp"):
        return {}
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--no-warnings", "--print",
             "%(upload_date)s\t%(channel,uploader)s\t%(duration)s", url],
            capture_output=True, text=True, timeout=90,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        upload_date, channel, duration = (result.stdout.strip().split("\t") + ["", "", ""])[:3]
        return {
            "upload_date": upload_date or None,
            "channel": channel or None,
            "duration": int(duration) if duration.isdigit() else None,
        }
    except Exception as exc:  # noqa: BLE001 - el enriquecido es best-effort
        logger.debug(f"No se pudo enriquecer {url}: {exc}")
        return {}


def first_value(video: dict[str, Any], *keys: str) -> Any:
    """Devuelve el primer campo presente (tolera distintos nombres de origen)."""
    for key in keys:
        if video.get(key) not in (None, ""):
            return video[key]
    return None


def build_markdown(video: dict[str, Any], transcript: str) -> str:
    title = first_value(video, "title", "name") or video.get("video_id")
    video_id = first_value(video, "video_id", "id")
    url = first_value(video, "url", "webpage_url", "link") or (
        f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    )
    date_value = first_value(video, "upload_date", "date", "published", "published_at", "timestamp")
    duration = first_value(video, "duration", "duration_seconds", "length")
    channel = first_value(video, "channel", "uploader", "author", "channel_name")
    lines = [
        "---",
        f"title: {yaml_escape(title)}",
        f"video_id: {yaml_escape(video_id)}",
        f"url: {yaml_escape(url)}",
        f"date: {yaml_escape(format_date(date_value))}",
        f"duration_seconds: {duration if isinstance(duration, (int, float)) else 'null'}",
        f"channel: {yaml_escape(channel)}",
        "---",
        "",
        f"# {title}",
        "",
        f"Vídeo: {url}",
        "",
        transcript.strip(),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte el canal indexado + transcripciones en Markdown con frontmatter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python tools/to_markdown.py --in data/videos.jsonl --transcripts out --out markdown
  python tools/to_markdown.py --in data/videos.jsonl --include-missing --no-enrich
        """,
    )
    parser.add_argument("--in", dest="input", type=Path, default=Path("data/videos.jsonl"),
                        help="JSONL de vídeos (salida de channel_index.py)")
    parser.add_argument("--transcripts", type=Path, default=Path("out"),
                        help="Directorio de transcripciones (salida de transcribe_channel.py)")
    parser.add_argument("--out", type=Path, default=Path("markdown"),
                        help="Directorio de salida para los .md (default: markdown/)")
    parser.add_argument("--include-missing", action="store_true",
                        help="Incluye también los vídeos sin transcripción (con el cuerpo vacío)")
    parser.add_argument("--no-enrich", action="store_true",
                        help="No pidas a yt-dlp la fecha/canal que falten")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.input.exists():
        logger.error(f"No existe el fichero de entrada: {args.input}")
        sys.exit(1)

    videos = load_videos(args.input)
    args.out.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    enriched = 0
    for video in videos:
        video_id = first_value(video, "video_id", "id")
        if not video_id:
            continue
        transcript_path = args.transcripts / video_id / "transcript.txt"
        if transcript_path.exists():
            transcript = transcript_path.read_text(encoding="utf-8", errors="replace")
        elif args.include_missing:
            transcript = ""
        else:
            skipped += 1
            continue

        # Frontmatter: completa fecha/canal si faltan (el índice rápido no los trae).
        has_date = first_value(video, "upload_date", "date", "published", "published_at", "timestamp")
        has_channel = first_value(video, "channel", "uploader", "author", "channel_name")
        if not args.no_enrich and (not has_date or not has_channel):
            metadata = fetch_metadata(video.get("url") or video.get("webpage_url") or "")
            if metadata:
                enriched += 1
                for key, value in metadata.items():
                    if value and not video.get(key):
                        video[key] = value

        target = args.out / f"{video_id}.md"
        target.write_text(build_markdown(video, transcript), encoding="utf-8")
        written += 1

    logger.info(f"Escritos {written} documentos Markdown en {args.out}/ "
                f"({skipped} sin transcripción, {enriched} enriquecidos con yt-dlp)")


if __name__ == "__main__":
    main()
