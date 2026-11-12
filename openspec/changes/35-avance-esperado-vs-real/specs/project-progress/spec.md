# project-progress Specification

## Purpose

Calcula, para cada proyecto de la organización, el avance ESPERADO a la fecha (distribuido sobre los días laborales del calendario resuelto — cambio 28) frente al avance REAL (tareas completadas, ponderadas por horas), su desviación con semáforo configurable por empresa, la tendencia de las últimas 4 semanas (snapshots) y el corte mensual por área (`project_kind` del cambio 27). Vive en `app/modules/progress/`, reutilizando `WorkCalendarResolver`, `ProjectRepository` (árbol/`project_kind`) y `TaskRepository`, sin duplicar su lógica.

## Alcance propuesto

| Método | Ruta | Propósito |
|---|---|---|
| GET | /api/v1/progress/projects/{id} | Tarjeta consolidada (subárbol) del proyecto o área: esperado, real, desviación, semáforo, tendencia 4 semanas |
| GET | /api/v1/progress/monthly-cut?area_id=&month= | Corte mensual: proyectos del área que llegan / necesitan refuerzo / van adelantados |
| GET | /api/v1/organizations/me/progress-thresholds | Umbrales vigentes de la empresa (cualquier miembro) |
| PUT | /api/v1/organizations/me/progress-thresholds | Editar umbrales verde/amarillo (admin) |

Toda operación se acota por `organization_id` de la membresía activa del JWT (mismo patrón que `organizations/me/theme` y `work-calendar`).

## Requirements

### Requirement: Peso de cada tarea (ponderación por horas o conteo)

Para cualquier alcance (proyecto, subárbol o área), el sistema DEBE ponderar por `estimation_hours` cuando AL MENOS UNA tarea del alcance tiene horas no nulas (las tareas sin horas pesan 0 en ese alcance); si NINGUNA tarea del alcance tiene horas, DEBE ponderar por conteo (peso 1 por tarea). Las tareas `cancelled` quedan excluidas del alcance.

#### Scenario: Alcance con horas mixtas usa modo horas
- DADO un proyecto con una tarea de 10h y otra sin `estimation_hours`
- CUANDO se calcula su avance
- ENTONCES la tarea sin horas pesa 0 y la de 10h pesa 10

#### Scenario: Alcance sin ninguna hora usa conteo
- DADO un proyecto donde ninguna tarea tiene `estimation_hours`
- CUANDO se calcula su avance
- ENTONCES cada tarea pesa 1

### Requirement: % real (completadas ponderadas, rollup por subárbol y área)

El % real DEBE ser `peso completado / peso total × 100` del alcance, usando el mismo criterio de "completada" que `project-hierarchy` (último estado permitido de la metodología PROPIA de cada nodo). Para un proyecto raíz o un área (`project_kind=area`), el alcance DEBE incluir el proyecto consultado MÁS todos sus descendientes activos (rollup por subárbol), misma convención que `GET /projects/{id}/progress`. Sin tareas en el alcance, el real es "sin dato".

#### Scenario: Real ponderado por horas
- DADO un proyecto con tareas de 10h (completada) y 30h (no completada)
- CUANDO se calcula el real
- ENTONCES `real_pct = 25%` (10/40)

#### Scenario: Rollup de área suma sus proyectos hijos
- DADO un área sin tareas propias con dos proyectos hijos (20h y 40h completadas, cada uno sobre 40h de peso total)
- CUANDO se consulta la tarjeta del área
- ENTONCES `real_pct` se calcula sobre el peso agregado de ambos hijos (60/80 = 75%)

### Requirement: % esperado a la fecha (due dates sobre días laborales, fallback lineal)

Para tareas CON `due_date`, su peso completo cuenta como "esperado" desde que `due_date <= hoy`, y 0 antes. Para tareas SIN `due_date`, su peso se distribuye linealmente entre `rango_inicio` (mínimo `start_date` o `created_at` del alcance) y `rango_fin` (máximo `due_date` del alcance), contando SOLO los días cuyo ISO-weekday pertenece a `working_days` del `ResolvedCalendar` del proyecto: `peso × min(1, días_laborales(rango_inicio, hoy) / días_laborales(rango_inicio, rango_fin))`. Si ninguna tarea del alcance tiene `due_date`, el esperado es "sin dato" (no hay `rango_fin` resoluble).

#### Scenario: Esperado con calendario estándar (L-V)
- DADO un `ResolvedCalendar` de 8h L-V, `rango_inicio=2026-06-01` (lunes), una tarea de 10h con `due_date=2026-06-12` (ya vencida a "hoy"), otra de 10h con `due_date=2026-06-26` (futura) y una tercera de 20h sin `due_date`
- CUANDO se calcula el esperado a "hoy"=2026-06-12
- ENTONCES `expected_pct=50%` (10 de la vencida + 10 de la lineal [20×10/20 días laborales] + 0 de la futura, sobre 40 de peso total)

#### Scenario: Mismo caso con calendario de fin de semana (equipo 7 días)
- DADO el mismo proyecto pero con `ResolvedCalendar` de `working_days=[1..7]` (equipo con jornada de fin de semana)
- CUANDO se calcula el esperado a la misma fecha "hoy"=2026-06-12
- ENTONCES `expected_pct=48%` (la tarea lineal pesa 20×12/26 ≈ 9.23h, distinto del calendario L-V porque cambia el conteo de días laborales)

#### Scenario: Sin ninguna tarea con due_date
- DADO un proyecto donde ninguna tarea tiene `due_date`
- CUANDO se calcula el esperado
- ENTONCES la API responde `expected_pct=null` ("sin dato"), sin error

### Requirement: Desviación, semáforo y umbrales por empresa

`Organization` DEBE persistir dos columnas `Numeric` `progress_threshold_green` (default 5) y `progress_threshold_yellow` (default 15), agregadas por migración aditiva y reversible. La desviación es `expected_pct − real_pct`. Semáforo: `verde` si `desviación ≤ threshold_green`, `amarillo` si `≤ threshold_yellow`, `rojo` si `> threshold_yellow`. `GET /organizations/me/progress-thresholds` DEBE estar disponible para cualquier miembro; `PUT` DEBE restringirse a rol `admin` y validar `green < yellow`, ambos ≥0.

#### Scenario: Semáforo rojo por desviación alta
- DADO `expected_pct=70`, `real_pct=40` (desviación=30) y umbrales default (5/15)
- CUANDO se calcula el semáforo
- ENTONCES el resultado es `rojo`

#### Scenario: Proyecto adelantado sigue en verde
- DADO `expected_pct=40`, `real_pct=60` (desviación=−20)
- CUANDO se calcula el semáforo
- ENTONCES el resultado es `verde` (desviación negativa siempre ≤ threshold_green)

#### Scenario: Solo admin edita umbrales
- DADO un usuario `manager`
- CUANDO intenta `PUT /organizations/me/progress-thresholds`
- ENTONCES la petición se rechaza por autorización

#### Scenario: Validación rechaza umbrales invertidos
- DADO un admin
- CUANDO envía `green=20, yellow=10`
- ENTONCES se rechaza con error de validación (422) y no persiste

### Requirement: Tarjeta por proyecto con tendencia de 4 semanas

`GET /progress/projects/{id}` DEBE responder `expected_pct`, `real_pct`, `deviation`, `semaphore` y `trend` (hasta 4 puntos, uno por `captured_week` reciente de `project_progress_snapshot`, ordenados cronológicamente). Un job semanal del scheduler existente DEBE persistir, por proyecto (incluidas áreas, con su valor YA consolidado por subárbol), una fila `project_progress_snapshot(organization_id, project_id, captured_week, expected_pct, real_pct, deviation)`. El `real_pct` histórico DEBE reconstruirse por backfill usando `completed_at`; el `expected_pct` de semanas anteriores a la primera captura queda "sin dato" (no se reconstruye retroactivamente).

#### Scenario: Tendencia con 4 snapshots
- DADO 4 snapshots semanales consecutivos de un proyecto
- CUANDO se consulta su tarjeta
- ENTONCES `trend` trae las 4 desviaciones en orden cronológico

#### Scenario: Proyecto nuevo sin snapshots previos
- DADO un proyecto creado esta semana, sin snapshots
- CUANDO se consulta su tarjeta
- ENTONCES `trend` es una lista vacía y la tarjeta "hoy" se calcula on-demand igualmente

### Requirement: Corte mensual por área

`GET /progress/monthly-cut?area_id=&month=` DEBE clasificar cada proyecto `proyecto` del subárbol del área (a cualquier profundidad) en exactamente una categoría: `adelantado` (desviación ≤ −threshold_green), `llega` (−threshold_green < desviación ≤ threshold_green) o `necesita_refuerzo` (desviación > threshold_green). Para el mes en curso usa la tarjeta on-demand; para meses cerrados usa el snapshot semanal más cercano al cierre de ese mes.

#### Scenario: Clasificación de tres proyectos de una misma área
- DADO un área con tres proyectos de desviaciones −10, 3 y 25 (umbrales default 5/15)
- CUANDO se consulta el corte mensual del mes en curso
- ENTONCES quedan clasificados como `adelantado`, `llega` y `necesita_refuerzo` respectivamente

#### Scenario: Aislamiento de tenant en el corte
- DADO un área que pertenece a otra organización
- CUANDO un usuario de una organización distinta consulta su corte mensual
- ENTONCES la API responde 404, igual que el resto de endpoints de detalle de `projects`

### Requirement: Permisos y envelope

`GET /progress/projects/{id}` y `GET /progress/monthly-cut` DEBEN estar disponibles para cualquier miembro autenticado de la organización, con envelope `{data}`. `PUT /organizations/me/progress-thresholds` DEBE exigir rol `admin` y responder `{data, message}`. Cualquier error de validación DEBE responder `{detail, code, status}` con un `code` específico por causa.

#### Scenario: Member consulta tarjeta y corte sin restricción
- DADO un usuario `member`
- CUANDO consulta `GET /progress/projects/{id}` o `GET /progress/monthly-cut`
- ENTONCES la API responde 200 con los datos de su organización

## Limitaciones y deuda conocida

- El `expected_pct` histórico previo a los snapshots no se reconstruye (revisionista); solo el `real_pct` es reconstruible por `completed_at`.
- Sin festivos/husos horarios (deuda heredada del cambio 28).
- Burndown por sprint queda fuera de alcance (cambio 42).
- La clasificación `adelantado` del corte mensual reutiliza `threshold_green` de forma simétrica; no existe un tercer umbral configurable independiente.

## Referencias

- `openspec/changes/35-avance-esperado-vs-real/proposal.md`
- `openspec/changes/28-calendario-laboral/specs/work-calendar/spec.md` (`ResolvedCalendar`)
- `openspec/specs/project-hierarchy/spec.md` (rollup por subárbol, criterio de "completada")
- `openspec/changes/27-plantillas-idempotentes/specs/projects/spec.md` (`project_kind`)
- `backend/app/modules/dashboard/service.py` (`_build_projects_progress`, semántica de referencia previa)
