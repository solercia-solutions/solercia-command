# Delta for tasks

> Base: `openspec/specs/tasks/spec.md` (R4, MODIFIED por 10-búsqueda-global). El
> campo `is_context`/`include_subtasks` referido abajo lo introduce el cambio 32
> (`design.md`, spec del 32 aún pendiente); este delta asume que 32 se aplica y
> archiva antes que 33, dejando `is_context` ya mergeado en el spec principal.

## MODIFIED Requirements

### Requirement: Filtros combinables en la lista de tareas por proyecto

`GET /projects/{id}/tasks` DEBE aceptar, en cualquier combinación simultánea, los filtros `status`, `priority`, `assignee_id` (uno o más valores, unión entre asignados), `sprint_id`, `label_id` (uno o más valores, unión entre etiquetas), `due_from`/`due_to` (rango sobre `due_date`) y `q` (texto libre sobre `title`/`description`). El endpoint DEBE mantener la paginación estándar `?page&size&sort&order` con `meta{page, size, total}` (02-contrato-api).

(Previously: `assignee_id` aceptaba un único valor UUID; el resto de filtros ya combinaban libremente desde 10-búsqueda-global.)

#### Scenario: Combinación simultánea de filtros
- DADO un proyecto con tareas de distinta prioridad, asignado y etiqueta
- CUANDO se consulta `?status=in_progress&priority=high&assignee_id={u}&label_id={l}&due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas que cumplen TODOS los criterios a la vez

#### Scenario: label_id acepta múltiples valores
- DADO tareas etiquetadas con "Urgente" o con "Backend" (sin solapamiento)
- CUANDO se consulta `?label_id={urgente}&label_id={backend}`
- ENTONCES se devuelven las tareas que tienen cualquiera de las dos etiquetas

#### Scenario: Filtro de texto sobre título y descripción
- DADO dos tareas, una con "migrar base de datos" en el título y otra sin relación
- CUANDO se consulta `?q=migrar`
- ENTONCES solo se devuelve la tarea cuyo título o descripción contiene "migrar"

#### Scenario: Filtro de rango de fechas de vencimiento
- DADO tareas con `due_date` en junio y en julio
- CUANDO se consulta `?due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas con `due_date` dentro de julio

#### Scenario: assignee_id acepta múltiples valores (NUEVO)
- DADO tareas asignadas a los usuarios A, B y C
- CUANDO se consulta `?assignee_id={A}&assignee_id={B}`
- ENTONCES se devuelven solo las tareas asignadas a A o a B (unión, no intersección)

## ADDED Requirements

### Requirement: Contexto de padres bajo selección múltiple de asignados

Cuando `assignee_id` recibe dos o más valores, el cálculo de padres de contexto (`is_context=true`, introducido por el cambio 32 sobre `assignee_id` singular) DEBE extenderse a la unión de asignados solicitados: una subtarea que matchea CUALQUIERA de los `assignee_id` SIEMPRE aparece, y su padre, si no matchea NINGUNO de los `assignee_id`, se devuelve como contexto (`is_context=true`) sin duplicarse ni sumar a `meta.total`.

#### Scenario: Padre de contexto con selección múltiple
- DADO una subtarea asignada al usuario B cuyo padre está asignado a un tercer usuario D
- CUANDO se consulta `?assignee_id={A}&assignee_id={B}`
- ENTONCES la subtarea aparece como match y el padre aparece con `is_context=true`, sin sumar a `meta.total`

#### Scenario: Sin duplicación cuando el padre también matchea
- DADO un padre asignado a A y una subtarea asignada a B
- CUANDO se consulta `?assignee_id={A}&assignee_id={B}`
- ENTONCES el padre aparece una sola vez con `is_context=false`
