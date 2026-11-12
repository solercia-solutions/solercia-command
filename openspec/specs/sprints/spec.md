# Spec — Sprints (sprints)

> **Origen**: línea base as-built (2026-07-11), delta merge 29-sprint-borrador (2026-07-20), delta merge 30-backlog-sprints-agrupados (2026-07-20)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código. Delta 29-sprint-borrador: añade creación en estado borrador, autonombre, transición draft→active, y endpoint de sugerencia de nombre. Delta 30-backlog-sprints-agrupados: enriquece la lista de sprints con agregados por sprint (conteo/suma) y del backlog; UI del backlog reorganizada con secciones colapsables por sprint.

## Propósito

Sprints por proyecto (metodologías con `sprints_enabled`): creación con flexibilidad de fechas (borrador → activo), autonombre sugerido, edición, burndown ideal vs real y cierre con acumulación de puntos completados y devolución de tareas incompletas al backlog. Desde el cambio 30: pestaña Backlog reorganizada con sprints como secciones colapsables (cada una mostrando conteo de historias y suma de horas estimadas del servidor) + sección Backlog de tareas sin sprint.

## Alcance (con cambio 29 y 30)

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET/POST | /api/v1/projects/{id}/sprints | Lista (desde 30: incluye `story_count`, `estimation_hours_sum` por sprint y `meta.backlog` con agregados) y creación (nombre opcional, nace `draft` sin fechas o `active` con ambas) |
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

### Cambio 30 — Agregados por sprint y por Backlog en la lista

- **R11**: La lista de sprints por proyecto (`GET /projects/{id}/sprints`) DEBE incluir, por cada sprint, `story_count` (tareas asignadas, sin contar eliminadas) y `estimation_hours_sum` (suma de `estimation_hours` de esas tareas), y DEBE incluir también el conteo/suma de las tareas sin sprint (Backlog) del proyecto en la respuesta (`meta.backlog`). Ningún campo existente de `SprintRead` cambia.

#### Escenario: Conteo y suma con tareas mixtas y sprint vacío
- Dado un sprint con tareas activas de 2h y 3h más una eliminada, y otro sprint recién creado sin tareas
- Cuando se lista el proyecto
- Entonces el primero muestra `story_count=2`, `estimation_hours_sum=5`; el segundo muestra `0` y `0` (nunca null).

#### Escenario: Backlog con y sin tareas sueltas
- Dado un proyecto con 2 tareas sin sprint (4h y 1h) y otro sin ninguna
- Cuando se lista cada proyecto
- Entonces el primero reporta conteo=2/suma=5h; el segundo, conteo=0/suma=0.

### Cambio 30 — Permisos de la lectura de agregados

- **R12**: Aplican los mismos permisos del módulo `sprints` a la lectura de agregados (autenticación + membresía, cualquier rol, sin restricción nueva); otra organización responde 404, sin token 401.

#### Escenario: Aislamiento de tenant y autenticación
- Dado un `member`, una solicitud sin token y un proyecto de otra organización
- Cuando lista su proyecto, repite sin token, y consulta el ajeno
- Entonces obtiene sus agregados; sin token responde 401; el ajeno responde 404.

### Cambio 30 — Orden, visibilidad y estados vacíos del Backlog agrupado

- **R13**: La pestaña Backlog DEBE mostrar primero las secciones `active`, luego las `draft` ordenadas ascendente por `created_at`, y la sección **Backlog** (tareas sin sprint) al final; los sprints `closed` NO se muestran aquí (siguen visibles en la pestaña Sprints). Cuando un proyecto no tiene sprints, la sección Backlog está sin tareas, o un sprint no tiene historias, DEBE mostrarse un mensaje vacío claro en español en vez de una lista en blanco.

#### Escenario: Orden mixto con cerrado oculto
- Dado un `active`, dos `draft` creados en distinto momento, un `closed` y tareas sueltas
- Cuando se abre la pestaña Backlog
- Entonces el orden es `active`, `draft` más antiguo, `draft` más nuevo, Backlog; el `closed` no aparece.

#### Escenario: Tres vacíos distintos
- Dado un proyecto sin sprints, uno con Backlog vacío y un sprint sin tareas
- Cuando se abre cada pestaña
- Entonces cada caso muestra su propio mensaje vacío.

### Cambio 30 — Cabecera de sección y acción contextual

- **R14**: Cada cabecera de sección DEBE mostrar nombre, badge de estado, fechas o "Sin fechas" (si `draft` sin ambas), `story_count`, `estimation_hours_sum`, y una acción contextual: `draft` sin fechas → "Añadir fechas"; `draft` con ambas fechas → "Iniciar sprint"; `active` → "Completar sprint".

#### Escenario: Acción correcta por estado
- Dado un `draft` sin fechas, un `draft` con ambas fechas y un `active`
- Cuando se renderiza cada cabecera
- Entonces muestran "Añadir fechas", "Iniciar sprint" y "Completar sprint" respectivamente.

### Cambio 30 — Persistencia del colapso por proyecto y sección

- **R15**: El colapso de cada sección DEBE persistir en `localStorage` con clave única por proyecto + identificador de sección; sin clave previa, el valor por defecto es expandido.

#### Escenario: Colapsar, recargar y aislar entre proyectos
- Dado una sección colapsada en el proyecto A
- Cuando se recarga A y se abre el proyecto B
- Entonces A sigue colapsada; B aparece expandida por defecto.

### Cambio 30 — Ids estables por sección (seam drag & drop)

- **R16**: Cada sección DEBE exponer un identificador estable (`sprint.id`, o el literal `'backlog'`) reutilizable como destino de arrastre en el cambio 31.

#### Escenario: Identificador estable tras recarga
- Dado una sección de sprint y la sección Backlog
- Cuando se recarga la vista
- Entonces ambos identificadores se mantienen iguales.

### Cambio 30 — No regresión del listado y acciones existentes

- **R17**: El listado, `burndown`, `close` y `start` (29) DEBEN seguir funcionando sin cambio de contrato; la suite backend existente DEBE permanecer en verde.

#### Escenario: Suite en verde con agregados nuevos
- Dado la suite de `sprints` previa a este cambio
- Cuando se agregan los agregados y la vista agrupada
- Entonces la suite sigue en verde y `SprintRead`/burndown/close no cambian de forma.

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
- Cambio 30: sin test runner en frontend (requirements de UI verificadas por source inspection y build verde, no por tests de comportamiento); `showClosedSprints` estado en memoria, no persistido en localStorage.
- Cobertura baseline: test_sprint_close (8 tests); cambio 29 agrega 30 tests (test_sprint_naming, test_sprint_draft_creation, test_sprint_start, test_sprint_suggested_name); cambio 30 agrega 5 tests (test_sprint_backlog_aggregates).

## Referencias

- backend/app/modules/sprints/ (router.py, service.py, repository.py, models.py, schemas.py, naming.py desde 29)
- backend/tests/test_sprint_close.py
- backend/tests/test_sprint_naming.py (cambio 29)
- backend/tests/test_sprint_draft_creation.py (cambio 29)
- backend/tests/test_sprint_start.py (cambio 29)
- backend/tests/test_sprint_suggested_name.py (cambio 29)
- backend/tests/test_sprint_backlog_aggregates.py (cambio 30)
- backend/tests/test_catalog_pagination.py (cambio 30 — 2 tests modificados)
- frontend/src/entities/workspace/ (workspace.model.ts, workspace.service.ts desde 30)
- frontend/src/widgets/project-workspace/project-workspace.component.ts (desde 30)
- frontend/src/assets/i18n/es-CO.json (desde 30)
- openspec/changes/29-sprint-borrador/ (proposal, design, tasks)
- openspec/changes/30-backlog-sprints-agrupados/ (proposal, design, tasks)
