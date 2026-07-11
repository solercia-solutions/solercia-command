# Spec — Estrategias de metodología (methodology-strategies)

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

## Limitaciones y deuda conocida

- La metodología `custom` es INUTILIZABLE: devuelve columnas vacías y no existe API para configurarlas en runtime.
- No hay entidad Board/BoardColumn persistida ni límites WIP (kanban incompleto frente al CLAUDE.md).
- Sin validación Fibonacci de `estimation_points` en scrum.
- CERO tests de las estrategias y de la factory.

## Referencias

- backend/app/methodology/ (base.py, factory.py, planner.py, kanban.py, scrum.py, custom.py)
- backend/app/modules/tasks/service.py (validación de estados vía strategy)
- docs/METHODOLOGY-FEATURES.md (desactualizado respecto al código)
