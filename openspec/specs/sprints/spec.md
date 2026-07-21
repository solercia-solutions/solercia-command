# Spec — Sprints (sprints)

> **Origen**: línea base as-built (2026-07-11), delta merge 29-sprint-borrador (2026-07-20)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código. Delta 29-sprint-borrador: añade creación en estado borrador, autonombre, transición draft→active, y endpoint de sugerencia de nombre.

## Propósito

Sprints por proyecto (metodologías con `sprints_enabled`): creación con flexibilidad de fechas (borrador → activo), autonombre sugerido, edición, burndown ideal vs real y cierre con acumulación de puntos completados y devolución de tareas incompletas al backlog.

## Alcance (con cambio 29)

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET/POST | /api/v1/projects/{id}/sprints | Lista y creación (nombre opcional, nace `draft` sin fechas o `active` con ambas) |
| GET | /api/v1/projects/{id}/sprints/suggested-name | Autonombre sugerido para el próximo sprint (no persiste) |
| GET | /api/v1/projects/{id}/sprints/{sid}/burndown | Burndown ideal vs real (unidad: puntos o tareas) |
| PATCH | /api/v1/sprints/{id} | Edición (incluye "Añadir fechas") |
| POST | /api/v1/sprints/{id}/start | Transición `draft → active` (valida fechas presentes) |
| POST | /api/v1/sprints/{id}/close | Cierre del sprint (409 si ya está cerrado) |

Modelo `Sprint` (Pk + Timestamp + SoftDelete):

| Campo | Descripción |
|-------|-------------|
| project_id, name, goal? | Identificación |
| start_date?, end_date? | Ventana temporal (ambas null en `draft`, obligatorias en `active`) |
| status | draft \| active \| closed |
| completed_points, closed_at? | Resultado del cierre (null hasta `closed`) |

## Requisitos

### Baseline (as-built, cambio 25)

- **R1**: El cierre DEBE sumar los puntos de las tareas completadas en `completed_points`, mover las tareas incompletas al backlog (`sprint_id = null`) y sellar `closed_at`.
- **R2**: Cerrar un sprint ya cerrado DEBE responder 409.
- **R3**: El burndown DEBE contrastar la línea ideal contra el avance real, en puntos o en número de tareas según la unidad.
- **R4**: Los sprints DEBEN pertenecer a proyectos cuya metodología tenga `sprints_enabled` (scrum).

### Cambio 29 — Creación en borrador sin fechas

- **R5**: `POST /projects/{id}/sprints` DEBE aceptar `name` vacío u omitido y usar el autonombre calculado en ese caso; el sprint nace `draft` sin fechas. Sigue exigiendo `sprints_enabled` (422 si no aplica).

#### Escenario: Con o sin nombre; metodología no habilitada rechaza
- Dado un proyecto con `sprints_enabled` (o sin)
- Cuando se crea un sprint con nombre, sin nombre, o sobre metodología no habilitada
- Entonces nace `draft` con el nombre o el autonombre (si nombre omitido/vacío); o responde 422 `sprints_not_enabled` si la metodología no lo permite.

### Cambio 29 — Autonombre sugerido del próximo sprint

- **R6**: `GET /projects/{id}/sprints/suggested-name` DEBE sugerir (sin persistir) el nombre del siguiente sprint según el último por `created_at`; es sugerencia editable, una colisión de nombre NO bloquea (sin unicidad).

**Reglas de autonombre:**

| Último sprint | Autonombre sugerido |
|---|---|
| Termina en número (`PANDORA 2026-1`) | Incrementa la última corrida (mismo separador) → `PANDORA 2026-2` |
| Sin número final (`Sprint Kickoff`) | Sufija ` 2` → `Sprint Kickoff 2` |
| Sin previo, `code` presente | `<CODE> Sprint 1` |
| Sin previo, `code` nulo | `Sprint 1` |

#### Escenario: Consecutivo con separador y año
- Dado el último sprint "PANDORA 2026-1"
- Cuando se pide el autonombre
- Entonces sugiere "PANDORA 2026-2"

### Cambio 29 — Inicio de sprint exige fechas presentes

- **R7**: `POST /sprints/{id}/start` DEBE transicionar `draft → active` solo con ambas fechas presentes; si falta alguna, responde 422 `sprint_missing_dates` (mensaje español: "El sprint necesita fecha de inicio y fin antes de iniciarse."). Ya `active` o `closed` responde 409/422. La misma validación aplica si se fija `status=active` por `PATCH` directo.

#### Escenario: Sin fechas no inicia; con fechas sí
- Dado un sprint `draft` sin fechas (o solo una)
- Cuando se llama `POST /sprints/{id}/start` o `PATCH /sprints/{id}` con `status=active`
- Entonces responde 422 `sprint_missing_dates` (español) y el sprint sigue `draft`; con ambas fechas sí transiciona a `active`.

### Cambio 29 — Permisos y aislamiento de tenant

- **R8**: `/sprints/{id}/start` y `/projects/{id}/sprints/suggested-name` DEBEN exigir autenticación y membresía del proyecto, con el mismo modelo que el resto del módulo `sprints` (cualquier rol; sin restricción nueva). Otra organización responde 404; sin token, 401.

#### Escenario: Happy path, sin auth y tenant ajeno
- Dado un `member` con su sprint `draft` con fechas, una solicitud sin token, y un sprint ajeno
- Cuando inicia el propio, repite sin token, y consulta el ajeno
- Entonces el propio pasa a `active`; sin token responde 401; el ajeno responde 404.

### Cambio 29 — UI del flujo de sprint borrador

- **R9**: La UI DEBE ofrecer "Crear sprint" liviano (solo nombre, autonombre precargado editable, sin fechas); un `draft` DEBE mostrar "Borrador" y acciones "Añadir fechas" e "Iniciar sprint" (deshabilitado sin ambas fechas).

#### Escenario: Creación liviana e inicio condicionado
- Dado el modal "Crear sprint" y un `draft` sin ambas fechas
- Cuando se confirma solo el nombre (o vacío, usa autonombre), y luego se revisa la fila
- Entonces se crea sin pedir fechas; "Iniciar sprint" queda deshabilitado hasta completar ambas fechas.

### Cambio 29 — No regresión sobre sprints existentes

- **R10**: Sprints previos (`active`/`closed`) DEBEN seguir listándose, editándose, cerrándose y calculando burndown/velocity sin cambios; sin migración. La suite de tests DEBE permanecer en verde.

#### Escenario: Suite en verde con sprints previos intactos
- Dado sprints previos `active`/`closed`
- Cuando se agrega `draft`, autonombre y `/start`
- Entonces la suite sigue en verde; sprints previos no cambian.

### Escenarios centrales — Baseline

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
- Cambio 29: no se introduce unicidad de nombres de sprint (colisiones editable).
- Cobertura baseline: test_sprint_close (8 tests); cambio 29 agrega 30 tests (test_sprint_naming, test_sprint_draft_creation, test_sprint_start, test_sprint_suggested_name).

## Referencias

- backend/app/modules/sprints/ (router.py, service.py, repository.py, models.py, schemas.py, naming.py desde 29)
- backend/tests/test_sprint_close.py
- backend/tests/test_sprint_naming.py (cambio 29)
- backend/tests/test_sprint_draft_creation.py (cambio 29)
- backend/tests/test_sprint_start.py (cambio 29)
- backend/tests/test_sprint_suggested_name.py (cambio 29)
- openspec/changes/29-sprint-borrador/ (proposal, design, tasks)
