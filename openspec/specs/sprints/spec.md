# Spec — Sprints (sprints)

> **Origen**: línea base as-built (2026-07-11)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Sprints por proyecto (metodologías con `sprints_enabled`): creación, edición, burndown ideal vs real y cierre con acumulación de puntos completados y devolución de tareas incompletas al backlog.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET/POST | /api/v1/projects/{id}/sprints | Lista y creación |
| GET | /api/v1/projects/{id}/sprints/{sid}/burndown | Burndown ideal vs real (unidad: puntos o tareas) |
| PATCH | /api/v1/sprints/{id} | Edición |
| POST | /api/v1/sprints/{id}/close | Cierre del sprint (409 si ya está cerrado) |

Modelo `Sprint` (Pk + Timestamp + SoftDelete):

| Campo | Descripción |
|-------|-------------|
| project_id, name, goal? | Identificación |
| start_date?, end_date? | Ventana temporal |
| status | active \| closed |
| completed_points, closed_at? | Resultado del cierre |

## Requisitos

- **R1**: El cierre DEBE sumar los puntos de las tareas completadas en `completed_points`, mover las tareas incompletas al backlog (`sprint_id = null`) y sellar `closed_at`.
- **R2**: Cerrar un sprint ya cerrado DEBE responder 409.
- **R3**: El burndown DEBE contrastar la línea ideal contra el avance real, en puntos o en número de tareas según la unidad.
- **R4**: Los sprints DEBEN pertenecer a proyectos cuya metodología tenga `sprints_enabled` (scrum).

### Escenarios centrales

**R1 — Cierre de sprint**
- Dado un sprint activo con tareas completadas (8 puntos) y tareas pendientes
- Cuando se llama `POST /sprints/{id}/close`
- Entonces `completed_points = 8`, las incompletas quedan en backlog y el sprint pasa a `closed`.

**R2 — Cierre idempotente rechazado**
- Dado un sprint ya cerrado
- Cuando se vuelve a llamar `POST /sprints/{id}/close`
- Entonces la API responde 409.

**R3 — Burndown**
- Dado un sprint con fechas definidas y avance parcial
- Cuando se consulta el burndown
- Entonces devuelve las series ideal y real por día en la unidad solicitada.

## Limitaciones y deuda conocida

- No hay validación de solapamiento de sprints ni límite de sprints activos simultáneos.
- Sin paginación en la lista.
- Cobertura: test_sprint_close (8 tests: cierre + velocity). Creación, edición y burndown sin tests directos.

## Referencias

- backend/app/modules/sprints/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/tests/test_sprint_close.py
