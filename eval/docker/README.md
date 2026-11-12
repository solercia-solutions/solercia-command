# Entorno de evaluación «igual a producción» (E07a)

Mide el clasificador de correo a tareas (canal v2) en las mismas condiciones del servidor de
destino: Ollama limitado a 4 CPU y 8 GB de RAM, sin GPU y con un solo modelo cargado. Usa el mismo
evaluador del repositorio (`backend/scripts/eval_classifier.py`) y el conjunto dorado que vive
fuera del repo (`~/Proyectos/SOLERCIA/evaluaciones/`).

## Supuesto de servidor

Hasta tener el diagnóstico real (`scripts/diagnostico-servidor-ia.sh`), el destino se modela así:

| Aspecto | Supuesto |
|---|---|
| Virtualización | VMware u Oracle |
| CPU | Intel Xeon, 4 vCPU, AVX2, sin AVX-512 |
| RAM | 16 GB, compartida con PANDORA |
| GPU | No |
| Presupuesto del modelo | 4 CPU y 8 GB de RAM |

Si el diagnóstico real difiere, ajusta `cpus` y `mem_limit` en `compose.eval.yml` y repite la
matriz.

## Qué hay aquí

| Archivo | Para qué |
|---|---|
| `compose.eval.yml` | Servicios `ollama` (imagen fijada por digest, 4 CPU, 8 GB, sin swap extra, puerto 11534 solo en loopback, volumen propio) y `evaluator` |
| `Dockerfile.evaluator` | Python 3.12 slim con solo `app/` y `scripts/` del backend y las dependencias del evaluador |
| `requirements.evaluator.txt` | Dependencias mínimas (mismos pines que `backend/requirements.txt`) |
| `run_matrix.sh` | Recorre los modelos con los cortes de prueba, 3 corridas, y arma la tabla comparativa |

Aislamiento:

- El Ollama de evaluación usa el volumen `solercia-eval-ollama-models`; no toca el Ollama del host
  (puerto 11434) ni el compose principal.
- El evaluador monta `evaluaciones/` en solo lectura y solo `resultados/` con escritura.
- El evaluador solo está en la red interna `eval-internal` (sin salida a internet): el conjunto
  dorado contiene correos reales.
- Los embeddings se cachean por plataforma (`resultados/_cache/embeddings-arm64|amd64`), sin
  mezclarse con los calculados en la Mac.

## La horquilla arm64 / amd64

En una Mac con Apple Silicon no existe un Xeon real, así que se miden dos límites:

| Plataforma | Cómo corre | Por qué es un límite |
|---|---|---|
| `linux/arm64` | Nativo en la Mac, con 4 núcleos y 8 GB | **Optimista**: los núcleos de la Mac son más rápidos por hilo y la memoria tiene más ancho de banda que una VM compartida |
| `linux/amd64` | Emulado (Rosetta o QEMU) | **Pesimista**: la traducción de instrucciones agrega costo y puede no exponer AVX2, así que Ollama elige rutinas más lentas |

El servidor real queda entre ambos: corre x86 nativo con AVX2 (sin costo de traducción), pero con
4 vCPU de un Xeon compartido con PANDORA y menos ancho de banda de memoria que la Mac. La horquilla
es orientativa: confirma qué modelos caben en 8 GB y el orden de magnitud de la latencia; la cifra
definitiva sale de correr el mismo compose en el servidor.

La exactitud y el macro-F1 no deberían cambiar entre plataformas (mismo modelo, semilla y
parámetros); sí pueden cambiar el determinismo en CPU y la latencia.

## Requisitos

- Docker Desktop con **12 a 16 GB** de memoria asignada a la VM (8 GB para Ollama, el evaluador y
  los contenedores que ya corren) y swap disponible. Con 4 GB y la swap llena **no** se debe
  correr.
- Para `linux/amd64` en la Mac: activa «Use Rosetta for x86_64/amd64 emulation on Apple Silicon»
  en Docker Desktop (sin Rosetta, QEMU es mucho más lento).
- Unos 25 GB de disco para los modelos del volumen.
- La carpeta `evaluaciones/` con `golden/`, `reglas.json` y `resultados/`.

## Comandos

Todos desde la raíz del repo.

```bash
export EVALUACIONES_DIR=~/Proyectos/SOLERCIA/evaluaciones
COMPOSE="docker compose -f eval/docker/compose.eval.yml"

# 0. Validar la configuración (no descarga ni arranca nada).
$COMPOSE config -q && bash -n eval/docker/run_matrix.sh
EVALUACIONES_DIR=$EVALUACIONES_DIR eval/docker/run_matrix.sh --dry-run
```

### 1. Precargar los modelos en el volumen del contenedor

Los GGUF no dependen de la plataforma: se descargan una vez y sirven para arm64 y amd64.

```bash
PLATFORM=linux/arm64 $COMPOSE up -d --wait ollama
for m in qwen3-embedding:0.6b qwen3.5:9b-q4_K_M ornith:9b qwen3.5:4b gemma4:e2b; do
  $COMPOSE exec ollama ollama pull "$m"
done
$COMPOSE exec ollama ollama list
```

#### 1b. Alternativa sin descargar: modelos del host en solo lectura (E08)

`compose.hostmodels.yml` monta `~/.ollama/models` del host en `/models` con `:ro`
(`OLLAMA_MODELS=/models`, `OLLAMA_NOPRUNE=1`). Ollama arranca y carga los GGUF sin escribir en el
almacén, así que no hace falta el paso 1. `run_matrix.sh` lo usa con `HOST_MODELS=1`:

```bash
HOST_MODELS=1 OUT_SUBDIR=e08 PLATFORM=linux/arm64 eval/docker/run_matrix.sh
# amd64 con sonda: si el p50 de 10 registros supera 60 s, corre 15 por corte (30 registros).
HOST_MODELS=1 OUT_SUBDIR=e08 PROBE_P50_S=60 PLATFORM=linux/amd64 eval/docker/run_matrix.sh
```

Cada modelo deja `ram_pico.txt` (pico de `docker stats` del contenedor de Ollama, muestreo cada
2 s) y, si se cortó, `LIMITE.txt`. El contenedor usa `cpuset: "0-3"` además de `cpus: 4`: sin
cpuset, `nproc` veía 8 CPU con cuota de 4; así ve 4, como la VM supuesta.

### 2. Matriz en CPU, límite optimista (arm64 nativo)

```bash
PLATFORM=linux/arm64 eval/docker/run_matrix.sh
```

### 3. Matriz en CPU, límite pesimista (amd64 emulado)

```bash
PLATFORM=linux/amd64 eval/docker/run_matrix.sh
# Solo algunos modelos:
PLATFORM=linux/amd64 eval/docker/run_matrix.sh qwen3.5:4b gemma4:e2b
```

Al cambiar de plataforma, `run_matrix.sh` reconstruye el evaluador y Compose recrea el contenedor
de Ollama con la plataforma nueva; el volumen de modelos se conserva.

Variables opcionales: `RUNS` (3), `CORTES` (prueba: `2026-10-01,2026-10-05`), `EVAL_ARGS`
(argumentos extra para el evaluador, p. ej. `--limit 20`), `KEEP_UP=1` (no apaga el entorno al
final), `EVAL_OLLAMA_PORT` (11534).

Resultados: `evaluaciones/resultados/e07a/<fecha>_<arch>/<modelo>/` (`metrics.json`,
`predictions.jsonl`, `report.md`) y `COMPARATIVA.md` con la tabla de todos los modelos.

### 4. En el servidor real x86

Requiere autorización para llevar el conjunto dorado (correos reales) al servidor; no sale de la
entidad. Primero el diagnóstico de solo lectura y luego el mismo compose, ahora nativo:

```bash
bash scripts/diagnostico-servidor-ia.sh > diagnostico.txt
export EVALUACIONES_DIR=/ruta/a/evaluaciones EVAL_UID=$(id -u) EVAL_GID=$(id -g)
PLATFORM=linux/amd64 docker compose -f eval/docker/compose.eval.yml up -d --wait ollama
# precarga como en el paso 1, luego:
PLATFORM=linux/amd64 eval/docker/run_matrix.sh
```

Los límites de 4 CPU y 8 GB evitan que la evaluación le quite más recursos a PANDORA que los del
presupuesto. `EVAL_UID`/`EVAL_GID` dejan los resultados con tu usuario en Linux.

## Imagen fijada

`ollama/ollama:0.35.1@sha256:292ee7945dfc3d5840a181f3ab86fedb1e66703e02c8af98b50f4da56b7e278c`
(índice multiplataforma; misma versión que el Ollama del host en E05). Para actualizarla:

```bash
docker buildx imagetools inspect ollama/ollama:<versión>
```

y reemplaza la etiqueta y el digest del índice (`Digest:` de la primera línea) en
`compose.eval.yml`.
