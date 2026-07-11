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

## Limitaciones y deuda conocida

- NO existe el cruce "trabajo asignado vs realizado" (capacidad transversal clave del producto): no hay TaskTimeLog ni ActivityLog que lo alimenten.
- La carga (`workload`) se mide solo por conteo de tareas activas; no hay noción de capacidad por persona.
- Sin alertas embebidas en la respuesta (el frontend combina con `/notifications`).
- CERO tests del módulo.

## Referencias

- backend/app/modules/dashboard/ (router.py, service.py, schemas.py)
- backend/app/modules/tasks/, backend/app/modules/sprints/ (fuentes de datos)
