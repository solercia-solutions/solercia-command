# Guía de activación del clasificador de correo y la sincronización programada

Esta guía reúne, en el orden en que conviene ejecutarlos, los pasos para pasar el clasificador
de correo de Solercia Command de la evaluación a la operación diaria. Cada etapa se puede
ejecutar cuando se decida; ninguna se activa sola. Aplica a las organizaciones **SDMujer** e
**IDARTES**.

- Rama de trabajo: `feat/clasificador-local` (sin publicar).
- Seguimiento detallado y evidencia: `odd/tasks/clasificador-local-y-sync-programado.md`.
- Línea base, reglas y resultados (contienen correos reales, fuera del repositorio):
  `~/Proyectos/SOLERCIA/evaluaciones/`.

## 1. Qué existe hoy

| Pieza | Estado | Dónde |
|---|---|---|
| Sincronización programada 06:00 y 23:59 (Bogotá): checklist → correo → clasificación | Activa en local desde 2026-10-07 | `backend/app/modules/scheduled_sync/` |
| Clasificador **v1** (propuestas en la «Bandeja de seguimiento») | Activo en local | `RECONCILIATION_CHANNEL=v1` |
| Clasificador **v2** alineado a la metodología de cortes (8 clases, reglas versionadas, candidatas por fusión léxica + embeddings, prompt v2.2) | Evaluado; no activo | `RECONCILIATION_CHANNEL=v2` |
| Proveedor de IA por organización (local o BYOK con llave cifrada) | Activo | Administración › Inteligencia artificial |
| Evaluador en simulación y entorno en contenedores con perfil de servidor | Listo | `backend/scripts/eval_classifier.py`, `eval/docker/` |
| Diagnóstico de solo lectura para servidores | Listo | `scripts/diagnostico-servidor-ia.sh` |

### Resultados de referencia (cortes de prueba 1-oct y 5-oct)

| Modelo | Entorno | Macro-F1 | Determinismo de la clase | 40 hilos |
|---|---|---|---|---|
| `qwen3.5:9b-q4_K_M` | Mac (GPU) | 0,40 | 100 % | ~2 min |
| `qwen3.5:9b-q4_K_M` | Contenedor 4 CPU / 8 GB, arm64 (optimista) | 0,46* | 100 % | ~18 min |
| `qwen3.5:9b-q4_K_M` | Contenedor 4 CPU / 8 GB, amd64 emulado (pesimista) | — | 100 % | ~134 min |
| `qwen3.5:4b` (plan B) | Contenedor 4 CPU / 8 GB, arm64 | 0,33* | 100 % | ~11 min |

\* Muestra de 30 registros. Detalle: `evaluaciones/resultados/e08/COMPARATIVA_REALISTA.md`.

**Modelo recomendado:** `qwen3.5:9b-q4_K_M` con embeddings `qwen3-embedding:0.6b`. Plan B si una
corrida en el servidor pasa de unos 60 minutos: `qwen3.5:4b`.

## 2. Etapa local (en tu equipo)

### 2.1 Requisitos

- Docker Desktop con al menos 12–16 GB de memoria (Settings › Resources).
- Ollama en el equipo con los modelos:
  `ollama pull qwen3.5:9b-q4_K_M && ollama pull qwen3-embedding:0.6b`.
- Contenedores `postgres` y `redis` del compose principal en ejecución:
  `docker compose up -d postgres redis`.
- Solercia Connect en ejecución para la ingesta de correo de SDMujer (ver la nota de relanzamiento
  en la memoria del proyecto: entorno limpio y `SOLERCIA_CONNECT_ENV_FILE`).

### 2.2 Variables del backend en el host

El backend corre en el host (no en el contenedor) con un archivo de entorno propio. Variables
relevantes:

| Variable | Valor sugerido | Para qué |
|---|---|---|
| `STARTUP_PROFILE` | `local_restricted` | Sin seed ni trabajos de alertas o correo saliente |
| `EMAIL_ENABLED` | `false` | No envía correos |
| `SCHEDULED_SYNC_ENABLED` | `true` | Activa las corridas 06:00 y 23:59 |
| `SCHEDULED_SYNC_TIMES` / `SCHEDULED_SYNC_TZ` | `06:00,23:59` / `America/Bogota` | Horario |
| `CHECKLIST_SYNC_PATH` | Ruta del `CHECKLIST_TAREAS.csv` | Solo SDMujer, durante la transición |
| `CHECKLIST_SYNC_TAREAS_ROOT` / `CHECKLIST_SYNC_ORG_SLUG` / `CHECKLIST_SYNC_ACTOR_EMAIL` | Carpeta TAREAS / `sdmujer` / correo del administrador | Idem |
| `CHECKLIST_SYNC_UPDATE_EXISTING` | `true` mientras el CSV mande | El CSV prevalece hasta la migración definitiva |
| `SOLERCIA_CONNECT_BASE_URL` | `http://127.0.0.1:8765` | Connect en el mismo equipo |
| `RECONCILIATION_CHANNEL` | `v1` hoy; `v2` al activar la etapa 2.4 | Canal del clasificador |
| `RECONCILIATION_RULES_PATH` | `~/Proyectos/SOLERCIA/evaluaciones/reglas.json` (o carpeta con `<slug>.json`) | Reglas versionadas por organización |
| `RECONCILIATION_V2_TOP_K` | `5` | Candidatas por hilo (8 empeora «tarea nueva») |
| `AI_DEFAULT_NUM_CTX` | `8192` | Contexto del modelo local |

### 2.3 Comprobar el estado

1. Administración › Sincronización: últimas corridas por organización y conteos por paso.
2. Bandeja de seguimiento: propuestas pendientes.
3. Administración › Inteligencia artificial › «Probar conexión».

### 2.4 Activar el clasificador v2 en local (cuando se decida)

Antes de activarlo deben estar resueltos los ajustes de la sección 4.

1. Definir `RECONCILIATION_CHANNEL=v2` y `RECONCILIATION_RULES_PATH`.
2. Reiniciar solo el backend del host.
3. Disparar una corrida manual desde Administración › Sincronización (o `POST /api/v1/sync/run`).
4. Revisar 20 propuestas en la Bandeja y comparar con el criterio de la metodología.
5. Volver a v1 es cambiar la variable y reiniciar el backend; las propuestas existentes se
   conservan. Los hilos sin `conversation_id` pueden duplicar una propuesta una sola vez al
   cambiar de canal.

### 2.5 Repetir el benchmark cuando cambie algo

```bash
# En el equipo, con el Ollama nativo
cd backend
.venv/bin/python -m scripts.eval_classifier --golden-dir ~/Proyectos/SOLERCIA/evaluaciones/golden \
  --cortes 2026-10-01,2026-10-05 --model qwen3.5:9b-q4_K_M --runs 3 --profile mac

# Con el perfil de servidor en contenedores (ver eval/docker/README.md)
bash eval/docker/run_matrix.sh
```

## 3. Etapa de producción (servidor por organización)

### 3.1 Antes de instalar

1. Ejecutar `scripts/diagnostico-servidor-ia.sh` en el servidor y revisar la salida (CPU, AVX2,
   RAM libre, Docker, salida a internet).
2. Correr la matriz del evaluador en el propio servidor con `eval/docker/compose.eval.yml`
   (perfil `server`, 3 corridas) para confirmar tiempos y determinismo reales.
3. Respaldo completo de la base antes de cualquier migración.

### 3.2 Particularidades por organización

| | SDMujer | IDARTES |
|---|---|---|
| Origen de tareas | Checklist CSV (transición) | Importación de Jira (`scripts/import_jira`) |
| Origen de correo | Outlook vía Solercia Connect (sesión de navegador en el equipo del usuario) | Gmail (conector planeado) |
| Restricción conocida | En un servidor, Connect requiere permisos oficiales de Graph o un runtime alcanzable; con la sesión de navegador solo funciona desde el equipo del usuario | El conector de correo de IDARTES aún no está operativo; hoy la ingesta de esa organización termina en error |
| Reglas | `evaluaciones/reglas.json` (v2) | Pendiente construir su línea base con cortes propios |

### 3.3 Instalación (resumen)

1. Docker Engine y Compose en el servidor; imágenes fijadas por digest.
2. Postgres y Redis con `restart: unless-stopped` y volumen con respaldo diario.
3. Backend con `STARTUP_PROFILE=default`, `EMAIL_ENABLED` según se decida, y las variables de la
   sección 2.2.
4. Ollama en contenedor con `cpus` y `mem_limit` acordes al servidor, `OLLAMA_NUM_PARALLEL=1`,
   `OLLAMA_MAX_LOADED_MODELS=1` y `LLAMA_ARG_CACHE_RAM=0` (sin esta última, el modelo de 9B se
   queda sin memoria con 8 GB).
5. `alembic upgrade head` tras el respaldo.
6. Proveedor de IA de la organización: preset `ollama_local` apuntando al Ollama del servidor, o
   BYOK si se decide (el contenido del correo sale hacia el proveedor externo).

## 4. Ajustes pendientes antes de activar v2

- [ ] Conectar el adaptador nativo de Ollama al canal de producción (por `/v1`, Ollama ignora
      `num_ctx` y carga el modelo con 64K de contexto).
- [ ] Calcular los embeddings del lote antes de clasificar (con un solo modelo cargado, alternar
      embeddings y chat recarga el modelo en cada hilo).
- [ ] Enviar el número de hilos también en la llamada de embeddings.
- [ ] Pasar Detalle y Observaciones de la tarea al servicio (hoy solo el evaluador los usa).
- [ ] `restart: unless-stopped` en `postgres` y `redis` del compose principal.
- [ ] Registrar el código de error por cuenta en el paso de ingesta.
- [ ] Decisiones de criterio pendientes: correo a todos@ que además va dirigido al dueño del
      buzón; «Confirma» en tareas abiertas frente a «Avanza».
- [ ] Revisar los 70 registros de `evaluaciones/golden/manual_queue.jsonl`.
