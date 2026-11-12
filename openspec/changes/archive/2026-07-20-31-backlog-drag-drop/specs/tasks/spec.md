# Delta for Tasks

## Alcance propuesto (delta)

| Método | Ruta | Cambio |
|---|---|---|
| PATCH | /tasks/{id} | Al asignar `sprint_id`, rechaza con `422` si el sprint destino tiene `status = closed`; `draft` y `active` se aceptan sin restricción adicional en el servidor |
| POST | /tasks/reorder | **(Reconciliación de diseño)** Endpoint nuevo: mueve `task_id` a `sprint_id` (o `null` = Backlog) y reindexa `order` de `ordered_task_ids` del contenedor destino en una sola transacción; aplica el mismo guard de `closed` que el PATCH |

Nota: única regla dura server-side de este cambio. Las reglas más finas del
arrastre (p. ej. sprint↔sprint solo entre `draft`) se enforcen en la UI
(cambio 31, capability `frontend-backlog-dnd`); el servidor las permite si no
involucran un sprint `closed`. Separación de responsabilidades: **servidor =
integridad** (nunca mover hacia/desde un sprint cerrado), **UI = flujo
guiado** (reglas más finas de destino). El guard aplica a cualquier
consumidor del endpoint (arrastre, el menú "Mover a…" o el modal existente de
"mover a sprint"), sin cambio de contrato para `draft`/`active`.

## ADDED Requirements

### Requirement: Guard de integridad al asignar sprint_id en PATCH

`PATCH /tasks/{id}` DEBE rechazar con `422` y un mensaje claro en español la
asignación de `sprint_id` cuando el sprint destino tiene `status = closed`.
Cuando el destino es `draft` o `active`, el servidor DEBE aceptar la
asignación sin exigir que origen y destino compartan estado. El servidor NO
DEBE validar el estado del sprint de origen; esta es la única validación de
destino a nivel de API.

#### Scenario: Mover a un sprint draft se acepta

- DADO una tarea en el Backlog y un sprint del mismo proyecto en `draft`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <draft> }`
- ENTONCES la API responde `200` y la tarea queda asignada al sprint

#### Scenario: Mover a un sprint active se acepta

- DADO una tarea en un sprint `draft` y otro sprint del proyecto en `active`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <active> }`
- ENTONCES la API responde `200` y la tarea queda asignada al sprint `active`

#### Scenario: Mover hacia un sprint closed se rechaza

- DADO una tarea en el Backlog y un sprint del mismo proyecto en `closed`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <closed> }`
- ENTONCES la API responde `422` con un mensaje que indica que el sprint destino está cerrado, y la tarea conserva su `sprint_id` anterior

#### Scenario: Permisos existentes de PATCH sin cambio

- DADO un usuario `member` de la organización y un sprint `draft` del mismo proyecto
- CUANDO hace `PATCH /tasks/{id}` asignando ese sprint
- ENTONCES aplican los mismos permisos vigentes (autenticación + membresía), sin restricción nueva de rol

#### Scenario: Aislamiento de organización se mantiene

- DADO un `sprint_id` que pertenece a un proyecto de otra organización
- CUANDO se hace `PATCH /tasks/{id}` asignando ese `sprint_id`
- ENTONCES la API responde `422` con `code=invalid_sprint` (sprint no encontrado en el org/proyecto del solicitante), sin relación con el nuevo guard de `closed`

> Nota de reconciliación (verify, 31-backlog-drag-drop): este escenario
> describía originalmente `404`. `_verify_sprint` (comportamiento
> preexistente, sin cambios en este alcance) responde `422 invalid_sprint`
> para cualquier `sprint_id` que no exista en el org/proyecto del
> solicitante, sin distinguir "no existe" de "pertenece a otra
> organización" — el mismo código que ya cubre un `sprint_id` inexistente.
> El efecto protector es idéntico (nunca se reasigna un sprint ajeno);
> se corrige aquí el código de estado documentado para reflejar el
> comportamiento real, verificado por
> `test_patch_task_sprint_guard_respects_permissions_and_org_isolation`
> (`backend/tests/test_task_sprint_closed_guard.py`). Diferenciar 404 de
> 422 en `_verify_sprint` queda fuera de alcance de este cambio.

### Requirement: Reordenamiento transaccional vía `POST /tasks/reorder`

**(Reconciliación de diseño)** `POST /tasks/reorder` DEBE mover una tarea a
un `sprint_id` destino (o `null` para el Backlog) y reindexar el campo
`order` de todas las tareas del contenedor destino según el arreglo
`ordered_task_ids` recibido, en una única transacción (`task_id: UUID`,
`sprint_id: UUID | null`, `ordered_task_ids: list[UUID]`). El servidor DEBE
aplicar el mismo guard de integridad que el requisito anterior: rechaza con
`422` (`code=sprint_closed`) si el sprint destino tiene `status = closed`.
El campo `order` NO DEBE generar entradas de `TaskHistory` (no forma parte de
`_HISTORY_TRACKED_FIELDS`); solo un cambio efectivo de `sprint_id` genera una
fila de historial, igual que en `update_task`. Una tarea que no pertenece a
la organización del solicitante (aislamiento de tenant) DEBE responder `404`,
sin ejecutar ninguna reasignación.

#### Scenario: Mover a una posición arbitraria reindexa a los hermanos

- DADO un sprint destino `draft` con tres tareas en orden `[A, B, C]` (`order` 0,1,2) y una tarea `D` en el Backlog
- CUANDO se hace `POST /tasks/reorder` con `{ task_id: D, sprint_id: <destino>, ordered_task_ids: [A, D, B, C] }`
- ENTONCES la API responde `200`, `D.sprint_id` queda asignado al destino, y el `order` de `A, D, B, C` queda `0, 1, 2, 3` respectivamente, todo en una sola transacción

#### Scenario: Mover hacia un sprint destino closed se rechaza

- DADO una tarea en el Backlog y un sprint del mismo proyecto en `closed`
- CUANDO se hace `POST /tasks/reorder` con `{ task_id, sprint_id: <closed>, ordered_task_ids: [...] }`
- ENTONCES la API responde `422` con código `sprint_closed`, y la tarea conserva su `sprint_id` y `order` anteriores sin reindexar a nadie

#### Scenario: Tarea de otra organización se rechaza

- DADO un `task_id` que pertenece a un proyecto de una organización distinta a la del solicitante
- CUANDO se hace `POST /tasks/reorder` con ese `task_id`
- ENTONCES la API responde `404` (tarea no encontrada en el tenant), sin ejecutar ninguna reasignación de `sprint_id` ni de `order`

#### Scenario: Permisos existentes de `tasks` sin cambio

- DADO un usuario `member` de la organización y un sprint `draft` del mismo proyecto
- CUANDO hace `POST /tasks/reorder` moviendo una tarea a ese sprint
- ENTONCES aplican los mismos permisos vigentes del módulo (autenticación + membresía), sin restricción nueva de rol

## Referencias

- `openspec/changes/31-backlog-drag-drop/proposal.md`
- `openspec/changes/31-backlog-drag-drop/design.md` (D1, D3 — `reorder_tasks`, `_verify_sprint(reject_closed=...)`)
- `openspec/specs/tasks/spec.md` (línea base); `backend/app/modules/tasks/service.py` (`_verify_sprint`, `update_task`)
- `openspec/changes/31-backlog-drag-drop/specs/frontend-backlog-dnd/spec.md` (consumidor UI de este guard y del endpoint `reorder`)
