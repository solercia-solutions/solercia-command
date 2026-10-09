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
# Los modelos deben estar precargados en el volumen del contenedor (ver README): el script no
# descarga nada; si falta uno, se detiene antes de evaluar.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HERE/compose.eval.yml")
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
STAMP="$(date +%Y-%m-%d_%H%M)"
OUT_ROOT="/data/resultados/e07a/${STAMP}_${ARCH}"
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

folders=()
for model in "${MODELS[@]}"; do
  safe="${model//[^A-Za-z0-9._-]/-}"
  out="$OUT_ROOT/$safe"
  # shellcheck disable=SC2086 # EVAL_ARGS se separa por espacios a propósito.
  run "${COMPOSE[@]}" run --rm evaluator python -m scripts.eval_classifier \
    --golden-dir /data/golden --rules /data/reglas.json --cortes "$CORTES" \
    --model "$model" --embedding-model "$EMBEDDING_MODEL" --runs "$RUNS" \
    --profile server --num-thread 4 \
    --base-url http://ollama:11434 --embedding-url http://ollama:11434 \
    --cache-dir "$CACHE_DIR" --out-dir "$out" ${EVAL_ARGS:-}
  folders+=("$out")
  # Un modelo a la vez: se descarga antes del siguiente (OLLAMA_MAX_LOADED_MODELS=1).
  run "${COMPOSE[@]}" exec -T ollama ollama stop "$model" || true
done

run "${COMPOSE[@]}" run --rm evaluator python -m scripts.eval_compare "${folders[@]}" \
  --out "$OUT_ROOT/COMPARATIVA.md"
echo "Tabla: ${EVALUACIONES_DIR}/resultados/e07a/${STAMP}_${ARCH}/COMPARATIVA.md"

if [[ "${KEEP_UP:-0}" != "1" ]]; then
  # Sin -v: el volumen de modelos se conserva.
  run "${COMPOSE[@]}" down
fi
