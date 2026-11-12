# Delta for sprints

## ADDED Requirements

### Requirement: Cierre masivo de sprints activos al migrar el proyecto a una metodología sin sprints

Cuando `methodology-migration` migra un proyecto hacia una metodología con
`sprints_enabled = false`, el sistema DEBE cerrar TODO sprint en estado
`active` del proyecto dentro de la misma transacción de la migración, con el
mismo efecto que el cierre manual (R1 de esta capacidad): acumular
`completed_points` de las tareas completadas y sellar `closed_at`. Las
tareas que quedan incompletas en esos sprints DEBEN desvincularse
(`sprint_id = NULL`). Los sprints ya `closed` antes de la migración NO se
modifican.
(Previously: no existía ningún disparador de cierre de sprint fuera de
`POST /sprints/{id}/close` manual.)

#### Scenario: Cierre manual sigue funcionando sin cambios

- DADO un sprint activo con tareas completadas e incompletas
- CUANDO se llama `POST /sprints/{id}/close`
- ENTONCES `completed_points` se sella, las incompletas quedan en backlog y
  el sprint pasa a `closed`, igual que antes de este cambio

#### Scenario: Migración a metodología sin sprints cierra los sprints activos del proyecto

- DADO un proyecto scrum con un sprint activo con tareas completadas e
  incompletas
- CUANDO se ejecuta la migración hacia `planner`
- ENTONCES el sprint activo queda `closed` con `completed_points` sellado, y
  las tareas incompletas de ese sprint quedan con `sprint_id = NULL`

#### Scenario: Sprints ya cerrados no se tocan durante la migración

- DADO un proyecto scrum con un sprint `closed` histórico y un sprint
  `active`
- CUANDO se ejecuta la migración hacia `kanban`
- ENTONCES el sprint `closed` conserva sus datos (`completed_points`,
  `closed_at`) sin cambios

## Referencias

- `openspec/specs/sprints/spec.md` (línea base, R1: cierre manual)
- `openspec/changes/37-cambio-metodologia/proposal.md`
- `openspec/changes/37-cambio-metodologia/specs/methodology-migration/spec.md`
