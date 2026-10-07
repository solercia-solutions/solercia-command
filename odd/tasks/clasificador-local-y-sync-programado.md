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
- [x] C03 Ingesta con señales de hilo: `conversation_id`, `internet_message_id`, dirección, `cc`,
      fecha real; refresco de ítems existentes.
- [x] C04 Proveedor de IA por organización (BYOK) con llave cifrada, presets y prueba de conexión.
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
- 2026-10-07 C03 (`86c1106`): `MailMessage` gana `conversation_id`, `internet_message_id`,
  `in_reply_to`, `references`, `cc`, `direction`, `sent_at`, `delivered_at` y `has_attachments`
  (opcionales; Google, Microsoft 365 y fake no cambian). El mapper de Connect los lee; la
  dirección sale del `folder` del registro y, si falta, de la carpeta leída (`read_mail` ahora
  devuelve `(carpeta, registros)`). Connect no emite `in_reply_to`/`references`: quedan vacíos.
  Migración `0030_add_intake_thread_signals`: tres columnas nulas con índices
  `(organization_id, conversation_id)`, `(organization_id, internet_message_id)` y `direction`;
  paso de datos no destructivo que solo copia desde `raw_payload` de correos (dirección solo si es
  `inbound`/`outbound`). `occurred_at` ya es el instante de envío; la recepción queda en
  `raw_payload.delivered_at` (sin columna nueva). `upsert_item` refresca señales y agrega claves a
  `raw_payload` sin borrar valores conocidos ni tocar `status`, `created_task_id`,
  `matched_rule_id` ni `classified_at`. Privacidad: `GET /intake/items` y el detalle omiten
  `raw_payload.body_text` para roles distintos de admin/manager (el `snippet` se conserva).
  RED: `TypeError`/`AttributeError` de los campos nuevos, `listed_from` inexistente y revisión
  0030 ausente. GREEN: 46 pruebas del cambio; 307 del cambio y vecinas (intake, adaptadores,
  conectores, sync programado, migraciones base) contra PostgreSQL desechable (:55432); 0030
  probada en la desechable con upgrade, downgrade, upgrade y `alembic check` sin diferencias.
- Sin señal tras C03: los ítems ingeridos antes no traen estas claves en `raw_payload`, así que la
  migración no les asigna nada; se completan al reingerir su ventana (p. ej. `POST /intake/pull`
  o la corrida programada con `since` anterior a su fecha). Otros conectores (Google, Microsoft
  365) siguen sin poblar las señales.
- 2026-10-07 C04 (`16371f8`): tabla `ai_provider_settings` (una fila por organización, sin
  historial; llave solo como token Fernet + `api_key_last4`). Presets en código
  (`app/ai/presets.py`): `ollama_local` (por defecto), `llamacpp_local`, `openai`, `openrouter`,
  `groq`, `deepseek`, `mistral`, `custom`, cada uno local/externo. Guarda anti-SSRF
  (`app/ai/url_guard.py`): externos con URL fija; locales solo loopback o `host.docker.internal`;
  `custom` exige HTTPS a host público (toda IP resuelta global), HTTP solo a loopback explícito;
  bloquea privadas, link-local/metadatos, CGNAT, IPv4 mapeada y credenciales en la URL.
  `LLM_BASE_URL_ALLOWLIST` admite además las URL de presets. Puerto: `embed()` en `LlmPort`
  (fake determinista, anthropic denegado) y en el adaptador (`/embeddings`), `reasoning_effort`,
  `extra_body` (`options.num_ctx` en Ollama), `LlmRequest.temperature` opcional. La barrera de
  `cf0beff` se conserva: el adaptador solo despacha con `LlmDispatchContext`, que únicamente
  crea `build_llm_port`/`get_llm_port_for_org` con la organización resuelta en servidor; los
  logs de error ya no incluyen el cuerpo de la respuesta. Precedencia: fila de la organización
  (si `enabled=false` se detiene con `llm_provider_disabled`, sin respaldo) > `LLM_*` global si
  `LLM_PROVIDER` ≠ `fake` (`anthropic` va al registro y sigue denegado) > preset `ollama_local`.
  Una llave conservada solo se reutiliza para la misma URL destino; los presets externos exigen
  llave (`AI_API_KEY_REQUIRED`). Endpoints `GET/PUT /ai/settings`, `GET /ai/presets`,
  `POST /ai/settings/test` (admin escribe y prueba; manager solo lee). Migración
  `0031_add_ai_provider_settings` probada en la desechable: upgrade, downgrade, upgrade y
  `alembic check` sin diferencias. RED: `ImportError`/`ModuleNotFoundError` de los 5 módulos y
  revisión 0031 ausente. GREEN: 114 pruebas del cambio; 181 del cambio y vecinas (IA, salud del
  asistente, migraciones base, sync programado, señales de hilo) + 8 de anthropic aparte, contra
  PostgreSQL desechable (:55432). Humo manual contra Ollama local con el preset por defecto:
  chat 4,2 s, embeddings 1024 dimensiones.
- Hallazgo previo (no de C04): `test_ai_registry.py::test_does_not_import_the_anthropic_package…`
  falla si se ejecuta en la misma corrida que `test_ai_adapter_anthropic.py` (la colección importa
  el adaptador); pasa por separado y también falla igual en la rama antes de C04.
- Pendiente para activar en la base real: aplicar `alembic upgrade head` (0029, 0030 y 0031) en
  127.0.0.1:5434 con confirmación del comando exacto; definir `CHECKLIST_SYNC_PATH`,
  `CHECKLIST_SYNC_ORG_SLUG`, `CHECKLIST_SYNC_ACTOR_EMAIL` y `SCHEDULED_SYNC_ENABLED=true` en el
  entorno del uvicorn del host y reiniciarlo.

## Siguiente paso

C05 (canal de clasificación con `get_llm_port_for_org`).
