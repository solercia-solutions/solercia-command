# Tasks: 40 · Importación Jira por usuario (elegir → previsualizar → importar)

## Reconciliación aplicada (orquestador)

1. **Ancla D2 ratificada**: `projects` usa `(organization_id, source, external_key)`;
   `sprints`/`tasks` usan `(project_id, source, external_key)` — únicos parciales
   `WHERE external_key IS NOT NULL`. `project_id` ya implica organización (CASCADE);
   evita denormalizar `organization_id` en `sprints`/`tasks`.
2. **Anti-inyección JQL obligatoria**: `import-project` valida `jira_project_key` contra
   `^[A-Z][A-Z0-9]+$` ANTES de construir `project = "KEY"` y ANTES de llamar al cliente
   HTTP. Fase 3 incluye el RED test explícito (3.3) antes de cualquier implementación.
3. **Seam reutilizable por el 41**: `importar_proyecto(connector, jira_project_key,
   mapping, *, organization_id, session) -> ImportSummary` corre en **una transacción
   propia por proyecto** — el 41 la invoca una vez por proyecto de su lote, cada uno con
   su propio savepoint; el 40 la invoca una sola vez.
4. **Auditoría de precondiciones (Fase 0, hallazgo de este documento)**: al escribir este
   `tasks.md` se verificó en disco que **28-calendario-laboral, 29-sprint-borrador,
   34-estimación-normalizada y 39-conector-capacidades siguen con `apply: pending`** —
   `backend/app/modules/work_calendar/` no existe, `sprints/service.py` no reconoce
   `'draft'`, y `connectors`/`jira_import` no exponen ningún endpoint de acciones nuevo.
   El supuesto "29/34 ya en preview" del orquestador NO coincide con el estado real del
   repositorio a la fecha de este documento. La Fase 0 vuelve a verificar cada
   precondición al momento de `apply`; si alguna sigue faltando, este cambio se detiene
   y corren primero 28→29/34→39 en ese orden.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1750–2340 (migración+modelos ~70-110, solo `projects`/`sprints` — el 43 ya entregó el ancla de `tasks`; adapter/dto/normalizer/client ~150-200 + tests ~350-450; importer/preview/repository nuevos ~450-600 + tests ~600-800; router/schemas/service ~180-260 + tests ~300-400; frontend wizard+entities ~350-450) |
| 400-line budget risk | High — el cambio completo (migración + 3 módulos backend nuevos + 3 endpoints + asistente frontend) supera el presupuesto de revisión con certeza |
| Chained PRs recommended | No — instrucción explícita del orquestador: single-pr, merge local a `preview` con commits escalonados (mismo patrón que 25/27/28/34) |
| Suggested split | Fase 0 gate 28/29/34/39 → Fase 1 migración de anclas → Fase 2 extensión adapter/DTO/normalizer → Fase 3 `JiraProjectImporter`+`PreviewBuilder` (bloque más grande, batería RED completa) → Fase 4 endpoints → Fase 5 asistente frontend → Fase 6 suite completa + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U0 | Fase 0 — confirmar 28/29/34/39 aplicados en disco + head Alembic real | (sin commit propio) | `ls backend/app/modules/work_calendar/{resolver,schemas,estimation}.py && rg -n "draft" backend/app/modules/sprints/service.py && rg -n "jira_import" backend/app/modules/connectors/*.py` | N/A — solo lectura de disco | N/A |
| U1 | Fase 1 — migración `source`/`external_key` + únicos parciales en `projects`/`sprints` (el ancla de `tasks` ya la entregó el 43) | 1 — `feat(anchors): agrega source/external_key con únicos parciales a projects/sprints` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_external_anchor_migration.py` | Pytest contra Postgres real de test + `alembic downgrade -1 && alembic upgrade head` | Revert commit + `alembic downgrade -1`; columnas/índices nuevos, cero filas afectadas |
| U2 | Fase 2 — `list_projects`, `original_estimate_seconds`, `assignee_email`, `parent_key` en el adaptador Jira | 2 — `feat(jira-adapter): agrega list_projects, original_estimate_seconds, assignee_email y parent_key` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_adapter_client.py backend/tests/test_jira_adapter_normalizer.py backend/tests/test_jira_adapter_dtos.py` | Pytest, `httpx.MockTransport` (sin red real) | Revert commit; campos nuevos con default `None`, cero consumidores todavía |
| U3 | Fase 3 — `JiraProjectImporter`+`PreviewBuilder`+`JiraImportRepository` (jerarquía, task_key atómico, reconciliación, anti-inyección, rollback total) | 3 — `feat(jira-import): agrega JiraProjectImporter con jerarquía, task_key atómico y reconciliación idempotente` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_import_preview.py backend/tests/test_jira_import_importer.py` | Pytest contra Postgres real de test | Revert commit; módulo nuevo sin endpoint expuesto todavía |
| U4 | Fase 4 — `GET .../jira/projects`, `POST .../jira/preview`, `POST .../jira/import-project` | 4 — `feat(jira-import): expone projects/preview/import-project en la API` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_import_router.py` | Pytest contra Postgres real de test | Revert commit; sub-rutas nuevas dejan de exponerse, `import`/`import-file` intactos |
| U5 | Fase 5 — asistente frontend de 3 pasos + entities/jira-import + cableado del punto de entrada (39) | 5 — `feat(jira-import-wizard): asistente de 3 pasos para importar un proyecto Jira` | `cd frontend && npx jest --testPathPattern jira-import-wizard` (o el runner configurado; confirmar en `package.json`) | `cd frontend && npm run build` (build real, sin mocks) | Revert commit; la acción vuelve a `coming_soon`, el backend sigue funcionando vía Swagger |
| U6 | Fase 6 — suite completa verde + commit final si aplica | 6 — `fix(jira-import): cierra hallazgos de la suite completa` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U6 no aporta commit nuevo |

## Fase 0 — Precondiciones: 28/29/34/39 aplicados + head Alembic real

- [ ] 0.1 Confirmar que `backend/app/modules/work_calendar/{resolver,schemas,estimation}.py` existen (`WorkCalendarResolver`, `ResolvedCalendar`, `seconds_to_hours`). Verify: `ls backend/app/modules/work_calendar/{resolver,schemas,estimation}.py`. Si falta cualquiera, DETENER y aplicar primero `28-calendario-laboral` y `34-estimacion-normalizada`.
- [ ] 0.2 Confirmar que `backend/app/modules/sprints/service.py` reconoce `'draft'` en `_ALLOWED_STATUSES` y que `create_sprint` puede nacer sin fechas. Verify: `rg -n "draft" backend/app/modules/sprints/service.py`. Si falta, DETENER y aplicar primero `29-sprint-borrador`.
- [ ] 0.3 Confirmar que `39-conector-capacidades` aplicó el panel de acciones (`GET /connectors/{id}/actions`) y que la acción `jira_import` dejó de estar `coming_soon`. Verify: `rg -n "jira_import" backend/app/modules/connectors/*.py`. Si falta, DETENER y aplicar primero `39`.
- [ ] 0.4 Confirmar el head Alembic real en disco antes de fijar `down_revision`. Verify: `cd backend && .venv/bin/alembic heads` (documento verificó `0021_unique_org_member` como head en su momento; el head real hoy en disco es `0024_add_work_calendar`, y tras el `apply` del `43-tareas-origen-externo` será `0025_add_task_external_origin`; reanclar siempre al head efectivamente vigente en el momento del `apply` del 40, no a ninguno de estos valores fijados por escrito).
- [ ] 0.5 Confirmar el próximo consecutivo de migración libre. Verify: `ls backend/alembic/versions/ | tail -3` → el siguiente consecutivo **no es un número reservado por adelantado**: es el que esté libre en el momento del `apply` del 40, verificado entonces con `alembic heads` y con los cambios pendientes que aterricen antes (hoy sería `0029` si el `44-importar-checklist-xlsx` —`0026`/`0027`— y el `45a-planes-modelo-api` —`0028`— se aplican primero). Un `down_revision` hacia una revisión que nadie ha escrito rompe `alembic upgrade head` en despliegue.

## Fase 1 — Migración de anclas + exposición en `TaskRead` (Commit 1)

- [ ] 1.1 Crear `backend/alembic/versions/00NN_add_external_anchor_projects_sprints.py` (`00NN` = el consecutivo libre confirmado en 0.5; `down_revision` = el head confirmado en 0.4): agrega `source String(50)` y `external_key VARCHAR(255)` nullable a `projects`, `sprints`; índices únicos parciales `uq_projects_org_source_external_key (organization_id, source, external_key) WHERE external_key IS NOT NULL`, `uq_sprints_project_source_external_key (project_id, source, external_key) WHERE external_key IS NOT NULL`. `tasks` queda **fuera**: el `43-tareas-origen-externo` ya entregó su propio ancla (`uq_tasks_source_external_key_project`, otro orden de columnas — `(source, external_key, project_id)` — y otro nombre). `downgrade()` elimina los 2 índices y las 4 columnas.
- [ ] 1.2 `backend/app/modules/projects/models.py`, `backend/app/modules/sprints/models.py`: agregar `source: Mapped[str | None]` y `external_key: Mapped[str | None]` + el índice único parcial correspondiente en `__table_args__` (mismo patrón `postgresql_where` que los índices trgm existentes). `backend/app/modules/tasks/models.py` **no se toca**: su ancla ya la declaró el 43.
- [ ] 1.3 [RED] Crear `backend/tests/test_external_anchor_migration.py`: dos projects de la misma organización con `(source='jira', external_key='X')` → el segundo `IntegrityError`; `external_key=None` repetido en la misma organización no viola nada; mismo `external_key` en organizaciones DISTINTAS tampoco viola nada. Igual para `sprints` (`project_id`). `tasks` queda fuera de este archivo: sus aserciones las cubre `test_migration_task_external_origin.py` del 43. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_external_anchor_migration.py` → falla hasta 1.1/1.2.
- [ ] 1.4 [GREEN] Aplicar 1.1/1.2 hasta cerrar 1.3 en verde. Verify: mismo comando.
- [ ] 1.5 Verificar (ya NO es RED/GREEN — el 43, rebanada B, ya agregó ambos campos): confirmar que `GET /tasks/{id}` sigue exponiendo `external_key` junto al `task_key` local, sin alterar su cálculo. Verify: `rg -n "external_key" backend/app/modules/tasks/schemas.py`.
- [ ] 1.6 Verificar (ya NO es RED/GREEN): `backend/app/modules/tasks/schemas.py::TaskRead` ya declara `source: str | None = None` y `external_key: str | None = None`, entregados por el 43; este cambio no agrega código nuevo aquí. Verify: mismo comando de 1.5.
- [ ] 1.7 Migración reversible. Verify: `cd backend && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head` sin error.

Commit 1: `feat(anchors): agrega source/external_key con únicos parciales a projects/sprints`

## Fase 2 — Adaptador Jira: `list_projects`, estimación en segundos, email, padre (Commit 2)

- [ ] 2.1 [RED] Extender `backend/tests/test_jira_adapter_dtos.py`: `NormalizedJiraIssue` acepta `original_estimate_seconds`, `assignee_email`, `parent_key` con default `None` (retrocompat con instancias existentes). Verify: `pytest -q backend/tests/test_jira_adapter_dtos.py`.
- [ ] 2.2 [GREEN] `backend/app/integrations/adapters/jira/dtos.py`: agregar los 3 campos al final del dataclass con `= None`. Verify: mismo comando.
- [ ] 2.3 [RED] Extender `backend/tests/test_jira_adapter_client.py`: `JiraClient.list_projects()` pagina `/rest/api/3/project/search` (`startAt`/`isLast`) y devuelve `[{key,name}]`, acotado por `JIRA_MAX_PAGES` igual que `list_issues`. Verify: `pytest -q backend/tests/test_jira_adapter_client.py -k list_projects` → falla (método no existe).
- [ ] 2.4 [GREEN] `backend/app/integrations/adapters/jira/client.py`: `_PROJECT_SEARCH_PATH = "/rest/api/3/project/search"`; `async def list_projects(self) -> list[dict]` con paginación `startAt` acotada, mismo manejo de errores que `_get`. Verify: mismo comando.
- [ ] 2.5 [RED] Extender `backend/tests/test_jira_adapter_normalizer.py`: issue con `timeoriginalestimate=14400`, `assignee.emailAddress="mia@acme.com"`, `parent.key="PROJ-1"` → `original_estimate_seconds==14400`, `assignee_email=="mia@acme.com"`, `parent_key=="PROJ-1"`; ausentes → los 3 en `None`. Verify: `pytest -q backend/tests/test_jira_adapter_normalizer.py -k "estimate_seconds or assignee_email or parent_key"`.
- [ ] 2.6 [GREEN] `backend/app/integrations/adapters/jira/normalizer.py`: `_canonical_from_api_issue` extrae `fields.get("timeoriginalestimate")`, `(fields.get("assignee") or {}).get("emailAddress")`, `(fields.get("parent") or {}).get("key")`; `_canonical_from_file_row` intenta columnas equivalentes del export (`"Original Estimate"`, email de `"Assignee"`, `"Parent id"`) con fallback `None` sin romper el import de archivo; `_build_issue` pasa los 3 campos al DTO. Verify: mismo comando.
- [ ] 2.7 [GREEN] `backend/app/integrations/adapters/jira/adapter.py`: `_BASE_SEARCH_FIELDS += ("timeoriginalestimate", "parent")` (`assignee` ya se solicita; Jira incluye `emailAddress` salvo restricción de privacidad de la instancia, caso que ya cae en `assignee_email=None` sin romper nada). Verify: `pytest -q backend/tests/test_jira_adapter_client.py backend/tests/test_jira_adapter_normalizer.py backend/tests/test_jira_import_router.py`.
- [ ] 2.8 Suite dirigida verde. Verify: comando de 2.7.

Commit 2: `feat(jira-adapter): agrega list_projects, original_estimate_seconds, assignee_email y parent_key`

## Fase 3 — `JiraProjectImporter` + `PreviewBuilder` + repositorio (Commit 3)

- [ ] 3.1 [RED] Crear `backend/tests/test_jira_import_preview.py`: dado issues normalizados (épica/historia/subtarea/bug + 2 sprints), `build_preview(issues, report, strategy=ScrumStrategy())` devuelve conteos por tipo, sprints detectados y mapeo propuesto de estado — función PURA, sin tocar la BD (assert de conteo de filas antes/después). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_import_preview.py` → falla (módulo no existe).
- [ ] 3.2 [GREEN] Crear `backend/app/modules/jira_import/preview.py`: `build_preview(issues, report, *, strategy) -> PreviewResult` (conteos, sprints, mapeo estado/tipo/estimación). Verify: mismo comando.
- [ ] 3.3 [RED] Crear `backend/tests/test_jira_import_importer.py`: **anti-inyección JQL** — `test_rejects_project_key_that_fails_jql_safe_pattern`, clave maliciosa (p. ej. `'ABC" OR 1=1--'`) → `importar_proyecto` rechaza con `AppException(422)` ANTES de construir el JQL o invocar el transporte HTTP (assert de 0 llamadas al mock). Verify: `pytest -q backend/tests/test_jira_import_importer.py -k jql_injection` → falla (validación no existe).
- [ ] 3.4 [GREEN] Crear `backend/app/modules/jira_import/importer.py`: `_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+$")`; validar `jira_project_key` al inicio de `importar_proyecto`, antes de tocar el adaptador. Verify: mismo comando.
- [ ] 3.5 [RED] `test_jerarquia_epic_story_subtask_dos_pasadas`: épica + 2 historias hijas + 1 subtarea cada una → historias con `parent_task_id`=id de la épica, subtareas con `parent_task_id`=id de su historia; cada task con `task_key` local secuencial y `external_key`=clave Jira. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k jerarquia`.
- [ ] 3.6 [RED] `test_subtarea_huerfana_sin_padre_en_el_set`: subtarea con `parent_key` fuera del conjunto importado → se crea con `parent_task_id=None`, `ImportSummary.huerfanas` la registra. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k huerfana`.
- [ ] 3.7 [RED] `test_task_key_atomico_por_bloque`: N issues nuevos → `task_counter` avanza exactamente N en UNA `UPDATE...RETURNING`, asignación secuencial desde `counter-N+1`; reimportar el mismo set no vuelve a consumir contador. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k task_key_atomico`.
- [ ] 3.8 [RED] `test_mapeo_estado_via_strategy_sin_if_methodology`: issues con `status_bucket` todo/in_progress/done → `status` = `strategy.allowed_statuses()[0]` / el estado interior `"In Progress"` / `strategy.allowed_statuses()[-1]`; bucket no homologado usa el fallback del 18 y queda en `NormalizationReport`. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k mapeo_estado`.
- [ ] 3.9 [RED] `test_sprint_future_activo_cerrado_mapea_a_draft_active_closed`: `sprint_state` `future`/`active`/`closed` → Sprint local `draft`/`active`/`closed` preservando fechas (ancla de sprint = nombre del sprint, ya que el adaptador actual no expone id de sprint — ver Risks). Verify: `pytest -q backend/tests/test_jira_import_importer.py -k sprint_state`.
- [ ] 3.10 [RED] `test_estimation_seconds_a_horas_y_story_points`: `original_estimate_seconds=14400`, `story_points=5.0` → `estimation_hours==Decimal("4")` (vía `seconds_to_hours` de 34), `estimation_points==5`. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k estimation_conversion`.
- [ ] 3.11 [RED] `test_asignado_por_email_match_y_sin_match`: `assignee_email` de un miembro de la org → `assignee_id` resuelto; email ajeno → `assignee_id=None` + nota en `description` con el asignado original de Jira. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k asignado_email`.
- [ ] 3.12 [RED] `test_reimportar_no_duplica_reconcilia`: import inicial crea N tasks; reimportar con un título cambiado → 0 tasks nuevas, la tarea anclada actualiza título, `actualizados >= 1`, `creados == 0`. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k reimportar_no_duplica`.
- [ ] 3.13 [RED] `test_conflicto_ambiguo_se_rechaza`: mismo `external_key` ya anclado con `task_type` incompatible (p. ej. `epic` reimportado como `subtask`) → `AppException` clara, SIN cambios parciales (counts pre/post iguales). Verify: `pytest -q backend/tests/test_jira_import_importer.py -k conflicto_ambiguo`.
- [ ] 3.14 [RED] `test_fallo_a_mitad_de_import_hace_rollback_total`: transporte que falla a mitad de página → nada se persiste (`select(func.count()).select_from(Task)` sin cambios), la excepción se propaga. Verify: `pytest -q backend/tests/test_jira_import_importer.py -k rollback_total`.
- [ ] 3.15 [GREEN] Crear `backend/app/modules/jira_import/repository.py`: `JiraImportRepository` — `upsert_project`/`upsert_sprint`/`upsert_task` (buscan por `(scope, source='jira', external_key)`; existe → actualiza campos base, si no → crea); `async def allocate_task_numbers(self, project_id, n) -> int` (extiende `allocate_task_number` de bloque 1 a bloque n con UNA `UPDATE...RETURNING`).
- [ ] 3.16 [GREEN] Completar `backend/app/modules/jira_import/importer.py`: `class JiraProjectImporter` con `async def importar_proyecto(connector, jira_project_key, mapping, *, organization_id, session) -> ImportSummary` — arma JQL `project = "KEY"`, llama `adapter.import_issues`, resuelve/crea Project local (scrum), upsert de Sprints, pasada 1 (tasks sin padre + `flush` + índice `external_key→id`), pasada 2 (enlaza `parent_task_id`, huérfana→nota), aplica `seconds_to_hours`/`estimation_points`, resuelve asignado por email, detecta conflicto ambiguo, TODO en una transacción (rollback total ante cualquier fallo). Verify: `pytest -q backend/tests/test_jira_import_importer.py` completo → verde.
- [ ] 3.17 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_import_preview.py backend/tests/test_jira_import_importer.py backend/tests/test_jira_adapter_normalizer.py backend/tests/test_jira_adapter_client.py`

Commit 3: `feat(jira-import): agrega JiraProjectImporter con jerarquía, task_key atómico y reconciliación idempotente`

## Fase 4 — Endpoints `projects`/`preview`/`import-project` (Commit 4)

- [ ] 4.1 [RED] Extender `backend/tests/test_jira_import_router.py`: `GET /connectors/{id}/jira/projects` happy, sin cuenta conectada/credenciales vencidas (error controlado es-CO, sin exponer el token), conector de otra organización → 404, rol member → 403. Verify: `pytest -q backend/tests/test_jira_import_router.py -k jira_projects_endpoint`.
- [ ] 4.2 [GREEN] `backend/app/modules/jira_import/router.py`: `GET /connectors/{connector_id}/jira/projects` (mismo `require_jira_import_role`); `backend/app/modules/jira_import/service.py::list_projects` decripta credenciales + `client.list_projects()`. Verify: mismo comando.
- [ ] 4.3 [RED] `POST /connectors/{id}/jira/preview` happy (conteos+mapeo, conteo de filas antes/después igual — NO persiste), proyecto ya no accesible → error controlado sin generar datos, mismos permisos que 4.1. Verify: `pytest -q backend/tests/test_jira_import_router.py -k jira_preview_endpoint`.
- [ ] 4.4 [GREEN] `router.py`+`schemas.py` (`JiraPreviewRequest{project_key}`, `JiraPreviewResponse`) + `service.py::preview` (llama `adapter.import_issues` + `build_preview`, sin invocar el importer). Verify: mismo comando.
- [ ] 4.5 [RED] `POST /connectors/{id}/jira/import-project` happy (creados en la primera corrida), reimport (actualizados sin duplicar), clave con formato inválido → 422 sin llamar a Jira, conector de otra org → 404, rol member → 403. Verify: `pytest -q backend/tests/test_jira_import_router.py -k jira_import_project_endpoint`.
- [ ] 4.6 [GREEN] `router.py`+`schemas.py` (`JiraImportProjectRequest{project_key, project_name?, project_code?, status_overrides?}`, `ImportSummaryRead`) + `service.py::import_project` (arma `ImportMapping`, llama `JiraProjectImporter.importar_proyecto`). Verify: mismo comando.
- [ ] 4.7 Suite dirigida completa del módulo + no-regresión de `import`/`import-file` (frontera solo-lectura intacta salvo `import-project`). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_jira_import_router.py backend/tests/test_jira_import_importer.py backend/tests/test_jira_import_preview.py`

Commit 4: `feat(jira-import): expone projects/preview/import-project en la API`

## Fase 5 — Asistente frontend de 3 pasos (Commit 5)

- [ ] 5.1 Crear `frontend/src/entities/jira-import/jira-import.model.ts`: `JiraProjectSummary`, `JiraPreviewResult`, `ImportSummary` (mirror de los schemas del backend).
- [ ] 5.2 Crear `frontend/src/entities/jira-import/jira-import.service.ts`: `listJiraProjects(connectorId)`, `previewJiraProject(connectorId, projectKey)`, `importJiraProject(connectorId, payload)` sobre el cliente HTTP compartido.
- [ ] 5.3 Crear `frontend/src/widgets/jira-import-wizard/` (componente nuevo, separado del drawer hardcodeado actual en `pages/connections/connections.component.ts`): 3 pasos con estados de carga/vacío/error diferenciados (spec jira-import-wizard, todos los escenarios); paso 2 con nombre/código editables prellenados desde el proyecto Jira; paso 3 muestra el resumen final (creados/actualizados/omitidos + no homologados).
- [ ] 5.4 Cablear el punto de entrada: en `pages/connections/connections.component.ts`, la acción `jira_import` del panel de acciones del conector (39) abre este asistente en vez de quedar `coming_soon`.
- [ ] 5.5 Textos en español colombiano formal (tuteo) en cada paso/estado (spec "Errores claros en cada paso").
- [ ] 5.6 Build verde. Verify: `cd frontend && npm run build` (o el comando configurado en `package.json`).

Commit 5: `feat(jira-import-wizard): asistente de 3 pasos para importar un proyecto Jira`

## Fase 6 — Suite completa + commits (Commit 6 condicional)

- [ ] 6.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 6.2 Aislamiento cross-tenant no regresó con `external_key`. Verify: `ls backend/tests | rg cross_tenant` para confirmar el archivo exacto, luego `pytest -q <archivo> -k "jira or external"`.
- [ ] 6.3 Migración reversible confirmada tras toda la implementación. Verify: `cd backend && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head`.
- [ ] 6.4 Build de frontend verde (repetir tras cualquier ajuste de Fase 5). Verify: `cd frontend && npm run build`.
- [ ] 6.5 Commit final (solo si 6.1-6.3 generaron correcciones no cubiertas por los commits 1-5).

Commit 6 (solo si 6.5 generó cambios): `fix(jira-import): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Ancla de procedencia externa + único parcial (projects/sprints; `tasks` ya la entregó el 43) · 1.1,1.2,1.3,1.4
- Clave local y externa conviven (detalle de tarea expone ambas — requisito entregado por el 43; este cambio solo verifica que sigue expuesto) · 1.5,1.6
- Listado de proyectos Jira accesibles (+ sin cuenta/credenciales vencidas, RBAC, aislamiento) · 2.3,2.4,4.1,4.2
- Previsualización sin persistir (+ proyecto ya no accesible) · 3.1,3.2,4.3,4.4
- Conversión de estimación original a horas y puntos · 2.5,2.6,3.10
- Importación con jerarquía y clave local atómica (+ subtarea huérfana) · 3.5,3.6,3.7,3.15,3.16
- Idempotencia y reconciliación al reimportar (+ conflicto ambiguo) · 3.12,3.13
- Mapeo de estado/sprint vía strategy destino · 3.8,3.9
- Homologación de asignado por email · 3.11
- Anti-inyección JQL (clave de proyecto) · 3.3,3.4
- Consistencia parcial → rollback total · 3.14
- Frontera solo-lectura estricta (MODIFIED — import/import-file sin efectos) · 4.7
- Asistente de 3 pasos (selección/preview editable/resumen/errores/permisos) · 5.1,5.2,5.3,5.4,5.5,5.6
- Gate 28/29/34/39 → 40 + head Alembic real · 0.1,0.2,0.3,0.4,0.5
- No regresión y commits escalonados en una sola integración · 6.1,6.2,6.3,6.4,6.5

## Risks

- **Discrepancia de precondiciones (hallazgo de este documento)**: 28, 29, 34 y 39 tienen
  `apply: pending` en disco pese al supuesto "29/34 ya en preview" recibido del
  orquestador; la Fase 0 de este documento es la única defensa real — si `apply` la
  omite, Fases 1-5 fallarán en cascada (sin `seconds_to_hours`, sin `'draft'`, sin punto
  de entrada real del 39).
- **Ancla de sprint sin id propio**: el adaptador actual (`_extract_sprint_from_api`)
  solo expone `sprint_name`/`sprint_state`, no el id numérico de sprint de Jira; este
  documento usa el NOMBRE del sprint como `external_key` (supuesto de nombres únicos por
  proyecto/tablero) — si el equipo prefiere anclar por id real, requiere un cuarto campo
  nuevo en el DTO, fuera del alcance fijado por `design.md`.
- **Epic link en proyectos company-managed**: el MVP cubre solo proyectos team-managed/
  next-gen vía `fields.parent.key` (Open Question de `design.md`); el custom field de
  epic-link en company-managed queda para el 41.
- **Import grande / timeout**: una sola transacción por proyecto puede ser costosa en
  proyectos Jira muy grandes; el 41 (batch admin) introduce savepoints por proyecto, pero
  el 40 asume un volumen manejable por request.
- **Asignado sin `emailAddress`**: si la instancia Jira restringe la visibilidad de
  `emailAddress` (configuración de privacidad), todo asignado cae en "sin asignar + nota"
  aunque exista match potencial por nombre — comportamiento esperado, documentado en la
  spec.
