# Tasks: 41 · Importación Jira modo administrador (sitio completo, por lotes y reanudable)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900–1400 (2 modelos + repo + runner + reaper + 4 endpoints + client + config + migración + ~10 archivos de test backend; 3 archivos frontend) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR único bajo `size:exception` (decisión ya tomada); unidades lógicas listadas abajo para revisión por partes dentro del mismo PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migración `import_jobs`/`import_job_projects` reversible | PR 1 (size:exception) | `pytest -q backend/tests/test_migration_import_jobs.py` | `alembic upgrade head && alembic downgrade -1` | `alembic downgrade` elimina ambas tablas, sin datos huérfanos |
| 2 | Discover masivo (`list_projects/boards/sprints` + endpoint) | PR 1 | `pytest -q backend/tests/jira_import/test_discover.py` | `httpx.MockTransport` contra fixtures Jira | Revertir `client.py`/endpoint discover, sin afectar 40 |
| 3 | Job + runner (creación, secuencial, 409, JQL, RBAC) | PR 1 | `pytest -q backend/tests/jira_import/test_job_runner.py` | seam `importar_proyecto` (40) mockeado + BD test | Revertir `runner.py`/`repository.py`, tablas quedan vacías |
| 4 | Polling + resume + reaper | PR 1 | `pytest -q backend/tests/jira_import/test_resume_reaper.py` | `AsyncClient` + reloj inyectado | Revertir `reaper.py` + registro en `main.py` |
| 5 | No-exposición del token | PR 1 | `pytest -q backend/tests/jira_import/test_token_safety.py` | inspección de logs/respuestas capturados en el test | Sin cambios de esquema; solo saneo de logging |
| 6 | UI descubrimiento + selección + progreso | PR 1 | `ng test --include='**/connections*.spec.ts'` | `ng serve` manual contra backend en :8081 | Revertir 3 archivos frontend + claves i18n |

Requisitos (legend): R1 descubrimiento+conteos · R2 selección múltiple/"todo" · R3 creación de job · R4 un job activo/conector · R5 secuencial+throttling · R6 polling · R7 reanudación sin duplicar · R8 truncamiento honesto · R9 RBAC admin+aislamiento · R10 token nunca expuesto.

## Fase 0: Verificación previa (gate)

- [ ] 0.1 Verificar `alembic heads` real en disco y confirmar que 40 completó apply+verify+archive.
- [ ] 0.2 Confirmar en disco la firma exacta de `importar_proyecto(...)` y `ImportSummary` del 40 (contadores a mapear).

## Fase 1: Migración `import_jobs`/`import_job_projects` [R3][R4]

- [ ] 1.1 RED: test de migración — `add_import_jobs` sube y baja limpio (upgrade/downgrade sin residuos).
- [ ] 1.2 Crear `backend/app/modules/jira_import/models.py`: `ImportJob`+`ImportJobProject`, mixins, índice único parcial `(connector_id) WHERE status IN ('pending','running')`.
- [ ] 1.3 Crear `backend/alembic/versions/00XX_add_import_jobs.py`, `down_revision` anclado al head real de 0.1.
- [ ] 1.4 GREEN: correr 1.1, confirmar aplica y revierte sin datos huérfanos.

## Fase 2: Descubrimiento masivo [R1]

- [ ] 2.1 RED: `list_projects` excluye archivados por defecto (`status=live`), los incluye con filtro explícito.
- [ ] 2.2 RED: `list_boards`/`list_sprints` paginan por offset (`startAt/maxResults/isLast`) acotado por `JIRA_MAX_PAGES`.
- [ ] 2.3 RED: anti-SSRF — los 3 métodos nuevos pasan por el mismo `_get` validado (regresión, sin nueva superficie).
- [ ] 2.4 GREEN: implementar `list_projects/list_boards/list_sprints` en `backend/app/integrations/adapters/jira/client.py`.
- [ ] 2.5 RED: discover marca proyectos ya importados y devuelve conteos best-effort por tipo.
- [ ] 2.6 GREEN: `service.discover_site()` + `POST /connectors/{id}/admin-import/discover` + schemas en `jira_import/{service,router,schemas}.py`.

## Fase 3: Creación de job + runner en segundo plano [R3][R4][R5][R9]

- [ ] 3.1 RED: `403` para `manager`/`member` al crear/consultar/reanudar job.
- [ ] 3.2 RED: `409` job duplicado por conector (índice único parcial activo).
- [ ] 3.3 RED: inyección JQL — `KEY` inválida (fuera de `^[A-Z][A-Z0-9]+$`) rechazada antes del JQL.
- [ ] 3.4 RED: creación de job persiste N `ImportJobProject` en `pending`.
- [ ] 3.5 RED: runner procesa proyectos secuencial, invoca `importar_proyecto` por KEY, commit por proyecto, respeta backoff `429`.
- [ ] 3.6 RED: aislamiento — job de la organización A no accesible desde la organización B.
- [ ] 3.7 GREEN: crear `backend/app/modules/jira_import/repository.py` (CRUD job, upsert por proyecto, guard activo-por-conector).
- [ ] 3.8 GREEN: crear `backend/app/modules/jira_import/runner.py` (`run_import_job`, sesión propia, heartbeat ticker, bucle secuencial).
- [ ] 3.9 GREEN: `POST /connectors/{id}/admin-import/jobs`, encola `asyncio.create_task`, responde `202`.
- [ ] 3.10 GREEN: mapear `ImportSummary` del 40 a contadores por proyecto en `ImportJobProject`.

## Fase 4: Progreso, reanudación y reaper [R6][R7][R8]

- [ ] 4.1 RED: `GET /connectors/{id}/admin-import/jobs/{id}` devuelve header + detalle por proyecto.
- [ ] 4.2 RED: resume reprocesa solo `pending`/`failed`, salta `done`, sin duplicar (idempotencia por `external_key` del 40).
- [ ] 4.3 RED: fallo a mitad del lote → ese proyecto `failed` con `error_detail` corto; el lote continúa con el resto.
- [ ] 4.4 RED: proyecto que excede `JIRA_MAX_PAGES` queda `truncated=true` con conteo importado y omitido.
- [ ] 4.5 RED: reaper — `running` con `heartbeat_at` vencido pasa a `interrupted` (reloj inyectado, sin sleep real).
- [ ] 4.6 GREEN: endpoint `GET .../admin-import/jobs/{id}`.
- [ ] 4.7 GREEN: endpoint `POST .../admin-import/jobs/{id}/resume`.
- [ ] 4.8 GREEN: crear `backend/app/modules/jira_import/reaper.py` (`register_import_reaper_job`), registrar en `app/main.py` sobre el mismo `AsyncIOScheduler` de `alerts`/`reminders`.
- [ ] 4.9 GREEN: agregar a `backend/app/config.py`: `IMPORT_JOB_HEARTBEAT_INTERVAL_SECONDS`, `IMPORT_JOB_HEARTBEAT_TIMEOUT_SECONDS`, `IMPORT_REAPER_INTERVAL_SECONDS`, `IMPORT_PROJECT_PAUSE_SECONDS`.

## Fase 5: No-exposición del token [R10]

- [ ] 5.1 RED: ninguna respuesta de los 4 endpoints (`discover`, crear job, consultar, resume) contiene el token en claro ni cifrado crudo.
- [ ] 5.2 RED: logs capturados del runner/reaper no registran el token ni `access_token_enc`, solo estado del job.
- [ ] 5.3 GREEN: sanear `error_detail` y logging del runner para que jamás incluyan datos sensibles.

## Fase 6: UI — descubrimiento, selección y progreso [R1][R2][R6][R7]

- [ ] 6.1 Modificar `frontend/src/entities/connector/connector.model.ts`: tipos `DiscoveredProject`, `ImportJob`, `ImportJobProject`.
- [ ] 6.2 Modificar `frontend/src/entities/connector/connectors.service.ts`: `discoverSite()`, `createImportJob()`, `getImportJob()`, `resumeImportJob()`.
- [ ] 6.3 Modificar `frontend/src/pages/connections/connections.component.ts`: tabla de descubrimiento con selección múltiple + "Seleccionar todo", panel de progreso por polling, botón "Reanudar".
- [ ] 6.4 Agregar textos en español colombiano formal (tuteo) bajo `connectors` en `frontend/src/assets/i18n/es-CO.json`.
- [ ] 6.5 Build: `ng build` sin errores; verificar que el polling se detiene al finalizar el job (`done`/`failed`/`interrupted`).

## Fase 7: Suite completa y cierre

- [ ] 7.1 Suite backend completa: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` en verde.
- [ ] 7.2 Suite frontend completa (`ng test`) en verde.
- [ ] 7.3 Commits convencionales en español por unidad lógica (ej. `feat(jira-import-admin): agrega descubrimiento masivo del sitio`).
