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
- **R5**: `POST /api/v1/projects` DEBE aceptar un campo opcional `parent_project_id` (UUID de otro `Project`). Cuando se envía, la creación DEBE aplicar las validaciones de jerarquía definidas en `project-hierarchy` (mismo tenant, padre activo, sin ciclos, dentro de la profundidad máxima vigente) antes de persistir; si alguna falla, la creación completa DEBE rechazarse y ningún proyecto queda persistido. Cuando se omite, el proyecto se crea como raíz (`parent_project_id = null`), sin cambio respecto al contrato actual.
- **R6**: El detalle y la lista de proyectos (`GET /projects`, `GET /projects/{id}`) DEBEN exponer `parent_project_id` (`null` cuando el proyecto es raíz).

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

**R5 — Creación con padre opcional**
- Dado un usuario con membresía activa y un proyecto existente "Seguridad de la Información" en su organización
- Cuando envía `POST /projects` con `parent_project_id` apuntando a ese proyecto
- Entonces el proyecto nuevo queda creado (201) con `parent_project_id` poblado
- Y cuando envía `POST /projects` sin `parent_project_id`
- Entonces el proyecto se crea (201) con `parent_project_id = null`, igual que hoy
- Y cuando envía `POST /projects` con un `parent_project_id` de otra organización
- Entonces la API rechaza la creación completa con un error de validación y ningún proyecto queda persistido

**R6 — Exposición de jerarquía**
- Dado un proyecto hijo con padre asignado
- Cuando se consulta `GET /projects`
- Entonces el elemento correspondiente incluye `parent_project_id` con el id del padre
- Y cuando se consulta `GET /projects/{id}` para un proyecto raíz
- Entonces la respuesta incluye `parent_project_id: null`

**R7 — Responsable del proyecto**
- Dado un proyecto creado por la instanciación de una plantilla organizacional
- Cuando se consulta `GET /projects/{id}`
- Entonces la respuesta incluye `lead_user_id` con el id de la persona responsable
- Y dado un usuario que crea un proyecto vía `POST /projects` sin pasar por una plantilla
- Cuando se consulta el proyecto creado
- Entonces `lead_user_id` es `null`, sin romper el contrato actual

### Requirement: Campo project_kind en Project

`Project` DEBE tener una columna `project_kind` (enum `area | proyecto`, no nulo, default `proyecto`) agregada mediante una migración aditiva y reversible. Todo proyecto creado por `POST /projects` sin pasar por instanciación de plantilla DEBE quedar con `project_kind = proyecto`. La instanciación de plantillas (`org-role-templates`) lo asigna según la regla del nodo (contenedor con hijos = `area`, hoja = `proyecto`).

#### Scenario: Creación directa con POST /projects es siempre proyecto
- DADO un usuario con membresía activa
- CUANDO crea un proyecto vía `POST /projects` sin pasar por una plantilla
- ENTONCES el proyecto queda creado con `project_kind = proyecto`

#### Scenario: Migración es aditiva y reversible
- DADO proyectos existentes antes de la migración
- CUANDO se ejecuta `upgrade`
- ENTONCES todos quedan con `project_kind = proyecto` sin perder datos
- Y CUANDO se ejecuta `downgrade`
- ENTONCES la columna se elimina sin afectar el resto del modelo

### Requirement: Filtro opcional project_kind en el listado

`GET /projects` DEBE aceptar un parámetro de consulta opcional `project_kind` (`area` o `proyecto`); cuando se envía, la lista DEBE incluir únicamente proyectos de ese tipo dentro de la organización del solicitante; cuando se omite, el comportamiento DEBE ser idéntico al actual (todos los tipos, sin romper clientes existentes).

#### Scenario: Filtro por area devuelve solo contenedores
- DADO una organización con proyectos `area` y `proyecto` mezclados
- CUANDO consulta `GET /projects?project_kind=area`
- ENTONCES la respuesta incluye únicamente los proyectos `area`

#### Scenario: Filtro por proyecto devuelve solo trabajo real
- DADO la misma organización
- CUANDO consulta `GET /projects?project_kind=proyecto`
- ENTONCES la respuesta incluye únicamente los proyectos `proyecto`

#### Scenario: Sin parámetro el comportamiento no cambia
- DADO la misma organización
- CUANDO consulta `GET /projects` sin `project_kind`
- ENTONCES recibe todos los proyectos de la organización, igual que antes de este cambio

#### Scenario: Valor inválido de project_kind se rechaza
- DADO un usuario autenticado
- CUANDO consulta `GET /projects?project_kind=invalido`
- ENTONCES la API responde con un error de validación (422) y no ejecuta el listado

## Requisitos adicionales

- **R7**: `Project` DEBE soportar un campo opcional `lead_user_id` (referencia a `User`, `ON DELETE SET NULL`) que identifica al responsable/cabeza del proyecto. La instanciación de plantillas organizacionales (`org-role-templates`) DEBE poblarlo en TODOS los proyectos que genera. Los proyectos creados sin plantilla (flujo actual de `POST /projects`) mantienen `lead_user_id = null`.

## Limitaciones y deuda conocida

- NO hay PATCH ni DELETE de proyectos vía API (no se puede editar, archivar ni cambiar la metodología después de crear).
- NO hay gestión de miembros por proyecto (la consulta `GET /projects/{id}/members` de tasks lista miembros de la organización).
- Sin paginación en la lista.
- Velocity tiene cobertura indirecta (test_sprint_close); el CRUD de proyectos tiene CERO tests.

## Referencias

- backend/app/modules/projects/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/methodology/ (strategies consumidas al crear/validar)
