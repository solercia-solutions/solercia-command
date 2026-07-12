# Spec — Proyectos (projects)

> **Origen**: línea base as-built (2026-07-11)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Gestión de proyectos por organización. Cada proyecto declara su metodología al crearse (Strategy pattern) y lleva un prefijo `code` con el que se generan las claves legibles de sus tareas (ej. `SDM-7`).

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/projects | Lista de proyectos de la organización |
| POST | /api/v1/projects | Crea proyecto (201) |
| GET | /api/v1/projects/{id} | Detalle |
| GET | /api/v1/projects/{id}/velocity | Puntos completados por sprint, promedio y proyección |

Modelo `Project` (Pk + Timestamp + SoftDelete + Tenant):

| Campo | Descripción |
|-------|-------------|
| name, description | Identificación |
| methodology | Enum: planner \| kanban \| scrum \| custom |
| status | Estado del proyecto |
| code | Prefijo corto para claves de tarea (ej. SDM) |
| task_counter | Secuencia por proyecto para numerar tareas |

## Requisitos

- **R1**: Todo proyecto DEBE crearse con una metodología válida; el comportamiento (columnas, estados, sprints, estimación) se DEBE leer desde la strategy, nunca con condicionales por metodología.
- **R2**: El `code` del proyecto DEBE alimentar la clave legible de sus tareas mediante `task_counter` secuencial.
- **R3**: `GET /{id}/velocity` DEBE calcular los puntos completados por sprint cerrado, su promedio y una proyección.
- **R4**: Las consultas DEBEN filtrar por `organization_id` de la membresía activa.

### Escenarios centrales

**R1 — Creación con metodología**
- Dado un usuario con membresía activa
- Cuando envía `POST /projects` con `methodology: "scrum"`
- Entonces el proyecto queda creado (201) y sus tareas validan estados contra la estrategia scrum.

**R3 — Velocity**
- Dado un proyecto con sprints cerrados que suman puntos completados
- Cuando llama `GET /projects/{id}/velocity`
- Entonces recibe los puntos por sprint, el promedio y la proyección.

**R4 — Aislamiento**
- Dado proyectos de dos organizaciones distintas
- Cuando un miembro de la organización A lista `/projects`
- Entonces no ve proyectos de la organización B.

## Limitaciones y deuda conocida

- NO hay PATCH ni DELETE de proyectos vía API (no se puede editar, archivar ni cambiar la metodología después de crear).
- NO hay gestión de miembros por proyecto (la consulta `GET /projects/{id}/members` de tasks lista miembros de la organización).
- Sin paginación en la lista.
- Velocity tiene cobertura indirecta (test_sprint_close); el CRUD de proyectos tiene CERO tests.

## Referencias

- backend/app/modules/projects/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/methodology/ (strategies consumidas al crear/validar)
