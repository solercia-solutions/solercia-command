# Delta for Sprints

## Alcance propuesto (delta)

| Método | Ruta | Cambio |
|---|---|---|
| GET | /projects/{id}/sprints | Cada ítem suma `story_count` + `estimation_hours_sum` (aditivo); la respuesta agrega también conteo/suma del Backlog (tareas sin sprint) |
| GET /burndown, PATCH, POST /close, POST /start | — | Sin cambio; `SprintRead` intacto |

Nota: "draft/planned" en los requisitos de UI son la misma fila de datos (`status=draft`); "planned" solo describe un `draft` con ambas fechas ya definidas (no hay valor de enum nuevo).

## ADDED Requirements

### Requirement: Agregados por sprint y por Backlog en la lista

La lista de sprints por proyecto DEBE incluir, por cada sprint, `story_count` (tareas asignadas, sin contar eliminadas) y `estimation_hours_sum` (suma de `estimation_hours` de esas tareas), y DEBE incluir también el conteo/suma de las tareas sin sprint (Backlog) del proyecto. Ningún campo existente de `SprintRead` cambia.

#### Scenario: Conteo y suma con tareas mixtas y sprint vacío

- DADO un sprint con tareas activas de 2h y 3h más una eliminada, y otro sprint recién creado sin tareas
- CUANDO se lista el proyecto
- ENTONCES el primero muestra `story_count=2`, `estimation_hours_sum=5`; el segundo muestra `0` y `0` (nunca null)

#### Scenario: Backlog con y sin tareas sueltas

- DADO un proyecto con 2 tareas sin sprint (4h y 1h) y otro sin ninguna
- CUANDO se lista cada proyecto
- ENTONCES el primero reporta conteo=2/suma=5h; el segundo, conteo=0/suma=0

### Requirement: Permisos de la lectura de agregados

Aplican los mismos permisos del módulo `sprints` (autenticación + membresía, cualquier rol, sin restricción nueva); otra organización responde 404, sin token 401.

#### Scenario: Aislamiento de tenant y autenticación

- DADO un `member`, una solicitud sin token y un proyecto de otra organización
- CUANDO lista su proyecto, repite sin token, y consulta el ajeno
- ENTONCES obtiene sus agregados; sin token responde 401; el ajeno responde 404

### Requirement: Orden, visibilidad y estados vacíos del Backlog agrupado

La pestaña Backlog DEBE mostrar primero las secciones `active`, luego las `draft` ordenadas ascendente por `created_at`, y la sección **Backlog** (tareas sin sprint) al final; los sprints `closed` NO se muestran aquí (siguen visibles en la pestaña Sprints). Cuando un proyecto no tiene sprints, la sección Backlog está sin tareas, o un sprint no tiene historias, DEBE mostrarse un mensaje vacío claro en español en vez de una lista en blanco.

#### Scenario: Orden mixto con cerrado oculto

- DADO un `active`, dos `draft` creados en distinto momento, un `closed` y tareas sueltas
- CUANDO se abre la pestaña Backlog
- ENTONCES el orden es `active`, `draft` más antiguo, `draft` más nuevo, Backlog; el `closed` no aparece

#### Scenario: Tres vacíos distintos

- DADO un proyecto sin sprints, uno con Backlog vacío y un sprint sin tareas
- CUANDO se abre cada pestaña
- ENTONCES cada caso muestra su propio mensaje vacío

### Requirement: Cabecera de sección y acción contextual

Cada cabecera DEBE mostrar nombre, badge de estado, fechas o "Sin fechas" (si `draft` sin ambas), `story_count`, `estimation_hours_sum`, y una acción: `draft` sin fechas → "Añadir fechas"; `draft` con ambas fechas → "Iniciar sprint"; `active` → "Completar sprint".

#### Scenario: Acción correcta por estado

- DADO un `draft` sin fechas, un `draft` con ambas fechas y un `active`
- CUANDO se renderiza cada cabecera
- ENTONCES muestran "Añadir fechas", "Iniciar sprint" y "Completar sprint" respectivamente

### Requirement: Persistencia del colapso por proyecto y sección

El colapso de cada sección DEBE persistir en `localStorage` con clave única por proyecto + identificador de sección; sin clave previa, el valor por defecto es expandido.

#### Scenario: Colapsar, recargar y aislar entre proyectos

- DADO una sección colapsada en el proyecto A
- CUANDO se recarga A y se abre el proyecto B
- ENTONCES A sigue colapsada; B aparece expandida por defecto

### Requirement: Ids estables por sección (seam drag & drop)

Cada sección DEBE exponer un identificador estable (`sprint.id`, o el literal `'backlog'`) reutilizable como destino de arrastre en el cambio 31.

#### Scenario: Identificador estable tras recarga

- DADO una sección de sprint y la sección Backlog
- CUANDO se recarga la vista
- ENTONCES ambos identificadores se mantienen iguales

### Requirement: No regresión del listado y acciones existentes

El listado, `burndown`, `close` y `start` (29) DEBEN seguir funcionando sin cambio de contrato; la suite backend existente DEBE permanecer en verde.

#### Scenario: Suite en verde con agregados nuevos

- DADO la suite de `sprints` previa a este cambio
- CUANDO se agregan los agregados y la vista agrupada
- ENTONCES la suite sigue en verde y `SprintRead`/burndown/close no cambian de forma

## Referencias

- `openspec/changes/30-backlog-sprints-agrupados/proposal.md`
- `openspec/specs/sprints/spec.md` (línea base); `openspec/changes/29-sprint-borrador/specs/sprints/spec.md` (seams draft/start/badge)
- `backend/app/modules/sprints/*.py`; `frontend/.../project-workspace.component.ts`
