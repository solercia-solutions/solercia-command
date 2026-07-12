# Spec — Vista ejecutiva (dashboard-executive)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Dashboard para jefes en UNA pantalla: quién hace qué, qué está en riesgo, carga de trabajo y progreso de proyectos, más un tablero de desempeño por colaborador.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/dashboard/executive | by_assignee, at_risk, workload, projects_progress, totals |
| GET | /api/v1/dashboard/performance | completed_tasks/points, active_count, overdue_count, on_time_rate por colaborador; `sprint_id` opcional |

El módulo es solo service (sin modelos propios): agrega datos de tasks, sprints y projects de la organización del usuario.

## Requisitos

- **R1**: `executive` DEBE agrupar las tareas en curso por assignee (`by_assignee`) para responder "¿en qué anda cada persona?".
- **R2**: `executive` DEBE listar en `at_risk` las tareas marcadas con `risk_flag` o próximas a vencer sin completar.
- **R3**: `executive` DEBE reportar la carga por persona (`workload`) y el progreso por proyecto (`projects_progress`) con totales.
- **R4**: `performance` DEBE calcular por colaborador: tareas/puntos completados, activas, vencidas y tasa de cumplimiento a tiempo (`on_time_rate`), con filtro opcional por sprint.

### Escenarios centrales

**R1 — Estado del equipo**
- Dado tareas en curso asignadas a varios miembros
- Cuando el jefe llama `GET /dashboard/executive`
- Entonces `by_assignee` agrupa las tareas activas por persona.

**R2 — Panel de riesgo**
- Dado una tarea con `risk_flag = true` y otra que vence pronto sin completarse
- Cuando se consulta la vista ejecutiva
- Entonces ambas aparecen en `at_risk`.

**R4 — Desempeño por sprint**
- Dado un sprint con tareas completadas dentro y fuera de plazo
- Cuando se llama `GET /dashboard/performance?sprint_id=...`
- Entonces cada colaborador reporta sus métricas y su `on_time_rate` limitadas a ese sprint.

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

## Limitaciones y deuda conocida

- Bloque `work_gap` implementado en 05-trabajo-realizado (requiere TaskTimeLog y TaskHistory).
- La carga (`workload`) se mide solo por conteo de tareas activas; no hay noción de capacidad por persona.
- Sin alertas embebidas en la respuesta (el frontend combina con `/notifications`).
- Nota de entorno: tests del módulo dashboard requieren elevación temporal a rol `manager` vía SQL (dev seed sin manager membership en el contexto de pruebas).

## Referencias

- backend/app/modules/dashboard/ (router.py, service.py, schemas.py)
- backend/app/modules/tasks/, backend/app/modules/sprints/ (fuentes de datos)
