# Spec — Estrategias de metodología (methodology-strategies)

> **Origen**: línea base as-built (2026-07-11) + cambio [03-boards-persistentes](../../changes/archive/2026-07-11-03-boards-persistentes/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Strategy pattern que define el comportamiento de cada metodología de proyecto (columnas por defecto, estados permitidos, sprints, modo de estimación, backlog). La API y la UI leen el comportamiento DESDE la strategy; regla de oro: metodología nueva = clase nueva, cero condicionales dispersos.

## Alcance as-built

Contrato `MethodologyStrategy` (ABC): `default_columns()`, `allowed_statuses()`, `sprints_enabled`, `estimation_mode`, `has_backlog`, `to_info()`. `factory.get_strategy(name)` responde 422 ante metodología inválida.

| Strategy | Columnas por defecto | Sprints | Estimación | Backlog |
|----------|----------------------|---------|------------|---------|
| planner | Sin iniciar / En curso / Completada | No | none | No |
| kanban | Backlog / Doing / Done | No | horas | No |
| scrum | To Do / In Progress / In Review / Done | Sí | puntos | Sí |
| custom | [] (vacías) | — | — | — |

Las columnas son listas EFÍMERAS de strings devueltas por la strategy; no existe entidad persistida Board/BoardColumn ni `wip_limit`.

## Requisitos

- **R1**: `Task.status` DEBE validarse contra `allowed_statuses()` de la strategy del proyecto; un estado fuera de la lista DEBE rechazarse.
- **R2**: La factory DEBE responder 422 ante una metodología desconocida.
- **R3**: Las operaciones de sprint DEBEN estar disponibles solo si `sprints_enabled` es verdadero para la metodología del proyecto.
- **R4**: `to_info()` DEBE exponer el contrato completo de la metodología para que el frontend lo consuma sin lógica condicional propia.

### Escenarios centrales

**R1 — Validación de estado**
- Dado un proyecto con metodología planner
- Cuando se intenta mover una tarea al estado `in_review`
- Entonces la operación es rechazada (estado no permitido por la strategy).

**R2 — Metodología inválida**
- Dado una petición de creación de proyecto con `methodology: "xp"`
- Cuando la factory resuelve la strategy
- Entonces la API responde 422.

**R3 — Sprints por metodología**
- Dado un proyecto kanban
- Cuando se intenta crear un sprint
- Entonces la operación es rechazada porque `sprints_enabled` es falso.

### MODIFIED Requirements (03-boards-persistentes)

#### Requirement: Estados permitidos por metodología

`Task.status` DEBE validarse contra `allowed_statuses()` de la strategy del proyecto; un estado fuera de la lista DEBE rechazarse. Para las metodologías planner, kanban y scrum, `allowed_statuses()` DEBE seguir derivándose del conjunto fijo definido por cada strategy, sin cambios de comportamiento. Para la metodología custom, `allowed_statuses()` DEBE derivarse dinámicamente de los `status_key` de las `BoardColumn` persistidas del proyecto (la strategy delega en el board persistido); la strategy custom NUNCA DEBE hardcodear un conjunto de estados propio ni introducir condicionales `if methodology == ...` para resolverlo.
(Previously: `allowed_statuses()` de custom devolvía siempre una lista vacía fija, sin relación con ningún dato persistido, porque no existía `Board`/`BoardColumn`.)

**Scenario: Validación de estado en metodología fija (sin cambios)**
- DADO un proyecto con metodología planner
- CUANDO se intenta mover una tarea al estado `in_review`
- ENTONCES la operación es rechazada (estado no permitido por la strategy).

**Scenario: allowed_statuses() de custom lee las columnas persistidas**
- DADO un proyecto custom cuyo board tiene columnas con `status_key` `todo` y `doing`
- CUANDO se consulta `allowed_statuses()` de la strategy custom del proyecto
- ENTONCES devuelve exactamente `["todo", "doing"]`, leídos desde las columnas persistidas

**Scenario: allowed_statuses() de custom vacío bloquea el proyecto**
- DADO un proyecto custom cuyo board no tiene columnas
- CUANDO se consulta `allowed_statuses()`
- ENTONCES devuelve una lista vacía y la creación/movimiento de tareas del proyecto queda bloqueada (ver boards.md)

### ADDED Requirements (03-boards-persistentes)

#### Requirement: default_columns() sigue siendo la fuente de siembra para metodologías fijas

Para planner, kanban y scrum, `default_columns()` DEBE seguir siendo el mecanismo de origen de las columnas sembradas al crear el proyecto, sin cambios en su valor de retorno. custom DEBE seguir retornando `[]` desde `default_columns()` (el board nace vacío); la diferencia introducida por este cambio es que ese resultado ahora se PERSISTE como cero `BoardColumn`, en lugar de descartarse como lista efímera.

**Scenario: default_columns() persiste columnas al crear el proyecto**
- DADO un proyecto nuevo con metodología scrum
- CUANDO se crea el proyecto
- ENTONCES `default_columns()` retorna `["To Do", "In Progress", "In Review", "Done"]` y esas 4 columnas quedan persistidas en el board

## Limitaciones y deuda conocida

- Boards y columnas persistidas (introducidas en 03-boards-persistentes); custom ahora usable vía API de configuración runtime.
- Sin validación Fibonacci de `estimation_points` en scrum.
- CERO tests de las estrategias y de la factory.

## Referencias

- backend/app/methodology/ (base.py, factory.py, planner.py, kanban.py, scrum.py, custom.py)
- backend/app/modules/tasks/service.py (validación de estados vía strategy)
- docs/METHODOLOGY-FEATURES.md (desactualizado respecto al código)
