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

## Correcciones de gate (2026-07-11) — VINCULANTE para tasks/apply

Confirma 3 hallazgos CRITICAL y 3 WARNING. Las correcciones son vinculantes para las fases tasks y apply.

### C1 (CRITICAL) — Call sites de `get_strategy` no cubiertos
**Corrección**: helper único `resolve_board_strategy(project)` usado en LOS CUATRO sitios: tasks (create/move), dashboard._bounds_for, sprints.done_status, projects._attach_methodology_info. Para `list_projects` se exige precarga por lotes de columnas: una sola query para todos los boards del listado, nunca N+1.

### C2 (CRITICAL) — Bloqueo duro en lugar de fallback permisivo
**Corrección vinculante**: (a) `_CUSTOM_DEFAULT_STATUS` y la rama permisiva de `_resolve_status` SE ELIMINAN — board con cero columnas → error 422 explícito; (b) `create_task` se re-cablea por la misma resolución board-aware que los PATCH.

### C3 (CRITICAL) — Contrato de `02` afirmado pero no operacionalizado
(a) `actor_id: uuid.UUID | None` se enhebra en `move_to_column(...)` y en `reassign_column_tasks`. (b) **Exención documentada del contrato de paginación de `02`**: las columnas de un board son un conjunto acotado anidado, se devuelven completas.

### C4 (WARNING) — Dirección de imports entre boards y tasks
Patrón vinculante: el módulo `boards` accede a `Task` solo vía su propio repository, NUNCA vía `tasks.service`. Si `tasks` necesita `boards`, usa import diferido dentro del método.

### C5 (WARNING) — Encuadre del patrón WIP
El patrón de concurrencia NO es análogo 1:1 a `allocate_task_number`; es lock de fila de columna → count → escritura condicional. La reasignación masiva del delete de columna NO valida WIP: bypass intencional documentado.

### C6 (WARNING) — Snapshot literal del backfill
Las listas de la migración se reproducen VERBATIM: planner `["Sin iniciar", "En curso", "Completada"]`, kanban `["Backlog", "Doing", "Done"]`, scrum `["To Do", "In Progress", "In Review", "Done"]`, custom `[]`. Cualquier deriva de transcripción enrutaría tareas al fallback en silencio.
