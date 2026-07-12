# Tasks: Boards persistentes — Board/BoardColumn, board_column_id, WIP y configuración runtime

STRICT TDD: cada comportamiento nace de un test que falla (`[RED]`) antes del código que lo hace pasar (`[GREEN]`). Runner: `cd backend && pytest tests/ -v`.

## Trazabilidad de requisitos (specs delta)

| R# | Requisito | Fuente |
|----|-----------|--------|
| R1 | Siembra del board al crear el proyecto | boards.md |
| R2 | Estructura de BoardColumn | boards.md |
| R3 | Bloqueo de custom sin columnas | boards.md |
| R4 | Configuración runtime de columnas | boards.md |
| R5 | Reglas de eliminación de columnas con tareas | boards.md |
| R6 | Límite WIP al mover tareas | boards.md |
| R7 | Estado validado por metodología (PATCH deriva status de la columna) | tasks.md (delta) |
| R8 | Campo `board_column_id` en Task + default por `order` | tasks.md (delta) |
| R9 | Backfill de tareas existentes a columnas | tasks.md (delta) |
| R10 | Estados permitidos por metodología (`allowed_statuses()` custom lee columnas) | methodology-strategies.md |
| R11 | `default_columns()` sigue siendo la fuente de siembra | methodology-strategies.md |

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1800–2500 (módulo nuevo boards + 4 servicios re-cableados + migración + tests TDD) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes (aplicado como commits secuenciales, no PRs) |
| Suggested split | Batch A → B → C → D → E → Final (6 commits) |
| Delivery strategy | Commits locales directos a main (sin PR), ejecución automática |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Commit | Notes |
|------|------|--------|-------|
| A | Módulo `boards` (modelos, migración schema, seed en create_project, repo/service/router) | `feat(boards): add Board/BoardColumn models, migration and seeding` | Base para B-E |
| B | `resolve_board_strategy` + rewire 4 call sites + `create_task` board-aware | `refactor(methodology): resolve_board_strategy at all call sites` | Depende de A |
| C | `move_to_column` con `actor_id` + WIP row-lock + PATCH wiring | `feat(tasks): move_to_column with actor_id and WIP enforcement` | Depende de A, B |
| D | API de configuración de columnas (rename/reorder/add/remove) | `feat(boards): column config API with reassignment rules` | Depende de A, C (reassign reusa updated_by) |
| E | Backfill migration (snapshot verbatim) | `feat(migrations): backfill boards/columns and task.board_column_id` | Depende de A (mismo archivo de migración) |
| Final | Suite + ruff + mypy | `chore(boards): full test suite, ruff, mypy green` | Depende de A-E |

**Bloqueo de apply**: la cadena Alembic de 03 depende de `02-contrato-api` (AuditMixin, migración de auditoría). Apply de 03 NO puede iniciar hasta que 02 esté aplicado.

Batches secuenciales (comparten archivos/migración encadenada). Dentro de cada batch, tests marcados **[P]** son de archivos independientes y se escriben en paralelo; el GREEN correspondiente es siempre secuencial a su RED.

## Batch A — Módulo boards

- [x] T01 [RED] `tests/test_boards.py`: Board único por proyecto (UNIQUE project_id); BoardColumn requiere name/status_key/order; UNIQUE(board_id, status_key). (R2)
- [x] T02 [GREEN] `boards/models.py`: `Board`(Pk/Timestamp/SoftDelete/Audit, project_id FK CASCADE UNIQUE) y `BoardColumn`(board_id FK CASCADE, status_key String(60) inmutable, column_order int, wip_limit int?). (R2)
- [x] T03 [GREEN] `alembic/versions/0003_add_boards_and_board_column_id.py`: `upgrade()` crea `boards`/`board_columns` + `tasks.board_column_id` nullable (SET NULL); encadena tras head de 02. Solo schema (backfill en Batch E). (R2)
- [x] T04 [RED] Test: crear proyecto kanban persiste Board con `[Backlog,Doing,Done]` en orden y `status_key`; proyecto custom persiste Board con 0 columnas. (R1)
- [x] T05 [GREEN] `boards/repository.py`: `create_for_project`, `get_board_with_columns` (orden por `column_order, created_at`). (R1, R2)
- [x] T06 [GREEN] `boards/service.py`: `seed_board(project, strategy)` desde `strategy.default_columns()`. (R1)
- [x] T07 [GREEN] `projects/service.py:create_project` siembra el board en la misma transacción (flush proyecto → id → add board/cols → commit). (R1)
- [x] T08 [GREEN] `boards/{schemas,router}.py`: `GET /projects/{id}/board` sin paginar (conjunto anidado acotado); registrar router en `main.py`. (R2)
- [x] T09 [P][RED→GREEN] Integration: `GET board` verbatim para planner/kanban/scrum/custom tras crear proyecto. (R1, R11)

## Batch B — resolve_board_strategy + rewire

- [x] T10 [RED] `methodology/board_aware.py` unit test: `allowed_statuses()` = status_keys si no vacío, si no delega en base; flags delegan siempre. (R10)
- [x] T11 [GREEN] `board_aware.py`: `BoardAwareStrategy` + `async resolve_board_strategy(project)`. (R10)
- [x] T12 [RED] Test: custom con 0 columnas → `allowed_statuses()==[]` y creación de tarea rechazada (422 explícito). (R3, R10)
- [x] T13 [GREEN] `tasks/service.py`: eliminar `_CUSTOM_DEFAULT_STATUS` y rama permisiva de `_resolve_status`; usar `resolve_board_strategy`. (R3)
- [x] T14 [RED] Test: `create_task` sin `board_column_id` asigna la primera columna por `order` y deriva `status` de su `status_key`. (R8)
- [x] T15 [GREEN] `tasks/{service,schemas}.py`: `create_task` board-aware (default primera columna); exponer `board_column_id` en `TaskRead`. (R8)
- [x] T16 [P][RED] Regression: `dashboard._bounds_for`, `sprints.done_status`, `projects._attach_methodology_info` reflejan columnas custom renombradas (no la strategy base obsoleta). (R10)
- [x] T17 [GREEN] Rewire `dashboard/service.py`, `sprints/service.py`, `projects/service.py` de `get_strategy` crudo a `resolve_board_strategy`. (R10)
- [x] T18 [GREEN] `projects/repository.py` + `list_projects`: precarga por lotes de columnas (una query, sin N+1); test de conteo de queries. (R10)

## Batch C — move semantics

- [x] T19 [RED] Unit: conteo WIP (lock→count→escritura condicional) rechaza si `count>=wip_limit`, acepta si no, ignora `wip_limit` nulo. (R6)
- [x] T20 [GREEN] `boards/service.py:move_to_column(task, target, *, actor_id, enforce_wip=True)`: `SELECT ... FOR UPDATE` → count → 409 si excede, si no escribe `board_column_id/status` y estampa `updated_by=actor_id`; import de `Task` solo vía repo propio (nunca `tasks.service`). (R6)
- [x] T21 [RED] Integration: `PATCH /tasks/{id}/column` mueve y deriva `status`; columna inválida→422; destino no permitido por la strategy (planner→`in_review`)→rechazado. (R7)
- [x] T22 [GREEN] `tasks/router.py`: nuevo `PATCH /tasks/{id}/column` `{board_column_id}` → `actor_id=membership.user_id`. (R7)
- [x] T23 [GREEN] `tasks/service.py:update_task`: `status` en el payload mapea a columna por `status_key` y delega en el mismo `move_to_column` (un solo camino WIP). (R7)
- [x] T24 [RED] Integration: WIP en el límite rechaza el 4º movimiento (409); 2→3 se acepta; movimientos concurrentes a la misma columna serializan vía row lock (`skip_no_db`). (R6)
- [x] T25 [GREEN] Ajustes de `move_to_column` según T24; `completed_at` sigue derivando de `resolve_board_strategy(project).allowed_statuses()[-1]`. (R6)

## Batch D — configuración runtime de columnas

- [ ] T26 [RED] Test: renombrar columna conserva `status_key` y `status` de las tareas asignadas. (R4)
- [ ] T27 [GREEN] `PATCH /boards/{id}/columns/{col_id}` renombra `name` (status_key inmutable). (R4)
- [ ] T28 [RED] Test: reordenar `[A,B,C]→[C,A,B]` persiste y un GET posterior refleja el nuevo orden. (R4)
- [ ] T29 [GREEN] `PATCH /boards/{id}/columns/reorder {ordered_ids}` actualiza `column_order`. (R4)
- [ ] T30 [RED] Test: agregar columna a board custom vacío habilita creación de tareas; `status_key` = slug único por board. (R3, R4)
- [ ] T31 [GREEN] `POST /boards/{id}/columns {name, wip_limit?}`. (R4)
- [ ] T32 [RED] Test: eliminar columna vacía OK; con tareas sin destino→409/422; con destino válido reasigna (`board_column_id`+`status`, `updated_by` estampado); eliminar última columna→422. (R5)
- [ ] T33 [GREEN] `boards/service.py:reassign_column_tasks(source, target, *, actor_id)` (UPDATE masivo, bypass WIP documentado); `DELETE /boards/{id}/columns/{col_id}?target_column_id=`; guarda de última columna. (R5)

## Batch E — backfill migration

- [ ] T34 [RED] Test de migración: fixtures pre-migración (proyectos sin board, tareas con status variado) contra esquema descartable; asertar estado post-`upgrade`. (R9)
- [ ] T35 [GREEN] Extender `upgrade()` de la migración de Batch A: snapshot VERBATIM inline (planner `["Sin iniciar","En curso","Completada"]`, kanban `["Backlog","Doing","Done"]`, scrum `["To Do","In Progress","In Review","Done"]`, custom `[]`) sin importar la strategy; por proyecto crea board+columnas (custom→0); por tarea `board_column_id` = columna con `status_key` igual a `status`, si no hay match → primera columna por `order` (log de revisión); board sin columnas (custom) → NULL. (R9)
- [ ] T36 [RED] Test: tarea con `status="archived"` sin match → primera columna por `order`, caso registrado para revisión. (R9)
- [ ] T37 [GREEN] `boards/service.py`: `ensure_board` defensivo (lazy) para filas legacy entre el paso de schema y el de backfill.
- [ ] T38 [GREEN] Verificar `downgrade()` revierte `board_column_id`/`board_columns`/`boards` limpiamente.

## Final — suite + lint + types

- [ ] T39 `cd backend && pytest tests/ -v` en verde (incluye `skip_no_db`).
- [ ] T40 `ruff check`/`format` + `mypy` en `boards/`, `methodology/board_aware.py`, `tasks/*`, `projects/*`, `dashboard/*`, `sprints/*`; corregir hallazgos.
