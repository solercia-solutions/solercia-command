# Delta for dashboard-executive

## ADDED Requirements

### Requirement: Cruce asignado vs. realizado en la vista ejecutiva

`GET /api/v1/dashboard/executive` MUST incluir un bloque `work_gap` con, por colaborador: horas registradas (suma de `TaskTimeLog.hours`) frente a `estimation_hours` de sus tareas asignadas, y conteo de tareas asignadas frente a tareas con actividad reciente (con `TaskHistory` o `TaskTimeLog` en los últimos N días).

#### Scenario: Horas registradas vs. estimadas por colaborador

- GIVEN un colaborador con 10 horas estimadas en sus tareas asignadas y 6 horas registradas en `TaskTimeLog`
- WHEN el jefe consulta `GET /dashboard/executive`
- THEN el bloque `work_gap` reporta para ese colaborador `hours_logged=6` y `hours_estimated=10`

#### Scenario: Tareas asignadas vs. tareas con actividad

- GIVEN un colaborador con 5 tareas asignadas activas, 3 de ellas con al menos un cambio de historial o un time-log reciente
- WHEN se consulta la vista ejecutiva
- THEN el bloque reporta `tasks_assigned=5` y `tasks_with_activity=3` para ese colaborador

### Requirement: Colaboradores sin actividad reciente

El sistema MUST identificar, dentro de `work_gap`, a los colaboradores con al menos una tarea asignada activa y CERO actividad (sin `TaskHistory` ni `TaskTimeLog`) en los últimos N días. `N` MUST tener un valor por defecto de 3 y MUST ser configurable vía el query param `?threshold_days` de `GET /dashboard/executive`.

#### Scenario: Colaborador señalado por inactividad

- GIVEN un colaborador con una tarea activa asignada y sin ningún time-log ni cambio de historial en los últimos 3 días
- WHEN el jefe consulta `GET /dashboard/executive` sin parámetros
- THEN ese colaborador aparece en la lista de "sin actividad reciente" del bloque `work_gap`

#### Scenario: Umbral configurable

- GIVEN un colaborador cuya última actividad fue hace 4 días
- WHEN se consulta `GET /dashboard/executive?threshold_days=5`
- THEN ese colaborador NO aparece en la lista de "sin actividad reciente" (4 < 5)

#### Scenario: Colaborador con actividad reciente no se marca

- GIVEN un colaborador con una tarea asignada y un time-log registrado ayer
- WHEN se consulta la vista ejecutiva con el umbral por defecto
- THEN ese colaborador NO aparece en la lista de "sin actividad reciente"
