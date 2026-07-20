# Proposal: 37 · Cambio de metodología de un proyecto existente

## Intent

Hoy `methodology` es INMUTABLE: `ProjectService.update_project` rechaza con 422 `methodology_not_editable` cualquier PATCH que la incluya (`app/modules/projects/service.py:227`), porque el board sembrado y los estados de las tareas derivan de la Strategy. Un proyecto que arrancó como `planner` no puede migrar a `scrum` (ni al revés) sin recrearlo, perdiendo tareas, historial y claves. Este cambio (OLA 4, fase 4.3) habilita un asistente controlado para cambiar la metodología de un proyecto existente (planner ↔ kanban ↔ scrum ↔ custom) con mapeo explícito de estados/columnas origen → destino, transaccional, sin que ninguna tarea quede en estado inválido.

## Scope

### In Scope
- Capacidad nueva `methodology-migration`: endpoint de plan (GET preview) + endpoint de ejecución (POST confirmado), transaccional.
- Plan: estados/columnas origen (board actual), columnas requeridas del destino (`get_strategy(target).default_columns()`; para `custom` las define el usuario), mapeo propuesto por defecto (heurística por nombre/orden) y resumen de impacto (N tareas por estado, sprints a cerrar, estimaciones que dejan de exhibirse).
- Ejecución: reconstruye columnas destino, remapea `Task.status` + `board_column_id`, recalcula `completed_at` según la columna "done" del destino, cierra y desvincula sprints activos si el destino no tiene sprints, actualiza `Project.methodology`. Todo-o-nada.
- Validación de exhaustividad: todo estado origen con tareas activas debe tener destino (422 si falta).
- La Strategy destino provee `allowed_statuses()` y flags (`sprints_enabled`, `estimation_mode`, `has_backlog`) — cero `if methodology == ...` en el service.
- UI: asistente en la configuración del proyecto (2 pasos: mapeo → confirmación con impacto).
- Permisos: solo admin/manager.

### Out of Scope
- Migración masiva de varios proyectos a la vez.
- Reescribir el historial de tareas (`TaskHistory`) para reflejar estados viejos.
- Borrado de `estimation_points` al salir de scrum (se preservan, solo se ocultan).
- El `PATCH /projects/{id}` normal sigue rechazando `methodology` (la migración va por su endpoint dedicado).

## Capabilities

### New Capabilities
- `methodology-migration`: plan (preview del mapeo + impacto) y ejecución transaccional del cambio de metodología con remapeo de estados/columnas.

### Modified Capabilities
- `projects`: la metodología pasa a ser migrable vía endpoint dedicado; el PATCH normal la sigue rechazando.
- `sprints`: al migrar a una metodología sin sprints, los sprints activos se cierran y las tareas se desvinculan (`sprint_id → NULL`), con confirmación explícita.

## Approach

Endpoint dedicado, no el PATCH. `GET /projects/{id}/methodology-migration/plan?target=<m>` compara el board actual (`resolve_board_strategy`) contra `get_strategy(target)` y devuelve el mapeo propuesto más el impacto. `POST /projects/{id}/methodology-migration` recibe el mapeo confirmado y ejecuta en UNA transacción: crea columnas destino (`BoardService.add_column`), reasigna cada tarea a su columna destino (`reassign_column_tasks`, que fija status + board_column_id), recalcula `completed_at` (stamp si cae en la columna done del destino, clear si no), elimina las columnas origen, cierra y desvincula sprints si `not strategy.sprints_enabled`, y persiste `project.methodology`. Rollback total ante error. Decisiones: (1) scrum → sin-sprints cierra sprints activos y pone `sprint_id = NULL` (no destructivo, historial cerrado preservado); (2) `estimation_points`/`estimation_hours` se conservan aunque el destino no los exhiba (reversible); (3) planner/kanban → scrum: tareas sin puntos son válidas (puntos opcionales), sin bloqueo; (4) destino `custom`: el usuario define las columnas en el paso 1 antes de mapear.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/projects/*` (router/service nuevos endpoints) | New/Modified | Endpoints plan + ejecución de migración |
| `backend/app/methodology/{factory,board_aware}.py` | Reused | Strategy destino provee allowed_statuses + flags |
| `backend/app/modules/boards/service.py` | Reused | add_column/reassign_column_tasks/remove_column para reconstruir el board |
| `backend/app/modules/sprints/service.py` | Modified | Cierre + desvinculación de sprints al migrar a metodología sin sprints |
| `backend/app/modules/tasks/*` | Modified | Recalcular completed_at; status/board_column_id remapeados |
| `frontend/src/pages/projects (settings)` | New | Asistente de 2 pasos (mapeo → confirmación) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Tareas huérfanas si el mapeo es incompleto | Media | Validación de exhaustividad (422); todo estado con tareas debe mapear |
| `completed_at` inconsistente tras remapear | Media | Recalcular contra la columna done del destino en la misma transacción |
| Pérdida percibida de datos scrum (sprints/puntos) | Media | No destructivo: sprints cerrados+desvinculados, puntos preservados; confirmación con impacto |
| Destino `custom` sin columnas deja tareas sin estado | Media | El paso 1 obliga a definir ≥1 columna antes de mapear; rechazo si vacío |
| Edición concurrente de tareas durante la migración | Baja | Ejecución transaccional; validar allowed_statuses del destino al cerrar |

## Rollback Plan

Sin migración de esquema (usa columnas y tablas existentes: `board_columns`, `tasks`, `sprints`): retirar el router/endpoints de `methodology-migration` y el paso de UI restablece el comportamiento previo (el PATCH sigue bloqueando `methodology`). Cada ejecución es transaccional: un fallo revierte board, tareas y sprints al estado previo. No hay borrado de datos: `estimation_points` y sprints cerrados quedan como historial.

## Dependencies

- Ninguna en Engram (`depends_on: []`); se aplica en secuencia 35 → 36 → 37 por orden de la ola.
- Reúsa: `app/methodology/*` (Strategy + factory + board_aware), `BoardService` (add/remove/reassign de columnas), `sprints` (cierre).

## Success Criteria

- [ ] GET plan devuelve estados origen, columnas destino requeridas, mapeo propuesto e impacto (sprints/estimaciones afectadas).
- [ ] POST ejecución transaccional: toda tarea queda con `status ∈ allowed_statuses()` del destino (TDD).
- [ ] Mapeo no exhaustivo → 422; ningún estado con tareas queda sin destino.
- [ ] Migración a metodología sin sprints cierra + desvincula sprints activos con confirmación; puntos preservados.
- [ ] Rollback transaccional ante error; permisos admin/manager; scoping por organización intacto.
- [ ] Cero `if methodology == ...` en el service; la información viene de la Strategy.

## Proposal question round

Supuestos a validar con el usuario: (1) endpoint dedicado de migración, NO reutilizar el PATCH (que sigue bloqueando `methodology`); (2) sprints al pasar a metodología sin sprints se CIERRAN y las tareas se DESVINCULAN (`sprint_id = NULL`), no se borran, con confirmación explícita; (3) `estimation_points`/`estimation_hours` se PRESERVAN al salir de scrum (solo se ocultan por estrategia), reversible; (4) destino `custom` exige definir columnas en el paso 1 antes de mapear; (5) mapeo por defecto heurístico por nombre/orden, editable por el usuario; (6) sin migración de esquema Alembic (reúsa `board_columns`/`tasks`/`sprints`). Segunda ronda disponible si se quiere revisar la política de sprints (cerrar vs. mantener abiertos desvinculados) o el manejo de subtareas al remapear.
