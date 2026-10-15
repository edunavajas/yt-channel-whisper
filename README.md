# yt-channel-whisper

Herramientas para **convertir un canal de YouTube en una base de conocimiento en Markdown**: enumera el canal, descarga el audio, lo transcribe y genera un documento por vídeo listo para indexar (por ejemplo, en una base vectorial).

Nace como pieza del sistema self-hosted de "[Mi Empleado Digital](https://www.youtube.com/@DevKnives)": sirve para darle a un agente la memoria de todo lo que se ha dicho en un canal, sin depender de APIs de pago para indexar.

No usa la API de YouTube (no necesita clave): tira de [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).

---

## El pipeline (3 pasos)

```
1) channel_index.py    →  enumera los vídeos del canal        →  data/videos.jsonl
2) transcribe_channel.py →  descarga el audio y transcribe    →  out/<video_id>/transcript.txt
3) to_markdown.py      →  un Markdown por vídeo con frontmatter →  markdown/<video_id>.md
```

El resultado final (`markdown/`) es lo que indexarías en tu base de conocimiento (Outline, pgvector, lo que uses).

---

## Requisitos

- **Python 3.10+**
- **`yt-dlp`** en el `PATH` (`pip install yt-dlp`). Actualízalo a menudo: YouTube cambia y `yt-dlp` se rompe.
- Dependencias Python: `httpx`, `tqdm`, `python-dotenv` (ver `requirements.txt`).
- **Un servicio de transcripción Whisper** (solo para el paso 2). Cualquiera compatible con la API de OpenAI vale; ver más abajo.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## Uso

### 1. Indexar el canal

```bash
.venv/bin/python tools/channel_index.py \
  --channel-url "https://www.youtube.com/@DevKnives/videos" \
  --out data/videos.jsonl
```

Genera `data/videos.jsonl`, **una línea por vídeo**, con: `video_id`, `title`, `url`, `duration`, `view_count`… (la fecha y el canal no vienen en este índice rápido; `to_markdown.py` los completa si puede).

### 2. Transcribir

```bash
.venv/bin/python tools/transcribe_channel.py \
  --in data/videos.jsonl \
  --out-dir out \
  --speaches-base-url "http://localhost:8000" \
  --speaches-model whisper-large-v3 \
  --language es \
  --concurrency 2 \
  --skip-existing
```

- `--speaches-base-url` apunta a tu servicio de transcripción. Por defecto espera un servicio tipo **speaches** (una API compatible con OpenAI: `POST /v1/audio/transcriptions`).
- `--concurrency` lanza varias transcripciones a la vez.
- `--skip-existing` reanuda donde lo dejaste (no repite vídeos ya transcritos).
- `--delete-audio` borra los mp3 tras transcribir.
- Modo `--speaches-mode generic` para APIs que no son compatibles con OpenAI (`--speaches-endpoint /transcribe`).

Variables de entorno equivalentes: `SPEACHES_BASE_URL`, `SPEACHES_MODEL`, `SPEACHES_ENDPOINT`, `SPEACHES_MODE`, `LANGUAGE`.

**¿De dónde saco el servicio Whisper?** Tienes tres opciones:
- **[`media-tools`](https://github.com/edunavajas/media-tools)** (FastAPI con transcripción vía Nan Builders o Groq). Expone `POST /transcript` y `POST /jobs/whisper` con `Authorization: Bearer <token>`.
- **[`speaches`](https://github.com/speaches-ai/speaches)** self-hosted (Docker), compatible con la API de OpenAI. Es lo que espera el script por defecto.
- Cualquier endpoint compatible con `POST /v1/audio/transcriptions` de OpenAI (incluida la propia API de OpenAI).

Salida por vídeo: `out/<video_id>/transcript.txt`, `transcript.json` (con segmentos) y `transcript.srt`.

### 3. Convertir a Markdown

```bash
.venv/bin/python tools/to_markdown.py \
  --in data/videos.jsonl \
  --transcripts out \
  --out markdown
```

Genera **un `.md` por vídeo**, con frontmatter listo para RAG:

```markdown
---
title: "Cómo monté el segundo cerebro con IA"
video_id: "TUDjOSa1chQ"
url: "https://www.youtube.com/watch?v=TUDjOSa1chQ"
date: "2026-05-07"
duration_seconds: 942
channel: "Dev Knives"
---

# Cómo monté el segundo cerebro con IA

Vídeo: https://www.youtube.com/watch?v=TUDjOSa1chQ

...transcripción...
```

Opciones útiles: `--include-missing` (incluye vídeos sin transcripción), `--no-enrich` (no pidas fecha/canal extra a `yt-dlp`). El script tolera distintos nombres de campo (`title`/`name`, `date`/`published`, `duration`/`length`…), así que también funciona con tu propio JSON.

---

## Herramientas extra

| Herramienta | Para qué |
|---|---|
| `tools/merge_transcripts.py` | Junta todas las transcripciones de `out/` en un único corpus de texto (`data/corpus.txt`). |
| `tools/voice_profile.py` | Analiza el estilo del canal (palabras y frases más frecuentes) y genera un perfil de voz. |
| `tools/check_models.py` | Lista los modelos disponibles en tu servicio de transcripción (speaches). |
| `tools/find_working_model.py` | Prueba varios modelos Whisper con un audio y te dice cuál transcribe bien tu idioma. |

---

## Notas y problemas frecuentes

- **"Sign in to confirm you're not a bot".** Desde IPs de datacenter (VPS, cloud), YouTube bloquea la descarga de audio sin cookies. *El índice del canal funciona igual*, pero la transcripción necesita cookies. Exporta las cookies de una sesión logueada y pásalas con `--cookies` de `yt-dlp` (o usa un proxy residencial). En una máquina doméstica normalmente no hace falta.
- **`yt-dlp` desactualizado.** Si el paso 1 falla con errores de extracción, actualiza `yt-dlp` antes de nada (`pip install -U yt-dlp`).
- **Reanudar.** Vuelve a lanzar el paso 2 con `--skip-existing`: solo procesa lo que falte.

---

## Licencia

MIT © Eduardo Navajas
