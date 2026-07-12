# Delta for tasks

## MODIFIED Requirements

### Requirement: Estado validado por metodología

`PATCH` DEBE derivar el `status` de la tarea desde el `status_key` de la `BoardColumn` destino (`board_column_id`) cuando el movimiento se realiza entre columnas del board del proyecto. El `status` resultante DEBE pertenecer a `allowed_statuses()` de la strategy de la metodología del proyecto; un movimiento hacia una columna cuyo `status_key` no esté permitido DEBE rechazarse.
(Previously: `PATCH` aceptaba un campo `status` libre validado directamente contra `allowed_statuses()`, sin relación con ninguna entidad de columna persistida porque no existían `Board`/`BoardColumn`.)

#### Scenario: Movimiento válido actualiza status desde la columna

- DADO una tarea de un proyecto kanban asignada a la columna `Backlog` (`status_key = backlog`)
- CUANDO se hace `PATCH` moviéndola a la columna `Doing` (`status_key = doing`)
- ENTONCES `board_column_id` pasa a apuntar a `Doing` y `status` pasa a `doing`

#### Scenario: Movimiento a estado no permitido por la strategy

- DADO una tarea de un proyecto planner
- CUANDO se intenta mover la tarea a una columna cuyo `status_key` es `in_review` (no permitido por planner)
- ENTONCES la API rechaza el movimiento

## ADDED Requirements

### Requirement: Campo board_column_id

`Task` DEBE tener un campo `board_column_id` (FK nulable a `BoardColumn`). Toda tarea creada en un proyecto cuyo board tenga al menos una columna DEBE quedar asignada a una columna: la indicada explícitamente en la solicitud de creación, o —si no se indica ninguna— la primera columna del board por `order`, fijando `status` desde su `status_key`.

#### Scenario: Asignación a columna por defecto al crear

- DADO un proyecto kanban cuyo board tiene columnas `[Backlog, Doing, Done]` en ese orden
- CUANDO se crea una tarea sin especificar columna
- ENTONCES la tarea se asigna a la columna `Backlog` (primera por `order`) y `status = backlog`

### Requirement: Backfill de tareas existentes a columnas por status

Al aplicar la migración de este cambio, toda tarea existente DEBE quedar asignada a la `BoardColumn` sembrada cuyo `status_key` coincida con su `status` actual. Si ningún `status_key` sembrado coincide con el `status` de una tarea, esa tarea DEBE asignarse a la primera columna del board por `order` (columna de fallback) y el caso DEBE quedar registrado para revisión posterior.

#### Scenario: Backfill con coincidencia directa

- DADO una tarea existente con `status = "done"` en un proyecto kanban cuyo board sembrado tiene una columna con `status_key = "done"`
- CUANDO corre la migración de backfill
- ENTONCES la tarea queda con `board_column_id` apuntando a esa columna

#### Scenario: Backfill con status sin columna coincidente

- DADO una tarea existente con `status = "archived"` que no coincide con ningún `status_key` de las columnas sembradas del proyecto
- CUANDO corre la migración de backfill
- ENTONCES la tarea se asigna a la primera columna del board por `order` y el caso se registra para revisión
