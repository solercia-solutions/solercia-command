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

## Batches: 6 commits secuenciales

### Batch A — Módulo boards
- [x] Modelos Board/BoardColumn con constraints
- [x] Migración Alembic schema-only (0003)
- [x] Seed en create_project
- [x] Repository GET board con columnas ordenadas
- [x] Endpoints GET /projects/{id}/board

### Batch B — resolve_board_strategy + rewire 4 call sites
- [x] BoardAwareStrategy wrapper para custom
- [x] Helper resolve_board_strategy en tasks, dashboard, sprints, projects
- [x] Eliminación _CUSTOM_DEFAULT_STATUS y rama permisiva
- [x] Bloqueo 422 en custom sin columnas

### Batch C — move_to_column con WIP
- [x] move_to_column(task, target, actor_id, enforce_wip)
- [x] SELECT...FOR UPDATE → count → 409 si excede
- [x] PATCH /tasks/{id}/column nuevo endpoint
- [x] PATCH /tasks/{id} con status delegando al mismo método

### Batch D — API config runtime
- [x] PATCH rename columna (status_key inmutable)
- [x] PATCH reorder columnas
- [x] POST add columna con status_key slug
- [x] DELETE columna con reglas (vacía OK, con tareas exige destino, última→422)

### Batch E — backfill migration
- [x] Extender migración 0003: snapshot VERBATIM
- [x] Por proyecto: board + columnas
- [x] Por tarea: board_column_id=columna con status_key==status, sino primera, sino NULL
- [x] ensure_board lazy defensivo

### Final
- [x] Suite 179/179 passed
- [x] ruff check clean
- [x] mypy app clean

## Bloqueo de apply
Cadena Alembic de 03 depende de `02-contrato-api` (AuditMixin, migración auditoría). Apply de 03 NO puede iniciar hasta que 02 esté aplicado.

**Status**: 40/40 tasks completadas.
