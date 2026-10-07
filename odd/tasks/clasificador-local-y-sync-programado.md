# Clasificador local intercambiable y sincronización programada — ODD

## Objetivo

Que Command haga solo, dos veces al día, lo que hoy hace el agente de la carpeta TAREAS: traer las
tareas del checklist, leer el correo de entrada y salida, agrupar por hilo, decidir con un modelo
local si cada hilo habla de una tarea existente o de una nueva y si quedó respondido o pendiente.
El proveedor de IA se cambia como una llanta: local por defecto, externo con la llave del cliente
(BYOK).

## Problema y motivo

- La clasificación actual es por reglas fijas, sin IA y sin cruce con tareas existentes.
- El puerto LLM (cambio 48) existe con adaptador OpenAI-compatible, pero la configuración es global
  por proceso, la llave va en claro y ningún flujo de dominio lo usa.
- El mapper de Connect descarta `conversation_id`, `internet_message_id`, `cc`, la carpeta
  (entrada/enviados) y la fecha real: sin eso no se puede decir «respondida».
- No hay trabajo programado en el perfil local (`local_restricted`) y la sincronización del
  checklist solo existe como CLI.

## Alcance autorizado

Usuario, 2026-10-07: «Inicia con una clasificación local … modelos chicos … OpenAI API compatible
y deja la posibilidad de conectarse a otro externo con la técnica BYOK … que corra programado todos
los días a las 6am y a las 11:59pm y sincroniza de nuevo las tareas a la fecha actual».

## Decisiones

- **Modelos locales (Ollama, OpenAI-compatible):** principal `qwen3.5:9b` (instalado, ~7 GB, sin
  razonamiento: `reasoning_effort: "none"`); alterno liviano `qwen3.5:4b` (~4 GB) o `gemma4:e4b`;
  embeddings `qwen3-embedding:0.6b` (~640 MB). Fuentes: ollama.com/library/qwen3.5,
  ollama.com/library/qwen3-embedding, docs.ollama.com/api/openai-compatibility.
- **Canal en dos pasos:** (1) determinista: hilo por `conversation_id` (o asunto normalizado),
  «respondido» si hay un mensaje en enviados posterior al último entrante; (2) embeddings para el
  top-k de tareas candidatas; (3) LLM con JSON por esquema decide tarea existente/nueva/irrelevante
  y extrae acción, solicitante y fecha límite.
- **Propone, no aplica:** el resultado queda como propuesta por hilo; el cambio de estado de una
  tarea lo confirma una persona. Vincular hilo↔tarea con confianza alta sí se registra.
- **BYOK:** configuración por organización con llave cifrada (Fernet, `INTEGRATIONS_FERNET_KEY`),
  presets (Ollama local, llama.cpp, OpenAI, OpenRouter, Groq, DeepSeek, Mistral) y URL propia solo
  HTTPS para admin. El proveedor externo saca contenido de correo de la máquina: se muestra aviso.
- **Programación:** `CronTrigger` 06:00 y 23:59 `America/Bogota`, flag propio
  `SCHEDULED_SYNC_ENABLED` independiente del perfil y de `EMAIL_ENABLED`; `max_instances=1`,
  `coalesce=True`. Orden: checklist → ingesta (desde la última corrida exitosa) → clasificación.
- **Fuente de verdad durante la transición:** el CSV manda sobre los campos que importa
  (`--update-existing`) hasta la migración definitiva; se apaga con un flag.

## Restricciones

- Rama `feat/clasificador-local` (desde `feat/ui-shell-pandora`). Commits por unidad, sin
  atribución, sin push.
- Ninguna operación destructiva sobre datos. Migraciones solo en base desechable; a la base real
  (127.0.0.1:5434) únicamente con confirmación del comando exacto.
- El backend del compose no se enciende (correo saliente). El host corre con
  `STARTUP_PROFILE=local_restricted`, `EMAIL_ENABLED=false`.
- Persistencia: `agents/rules/solercia-persistence.md`.
- Textos de interfaz en español colombiano con tuteo; lista de UX antes de cerrar pantallas.

## Modo de pruebas

- Backend: TDD estricto (`openspec/config.yaml`). Runner `cd backend && pytest tests/<archivo> -v`
  contra PostgreSQL desechable (:55432). LLM y embeddings con fakes en pruebas.
- Frontend: `npm run build`, `npm run lint` y navegador.

## Entrega

Estrategia `ask-on-risk`. Pronóstico > 2.000 líneas; cada tarea es una rebanada.

## Tareas

- [x] C00 Resincronizar el checklist a la fecha (2026-10-07): 8 nuevas, 19 actualizadas.
- [x] C01 Servicio reutilizable de sincronización del checklist (extraer del CLI) + configuración.
- [x] C02 Trabajos programados 06:00 y 23:59 Bogotá con registro de corridas.
- [ ] C03 Ingesta con señales de hilo: `conversation_id`, `internet_message_id`, dirección, `cc`,
      fecha real; refresco de ítems existentes.
- [ ] C04 Proveedor de IA por organización (BYOK) con llave cifrada, presets y prueba de conexión.
- [ ] C05 Canal de clasificación: hilos, respondido/pendiente, embeddings, LLM con esquema,
      propuestas persistidas.
- [ ] C06 UI: «Inteligencia artificial» (proveedor) y bandeja de propuestas por tarea.
- [ ] C07 Verificación con datos reales en simulación y medición de precisión.

## Progreso y evidencia

- 2026-10-07 C00: simulación 213 planificadas (8 nuevas, 19 con cambios, 186 sin cambios);
  aplicación `{"created": 8, "updated": 19, "unchanged": 186}`; verificación `{"unchanged": 213}`.

- 2026-10-07 C01 (`edf00bf`): `backend/app/modules/task_import/checklist_sync_service.py`
  (`load_checklist_plan`, `run_checklist_sync`, `ChecklistSyncConfig`, errores tipados); el CLI
  `scripts/import_sdm_tasks.py` conserva flags, mensajes y códigos. `CHECKLIST_SYNC_*` en
  `app/config.py` y `env.example`. RED: `ModuleNotFoundError` del servicio; caracterización del
  CLI verde antes y después. GREEN: `test_task_import_checklist_sync_service.py` y
  `test_import_sdm_tasks_cli.py` 22/22 contra PostgreSQL desechable (:55432).
- 2026-10-07 C02 (`a3cf9a4`): módulo `backend/app/modules/scheduled_sync/` (scheduler propio con
  `CronTrigger` por hora y zona, `max_instances=1`, `coalesce=True`, `misfire_grace_time=3600`;
  pasos aislados checklist → ingesta desde la última corrida con ingesta `ok` → clasificación
  no-op para C05; `POST /sync/run` y `GET /sync/runs` solo admin y por organización; 409
  `SYNC_ALREADY_RUNNING`). Migración `0029_add_scheduled_sync_runs` (solo inserción, una fila
  por corrida y organización) probada en la desechable: upgrade, downgrade, upgrade y
  `alembic check` sin diferencias. RED: `ModuleNotFoundError` y 7 fallas del lifespan; GREEN:
  93 pruebas del cambio y vecinas.
- Pendiente para activar en la base real: aplicar `alembic upgrade head` (0029) en
  127.0.0.1:5434 con confirmación del comando exacto; definir `CHECKLIST_SYNC_PATH`,
  `CHECKLIST_SYNC_ORG_SLUG`, `CHECKLIST_SYNC_ACTOR_EMAIL` y `SCHEDULED_SYNC_ENABLED=true` en el
  entorno del uvicorn del host y reiniciarlo.

## Siguiente paso

C03 (señales de hilo en la ingesta).
