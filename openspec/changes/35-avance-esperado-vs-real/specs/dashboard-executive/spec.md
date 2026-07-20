# Delta for dashboard-executive

## MODIFIED Requirements

### Requirement: Progreso por proyecto en la vista ejecutiva (enriquecido con esperado/real/semáforo)

`GET /api/v1/dashboard/executive` DEBE reportar la carga por persona (`workload`) y el progreso por proyecto (`projects_progress`) con totales. Cada entrada de `projects_progress` DEBE incluir, además del `percent_done` existente (conteo simple), los campos de la capability `project-progress`: `expected_pct`, `real_pct`, `deviation` y `semaphore` (verde/amarillo/rojo) del proyecto raíz del alcance. `percent_done` se conserva sin cambios para no romper consumidores existentes.
(Previously: `projects_progress` solo reportaba `total`, `done`, `in_progress` y `percent_done` por conteo simple, sin esperado ni semáforo.)

#### Scenario: Estado del equipo (sin cambio)

- GIVEN tareas en curso asignadas a varios miembros
- WHEN el jefe llama `GET /dashboard/executive`
- THEN `by_assignee` agrupa las tareas activas por persona

#### Scenario: Tarjeta enriquecida con semáforo

- GIVEN un proyecto con `expected_pct=70`, `real_pct=40` calculados por `project-progress`
- WHEN el jefe consulta `GET /dashboard/executive`
- THEN la entrada de ese proyecto en `projects_progress` incluye `deviation=30` y `semaphore="rojo"` junto al `percent_done` existente

#### Scenario: percent_done existente no cambia

- GIVEN un proyecto con 8 de 10 tareas completadas por conteo
- WHEN se consulta la vista ejecutiva
- THEN `percent_done=80` se mantiene igual que antes de este cambio, además de los campos nuevos

## Referencias

- `openspec/specs/dashboard-executive/spec.md` (línea base)
- `openspec/changes/35-avance-esperado-vs-real/proposal.md`
- `openspec/changes/35-avance-esperado-vs-real/specs/project-progress/spec.md`
