# Delta for Tasks

> Base: `openspec/specs/tasks/spec.md`. Ninguno de los requisitos existentes
> (R1-R6, filtros, columnas) tenía un requisito formal sobre estimación —
> solo se documentaba `estimation_hours` como campo del modelo. Este delta
> AGREGA el contrato de estimación por texto y el campo calculado de
> despliegue; no reemplaza texto existente.

## ADDED Requirements

### Requirement: Estimación por texto con precedencia sobre el valor numérico

`TaskCreate`/`TaskUpdate` DEBEN aceptar un campo opcional `estimation_input`
(string, gramática `w/d/h` de la capability `estimation`), además del
`estimation_hours` numérico ya existente. Cuando ambos llegan en la misma
solicitud, `estimation_input` tiene PRECEDENCIA: su conversión (vía
`estimate_to_hours` con el `ResolvedCalendar` del proyecto) reemplaza
cualquier `estimation_hours` enviado en la misma solicitud. Un
`estimation_input` de cadena vacía DEBE limpiar la estimación
(`estimation_hours = null`). Un `estimation_input` con gramática inválida
DEBE responder `422` con un mensaje claro y no persistir ningún cambio.
Cuando solo llega `estimation_hours` numérico (sin `estimation_input`), DEBE
aceptarse tal cual, preservando la retrocompatibilidad de la API directa.

#### Scenario: Crear tarea con estimación en texto
- DADO un proyecto con calendario resuelto de 8h/día, `working_days=[1,2,3,4,5]`
- CUANDO se ejecuta `POST /projects/{id}/tasks` con `estimation_input="2d 4h"`
- ENTONCES la tarea persiste `estimation_hours=20`

#### Scenario: estimation_input manda sobre estimation_hours numérico
- DADO una solicitud que envía `estimation_input="1d"` y `estimation_hours=100` a la vez
- CUANDO se crea o actualiza la tarea
- ENTONCES el valor persistido corresponde a la conversión de `"1d"`, ignorando el `100` recibido

#### Scenario: estimation_input vacío limpia la estimación existente
- DADO una tarea con `estimation_hours=16` ya persistido
- CUANDO se ejecuta `PATCH /tasks/{id}` con `estimation_input=""`
- ENTONCES `estimation_hours` queda en `null`

#### Scenario: estimation_input inválido es rechazado
- DADO una solicitud de creación o edición de tarea
- CUANDO `estimation_input` no cumple la gramática (ej. `"3x"`, `"4h 3d"`)
- ENTONCES la API responde `422` con un mensaje claro y no persiste ningún cambio

#### Scenario: estimation_hours numérico directo sigue siendo válido
- DADO una solicitud que solo envía `estimation_hours=12` (sin `estimation_input`)
- CUANDO se crea o actualiza la tarea
- ENTONCES `estimation_hours=12` se persiste sin conversión adicional

#### Scenario: Miembro de otra organización no puede afectar una tarea ajena
- DADO una tarea que pertenece a la organización B
- CUANDO un miembro de la organización A intenta `PATCH /tasks/{id}` con `estimation_input`
- ENTONCES la API responde con el mismo comportamiento de aislamiento de tenant que el resto de endpoints de detalle de `tasks` (404), sin persistir nada

### Requirement: Campo calculado estimation_display en la lectura de tareas

`TaskRead` DEBE exponer `estimation_display`, calculado a partir de
`estimation_hours` persistido y el `ResolvedCalendar` del proyecto de la
tarea (vía `format_hours`). El cálculo NO DEBE requerir persistencia nueva
(campo transitorio, calculado en cada respuesta). Al listar varias tareas de
un mismo proyecto, el calendario DEBE resolverse UNA sola vez por respuesta
(batch en memoria), sin una consulta de calendario por fila.

#### Scenario: Detalle de tarea expone estimation_display
- DADO una tarea con `estimation_hours=26` en un proyecto con calendario de 8h/día
- CUANDO se consulta `GET /tasks/{id}`
- ENTONCES la respuesta incluye `estimation_display="3d 2h"`

#### Scenario: Listado de tareas resuelve el calendario una sola vez
- DADO un proyecto con 20 tareas con `estimation_hours` distintos
- CUANDO se consulta `GET /projects/{id}/tasks`
- ENTONCES el calendario del proyecto se resuelve una única vez para toda la respuesta, no una vez por tarea

#### Scenario: Tarea sin estimación no expone estimation_display
- DADO una tarea con `estimation_hours=null`
- CUANDO se consulta su detalle o aparece en un listado
- ENTONCES `estimation_display` es `null`, sin error

## Referencias

- `openspec/specs/tasks/spec.md` (spec base — modelo `Task`, R1-R6)
- `openspec/changes/34-estimacion-normalizada/specs/estimation/spec.md` (`estimate_to_hours`, `format_hours`, gramática, calendario)
