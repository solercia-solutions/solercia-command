# Spec — Tareas (tasks)

> **Origen**: línea base as-built (2026-07-11) + cambio [03-boards-persistentes](../../changes/archive/2026-07-11-03-boards-persistentes/) + cambio [10-busqueda-global](../../changes/archive/2026-07-12-10-busqueda-global/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Núcleo del producto: tareas por proyecto con clave legible (`SDM-7`), subtareas, asignación, estimación dual (puntos/horas), estados validados por la metodología del proyecto y marcado de riesgo.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/projects/{id}/members | Miembros asignables |
| GET | /api/v1/projects/{id}/tasks | Lista con filtros sprint_id / status / assignee_id |
| POST | /api/v1/projects/{id}/tasks | Crea tarea (201); admite parent_task_id |
| GET | /api/v1/tasks/by-key/{key} | Busca por clave legible (ej. SDM-7) |
| GET | /api/v1/tasks/{id} | Detalle + progreso de subtareas |
| PATCH | /api/v1/tasks/{id} | Mover estado, reasignar, estimar, riesgo, orden, sprint |
| DELETE | /api/v1/tasks/{id} | Borrado suave (204) |
| GET | /api/v1/tasks/{id}/subtasks | Subtareas de una tarea |

Modelo `Task` (Pk + Timestamp + SoftDelete; scope de tenant vía join a Project):

| Campo | Descripción |
|-------|-------------|
| project_id, sprint_id?, parent_task_id? | Relaciones (sprint null = backlog) |
| title, description, task_type, priority | Contenido y clasificación |
| status | String validado por la strategy de metodología (NO enum fijo) |
| assignee_id? | Asignado |
| estimation_points?, estimation_hours? (Decimal) | Estimación dual |
| due_date?, start_date?, completed_at? | Fechas |
| order, risk_flag, risk_reason?, task_number? | Orden, riesgo y numeración por proyecto |
| labels[] | Etiquetas asignadas (vía TaskLabel) |
| checklist_progress | Progreso agregado de checklists (done/total) |
| is_blocked | Booleano indicando bloqueo activo |
| blockers[] | Tareas que bloquean a esta tarea |

## Requisitos

- **R1**: Cada tarea creada DEBE recibir `task_number` secuencial del proyecto, y `GET /tasks/by-key/{code}-{n}` DEBE resolverla.
- **R2**: `PATCH` DEBE rechazar estados no permitidos por la strategy de la metodología del proyecto.
- **R3**: El detalle de una tarea con subtareas DEBE incluir el progreso agregado de sus subtareas.
- **R4**: La lista por proyecto DEBE soportar los filtros combinables `sprint_id`, `status` y `assignee_id`.
- **R5** (03-boards-persistentes): `Task` DEBE tener campo `board_column_id` (FK nullable a BoardColumn); al crear, asignación por defecto a primera columna por order; al mover, status derivado de status_key de la columna destino.
- **R6** (03-boards-persistentes): Backfill al aplicar migración: tarea existente → columna con status_key coincidente, si no → primera columna por order.

### Escenarios centrales

**R1 — Clave legible**
- Dado un proyecto con `code = "SDM"` y 6 tareas
- Cuando se crea una tarea nueva
- Entonces obtiene la clave `SDM-7` y `GET /tasks/by-key/SDM-7` la devuelve.

**R2 — Estado validado por metodología**
- Dado una tarea de un proyecto planner
- Cuando se envía `PATCH` con un estado ajeno a la estrategia (ej. `in_review`)
- Entonces la API rechaza el cambio.

**R3 — Progreso de subtareas**
- Dado una tarea padre con 4 subtareas, 2 completadas
- Cuando se consulta `GET /tasks/{id}`
- Entonces el detalle reporta el progreso 2/4.

### MODIFIED Requirements (03-boards-persistentes)

#### Requirement: Estado validado por metodología

`PATCH` DEBE derivar el `status` de la tarea desde el `status_key` de la `BoardColumn` destino (`board_column_id`) cuando el movimiento se realiza entre columnas del board del proyecto. El `status` resultante DEBE pertenecer a `allowed_statuses()` de la strategy de la metodología del proyecto; un movimiento hacia una columna cuyo `status_key` no esté permitido DEBE rechazarse.
(Previously: `PATCH` aceptaba un campo `status` libre validado directamente contra `allowed_statuses()`, sin relación con ninguna entidad de columna persistida porque no existían `Board`/`BoardColumn`.)

**Scenario: Movimiento válido actualiza status desde la columna**
- DADO una tarea de un proyecto kanban asignada a la columna `Backlog` (`status_key = backlog`)
- CUANDO se hace `PATCH` moviéndola a la columna `Doing` (`status_key = doing`)
- ENTONCES `board_column_id` pasa a apuntar a `Doing` y `status` pasa a `doing`

**Scenario: Movimiento a estado no permitido por la strategy**
- DADO una tarea de un proyecto planner
- CUANDO se intenta mover la tarea a una columna cuyo `status_key` es `in_review` (no permitido por planner)
- ENTONCES la API rechaza el movimiento

### ADDED Requirements (03-boards-persistentes)

#### Requirement: Campo board_column_id

`Task` DEBE tener un campo `board_column_id` (FK nulable a `BoardColumn`). Toda tarea creada en un proyecto cuyo board tenga al menos una columna DEBE quedar asignada a una columna: la indicada explícitamente en la solicitud de creación, o —si no se indica ninguna— la primera columna del board por `order`, fijando `status` desde su `status_key`.

**Scenario: Asignación a columna por defecto al crear**
- DADO un proyecto kanban cuyo board tiene columnas `[Backlog, Doing, Done]` en ese orden
- CUANDO se crea una tarea sin especificar columna
- ENTONCES la tarea se asigna a la columna `Backlog` (primera por `order`) y `status = backlog`

#### Requirement: Backfill de tareas existentes a columnas por status

Al aplicar la migración de este cambio, toda tarea existente DEBE quedar asignada a la `BoardColumn` sembrada cuyo `status_key` coincida con su `status` actual. Si ningún `status_key` sembrado coincide con el `status` de una tarea, esa tarea DEBE asignarse a la primera columna del board por `order` (columna de fallback) y el caso DEBE quedar registrado para revisión posterior.

**Scenario: Backfill con coincidencia directa**
- DADO una tarea existente con `status = "done"` en un proyecto kanban cuyo board sembrado tiene una columna con `status_key = "done"`
- CUANDO corre la migración de backfill
- ENTONCES la tarea queda con `board_column_id` apuntando a esa columna

**Scenario: Backfill con status sin columna coincidente**
- DADO una tarea existente con `status = "archived"` que no coincide con ningún `status_key` de las columnas sembradas del proyecto
- CUANDO corre la migración de backfill
- ENTONCES la tarea se asigna a la primera columna del board por `order` y el caso se registra para revisión

### MODIFIED Requirements (10-busqueda-global)

#### Requirement: Filtros combinables en la lista de tareas por proyecto

`GET /projects/{id}/tasks` DEBE aceptar, en cualquier combinación simultánea, los filtros `status`, `priority`, `assignee_id`, `sprint_id`, `label_id` (uno o más valores, unión entre etiquetas), `due_from`/`due_to` (rango sobre `due_date`) y `q` (texto libre sobre `title`/`description`). El endpoint DEBE mantener la paginación estándar `?page&size&sort&order` con `meta{page, size, total}` (02-contrato-api).

(Previously: solo aceptaba `sprint_id`, `status`, `assignee_id` y `label_id` de valor único, sin `priority`, sin rango de fechas y sin texto libre.)

**Scenario: Combinación simultánea de filtros**
- DADO un proyecto con tareas de distinta prioridad, asignado y etiqueta
- CUANDO se consulta `GET /projects/{id}/tasks?status=in_progress&priority=high&assignee_id={u}&label_id={l}&due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas que cumplen TODOS los criterios a la vez

**Scenario: label_id acepta múltiples valores**
- DADO tareas del proyecto etiquetadas con "Urgente" o con "Backend" (sin solapamiento)
- CUANDO se consulta `GET /projects/{id}/tasks?label_id={urgente}&label_id={backend}`
- ENTONCES se devuelven las tareas que tienen cualquiera de las dos etiquetas

**Scenario: Filtro de texto sobre título y descripción**
- DADO dos tareas del proyecto, una con "migrar base de datos" en el título y otra sin relación
- CUANDO se consulta `GET /projects/{id}/tasks?q=migrar`
- ENTONCES solo se devuelve la tarea cuyo título o descripción contiene "migrar"

**Scenario: Filtro de rango de fechas de vencimiento**
- DADO tareas del proyecto con `due_date` en junio y en julio
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas con `due_date` dentro de julio

### ADDED Requirements (10-busqueda-global)

#### Requirement: Validación de filtros inválidos en la lista de tareas

El sistema DEBE responder `422` cuando `status` o `priority` no pertenecen al catálogo permitido, o cuando `due_from` es posterior a `due_to`; NO PUEDE ignorar silenciosamente un filtro inválido ni devolver una colección vacía como si fuera un resultado válido.

**Scenario: Prioridad fuera de catálogo rechazada**
- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?priority=urgentísima`
- ENTONCES la API responde `422`

**Scenario: Rango de fechas invertido rechazado**
- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-31&due_to=2026-07-01`
- ENTONCES la API responde `422`

## Limitaciones y deuda conocida

- Boards y columnas persistidas (introducidas en 03-boards-persistentes); board_column_id en Task es nullable para compatibilidad con custom sin columnas.
- Existen Label/TaskLabel (04-labels-checklists-dependencias), TaskChecklist/ChecklistItem (04-labels-checklists-dependencias), TaskDependency (04-labels-checklists-dependencias).
- TaskTimeLog y TaskHistory implementados en 05-trabajo-realizado (registros de tiempo y changelog automático).
- Estado `cancelled` en Task aún no implementado; requiere enriquecimiento en desbloqueo de TaskDependency (deuda trazada en 04).
- Sin validación Fibonacci de puntos; sin paginación en listas.
- Tests: cobertura de clave legible (test_task_key, 13) y subtareas (test_subtasks, 4); el CRUD/PATCH general y los filtros tienen CERO tests directos. Sin tests de permisos.
- (SUGGESTION 04-verify) Formalizar tabla TDD Cycle Evidence en apply-progress para batches futuros (mejora de proceso, no defecto).
- (SUGGESTION 04-verify) Desbloqueo al completar tarea bloqueante requiere criterio preciso: completado (completed_at NOT NULL) vs. estado=done, comportamiento futuro a definir con UX.

## Referencias

- backend/app/modules/tasks/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/methodology/ (validación de estados)
- backend/tests/test_task_key.py, backend/tests/test_subtasks.py
