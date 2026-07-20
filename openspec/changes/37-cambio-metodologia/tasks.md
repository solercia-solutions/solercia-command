# Tasks: 37 · Cambio de metodología de un proyecto existente

## Reconciliación aplicada (orquestador)

1. **Ruta del preview** — `design.md` (Technical Approach, D1, Data Flow) usa
   `GET /projects/{id}/methodology-migration/plan?target=<m>`;
   `specs/methodology-migration/spec.md` (Alcance propuesto y todos sus
   escenarios) fija la ruta como `GET
   /projects/{id}/methodology-migration/preview?target=<methodology>`. Por
   instrucción explícita del orquestador, **gana la spec**: este documento usa
   `/preview` en todas partes; el segmento `/plan` del `design.md` queda
   superado y no se reabre en `apply`. El resto de decisiones de `design.md`
   (módulo dedicado `methodology_migration`, flag `commit` en `boards`
   service, recompute de `completed_at`, 422 `same_methodology`) se mantienen
   sin cambios.

## Notas técnicas adicionales (autor de este documento, no reconciliación del orquestador)

- **`target_status_key` real vs. literal de la strategy**: `design.md` D3/D4
  usa `target.allowed_statuses()` en su pseudocódigo, pero `BoardService.
  add_column` (reutilizado por decisión de `state.yaml`/D1, sin nuevas
  primitivas de board) SIEMPRE deriva `status_key` con `_slugify(name)` — para
  metodologías fijas eso NO coincide con el string literal de
  `default_columns()` (p. ej. `"Sin iniciar"` → `"sin_iniciar"`). Este
  documento resuelve la ambigüedad a favor del principio ya establecido en el
  código ("el board persistido es la fuente de verdad", `BoardAwareStrategy`):
  el `target_status_key` de cada mapeo y el invariante D4 usan el `status_key`
  REALMENTE creado en las columnas destino, nunca el string literal de la
  strategy base. Confirmar esta lectura en `apply` si se prefiere otra.
- `MigrationPlanner` (mencionado en `design.md` Data Flow) vive como
  clase/función interna de `methodology_migration/service.py` — el `File
  Changes` de `design.md` no lista un archivo propio para él.
- No existe hoy una página de "configuración de proyecto"; Fase 5 integra el
  asistente como botón/modal dentro de `project-workspace.component.ts`
  (encabezado del proyecto), sin ruta nueva.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1500–1750 (producción ~550–650: `boards/service.py` ~20-30, `methodology_migration/{schemas,repository,service,router}.py` ~450-550, `main.py` +2, frontend `entities/methodology-migration/*`+`widgets/methodology-migration-wizard/*`+`project-workspace.component.ts` ~200-280; tests ~950-1100: `test_methodology_migration_preview.py` ~180-220, `test_methodology_migration_execute.py` ~350-450, `test_methodology_migration_mapping.py` ~150-200, ajustes a `test_boards.py` ~40-70) |
| 400-line budget risk | High — supera el presupuesto de revisión con certeza, backend+frontend en 6 fases con TDD estricto y sin migración de esquema |
| Chained PRs recommended | No — instrucción explícita: single-pr, merge local a `preview` (mismo patrón que 25/27/28/34: commits escalonados dentro de una sola integración) |
| Suggested split | Fase 1 flag `commit` en boards (suite intacta) → Fase 2 módulo `methodology_migration` + preview → Fase 3 ejecución transaccional → Fase 4 matriz de mapeo por defecto → Fase 5 asistente UI + build → Fase 6 suite completa + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U1 | Fase 1 — `commit: bool = True` en `add_column`/`remove_column`, suite de boards intacta | 1 — `refactor(boards): agrega el parámetro commit a add_column y remove_column` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_boards.py backend/tests/test_boards_backfill_migration.py` | Pytest contra Postgres real de test | Revert commit; `commit=True` por defecto deja el comportamiento actual intacto |
| U2 | Fase 2 — módulo `methodology_migration` + `GET .../preview` | 2 — `feat(methodology-migration): agrega el endpoint de previsualización del cambio de metodología` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_preview.py` | Pytest + cliente HTTP real | Revert commit + quitar `include_router` de `main.py`; sin escritura de datos, solo lectura |
| U3 | Fase 3 — `POST .../methodology-migration` transaccional | 3 — `feat(methodology-migration): ejecuta la migración transaccional con remapeo, sprints y completed_at` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_execute.py` | Ídem, incluye fault injection (monkeypatch) para el rollback | Revert commit; el endpoint queda sin exponer POST, GET preview de U2 no se ve afectado |
| U4 | Fase 4 — matriz de mapeo por defecto (4 metodologías) | 4 — `test(methodology-migration): cubre la matriz de mapeo por defecto entre las 4 metodologías` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_mapping.py` | Pytest puro (sin BD, `MigrationPlanner` con strategies fijas) | Revert commit; solo agrega cobertura sobre `MigrationPlanner` ya existente |
| U5 | Fase 5 — asistente UI de 2 pasos en `project-workspace` | 5 — `feat(methodology-migration): agrega el asistente de 2 pasos para cambiar la metodología del proyecto` | `cd frontend && npx jest --testPathPattern methodology-migration` (o el runner configurado; confirmar en `package.json`) | `cd frontend && npm run build` (build real) | Revert commit; el backend sigue funcionando sin el botón/modal nuevo |
| U6 | Fase 6 — suite completa + commit final si aplica | 6 — `fix(metodologia): cierra hallazgos de la suite completa` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U6 no aporta commit nuevo |

## Fase 1 — Refactor de `boards/service.py`: flag `commit` (Commit 1)

- [ ] 1.1 Baseline: confirmar que `test_boards.py`/`test_boards_backfill_migration.py` están verdes ANTES de tocar código. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_boards.py backend/tests/test_boards_backfill_migration.py`
- [ ] 1.2 [RED] `test_add_column_accepts_commit_false_and_caller_controls_the_transaction`: llamar `BoardService.add_column(..., commit=False)`, verificar que la fila es visible vía `flush`/la propia sesión pero solo se confirma tras un `db.commit()` explícito del test. Hoy falla: `add_column` no acepta `commit` (`TypeError`). Verify: `pytest -q backend/tests/test_boards.py -k accepts_commit_false`
- [ ] 1.3 [RED] `test_remove_column_accepts_commit_false_and_caller_controls_the_transaction`: mismo contrato para `remove_column`. Verify: `pytest -q backend/tests/test_boards.py -k remove_column_accepts_commit_false`
- [ ] 1.4 [GREEN] `backend/app/modules/boards/service.py`: agregar `commit: bool = True` a `add_column`/`remove_column` (mismo precedente que `move_to_column`): `if commit: await self.repo.db.commit(); await self.repo.db.refresh(...)`; con `commit=False` solo `flush` (ya implícito por el `self.repo.db.add`/`update`). Verify: 1.2 y 1.3 en verde.
- [ ] 1.5 Suite de `boards` completa sin regresión (comportamiento por defecto `commit=True` sin cambios). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_boards.py backend/tests/test_boards_backfill_migration.py`

Commit 1: `refactor(boards): agrega el parámetro commit a add_column y remove_column`

## Fase 2 — Módulo `methodology_migration` + `GET .../preview` (Commit 2)

- [ ] 2.1 [RED] Crear `backend/tests/test_methodology_migration_preview.py` (fixtures `client`/`tenant`/`make_member`/`two_orgs` de `conftest.py`). `test_preview_scrum_to_planner_returns_source_statuses_target_columns_mapping_and_impact`: proyecto scrum con tareas en `To Do`/`In Progress`/`In Review`/`Done` y 1 sprint activo → `GET /projects/{id}/methodology-migration/preview?target=planner` (admin) → 200; incluye los 4 estados origen con conteos, las 3 columnas destino (`Sin iniciar`/`En curso`/`Completada`), un mapeo propuesto no vacío y `sprints_to_close == 1`. Hoy falla: 404 (router no existe). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_preview.py -k scrum_to_planner`
- [ ] 2.2 [RED] `test_preview_rejects_target_equal_to_current_methodology_with_422`: proyecto scrum, `target=scrum` → 422 `same_methodology`. Verify: `-k rejects_target_equal`
- [ ] 2.3 [RED] `test_preview_requires_admin_or_manager_role`: `member`/`viewer` (`make_member`) → 403 `forbidden`; `manager` → 200. Verify: `-k requires_admin_or_manager`
- [ ] 2.4 [RED] `test_preview_of_other_organization_project_returns_404` (`two_orgs`): admin de la org A consulta el preview de un proyecto de la org B → 404. Verify: `-k other_organization`
- [ ] 2.5 [GREEN] `backend/app/modules/methodology_migration/schemas.py`: `StatusMapping`, `StatusImpact`, `MigrationPlan`, `MigrationExecute`, `MigrationResult` (campos por `design.md` Interfaces/Contracts).
- [ ] 2.6 [GREEN] `backend/app/modules/methodology_migration/repository.py`: `MethodologyMigrationRepository.count_active_tasks_by_status_key(project_id) -> dict[str, int]` (una query, `GROUP BY` sobre columnas activas del board) y `count_active_sprints(organization_id, project_id) -> int`.
- [ ] 2.7 [GREEN] `backend/app/modules/methodology_migration/service.py`: `MethodologyMigrationService.preview(organization_id, project_id, target) -> MigrationPlan`; internamente resuelve `resolve_board_strategy(project, db)` (origen) y `get_strategy(target)`/`custom_columns` (destino), rechaza 422 `same_methodology` si `target == project.methodology`, y delega en `MigrationPlanner` (clase interna, sin I/O) la heurística D2: slug exacto → bucket semántico `{todo/doing/review/done}` con colapso al bucket `doing` si el destino carece de `review` → fallback por índice proporcional.
- [ ] 2.8 [GREEN] `backend/app/modules/methodology_migration/router.py`: `APIRouter(prefix="/projects/{project_id}/methodology-migration", tags=["methodology-migration"])`; `GET "/preview"` con `require_role(MemberRole.admin, MemberRole.manager)` (mismo patrón que `_require_hierarchy_write_role` de `projects/router.py`), query param `target: Methodology`.
- [ ] 2.9 [GREEN] `backend/app/main.py`: importar y registrar `methodology_migration_router` (`app.include_router(..., prefix=API_PREFIX)`) junto a `projects_router`.
- [ ] 2.10 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_preview.py`

Commit 2: `feat(methodology-migration): agrega el endpoint de previsualización del cambio de metodología`

## Fase 3 — Ejecución transaccional (Commit 3)

- [ ] 3.1 [RED] Crear `backend/tests/test_methodology_migration_execute.py`. `test_execute_scrum_to_planner_remaps_every_task_within_allowed_statuses`: proyecto scrum con tareas en sus 4 estados + mapeo exhaustivo confirmado hacia planner → `POST /projects/{id}/methodology-migration` (admin) → 200; `Project.methodology == "planner"`; toda tarea con `status` dentro de `allowed_statuses()` real (vía `resolve_board_strategy` tras migrar) y su `board_column_id` correspondiente. Hoy falla: 404 (endpoint no existe). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_execute.py -k scrum_to_planner_remaps`
- [ ] 3.2 [RED] `test_execute_planner_to_scrum_allows_tasks_without_estimation_points`: proyecto planner con tareas sin `estimation_points` + mapeo exhaustivo hacia scrum → 200, tareas válidas sin bloqueo. Verify: `-k planner_to_scrum`
- [ ] 3.3 [RED] `test_execute_subtask_remaps_by_its_own_status_not_parent`: tarea padre en `In Progress` con una subtarea en `Done`, mapeo hacia planner → la subtarea recibe el destino correspondiente a `Done` según el mapeo, aunque difiera del que recibe el padre. Verify: `-k subtask_remaps_by_own_status`
- [ ] 3.4 [RED] `test_execute_rejects_incomplete_mapping_with_422_and_no_side_effects`: tareas en `In Review` sin destino en el mapeo confirmado → 422 con el detalle indicando `In Review`; ninguna tarea/columna/sprint/metodología cambia (verificar con un `GET` posterior). Verify: `-k rejects_incomplete_mapping`
- [ ] 3.5 [RED] `test_execute_migration_to_no_sprints_closes_active_sprint_and_unlinks_incomplete_tasks`: sprint activo con tareas completadas e incompletas, migración scrum→kanban → el sprint queda `closed` con `completed_points` sellado; las tareas incompletas quedan `sprint_id = NULL`; las completadas conservan su `sprint_id`. Verify: `-k closes_active_sprint`
- [ ] 3.6 [RED] `test_execute_does_not_touch_already_closed_sprints`: sprint `closed` histórico + sprint `active`, migración hacia kanban → el `closed` conserva `completed_points`/`closed_at` sin cambios. Verify: `-k does_not_touch_already_closed`
- [ ] 3.7 [RED] `test_execute_recomputes_completed_at_against_destination_done_column`: tarea en `Done` (`completed_at` ya sellado) que el mapeo lleva a una columna NO-done del destino → `completed_at` queda `NULL`; tarea mapeada a la columna done del destino sin `completed_at` previo → queda sellado. Verify: `-k recomputes_completed_at`
- [ ] 3.8 [RED] `test_execute_preserves_estimation_points_when_target_hides_them`: tarea con `estimation_points = 5`, migración scrum→planner → `estimation_points` sigue siendo `5` en BD aunque planner no lo exhiba. Verify: `-k preserves_estimation_points`
- [ ] 3.9 [RED] `test_execute_target_custom_without_columns_returns_422_and_keeps_original_methodology`: `POST` con `target=custom` y `custom_columns` vacío/ausente → 422 `custom_columns_required`; `project.methodology` no cambia. Verify: `-k target_custom_without_columns`
- [ ] 3.10 [RED] `test_execute_rolls_back_everything_on_injected_failure`: `monkeypatch` de un paso intermedio (p. ej. `repo.set_methodology`) para forzar una excepción antes del commit final → board, tareas, sprints y `Project.methodology` quedan exactamente como antes de la solicitud (comparar snapshot antes/después). Verify: `-k rolls_back_everything`
- [ ] 3.11 [RED] `test_execute_requires_admin_or_manager_and_scopes_by_organization`: `member` → 403 `forbidden`; proyecto de otra organización (`two_orgs`) → 404. Verify: `-k requires_admin_or_manager`
- [ ] 3.12 [GREEN] `backend/app/modules/methodology_migration/repository.py`: `recompute_completed_at(project_id, done_status_key)` (dos `UPDATE` en bloque: sella si `status == done_status_key` y `completed_at IS NULL`; limpia si no y `completed_at IS NOT NULL`); `close_and_unlink_sprints(organization_id, project_id, actor_id) -> int` (reutiliza `SprintRepository.sum_done_points_for_sprint` + `count_and_move_incomplete_tasks(target_sprint_id=None)` por cada sprint activo, pero fija `status`/`closed_at`/`completed_points` EN MEMORIA sin llamar a `SprintRepository.save`/`create`, que comitean por su cuenta — D3 exige un único commit); `count_invalid_tasks(project_id, allowed_status_keys) -> int`; `set_methodology(project, target, actor_id)`.
- [ ] 3.13 [GREEN] `backend/app/modules/methodology_migration/service.py`: `execute(organization_id, project_id, data, *, actor_id) -> MigrationResult` siguiendo la secuencia D3: 404 proyecto → 422 `mapping_not_exhaustive` (estados origen con tareas activas sin destino) → 422 `custom_columns_required` si `target=custom` sin columnas → por cada columna destino requerida `BoardService(db).add_column(..., commit=False)` (el `status_key` REAL resultante, no el literal de `default_columns()`, es el que se usa como `target_status_key`) → `reassign_column_tasks` por cada mapeo confirmado → `repo.recompute_completed_at` contra el `status_key` de la última columna destino → `remove_column(origen, commit=False)` por cada columna origen ya vacía → si `not get_strategy(target).sprints_enabled`: `repo.close_and_unlink_sprints(...)` → `repo.set_methodology(...)` → invariante D4: `repo.count_invalid_tasks` contra los `status_key` REALMENTE persistidos de las columnas destino; si `> 0` → `db.rollback()` + 500 `migration_invariant_violated` → `db.commit()` único. Cualquier `AppException`/excepción antes del commit dispara `db.rollback()`.
- [ ] 3.14 [GREEN] `backend/app/modules/methodology_migration/router.py`: `POST ""` (`/projects/{project_id}/methodology-migration`) con el mismo `require_role(admin, manager)`; body `MigrationExecute`; delega en `service.execute`.
- [ ] 3.15 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_execute.py backend/tests/test_methodology_migration_preview.py`

Commit 3: `feat(methodology-migration): ejecuta la migración transaccional con remapeo, sprints y completed_at`

## Fase 4 — Matriz de mapeo por defecto entre las 4 metodologías (Commit 4)

- [ ] 4.1 [RED] Crear `backend/tests/test_methodology_migration_mapping.py`: pruebas de tabla contra `MigrationPlanner` (sin BD, `get_strategy` fijas) para las 6 combinaciones de la matriz D2: planner→kanban (`Sin iniciar→Backlog`, `En curso→Doing`, `Completada→Done`); planner→scrum (`Sin iniciar→To Do`, `En curso→In Progress`, `Completada→Done`; `In Review` vacía); kanban→planner (`Backlog→Sin iniciar`, `Doing→En curso`, `Done→Completada`); kanban→scrum (`Backlog→To Do`, `Doing→In Progress`, `Done→Done`; `In Review` vacía); scrum→planner (`To Do→Sin iniciar`, `In Progress→En curso`, `In Review→En curso` [colapso al bucket `doing`], `Done→Completada`); scrum→kanban (`To Do→Backlog`, `In Progress→Doing`, `In Review→Doing` [colapso], `Done→Done`). Hoy falla: `MigrationPlanner` no existe. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_mapping.py`
- [ ] 4.2 [RED] `test_mapping_custom_target_falls_back_to_slug_and_ordinal`: destino `custom` con columnas definidas por el usuario (p. ej. `["Nueva", "En proceso", "Cerrada"]`) → el mapeo cae a slug-match + índice ordinal (sin bucket semántico, el destino no tiene rol conocido). Verify: `-k custom_target_falls_back`
- [ ] 4.3 [GREEN] Ajustar `MigrationPlanner` (`methodology_migration/service.py`) hasta que la matriz completa de 4.1/4.2 pase. Verify: mismo comando de 4.1
- [ ] 4.4 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_methodology_migration_mapping.py backend/tests/test_methodology_migration_preview.py backend/tests/test_methodology_migration_execute.py`

Commit 4: `test(methodology-migration): cubre la matriz de mapeo por defecto entre las 4 metodologías`

## Fase 5 — UI: asistente de 2 pasos en la configuración del proyecto (Commit 5)

- [ ] 5.1 `frontend/src/entities/methodology-migration/methodology-migration.model.ts`: interfaces `StatusMapping`, `StatusImpact`, `MigrationPlan`, `MigrationExecuteRequest`, `MigrationResult` (espejo 1:1 de los schemas backend).
- [ ] 5.2 `frontend/src/entities/methodology-migration/methodology-migration.service.ts`: `getPreview(projectId, target)` → `GET /projects/{id}/methodology-migration/preview?target=`; `execute(projectId, payload)` → `POST /projects/{id}/methodology-migration` (mismo patrón `HttpClient` que `projects.service.ts`).
- [ ] 5.3 `frontend/src/widgets/methodology-migration-wizard/methodology-migration-wizard.component.ts`: standalone, usa `SolModalComponent` de `@shared/ui`. Paso 1 — selector de metodología destino (+ inputs de columnas si `custom`) → llama `getPreview` → tabla de mapeo editable (dropdown por estado origen con el valor propuesto por defecto; confirmar el nombre exacto del componente de select en `@solercia/ui` al implementar). Paso 2 — resumen de impacto (conteos por estado, sprints a cerrar, aviso de estimaciones que dejarán de exhibirse) + botón "Confirmar" deshabilitado mientras la petición está en curso; la ejecución solo se dispara con clic explícito, nunca automático al terminar el paso 1. Todo texto en español colombiano formal con tuteo ("verifica", "confirma"; nunca "verificá"/"confirmá").
- [ ] 5.4 `frontend/src/widgets/project-workspace/project-workspace.component.ts` (encabezado, cerca de la línea 122): agregar un botón "Cambiar metodología" que abre `MethodologyMigrationWizardComponent`. Sin ocultar el botón por rol en el cliente — mismo patrón que la UI de reparent en `pages/hierarchy/hierarchy.component.ts`: el backend aplica el 403 y el error se muestra con el manejo de errores genérico existente.
- [ ] 5.5 Build de frontend verde. Verify: `cd frontend && npm run build`

Commit 5: `feat(methodology-migration): agrega el asistente de 2 pasos para cambiar la metodología del proyecto`

## Fase 6 — Suite completa + commits convencionales (Commit 6 condicional)

- [ ] 6.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 6.2 Confirmar que `PATCH /projects/{id}` sigue rechazando `methodology` con 422 `methodology_not_editable` (regresión, delta `projects`). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_projects.py -k methodology`
- [ ] 6.3 Confirmar cero `if methodology == ...` en `methodology_migration/service.py` y `projects/service.py`. Verify: `rg "if.*methodology ==" backend/app/modules/methodology_migration backend/app/modules/projects` → sin resultados
- [ ] 6.4 Confirmar que el aislamiento cross-tenant no regresó. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_cross_tenant_isolation.py -k "methodology or migration"` (confirmar el nombre exacto del archivo con `ls backend/tests | rg cross_tenant`)
- [ ] 6.5 Build de frontend verde (repetir tras cualquier ajuste de las Fases 2-5). Verify: `cd frontend && npm run build`
- [ ] 6.6 Commit final (solo si 6.1-6.4 generaron correcciones no cubiertas por los commits 1-5; en caso contrario no aporta commit nuevo).

Commit 6 (solo si 6.6 generó cambios): `fix(metodologia): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Previsualización del plan de migración (estados origen + conteos, columnas destino, mapeo propuesto, impacto) · 2.1,2.5,2.6,2.7,2.8
- Preview rechaza migrar a la misma metodología (422 `same_methodology`) · 2.2
- Ejecución transaccional (crea destino, remapea, elimina origen, persiste metodología) · 3.1,3.2,3.10,3.12,3.13,3.14
- Subtareas se remapean por su propio estado, sin regla especial del padre · 3.3
- Validación de exhaustividad del mapeo (422 con detalle de estados faltantes) · 3.4
- Invariante — ninguna tarea en estado inválido tras migrar (D4) · 3.1,3.10,3.13
- Cierre y desvinculación de sprints activos al migrar a metodología sin sprints; sprints `closed` intactos · 3.5,3.6,3.12
- Preservación de `estimation_points`/`estimation_hours` al salir de scrum · 3.8
- Sin condicionales `if methodology == ...` en el servicio · 2.7,3.13,6.3
- Destino `custom` exige columnas definidas antes de mapear (422 si vacío) · 3.9,4.2
- Permisos (admin/manager, 403 member/viewer) y aislamiento organizacional (404) · 2.3,2.4,3.11
- Asistente de dos pasos en la configuración del proyecto, español colombiano formal · 5.1,5.2,5.3,5.4,5.5
- PATCH de proyecto sigue rechazando `methodology` (delta `projects`, regresión) · 6.2
- Cierre manual de sprint sigue funcionando sin cambios (delta `sprints`, regresión) · 6.1
- Matriz de mapeo por defecto entre las 4 metodologías · 4.1,4.3,4.4
- No regresión y commits escalonados en una sola integración · 6.1,6.2,6.3,6.4,6.5,6.6

## Risks

- **Ambigüedad D3/D4 de `design.md`** (`target.allowed_statuses()` literal vs.
  board-aware): resuelta en este documento a favor de los `status_key`
  REALMENTE persistidos en las columnas destino (ver "Notas técnicas
  adicionales"). Si el equipo prefiere otra lectura, es una decisión a validar
  antes de `apply` — cambiaría 3.13/3.12/4.1.
- **Ubicación de la UI**: no existe hoy una página de "configuración de
  proyecto"; este documento integra el asistente como botón/modal dentro de
  `project-workspace.component.ts` en vez de una ruta nueva. Confirmar si el
  equipo prefiere una ruta/tab dedicada antes de aplicar la Fase 5.
- **Componente de select exacto en `@solercia/ui`** no confirmado — la Fase 5
  debe verificar el nombre real al implementar (mismo tipo de hedge que change
  34 con `formatOriginalEstimate`).
- **Tamaño**: backend+frontend con 6 fases de TDD estricto sobre un caso de
  uso cross-aggregate (projects+boards+sprints+tasks); supera ampliamente el
  presupuesto de 400 líneas de revisión incluso sin migración de esquema —
  instrucción explícita: single-pr con commits escalonados, sin PRs
  encadenados, merge local a `preview`.
