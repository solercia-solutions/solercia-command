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
- [x] C05 Canal de clasificación: hilos, respondido/pendiente, embeddings, LLM con esquema,
      propuestas persistidas.
- [x] C06 UI: «Inteligencia artificial» (proveedor) y bandeja de propuestas por tarea.
- [ ] C07 Verificación con datos reales y medición de precisión. Primera corrida real hecha;
      falta calibrar la confianza y subir el límite de correos por corrida (ver evidencia).

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
- 2026-10-07 C05 (`f88fbe9` canal + persistencia + paso programado; `e6e9dc7` endpoints): módulo
  `backend/app/modules/reconciliation/`. `threads.py` (puro): hilo por `conversation_id`;
  respaldo por asunto normalizado (sin RE/RV/FW/Fwd/TR, sin tildes) unido por contrapartes
  compartidas (sin el buzón que ingirió ni los remitentes salientes), clave `subj:<hash>` del
  primer mensaje para que no cambie al crecer el hilo; estado `respondido` /
  `pendiente_respuesta` / `solo_saliente` (dirección desconocida cuenta como entrante); corte de
  citas con los delimitadores del corte manual (`De:`, `From:`, `El … escribió:`…) y claves
  `PREFIJO-N` normalizadas (`t-07` → `T-7`). `candidates.py`: tareas activas (`completed_at`
  nulo) con clave externa o `CODIGO-N`; las mencionadas van primero (`via=clave`) y el resto del
  top-5 por coseno en Python. `prompt.py`: esquema Pydantic `ThreadClassification`,
  temperatura 0, `max_tokens` 600, prompt en español; `task_ref` fuera de las candidatas se
  degrada a `tarea_nueva` con confianza ≤ 0,3; fecha límite no ISO se descarta. `service.py`:
  `ReconciliationService.classify_window(org, since)` con un commit por hilo; hilo sin mensajes
  nuevos y ya clasificado no llama al LLM; mensajes nuevos actualizan la propuesta abierta; uno
  decidido solo se repropone si crece; una propuesta sin clasificar se reintenta. Si el proveedor
  cae, deja de llamarlo en esa corrida, guarda estado y candidatas por clave (con `task_id` de la
  clave) y devuelve `llm_error`. Embeddings cacheados en `task_embeddings` por
  `preset/modelo` y hash del texto. Paso 3 de C02: `reconciliation/step.py` (ventana de 7 días;
  `StepFailed` con conteos si `llm_error`), conectado en el scheduler y en `POST /sync/run`.
  `get_llm_for_org` devuelve puerto + resolución (nombre del modelo de embeddings); el preset
  local por defecto pide `num_ctx` = `AI_DEFAULT_NUM_CTX` (8192). Configuración
  `RECONCILIATION_*` (activado, ventana, máx. 40 hilos, 6000 caracteres, top-k 5, 600 tokens).
  Endpoints `GET /intake/proposals` (filtros `status`, `task_id`, `thread_state`; paginado),
  `POST …/{id}/accept` (comentario en la tarea con resumen, estado del hilo y enlace
  `/intake/proposals/{id}`; el estado de la tarea solo cambia con `status` explícito, validado
  antes por `TaskService.update_task`), `…/dismiss`, `…/create-task` (proyecto por defecto de
  intake, título = acción, fecha límite = `due_date`); admin/manager; 404 entre organizaciones,
  409 si ya fue decidida. Migración `0032_add_reconciliation_proposals` (dos tablas nuevas;
  índice único parcial de una propuesta abierta por hilo) probada en la desechable: upgrade,
  downgrade, upgrade y `alembic check` sin diferencias. RED: `ModuleNotFoundError` en 5 archivos,
  revisión 0032 ausente, `num_ctx` por defecto y rutas 404. GREEN: 57 pruebas del cambio;
  288 del cambio y vecinas (sync programado, IA, intake, comentarios, migraciones base,
  aislamiento) contra PostgreSQL desechable (:55432).
- Humo C05 con datos SINTÉTICOS contra Ollama local (preset por defecto, `num_ctx` 8192): 3
  hilos y 3 tareas en 13,5 s (≈4,5 s por hilo con embeddings); VPN → `T-7` respondido y
  atendido; cotización → `T-12` con fecha 2026-10-20; boletín → irrelevante; segunda corrida
  sin llamadas (0,00 s).
- Hallazgo previo (no de C05): `test_cross_tenant_isolation.py::test_all_modules_are_classified`
  ya fallaba por `ai_settings`, `plans`, `scheduled_sync` y `task_import` sin clasificar; C05
  clasifica `reconciliation` y deja esos cuatro igual.
- Límites conocidos de C05: sin filtro previo de ruido (boletines pasan por el LLM y salen
  `irrelevante`); el estado `pendiente_respuesta` también aplica a masivos; los ítems sin
  `direction` (anteriores a C03) cuentan como entrantes; la ruta `/intake/proposals/{id}` del
  comentario la materializa la UI de C06.
- 2026-10-07 C06 (`d10fea2` detalle en el API; `4466e96` IA; `6e2e675` bandeja; `57ce400`
  sincronización + menús): tres pantallas lazy con el patrón PANDORA (`h1.sol-display`,
  `sol-card`, `page-layout.scss`, cinco estados). `/settings/ai`: proveedor activo, presets en
  tarjetas `role=radio` (local · externos · personalizado) que precargan URL y modelos, URL
  bloqueada en externos, llave con últimos 4 (vacía conserva, «Quitar llave» envía `null`),
  avanzadas plegadas, aviso «El contenido de tus correos saldrá de tu equipo hacia …», «Probar
  conexión» (latencia, dimensiones o etapa + código) y «Guardar» solo con cambios (o para fijar
  un proveedor por defecto); manager solo lee. `/intake/proposals`: contadores por estado del
  hilo que también filtran, filtros (propuesta, hilo, relación, tarea) en la URL y plegables
  en móvil, grupos Pendiente de respuesta · Respondido · Solo saliente, tarjeta con solicitante,
  fecha, resumen, confianza alta/media/baja (≥ 0,75 / ≥ 0,5) y tarea con enlace `/task/:key`;
  Aceptar en `sol-modal` con los estados reales del proyecto (por defecto se mantiene),
  Descartar y Crear tarea con `sol-confirm-dialog`; `/intake/proposals/:id` con detalle,
  candidatas y acciones. `/sync`: próximas ejecuciones calculadas en Bogotá, última programada,
  historial paginado con conteos por paso y errores, «Ejecutar ahora» (admin) con 409 legible.
- Ajuste de backend imprescindible: `GET /intake/proposals/{id}` (admin/manager, 404 entre
  organizaciones). RED 404 de la ruta; GREEN 10/10 de `test_reconciliation_router.py` contra
  PostgreSQL desechable (:55432, contenedor nuevo `postgres:16-alpine`). Menús: el seed es
  idempotente (inserta faltantes al arrancar) → `seed_catalog.py` suma «Bandeja de seguimiento»
  (`/intake/proposals`, raíz, orden 8, ADMIN + MANAGER), «Sincronización» (`/sync`) y
  «Inteligencia artificial» (`/settings/ai`) bajo Administración (5 y 6, solo ADMIN).
  `test_menu_seed_classifier.py` RED sin el seed y GREEN con él + seed/RBAC vecinas (12).
  En la base real las filas aparecen al reiniciar el uvicorn (o con
  `scripts/sync_menu_catalog`); mientras tanto las rutas se abren por URL.
- Verificación C06: `npm run build` y `npm run lint` exit 0; bundle inicial 1,08 MB (igual).
  Navegador 1440×900 y 390×844, claro y oscuro, con TODAS las respuestas de `/ai/*`, `/sync/*`,
  `/intake/proposals*`, `/tasks/{id}` y el proyecto simuladas por `page.route` (datos
  sintéticos) y cualquier otra petición no GET abortada (0 abortadas; solo pasó el login).
  IA: OpenAI → aviso + URL fija; guardar sin llave → error en el campo; prueba → «Falló el
  chat … llm_auth_error»; Ollama + temperatura 0,2 → prueba OK (4213 ms, 1024 dim) y guardado
  («Guardado para tu organización», Guardar deshabilitado); manager → solo lectura. Bandeja:
  5 por decidir (3/1/1); aceptar con «Hecho» envía `{"task_id":"t1","status":"Done"}`; crear
  tarea `{}` con fecha límite en el mensaje; descartar; contador «Respondido» filtra
  (`?hilo=respondido`); relación sin coincidencias + «Limpiar filtros»; «Todas» 6; vacío
  legítimo; 500 → «Reintentar»; detalle, 409 → recarga como «Aceptada», 404 legible. Sync:
  «Hoy 23:59 · Mañana 06:00», pasos y conteos, 409 → aviso, ejecución → nueva corrida, vacío,
  403. Sin desplazamiento horizontal. Capturas `.playwright-mcp/c06-*.png`.
- Veredicto UX C06: vienen a decidir qué hilos se vinculan (bandeja), a elegir el modelo (IA) y
  a saber si la corrida funcionó (sync). Bien: presets en vez de URL a mano, decisión por
  defecto segura (mantener estado), estados distinguibles, errores del backend con su código.
  Fricciones: (1) el API de propuestas no trae la clave del proyecto ni el estado de la tarea:
  la bandeja hace un `GET /tasks/{id}` por tarea única (agregarlos al API lo evitaría); (2) el
  filtro de relación es de la página cargada (el API no lo acepta); (3) el horario de `/sync` es
  el configurado por defecto (el API no expone `SCHEDULED_SYNC_TIMES` ni si está activo); (4)
  «Ejecutar ahora» espera la corrida completa en la misma petición (sin progreso por paso); (5)
  `sol-card` deja `transform` y recortaba los diálogos: se anula en la bandeja; `sol-select`
  trae buscador por defecto (se apagó en selects cortos).
- Incidente menor: un `pytest` sin argumentos se lanzó por error contra la base desechable
  (:55432) y se detuvo; no tocó 127.0.0.1:5434.
- Pendiente para activar en la base real: aplicar `alembic upgrade head` (0029 a 0032) en
  127.0.0.1:5434 con confirmación del comando exacto; definir `CHECKLIST_SYNC_PATH`,
  `CHECKLIST_SYNC_ORG_SLUG`, `CHECKLIST_SYNC_ACTOR_EMAIL` y `SCHEDULED_SYNC_ENABLED=true` en el
  entorno del uvicorn del host y reiniciarlo.

- 2026-10-07 Activación (confirmada por el usuario): respaldo
  `~/Proyectos/SOLERCIA/respaldos/solercia-pre-0028-0032-2026-10-07.dump` (1.969 tareas, igual a la
  base); `alembic upgrade head` 0027 → 0032; `scripts.sync_menu_catalog --apply` (3 menús × 3
  organizaciones); uvicorn del host con `SCHEDULED_SYNC_ENABLED=true` y `CHECKLIST_SYNC_*`
  (log: «Sincronización programada activa: 06:00,23:59 (America/Bogota)»).
- 2026-10-07 Defectos encontrados en la primera corrida y corregidos con TDD:
  `f767283` la URL del runtime guardada en la credencial (`host.docker.internal`) no resuelve con
  Command en el host → las direcciones permitidas son alias y manda la del despliegue;
  `9b18d07` Connect exige `start` y `end` → la primera ingesta envía 7 días
  (`SOLERCIA_CONNECT_DEFAULT_LOOKBACK_DAYS`). 109 pruebas en verde (PG desechable).
- 2026-10-07 C07 primera corrida real (SDMujer, `POST /sync/run`, 242 s): checklist 213 sin
  cambios; ingesta 50 correos (41 entrantes, 9 enviados); clasificación 46 hilos, 40 procesados
  (tope `RECONCILIATION_MAX_THREADS_PER_RUN`). Resultado: 21 a tarea existente, 4 a tarea nueva,
  15 irrelevantes; estados 31 pendiente de respuesta, 2 respondidos, 7 solo salientes. Aciertos
  claros en los hilos de la semana (T-204, T-206..T-210, T-207 respondido). Débil: tres
  notificaciones automáticas con el mismo asunto quedaron en tres tareas distintas con 0,95; la
  confianza promedio (~0,97) no está calibrada.
- Pendientes C07: (1) calibrar confianza (penalizar remitentes automáticos/no-reply y asuntos
  genéricos; exigir evidencia textual); (2) el límite de 50 correos por cuenta se reparte entre
  entrada y enviados → subirlo; (3) registrar el código de error por cuenta en el paso de
  ingesta (hoy solo «1 de 1 cuentas terminaron con error»); (4) la Mac debe estar despierta a las
  06:00 y 23:59.

## Siguiente paso

Cerrar los pendientes de C07 y medir precisión con una muestra revisada por el usuario.
