# Spec — Tareas (tasks)

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

## Requisitos

- **R1**: Cada tarea creada DEBE recibir `task_number` secuencial del proyecto, y `GET /tasks/by-key/{code}-{n}` DEBE resolverla.
- **R2**: `PATCH` DEBE rechazar estados no permitidos por la strategy de la metodología del proyecto.
- **R3**: El detalle de una tarea con subtareas DEBE incluir el progreso agregado de sus subtareas.
- **R4**: La lista por proyecto DEBE soportar los filtros combinables `sprint_id`, `status` y `assignee_id`.

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

## Limitaciones y deuda conocida

- NO existe `board_column_id` ni entidades Board/BoardColumn: el "tablero" es solo el status string de la strategy.
- NO existen Label/TaskLabel, TaskChecklist/ChecklistItem, TaskDependency, TaskTimeLog ni TaskHistory (previstos en CLAUDE.md).
- Sin validación Fibonacci de puntos; sin paginación en listas.
- Tests: cobertura de clave legible (test_task_key, 13) y subtareas (test_subtasks, 4); el CRUD/PATCH general y los filtros tienen CERO tests directos. Sin tests de permisos.

## Referencias

- backend/app/modules/tasks/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/methodology/ (validación de estados)
- backend/tests/test_task_key.py, backend/tests/test_subtasks.py
