#!/usr/bin/env bash
# Un solo comando: canal de YouTube -> Markdown listo para indexar.
#
# Uso:
#   CHANNEL_URL="https://www.youtube.com/@TuCanal/videos" \
#   SPEACHES_BASE_URL="http://localhost:8000" \
#   ./build_corpus.sh
#
# Variables (todas opcionales salvo CHANNEL_URL):
#   CHANNEL_URL        URL del canal (página /videos)              [obligatoria]
#   SPEACHES_BASE_URL  Servicio Whisper compatible con OpenAI      [http://localhost:8000]
#   SPEACHES_MODEL     Modelo a usar                               [whisper-large-v3]
#   LANGUAGE           Idioma                                       [es]
#   OUT_JSONL          Índice de vídeos                             [data/videos.jsonl]
#   OUT_DIR            Carpeta de transcripciones                   [out]
#   MD_DIR             Carpeta de Markdown final                    [markdown]
set -euo pipefail

: "${CHANNEL_URL:?Define CHANNEL_URL, p.ej. https://www.youtube.com/@TuCanal/videos}"
SPEACHES_BASE_URL="${SPEACHES_BASE_URL:-http://localhost:8000}"
SPEACHES_MODEL="${SPEACHES_MODEL:-whisper-large-v3}"
LANGUAGE="${LANGUAGE:-es}"
OUT_JSONL="${OUT_JSONL:-data/videos.jsonl}"
OUT_DIR="${OUT_DIR:-out}"
MD_DIR="${MD_DIR:-markdown}"

echo "== 1/3 · Indexando el canal =="
python tools/channel_index.py --channel-url "$CHANNEL_URL" --out "$OUT_JSONL"

echo "== 2/3 · Transcribiendo (servicio: $SPEACHES_BASE_URL, modelo: $SPEACHES_MODEL) =="
python tools/transcribe_channel.py \
  --in "$OUT_JSONL" \
  --out-dir "$OUT_DIR" \
  --speaches-base-url "$SPEACHES_BASE_URL" \
  --speaches-model "$SPEACHES_MODEL" \
  --language "$LANGUAGE" \
  --skip-existing

echo "== 3/3 · Generando Markdown con frontmatter =="
python tools/to_markdown.py --in "$OUT_JSONL" --transcripts "$OUT_DIR" --out "$MD_DIR"

echo
echo "Listo. Documentos listos para indexar en: $MD_DIR/"
