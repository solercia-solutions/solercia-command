# Delta for tasks

## MODIFIED Requirements

### Requirement: Filtros combinables en la lista de tareas por proyecto

`GET /projects/{id}/tasks` DEBE aceptar, en cualquier combinación simultánea, los filtros `status`, `priority`, `assignee_id`, `sprint_id`, `label_id` (uno o más valores, unión entre etiquetas), `due_from`/`due_to` (rango sobre `due_date`) y `q` (texto libre sobre `title`/`description`). El endpoint DEBE mantener la paginación estándar `?page&size&sort&order` con `meta{page, size, total}` (02-contrato-api). El endpoint DEBE aceptar además el parámetro opcional `include_subtasks` (booleano, default `false`): sin `include_subtasks` y sin `assignee_id`, el listado sigue siendo exclusivamente de nivel superior (comportamiento actual sin cambio, usado por board y Gantt); con `include_subtasks=true`, el listado incluye también las subtareas junto a las tareas de nivel superior, en el orden ya existente (`order asc, created_at asc`), sin anidarlas en un árbol. Cuando `assignee_id` está presente (con o sin `include_subtasks`), el filtro DEBE incluir toda subtarea asignada a ese usuario aunque su tarea padre esté asignada a otra persona o no matchee el resto de filtros; el padre de esa subtarea DEBE devolverse también, marcado `is_context=true`, salvo que el padre matchee el filtro por sí mismo, caso en el que se devuelve normal (`is_context=false`) sin duplicarse. Ningún padre de contexto cuenta como resultado real: NO DEBE sumar al `meta.total` de paginación.
(Previously: solo aceptaba `sprint_id`, `status`, `assignee_id` y `label_id` de valor único, sin `priority`, sin rango de fechas y sin texto libre; el listado era siempre exclusivamente de nivel superior —sin parámetro para incluir subtareas— y `assignee_id` ocultaba toda subtarea cuyo padre perteneciera a otro usuario.)

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

#### Scenario: Listado por defecto sigue plano (no regresión de board y Gantt)

- DADO un proyecto con tareas de nivel superior y subtareas
- CUANDO se consulta `GET /projects/{id}/tasks` sin `include_subtasks` ni `assignee_id`
- ENTONCES solo se devuelven las tareas de nivel superior, igual que antes de este cambio

#### Scenario: include_subtasks incluye subtareas en el mismo listado

- DADO una tarea padre con 2 subtareas
- CUANDO se consulta `GET /projects/{id}/tasks?include_subtasks=true`
- ENTONCES la respuesta incluye el padre y sus 2 subtareas, en el orden `order asc, created_at asc`, sin árbol anidado

#### Scenario: Subtarea de padre ajeno visible al filtrar por asignado

- DADO una subtarea asignada al usuario A cuyo padre está asignado al usuario B
- CUANDO se consulta `GET /projects/{id}/tasks?assignee_id=A`
- ENTONCES la subtarea de A aparece en la respuesta y el padre de B también aparece, marcado `is_context=true`

#### Scenario: Padre que también matchea no se duplica como contexto

- DADO una subtarea asignada al usuario A cuyo padre también está asignado a A
- CUANDO se consulta `GET /projects/{id}/tasks?assignee_id=A`
- ENTONCES el padre aparece una sola vez, con `is_context=false`

## ADDED Requirements

### Requirement: Campo aditivo is_context y su exclusión de conteos

`TaskRead` DEBE incluir el campo `is_context` (booleano, default `false`); el resto de campos permanece intacto para consumidores previos. Un padre devuelto únicamente como contexto (`is_context=true`) NO DEBE contarse en `meta.total` de la paginación ni en los agregados por sección del cambio 30 (`story_count`, `estimation_hours_sum` por sprint o Backlog).

#### Scenario: is_context en false fuera de contexto

- DADO un listado sin `assignee_id`, o con `assignee_id` donde ningún padre queda fuera del filtro
- CUANDO se consulta `GET /projects/{id}/tasks`
- ENTONCES toda tarea de la respuesta trae `is_context=false`

#### Scenario: Total y agregados no se inflan por contexto

- DADO un sprint con 3 tareas que matchean `assignee_id=A` y 1 padre de contexto adicional cuyo dueño es B
- CUANDO se consulta el listado filtrado y los agregados del sprint
- ENTONCES `meta.total` refleja 3 y el `story_count` del sprint no incluye el padre de contexto

### Requirement: Permisos y aislamiento multi-tenant sin cambio

`include_subtasks` e `is_context` DEBEN respetar los mismos permisos y el mismo aislamiento de tenant que el listado existente (autenticación + membresía, cualquier rol); un proyecto de otra organización responde `404`; sin token responde `401`.

#### Scenario: Aislamiento de tenant con include_subtasks y assignee_id

- DADO un `member` autenticado y un proyecto de otra organización
- CUANDO consulta `GET /projects/{id}/tasks?include_subtasks=true&assignee_id=A` sobre el proyecto ajeno, y repite sin token
- ENTONCES el proyecto ajeno responde `404` y la solicitud sin token responde `401`

## Referencias

- `openspec/changes/32-jerarquia-subtareas/proposal.md`
- `openspec/specs/tasks/spec.md` (línea base, R4 filtros combinables)
- `openspec/changes/30-backlog-sprints-agrupados/specs/sprints/spec.md` (agregados de sección consumidos)
- `backend/app/modules/tasks/{repository,service,router,schemas}.py`
