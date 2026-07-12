# Delta for tasks

## MODIFIED Requirements

### Requirement: Filtros combinables en la lista de tareas por proyecto

`GET /projects/{id}/tasks` DEBE aceptar, en cualquier combinación simultánea, los filtros `status`, `priority`, `assignee_id`, `sprint_id`, `label_id` (uno o más valores, unión entre etiquetas), `due_from`/`due_to` (rango sobre `due_date`) y `q` (texto libre sobre `title`/`description`). El endpoint DEBE mantener la paginación estándar `?page&size&sort&order` con `meta{page, size, total}` (02-contrato-api).
(Previously: solo aceptaba `sprint_id`, `status`, `assignee_id` y `label_id` de valor único, sin `priority`, sin rango de fechas y sin texto libre.)

#### Scenario: Combinación simultánea de filtros

- DADO un proyecto con tareas de distinta prioridad, asignado y etiqueta
- CUANDO se consulta `GET /projects/{id}/tasks?status=in_progress&priority=high&assignee_id={u}&label_id={l}&due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas que cumplen TODOS los criterios a la vez

#### Scenario: label_id acepta múltiples valores

- DADO tareas del proyecto etiquetadas con "Urgente" o con "Backend" (sin solapamiento)
- CUANDO se consulta `GET /projects/{id}/tasks?label_id={urgente}&label_id={backend}`
- ENTONCES se devuelven las tareas que tienen cualquiera de las dos etiquetas

#### Scenario: Filtro de texto sobre título y descripción

- DADO dos tareas del proyecto, una con "migrar base de datos" en el título y otra sin relación
- CUANDO se consulta `GET /projects/{id}/tasks?q=migrar`
- ENTONCES solo se devuelve la tarea cuyo título o descripción contiene "migrar"

#### Scenario: Filtro de rango de fechas de vencimiento

- DADO tareas del proyecto con `due_date` en junio y en julio
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas con `due_date` dentro de julio

## ADDED Requirements

### Requirement: Validación de filtros inválidos en la lista de tareas

El sistema DEBE responder `422` cuando `status` o `priority` no pertenecen al catálogo permitido, o cuando `due_from` es posterior a `due_to`; NO PUEDE ignorar silenciosamente un filtro inválido ni devolver una colección vacía como si fuera un resultado válido.

#### Scenario: Prioridad fuera de catálogo rechazada

- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?priority=urgentísima`
- ENTONCES la API responde `422`

#### Scenario: Rango de fechas invertido rechazado

- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-31&due_to=2026-07-01`
- ENTONCES la API responde `422`
