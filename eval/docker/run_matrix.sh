#!/usr/bin/env bash
# Matriz de modelos en el entorno «igual a producción» (E07a): Ollama con 4 CPU y 8 GB, perfil
# «server» (sin GPU, 4 hilos), cortes de PRUEBA, 3 corridas por modelo y tabla comparativa final.
#
# Uso (desde cualquier carpeta):
#   EVALUACIONES_DIR=~/Proyectos/SOLERCIA/evaluaciones PLATFORM=linux/arm64 eval/docker/run_matrix.sh
#   EVALUACIONES_DIR=… PLATFORM=linux/amd64 eval/docker/run_matrix.sh qwen3.5:4b gemma4:e2b
#   … run_matrix.sh --dry-run          # solo imprime los comandos
#
# Variables: PLATFORM (linux/arm64 | linux/amd64), RUNS (3), CORTES (PRUEBA: 2026-10-01,2026-10-05),
# EVAL_ARGS (argumentos extra para eval_classifier), KEEP_UP=1 (no apaga el entorno al final).
# E08: HOST_MODELS=1 monta el almacén de modelos del host en solo lectura (compose.hostmodels.yml);
# OUT_SUBDIR (e07a) elige la carpeta de resultados; PROBE_P50_S=60 sondea 10 registros (5 por corte,
# 1 corrida) y, si el p50 supera ese umbral en segundos, corre el modelo con CUT_LIMIT (15 por
# corte = 30 registros) y lo anota en LIMITE.txt. Cada modelo deja ram_pico.txt (docker stats).
# Los modelos deben estar precargados en el volumen del contenedor (ver README): el script no
# descarga nada; si falta uno, se detiene antes de evaluar.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HERE/compose.eval.yml")
if [[ "${HOST_MODELS:-0}" == "1" ]]; then COMPOSE+=(-f "$HERE/compose.hostmodels.yml"); fi
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

DEFAULT_MODELS=(qwen3.5:9b-q4_K_M ornith:9b qwen3.5:4b gemma4:e2b)
if [[ $# -gt 0 ]]; then MODELS=("$@"); else MODELS=("${DEFAULT_MODELS[@]}"); fi
EMBEDDING_MODEL="${EMBEDDING_MODEL:-qwen3-embedding:0.6b}"
export PLATFORM="${PLATFORM:-linux/arm64}"
RUNS="${RUNS:-3}"
CORTES="${CORTES:-2026-10-01,2026-10-05}"
: "${EVALUACIONES_DIR:?Define EVALUACIONES_DIR con la carpeta evaluaciones/ (fuera del repo)}"
export EVALUACIONES_DIR

case "$PLATFORM" in
  linux/arm64 | linux/amd64) ;;
  *) echo "PLATFORM debe ser linux/arm64 o linux/amd64 (recibido: $PLATFORM)." >&2; exit 1 ;;
esac
ARCH="${PLATFORM#linux/}"
# Manifiestos por plataforma del índice ollama/ollama:0.35.1@sha256:292ee794… (imagetools inspect).
case "$ARCH" in
  amd64) DEFAULT_OLLAMA_IMAGE="ollama/ollama:0.35.1@sha256:17e945f1aa6e505707eeb621e3f36847d0a4a063d4778f7007645acccfb8bd4f" ;;
  arm64) DEFAULT_OLLAMA_IMAGE="ollama/ollama:0.35.1@sha256:149e245141f5d0370bd46f774229e87781276a44050a02e8fe7e35b82a15adb5" ;;
esac
export OLLAMA_IMAGE="${OLLAMA_IMAGE:-$DEFAULT_OLLAMA_IMAGE}"
STAMP="$(date +%Y-%m-%d_%H%M)"
OUT_SUBDIR="${OUT_SUBDIR:-e07a}"
OUT_ROOT="/data/resultados/${OUT_SUBDIR}/${STAMP}_${ARCH}"
HOST_OUT_ROOT="${EVALUACIONES_DIR}/resultados/${OUT_SUBDIR}/${STAMP}_${ARCH}"
PROBE_P50_S="${PROBE_P50_S:-0}"
CUT_LIMIT="${CUT_LIMIT:-15}"
# Embeddings cacheados por plataforma: los vectores calculados en CPU emulada no se mezclan
# con los de la Mac (Metal).
CACHE_DIR="/data/resultados/_cache/embeddings-${ARCH}"

run() {
  printf '+ %s\n' "$*"
  if [[ $DRY_RUN -eq 0 ]]; then "$@"; fi
}

# La imagen del evaluador se reconstruye para la plataforma pedida (la caché la hace rápida).
run "${COMPOSE[@]}" build evaluator
run "${COMPOSE[@]}" up -d --wait ollama

for model in "$EMBEDDING_MODEL" "${MODELS[@]}"; do
  if [[ $DRY_RUN -eq 0 ]] && ! "${COMPOSE[@]}" exec -T ollama ollama show "$model" >/dev/null 2>&1; then
    echo "Falta el modelo «$model» en el volumen del contenedor. Precárgalo con:" >&2
    echo "  docker compose -f $HERE/compose.eval.yml exec ollama ollama pull $model" >&2
    exit 1
  fi
done

evaluate() { # modelo carpeta corridas [argumentos extra…]
  local model="$1" out="$2" runs="$3"
  shift 3
  # shellcheck disable=SC2086 # EVAL_ARGS se separa por espacios a propósito.
  run "${COMPOSE[@]}" run --rm evaluator python -m scripts.eval_classifier \
    --golden-dir /data/golden --rules /data/reglas.json --cortes "$CORTES" \
    --model "$model" --embedding-model "$EMBEDDING_MODEL" --runs "$runs" \
    --profile server --num-thread 4 \
    --base-url http://ollama:11434 --embedding-url http://ollama:11434 \
    --cache-dir "$CACHE_DIR" --out-dir "$out" "$@" ${EVAL_ARGS:-}
}

# Pico de memoria del contenedor de Ollama mientras corre un modelo (muestreo cada 2 s).
ram_watch() {
  local cid file="$1"
  cid="$("${COMPOSE[@]}" ps -q ollama)"
  while true; do
    docker stats --no-stream --format '{{.MemUsage}}' "$cid" | cut -d/ -f1 >>"$file"
    sleep 2
  done
}

# E08: calienta la caché de embeddings antes de los modelos de chat. Sin esto, la primera corrida
# alterna /api/embed y /api/chat por registro y, con OLLAMA_MAX_LOADED_MODELS=1, recarga el modelo
# de chat cada vez (más de un minuto por registro en CPU) y ensucia la latencia y el determinismo.
if [[ "${WARM_EMBEDDINGS:-1}" == "1" ]]; then
  run "${COMPOSE[@]}" run --rm evaluator python -m scripts.eval_classifier \
    --golden-dir /data/golden --rules /data/reglas.json --cortes "$CORTES" \
    --embedding-model "$EMBEDDING_MODEL" --candidates-only --profile server --num-thread 4 \
    --embedding-url http://ollama:11434 --cache-dir "$CACHE_DIR" \
    --out-dir "$OUT_ROOT/_embeddings" ${EVAL_ARGS:-}  # shellcheck disable=SC2086
  run "${COMPOSE[@]}" exec -T ollama ollama stop "$EMBEDDING_MODEL" || true
fi

folders=()
for model in "${MODELS[@]}"; do
  safe="${model//[^A-Za-z0-9._-]/-}"
  out="$OUT_ROOT/$safe"
  limit_args=()
  if [[ $DRY_RUN -eq 0 && "$PROBE_P50_S" != "0" ]]; then
    evaluate "$model" "$OUT_ROOT/_sonda/$safe" 1 --limit 5
    p50_ms="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["latency_ms"]["p50"] or 0)' \
      "$HOST_OUT_ROOT/_sonda/$safe/metrics.json")"
    if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) > float(sys.argv[2]) * 1000 else 1)' \
      "$p50_ms" "$PROBE_P50_S"; then
      limit_args=(--limit "$CUT_LIMIT")
      mkdir -p "$HOST_OUT_ROOT/$safe"
      echo "p50 de la sonda ${p50_ms} ms > ${PROBE_P50_S} s: --limit $CUT_LIMIT por corte." \
        >"$HOST_OUT_ROOT/$safe/LIMITE.txt"
    fi
  fi
  watcher=""
  if [[ $DRY_RUN -eq 0 ]]; then
    mkdir -p "$HOST_OUT_ROOT/$safe"
    ram_watch "$HOST_OUT_ROOT/$safe/ram_muestras.txt" &
    watcher=$!
  fi
  evaluate "$model" "$out" "$RUNS" ${limit_args[@]+"${limit_args[@]}"}
  if [[ -n "$watcher" ]]; then
    kill "$watcher" 2>/dev/null || true
    wait "$watcher" 2>/dev/null || true
    python3 - "$HOST_OUT_ROOT/$safe/ram_muestras.txt" >"$HOST_OUT_ROOT/$safe/ram_pico.txt" <<'PY'
import re, sys
units = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "kB": 1e3, "MB": 1e6, "GB": 1e9}
peak = 0.0
for line in open(sys.argv[1]):
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", line)
    if m and m.group(2) in units:
        peak = max(peak, float(m.group(1)) * units[m.group(2)])
print(f"{peak / 2**30:.2f} GiB")
PY
  fi
  folders+=("$out")
  # Un modelo a la vez: se descarga antes del siguiente (OLLAMA_MAX_LOADED_MODELS=1).
  run "${COMPOSE[@]}" exec -T ollama ollama stop "$model" || true
done

run "${COMPOSE[@]}" run --rm evaluator python -m scripts.eval_compare "${folders[@]}" \
  --out "$OUT_ROOT/COMPARATIVA.md"
echo "Tabla: ${HOST_OUT_ROOT}/COMPARATIVA.md"

if [[ "${KEEP_UP:-0}" != "1" ]]; then
  # Sin -v: el volumen de modelos se conserva.
  run "${COMPOSE[@]}" down
fi
