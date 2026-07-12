# Design: Boards persistentes — Board/BoardColumn, board_column_id, WIP y configuración runtime

## Technical Approach

Módulo nuevo `backend/app/modules/boards/` (router → service → repository → models) que persiste el tablero por proyecto y lo siembra desde `strategy.default_columns()`. `Task` gana `board_column_id` (FK nullable). La clave del diseño es un **wrapper `BoardAwareStrategy`**: envuelve la strategy base y sobreescribe `default_columns()`/`allowed_statuses()` con los `status_key` de las columnas persistidas, delegando las flags (`sprints_enabled`, `estimation_mode`, `has_backlog`, `name`) en la base. Así el servicio sigue llamando `strategy.allowed_statuses()` como hoy (contrato SÍNCRONO intacto: el read async de columnas ocurre ANTES, en el repo) y NO aparece ningún `if methodology ==`. El tratamiento es uniforme para todas las metodologías; `custom` deja de ser un caso especial: solo es un board sin columnas hasta configurarse. Endpoints y migración siguen el contrato de `02` (`{data, meta}`, auditoría explícita, Alembic aditivo encadenado).

## Architecture Decisions

### D1 — Regla de oro para `custom` (fuente de `allowed_statuses`)
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `BoardAwareStrategy` envuelve la base con los `status_key` persistidos; delega flags | Un read async previo; interfaz única en todo el servicio | **Elegida** |
| Rama `if methodology == custom` que lee columnas | Rompe la regla de oro | Rechazada |
| Métodos de strategy async con acceso a BD | Contamina la strategy con I/O; cambia el contrato sync | Rechazada |

**Rationale**: las columnas persistidas pasan a ser la verdad en runtime para TODAS las metodologías (permite renombrar sin que la lista estática quede obsoleta). La strategy base queda como semilla + flags. La resolución se hace SIEMPRE vía el helper único `resolve_board_strategy(project)` (el repository carga las columnas de forma async → construye `BoardAwareStrategy(get_strategy(project.methodology), status_keys)` de forma sync); ningún consumidor de runtime llama `get_strategy` crudo (ver Correcciones de gate, C1).

### D2 — Modelo de datos
`Board` **1:1** con `Project` (`project_id` UNIQUE, FK CASCADE); mixins Pk/Timestamp/SoftDelete/Audit; alcance de tenant transitivo vía `project` (igual que `Task`, sin `TenantMixin`). `BoardColumn`: `board_id` (FK CASCADE, index), `name` (mutable), `status_key` String(60) **inmutable** (= valor que adopta `Task.status` al entrar), `column_order` int (nombre no reservado, patrón `task_order`), `wip_limit` int nullable. Constraint **UNIQUE(board_id, status_key)**. `order` NO es único en BD (reordenar sin swaps costosos; se ordena por `column_order, created_at`, igual que `Task.order`).

### D3 — Semántica de movimiento (columna = fuente de `status`)
Método único de servicio `move_to_column(task, target, *, actor_id: uuid.UUID | None, enforce_wip=True)` que fija `task.board_column_id` y `task.status = target.status_key` de forma atómica y estampa `updated_by = actor_id` (regla vinculante de `02`: todo UPDATE sobre filas auditadas estampa `updated_by`). Lo consumen DOS entradas: (a) endpoint dedicado `PATCH /tasks/{id}/column` `{board_column_id}` (canónico, `enforce_wip=True`); (b) `PATCH /tasks/{id}` con `status`: el servicio mapea el string a la columna por `status_key` y delega en el mismo método (mantiene sincronía para el frontend congelado). WIP en un solo camino. `completed_at` sigue derivándose del último status permitido.
**Concurrencia WIP**: dentro de la transacción se hace `SELECT BoardColumn ... WHERE id=target FOR UPDATE`, luego se cuentan las tareas activas en la columna destino y solo entonces se escribe; si `count >= wip_limit` → **409 Conflict**. Columna/estado inválido → **422**. Este patrón NO es análogo 1:1 a `allocate_task_number` (que es un statement único atómico `UPDATE ... RETURNING`): aquí son tres pasos — lock de fila de la columna → count → escritura condicional — correctos en Postgres porque el row lock serializa a los escritores concurrentes sobre la misma columna destino.

### D4 — Backfill (migración, determinista)
Migración Alembic aditiva: crea `boards`/`board_columns`, agrega `tasks.board_column_id` nullable, y siembra en tiempo de migración (elegido sobre lazy por previsibilidad). El mapa metodología→columnas se **inlinea** en la migración (snapshot de `default_columns()`), no se importa la strategy, para reproducibilidad. Snapshot VERBATIM a usar en la migración — cualquier deriva de transcripción (tildes, espacios, mayúsculas) enrutaría tareas al fallback en silencio: planner `["Sin iniciar", "En curso", "Completada"]`, kanban `["Backlog", "Doing", "Done"]`, scrum `["To Do", "In Progress", "In Review", "Done"]`, custom `[]`. Por cada proyecto: board + columnas (`custom` → board sin columnas). Por cada tarea: `board_column_id` = columna cuyo `status_key == task.status`; sin match → primera columna del board; board sin columnas (`custom`) → NULL y `status` intacto. Un `ensure_board` defensivo (lazy) cubre filas legacy sin board.

### D5 — Quitar/renombrar columnas con tareas
`status_key` INMUTABLE ⇒ **renombrar** (`name`) y **reordenar** siempre permitidos, sin tocar tareas. **Agregar**: `status_key` derivado del `name` (slug único por board), congelado al crear. **Quitar**: sin tareas activas → soft-delete; con tareas → exige `target_column_id` y reasigna; la reasignación masiva NO valida WIP (bypass intencional documentado, sin locking cruzado de columnas) y estampa `updated_by = actor_id` en todas las filas afectadas (regla vinculante de `02` para UPDATEs masivos sobre filas auditadas); sin destino → **409**. No se puede quitar la ÚLTIMA columna → **422** (dejaría tareas sin estado).

### D6 — Encadenamiento Alembic
`down_revision` = head tras la migración de auditoría de `02`. El orden exacto se resuelve en apply (03 `depends_on` 02, cadena lineal).

## Data Flow

    create_project → strategy.default_columns() → seed Board+Columns (mismo txn: flush project → id → add board/cols → commit)
    PATCH /tasks/{id}/column ─┐
    PATCH /tasks/{id}{status} ─┴→ move_to_column → [SELECT col FOR UPDATE → count activas vs wip_limit] → task.status = col.status_key
    validación status ← resolve_board_strategy(project).allowed_statuses()
    # mismo helper en los CUATRO sitios: tasks (create/move), dashboard._bounds_for,
    # sprints (done_status burndown/cierre), projects._attach_methodology_info

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/boards/{models,schemas,repository,service,router}.py`, `__init__.py` | Create | Módulo completo: seed, config CRUD columnas, `move_to_column` con lock WIP |
| `backend/app/methodology/board_aware.py` | Create | `BoardAwareStrategy` + helper único `resolve_board_strategy(project)` (repo carga columnas async → construye el wrapper sync) |
| `backend/app/modules/tasks/models.py` | Modify | `board_column_id` FK nullable (`SET NULL`) |
| `backend/app/modules/tasks/{service,schemas}.py` | Modify | Delegar status↔columna en board service; re-cablear `create_task` a la resolución board-aware (sin columna explícita → primera por `order`; cero columnas → 422); ELIMINAR `_CUSTOM_DEFAULT_STATUS` y la rama permisiva de `_resolve_status`; exponer `board_column_id` en `TaskRead` |
| `backend/app/modules/projects/service.py` | Modify | Sembrar board en `create_project`; `_attach_methodology_info` (línea 133, GET /projects) usa `resolve_board_strategy`; `list_projects` precarga columnas por lotes (una query para todos los boards del listado, sin N+1) |
| `backend/app/modules/dashboard/service.py` | Modify | `_bounds_for` (línea 314, cota "done" de la vista ejecutiva) usa `resolve_board_strategy(project)` en lugar de `get_strategy` crudo |
| `backend/app/modules/sprints/service.py` | Modify | `done_status` del burndown/cierre (líneas 131-139) usa `resolve_board_strategy(project)` en lugar de `get_strategy` crudo |
| `backend/app/main.py` | Modify | Registrar router de boards |
| `backend/alembic/versions/xxxx_add_boards_and_board_column_id.py` | Create | Tablas + `board_column_id` + backfill |

## Interfaces / Contracts

```python
class BoardAwareStrategy(MethodologyStrategy):
    def __init__(self, base: MethodologyStrategy, status_keys: list[str]): ...
    def allowed_statuses(self) -> list[str]: return list(self._status_keys) or self._base.allowed_statuses()
    # sprints_enabled / estimation_mode / has_backlog / name → delega en base

async def resolve_board_strategy(project) -> BoardAwareStrategy
# Helper ÚNICO de resolución: el repository carga las columnas del board (async)
# → construye BoardAwareStrategy (sync). Usado en LOS CUATRO sitios:
# tasks (create/move), dashboard._bounds_for, sprints.done_status, projects._attach_methodology_info.

async def move_to_column(task, target_column, *, actor_id: uuid.UUID | None, enforce_wip=True) -> Task
# SELECT ... FOR UPDATE; 409 si excede WIP; estampa updated_by = actor_id

async def reassign_column_tasks(source_column, target_column, *, actor_id: uuid.UUID | None) -> int
# delete de columna: UPDATE masivo SIN validación WIP (bypass documentado); estampa updated_by = actor_id
```

## Testing Strategy (TDD estricto)

| Layer | What | How |
|-------|------|-----|
| Unit | overlay del wrapper; `status_key` inmutable; lógica de conteo WIP | pytest sin BD |
| Integration | seed por metodología (incl. `custom` vacío); mover deriva `status`; columna inválida→422; WIP→409; concurrencia con FOR UPDATE; add/rename/reorder; quitar con tareas (reasigna) / última→422; `custom` end-to-end; backfill status→columna + fallback | httpx AsyncClient + fixtures de 01 |

## Migration / Rollout

Una revisión Alembic encadenada tras `02`. Rollback: `downgrade` elimina `board_column_id` y `board_columns`/`boards`; `Task` vuelve a operar solo con `status`. Reversible por pieza.

## Correcciones de gate (2026-07-11) — VINCULANTE para tasks/apply

Un gate adversarial confirmó 3 hallazgos CRITICAL y 3 WARNING contra la versión anterior de este design. Las correcciones siguientes son vinculantes para las fases tasks y apply, prevalecen sobre cualquier pasaje que las contradiga, y sus ajustes inline ya están aplicados en D1, D3, D4, D5, Data Flow, File Changes e Interfaces.

### C1 (CRITICAL) — Call sites de `get_strategy` no cubiertos

El design solo re-cableaba el service de tasks, pero `get_strategy(project.methodology)` se llama crudo en TRES sitios más que quedarían leyendo datos viejos tras reconfigurar columnas: `dashboard/service.py:314` (`_bounds_for`, cota "done" de la vista ejecutiva), `sprints/service.py:131-139` (`done_status` del burndown/cierre) y `projects/service.py:133` (`_attach_methodology_info`, GET /projects). **Corrección**: helper único `resolve_board_strategy(project)` (el repository carga las columnas de forma async → construye `BoardAwareStrategy` de forma sync) usado en LOS CUATRO sitios. Para `list_projects` se exige precarga por lotes de columnas: una sola query para todos los boards del listado, nunca N+1. Los tres archivos quedaron añadidos a File Changes.

### C2 (CRITICAL) — Bloqueo duro en lugar de fallback permisivo

`tasks/service.py` tiene `_CUSTOM_DEFAULT_STATUS = "todo"` y una rama permisiva en `_resolve_status` cuando `allowed_statuses()` está vacío (acepta status libre o asigna "todo"), lo que contradice el requisito de la spec «custom sin columnas → rechazo explícito de creación y movimiento». **Corrección vinculante**: (a) esa rama permisiva y `_CUSTOM_DEFAULT_STATUS` SE ELIMINAN — board con cero columnas → error 422 explícito tanto en create como en move; (b) `create_task` se re-cablea por la misma resolución board-aware que los PATCH: tarea nueva sin `board_column_id` explícito → primera columna por `order` (como fija la spec de tasks), y con cero columnas → rechazo.

### C3 (CRITICAL) — Contrato de `02` afirmado pero no operacionalizado

(a) `actor_id: uuid.UUID | None` se enhebra en `move_to_column(...)` y en el método de reasignación masiva del delete de columna (`reassign_column_tasks`): regla vinculante de `02`, todo UPDATE masivo sobre filas auditadas estampa `updated_by`. Firmas actualizadas en Interfaces. (b) **Exención documentada del contrato de paginación de `02`**: este cambio no introduce listados sin acotar — las columnas de un board son un conjunto acotado anidado en el GET del board, por lo que se devuelven completas, sin paginación. Esta exención se declara explícita aquí para que la afirmación «sigue el contrato de 02» sea verificable.

### C4 (WARNING) — Dirección de imports entre boards y tasks

Patrón vinculante: el módulo `boards` accede a `Task` solo vía su propio repository (el import a nivel de módulo de `models` está permitido), NUNCA vía `tasks.service`. Si `tasks` necesita `boards`, usa import diferido dentro del método — patrón ya existente en `tasks/service.py:453` con `SprintRepository`.

### C5 (WARNING) — Encuadre del patrón WIP

El patrón de concurrencia NO es análogo 1:1 a `allocate_task_number` (statement único atómico `UPDATE ... RETURNING`); es lock de fila de columna → count → escritura condicional, correcto en Postgres por la serialización que impone el row lock. Además, la reasignación masiva del delete de columna NO valida WIP: bypass intencional documentado, sin locking cruzado de columnas. D3 y D5 quedaron corregidos en ese sentido.

### C6 (WARNING) — Snapshot literal del backfill

Las listas de la migración se reproducen VERBATIM en D4: planner `["Sin iniciar", "En curso", "Completada"]`, kanban `["Backlog", "Doing", "Done"]`, scrum `["To Do", "In Progress", "In Review", "Done"]`, custom `[]`. Cualquier deriva de transcripción (tildes, espacios, mayúsculas) enrutaría tareas al fallback en silencio.

## Open Questions

- [ ] Divergencia `name` (display) vs `status_key` tras renombrar: aceptable para MVP (frontend congelado, sin UI de board). Confirmar en spec.
- [ ] Atomicidad seed-en-create: se prefiere flush+commit único; el `ensure_board` lazy cubre el borde. Confirmar en tasks.
