# Spec — Tareas (tasks)

> **Origen**: línea base as-built (2026-07-11) + cambio [03-boards-persistentes](../../changes/archive/2026-07-11-03-boards-persistentes/) + cambio [10-busqueda-global](../../changes/archive/2026-07-12-10-busqueda-global/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Núcleo del producto: tareas por proyecto con clave legible (`SDM-7`), subtareas, asignación, estimación dual (puntos/horas), estados validados por la metodología del proyecto y marcado de riesgo.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/projects/{id}/members | Miembros asignables |
| GET | /api/v1/projects/{id}/tasks | Lista con filtros sprint_id / status / assignee_id |
| POST | /api/v1/projects/{id}/tasks | Crea tarea (201); admite parent_task_id |
| GET | /api/v1/tasks/by-key/{key} | Busca por clave legible (ej. SDM-7) |
| GET | /api/v1/tasks/{id} | Detalle + progreso de subtareas |
| PATCH | /api/v1/tasks/{id} | Mover estado, reasignar, estimar, riesgo, orden, sprint |
| DELETE | /api/v1/tasks/{id} | Borrado suave (204) |
| GET | /api/v1/tasks/{id}/subtasks | Subtareas de una tarea |

Modelo `Task` (Pk + Timestamp + SoftDelete; scope de tenant vía join a Project):

| Campo | Descripción |
|-------|-------------|
| project_id, sprint_id?, parent_task_id? | Relaciones (sprint null = backlog) |
| title, description, task_type, priority | Contenido y clasificación |
| status | String validado por la strategy de metodología (NO enum fijo) |
| assignee_id? | Asignado |
| estimation_points?, estimation_hours? (Decimal) | Estimación dual |
| due_date?, start_date?, completed_at? | Fechas |
| order, risk_flag, risk_reason?, task_number? | Orden, riesgo y numeración por proyecto |
| labels[] | Etiquetas asignadas (vía TaskLabel) |
| checklist_progress | Progreso agregado de checklists (done/total) |
| is_blocked | Booleano indicando bloqueo activo |
| blockers[] | Tareas que bloquean a esta tarea |

## Requisitos

- **R1**: Cada tarea creada DEBE recibir `task_number` secuencial del proyecto, y `GET /tasks/by-key/{code}-{n}` DEBE resolverla.
- **R2**: `PATCH` DEBE rechazar estados no permitidos por la strategy de la metodología del proyecto.
- **R3**: El detalle de una tarea con subtareas DEBE incluir el progreso agregado de sus subtareas.
- **R4**: La lista por proyecto DEBE soportar los filtros combinables `sprint_id`, `status` y `assignee_id`.
- **R5** (03-boards-persistentes): `Task` DEBE tener campo `board_column_id` (FK nullable a BoardColumn); al crear, asignación por defecto a primera columna por order; al mover, status derivado de status_key de la columna destino.
- **R6** (03-boards-persistentes): Backfill al aplicar migración: tarea existente → columna con status_key coincidente, si no → primera columna por order.

### Escenarios centrales

**R1 — Clave legible**
- Dado un proyecto con `code = "SDM"` y 6 tareas
- Cuando se crea una tarea nueva
- Entonces obtiene la clave `SDM-7` y `GET /tasks/by-key/SDM-7` la devuelve.

**R2 — Estado validado por metodología**
- Dado una tarea de un proyecto planner
- Cuando se envía `PATCH` con un estado ajeno a la estrategia (ej. `in_review`)
- Entonces la API rechaza el cambio.

**R3 — Progreso de subtareas**
- Dado una tarea padre con 4 subtareas, 2 completadas
- Cuando se consulta `GET /tasks/{id}`
- Entonces el detalle reporta el progreso 2/4.

### MODIFIED Requirements (03-boards-persistentes)

#### Requirement: Estado validado por metodología

`PATCH` DEBE derivar el `status` de la tarea desde el `status_key` de la `BoardColumn` destino (`board_column_id`) cuando el movimiento se realiza entre columnas del board del proyecto. El `status` resultante DEBE pertenecer a `allowed_statuses()` de la strategy de la metodología del proyecto; un movimiento hacia una columna cuyo `status_key` no esté permitido DEBE rechazarse.
(Previously: `PATCH` aceptaba un campo `status` libre validado directamente contra `allowed_statuses()`, sin relación con ninguna entidad de columna persistida porque no existían `Board`/`BoardColumn`.)

**Scenario: Movimiento válido actualiza status desde la columna**
- DADO una tarea de un proyecto kanban asignada a la columna `Backlog` (`status_key = backlog`)
- CUANDO se hace `PATCH` moviéndola a la columna `Doing` (`status_key = doing`)
- ENTONCES `board_column_id` pasa a apuntar a `Doing` y `status` pasa a `doing`

**Scenario: Movimiento a estado no permitido por la strategy**
- DADO una tarea de un proyecto planner
- CUANDO se intenta mover la tarea a una columna cuyo `status_key` es `in_review` (no permitido por planner)
- ENTONCES la API rechaza el movimiento

### ADDED Requirements (03-boards-persistentes)

#### Requirement: Campo board_column_id

`Task` DEBE tener un campo `board_column_id` (FK nulable a `BoardColumn`). Toda tarea creada en un proyecto cuyo board tenga al menos una columna DEBE quedar asignada a una columna: la indicada explícitamente en la solicitud de creación, o —si no se indica ninguna— la primera columna del board por `order`, fijando `status` desde su `status_key`.

**Scenario: Asignación a columna por defecto al crear**
- DADO un proyecto kanban cuyo board tiene columnas `[Backlog, Doing, Done]` en ese orden
- CUANDO se crea una tarea sin especificar columna
- ENTONCES la tarea se asigna a la columna `Backlog` (primera por `order`) y `status = backlog`

#### Requirement: Backfill de tareas existentes a columnas por status

Al aplicar la migración de este cambio, toda tarea existente DEBE quedar asignada a la `BoardColumn` sembrada cuyo `status_key` coincida con su `status` actual. Si ningún `status_key` sembrado coincide con el `status` de una tarea, esa tarea DEBE asignarse a la primera columna del board por `order` (columna de fallback) y el caso DEBE quedar registrado para revisión posterior.

**Scenario: Backfill con coincidencia directa**
- DADO una tarea existente con `status = "done"` en un proyecto kanban cuyo board sembrado tiene una columna con `status_key = "done"`
- CUANDO corre la migración de backfill
- ENTONCES la tarea queda con `board_column_id` apuntando a esa columna

**Scenario: Backfill con status sin columna coincidente**
- DADO una tarea existente con `status = "archived"` que no coincide con ningún `status_key` de las columnas sembradas del proyecto
- CUANDO corre la migración de backfill
- ENTONCES la tarea se asigna a la primera columna del board por `order` y el caso se registra para revisión

### MODIFIED Requirements (10-busqueda-global)

#### Requirement: Filtros combinables en la lista de tareas por proyecto

`GET /projects/{id}/tasks` DEBE aceptar, en cualquier combinación simultánea, los filtros `status`, `priority`, `assignee_id`, `sprint_id`, `label_id` (uno o más valores, unión entre etiquetas), `due_from`/`due_to` (rango sobre `due_date`) y `q` (texto libre sobre `title`/`description`). El endpoint DEBE mantener la paginación estándar `?page&size&sort&order` con `meta{page, size, total}` (02-contrato-api). El endpoint DEBE aceptar además el parámetro opcional `include_subtasks` (booleano, default `false`): sin `include_subtasks` y sin `assignee_id`, el listado sigue siendo exclusivamente de nivel superior (comportamiento actual sin cambio, usado por board y Gantt); con `include_subtasks=true`, el listado incluye también las subtareas junto a las tareas de nivel superior, en el orden ya existente (`order asc, created_at asc`), sin anidarlas en un árbol. Cuando `assignee_id` está presente (con o sin `include_subtasks`), el filtro DEBE incluir toda subtarea asignada a ese usuario aunque su tarea padre esté asignada a otra persona o no matchee el resto de filtros; el padre de esa subtarea DEBE devolverse también, marcado `is_context=true`, salvo que el padre matchee el filtro por sí mismo, caso en el que se devuelve normal (`is_context=false`) sin duplicarse. Ningún padre de contexto cuenta como resultado real: NO DEBE sumar al `meta.total` de paginación.
(Previously: solo aceptaba `sprint_id`, `status`, `assignee_id` y `label_id` de valor único, sin `priority`, sin rango de fechas y sin texto libre; el listado era siempre exclusivamente de nivel superior —sin parámetro para incluir subtareas— y `assignee_id` ocultaba toda subtarea cuyo padre perteneciera a otro usuario.)

**Scenario: Combinación simultánea de filtros**
- DADO un proyecto con tareas de distinta prioridad, asignado y etiqueta
- CUANDO se consulta `GET /projects/{id}/tasks?status=in_progress&priority=high&assignee_id={u}&label_id={l}&due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas que cumplen TODOS los criterios a la vez

**Scenario: label_id acepta múltiples valores**
- DADO tareas del proyecto etiquetadas con "Urgente" o con "Backend" (sin solapamiento)
- CUANDO se consulta `GET /projects/{id}/tasks?label_id={urgente}&label_id={backend}`
- ENTONCES se devuelven las tareas que tienen cualquiera de las dos etiquetas

**Scenario: Filtro de texto sobre título y descripción**
- DADO dos tareas del proyecto, una con "migrar base de datos" en el título y otra sin relación
- CUANDO se consulta `GET /projects/{id}/tasks?q=migrar`
- ENTONCES solo se devuelve la tarea cuyo título o descripción contiene "migrar"

**Scenario: Filtro de rango de fechas de vencimiento**
- DADO tareas del proyecto con `due_date` en junio y en julio
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-01&due_to=2026-07-31`
- ENTONCES solo se devuelven las tareas con `due_date` dentro de julio

**Scenario: Listado por defecto sigue plano (no regresión de board y Gantt)**
- DADO un proyecto con tareas de nivel superior y subtareas
- CUANDO se consulta `GET /projects/{id}/tasks` sin `include_subtasks` ni `assignee_id`
- ENTONCES solo se devuelven las tareas de nivel superior, igual que antes de este cambio

**Scenario: include_subtasks incluye subtareas en el mismo listado**
- DADO una tarea padre con 2 subtareas
- CUANDO se consulta `GET /projects/{id}/tasks?include_subtasks=true`
- ENTONCES la respuesta incluye el padre y sus 2 subtareas, en el orden `order asc, created_at asc`, sin árbol anidado

**Scenario: Subtarea de padre ajeno visible al filtrar por asignado**
- DADO una subtarea asignada al usuario A cuyo padre está asignado al usuario B
- CUANDO se consulta `GET /projects/{id}/tasks?assignee_id=A`
- ENTONCES la subtarea de A aparece en la respuesta y el padre de B también aparece, marcado `is_context=true`

**Scenario: Padre que también matchea no se duplica como contexto**
- DADO una subtarea asignada al usuario A cuyo padre también está asignado a A
- CUANDO se consulta `GET /projects/{id}/tasks?assignee_id=A`
- ENTONCES el padre aparece una sola vez, con `is_context=false`

### ADDED Requirements (10-busqueda-global)

#### Requirement: Validación de filtros inválidos en la lista de tareas

El sistema DEBE responder `422` cuando `status` o `priority` no pertenecen al catálogo permitido, o cuando `due_from` es posterior a `due_to`; NO PUEDE ignorar silenciosamente un filtro inválido ni devolver una colección vacía como si fuera un resultado válido.

**Scenario: Prioridad fuera de catálogo rechazada**
- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?priority=urgentísima`
- ENTONCES la API responde `422`

**Scenario: Rango de fechas invertido rechazado**
- DADO un proyecto existente
- CUANDO se consulta `GET /projects/{id}/tasks?due_from=2026-07-31&due_to=2026-07-01`
- ENTONCES la API responde `422`

### ADDED Requirements (31-backlog-drag-drop)

#### Requirement: Guard de integridad al asignar sprint_id en PATCH

`PATCH /tasks/{id}` DEBE rechazar con `422` y un mensaje claro en español la asignación de `sprint_id` cuando el sprint destino tiene `status = closed`. Cuando el destino es `draft` o `active`, el servidor DEBE aceptar la asignación sin exigir que origen y destino compartan estado. El servidor NO DEBE validar el estado del sprint de origen; esta es la única validación de destino a nivel de API.

**Scenario: Mover a un sprint draft se acepta**
- DADO una tarea en el Backlog y un sprint del mismo proyecto en `draft`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <draft> }`
- ENTONCES la API responde `200` y la tarea queda asignada al sprint

**Scenario: Mover a un sprint active se acepta**
- DADO una tarea en un sprint `draft` y otro sprint del proyecto en `active`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <active> }`
- ENTONCES la API responde `200` y la tarea queda asignada al sprint `active`

**Scenario: Mover hacia un sprint closed se rechaza**
- DADO una tarea en el Backlog y un sprint del mismo proyecto en `closed`
- CUANDO se hace `PATCH /tasks/{id}` con `{ sprint_id: <closed> }`
- ENTONCES la API responde `422` con un mensaje que indica que el sprint destino está cerrado, y la tarea conserva su `sprint_id` anterior

**Scenario: Permisos existentes de PATCH sin cambio**
- DADO un usuario `member` de la organización y un sprint `draft` del mismo proyecto
- CUANDO hace `PATCH /tasks/{id}` asignando ese sprint
- ENTONCES aplican los mismos permisos vigentes (autenticación + membresía), sin restricción nueva de rol

**Scenario: Aislamiento de organización se mantiene**
- DADO un `sprint_id` que pertenece a un proyecto de otra organización
- CUANDO se hace `PATCH /tasks/{id}` asignando ese `sprint_id`
- ENTONCES la API responde `422` con `code=invalid_sprint` (sprint no encontrado en el org/proyecto del solicitante), manteniendo el aislamiento de tenant

#### Requirement: Reordenamiento transaccional vía `POST /tasks/reorder`

`POST /tasks/reorder` DEBE mover una tarea a un `sprint_id` destino (o `null` para el Backlog) y reindexar el campo `order` de todas las tareas del contenedor destino según el arreglo `ordered_task_ids` recibido, en una única transacción (`task_id: UUID`, `sprint_id: UUID | null`, `ordered_task_ids: list[UUID]`). El servidor DEBE aplicar el mismo guard de integridad que el requisito anterior: rechaza con `422` (`code=sprint_closed`) si el sprint destino tiene `status = closed`. El campo `order` NO DEBE generar entradas de `TaskHistory` (no forma parte de `_HISTORY_TRACKED_FIELDS`); solo un cambio efectivo de `sprint_id` genera una fila de historial, igual que en `update_task`. Una tarea que no pertenece a la organización del solicitante (aislamiento de tenant) DEBE responder `404`, sin ejecutar ninguna reasignación.

**Scenario: Mover a una posición arbitraria reindexa a los hermanos**
- DADO un sprint destino `draft` con tres tareas en orden `[A, B, C]` (`order` 0,1,2) y una tarea `D` en el Backlog
- CUANDO se hace `POST /tasks/reorder` con `{ task_id: D, sprint_id: <destino>, ordered_task_ids: [A, D, B, C] }`
- ENTONCES la API responde `200`, `D.sprint_id` queda asignado al destino, y el `order` de `A, D, B, C` queda `0, 1, 2, 3` respectivamente, todo en una sola transacción

**Scenario: Mover hacia un sprint destino closed se rechaza**
- DADO una tarea en el Backlog y un sprint del mismo proyecto en `closed`
- CUANDO se hace `POST /tasks/reorder` con `{ task_id, sprint_id: <closed>, ordered_task_ids: [...] }`
- ENTONCES la API responde `422` con código `sprint_closed`, y la tarea conserva su `sprint_id` y `order` anteriores sin reindexar a nadie

**Scenario: Tarea de otra organización se rechaza**
- DADO un `task_id` que pertenece a un proyecto de una organización distinta a la del solicitante
- CUANDO se hace `POST /tasks/reorder` con ese `task_id`
- ENTONCES la API responde `404` (tarea no encontrada en el tenant), sin ejecutar ninguna reasignación de `sprint_id` ni de `order`

**Scenario: Permisos existentes de `tasks` sin cambio**
- DADO un usuario `member` de la organización y un sprint `draft` del mismo proyecto
- CUANDO hace `POST /tasks/reorder` moviendo una tarea a ese sprint
- ENTONCES aplican los mismos permisos vigentes del módulo (autenticación + membresía), sin restricción nueva de rol

### MODIFIED Requirements (32-jerarquia-subtareas)

#### Requirement: Filtros combinables en la lista de tareas por proyecto (actualización para incluir `is_context`)

Ver la sección MODIFIED Requirements (10-busqueda-global) anterior, líneas 110-134 y scenarios adicionales de 32-jerarquia-subtareas, que documentan el comportamiento completo y actualizado del parámetro `include_subtasks` y la regla innegociable de `assignee_id` con padres de contexto.

### ADDED Requirements (32-jerarquia-subtareas)

#### Requirement: Campo aditivo is_context y su exclusión de conteos

`TaskRead` DEBE incluir el campo `is_context` (booleano, default `false`); el resto de campos permanece intacto para consumidores previos. Un padre devuelto únicamente como contexto (`is_context=true`) NO DEBE contarse en `meta.total` de la paginación ni en los agregados por sección del cambio 30 (`story_count`, `estimation_hours_sum` por sprint o Backlog).

**Scenario: is_context en false fuera de contexto**
- DADO un listado sin `assignee_id`, o con `assignee_id` donde ningún padre queda fuera del filtro
- CUANDO se consulta `GET /projects/{id}/tasks`
- ENTONCES toda tarea de la respuesta trae `is_context=false`

**Scenario: Total y agregados no se inflan por contexto**
- DADO un sprint con 3 tareas que matchean `assignee_id=A` y 1 padre de contexto adicional cuyo dueño es B
- CUANDO se consulta el listado filtrado y los agregados del sprint
- ENTONCES `meta.total` refleja 3 y el `story_count` del sprint no incluye el padre de contexto

#### Requirement: Permisos y aislamiento multi-tenant sin cambio

`include_subtasks` e `is_context` DEBEN respetar los mismos permisos y el mismo aislamiento de tenant que el listado existente (autenticación + membresía, cualquier rol); un proyecto de otra organización responde `404`; sin token responde `401`.

**Scenario: Aislamiento de tenant con include_subtasks y assignee_id**
- DADO un `member` autenticado y un proyecto de otra organización
- CUANDO consulta `GET /projects/{id}/tasks?include_subtasks=true&assignee_id=A` sobre el proyecto ajeno, y repite sin token
- ENTONCES el proyecto ajeno responde `404` y la solicitud sin token responde `401`

## Limitaciones y deuda conocida

- Boards y columnas persistidas (introducidas en 03-boards-persistentes); board_column_id en Task es nullable para compatibilidad con custom sin columnas.
- Existen Label/TaskLabel (04-labels-checklists-dependencias), TaskChecklist/ChecklistItem (04-labels-checklists-dependencias), TaskDependency (04-labels-checklists-dependencias).
- TaskTimeLog y TaskHistory implementados en 05-trabajo-realizado (registros de tiempo y changelog automático).
- Estado `cancelled` en Task aún no implementado; requiere enriquecimiento en desbloqueo de TaskDependency (deuda trazada en 04).
- Sin validación Fibonacci de puntos; sin paginación en listas.
- Tests: cobertura de clave legible (test_task_key, 13) y subtareas (test_subtasks, 4); el CRUD/PATCH general y los filtros tienen CERO tests directos. Sin tests de permisos.
- (SUGGESTION 04-verify) Formalizar tabla TDD Cycle Evidence en apply-progress para batches futuros (mejora de proceso, no defecto).
- (SUGGESTION 04-verify) Desbloqueo al completar tarea bloqueante requiere criterio preciso: completado (completed_at NOT NULL) vs. estado=done, comportamiento futuro a definir con UX.

## Referencias

- backend/app/modules/tasks/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/methodology/ (validación de estados)
- backend/tests/test_task_key.py, backend/tests/test_subtasks.py


## ADDED Requirements (43-tareas-origen-externo)

### Requirement: Ancla de procedencia externa (source + external_key)

`Task` DEBE tener las columnas nulables `source` (sistema de origen) y
`external_key` (clave original en ese sistema). Cuando ambas columnas tienen
valor en una misma tarea **activa**, el par (`source`, `external_key`) DEBE
ser único dentro del proyecto de esa tarea, garantía que provee el motor
mediante un índice único parcial. Esa unicidad del motor DEBE alcanzar
únicamente a las tareas activas: una tarea con borrado suave
(`is_active=false`) DEBE **liberar** su ancla, de modo que el mismo par pueda
volver a anclarse en ese proyecto sin que el motor lo rechace. La unicidad
dentro de la organización (a través de distintos proyectos) DEBE
garantizarla el servicio antes de insertar, consultando la costura de
repositorio dedicada — el motor por sí solo NO puede expresar unicidad a
través de un `JOIN` a `projects`, porque `tasks` no tiene `organization_id`
propio. Una tarea creada manualmente, sin origen externo, DEBE conservar
ambas columnas en `NULL`, sin restricción de unicidad ni valor centinela.
Una fila con `external_key` no nulo y `source` nulo DEBE ser rechazada.

#### Scenario: Duplicado exacto en el mismo proyecto es rechazado

- Dado un proyecto con una tarea anclada a `source="checklist_xlsx"`, `external_key="T-05"`
- Cuando se intenta insertar otra tarea del mismo proyecto con el mismo par
- Entonces el motor rechaza la inserción por violación de unicidad

#### Scenario: Múltiples tareas manuales sin ancla conviven

- Dado un proyecto con varias tareas creadas manualmente, cada una con `source` y `external_key` en `NULL`
- Cuando se consulta la unicidad del ancla
- Entonces ninguna de esas tareas entra en conflicto entre sí

#### Scenario: Misma clave en proyectos distintos no colisiona en el motor

- Dado dos proyectos distintos, cada uno con una tarea anclada a `source="jira"`, `external_key="PROJ-1"`
- Cuando ambas tareas coexisten en la base de datos
- Entonces el motor no reporta ninguna violación de unicidad, porque la garantía del motor es por proyecto

#### Scenario: Clave externa sin origen viola la integridad

- Dado un intento de persistir una fila con `external_key="T-05"` y `source=NULL`
- Cuando se ejecuta la escritura
- Entonces la base de datos la rechaza por integridad referencial de la procedencia

#### Scenario: Una tarea con borrado suave libera su ancla

- Dado una tarea anclada a `source="jira"`, `external_key="PROJ-1"` con `is_active=false` en el proyecto P
- Cuando se inserta otra tarea activa con la misma `(source, external_key)` en el proyecto P
- Entonces el motor la acepta y la costura `get_by_external_key` devuelve solo la activa

### Requirement: Migración aditiva `0025_add_task_external_origin` y su reversibilidad

DEBE existir una migración Alembic aditiva `0025_add_task_external_origin`
(`down_revision="0024"`) que agregue a `tasks` las columnas nulables `source
VARCHAR(50)` y `external_key VARCHAR(255)`, sin retrollenar ni transformar
ninguna fila existente. La migración DEBE ser reversible sin pérdida de
datos: aplicar el downgrade tras el upgrade DEBE dejar el esquema como antes
de la migración y conservar íntegras las filas que existían previamente.

#### Scenario: Migración agrega columnas nulables sin afectar filas existentes

- Dado un esquema en la revisión `0024` con tareas ya existentes
- Cuando se aplica `alembic upgrade 0025`
- Entonces las tareas existentes conservan sus valores y ambas columnas nuevas quedan en `NULL`

#### Scenario: Downgrade limpio conserva las filas

- Dado el esquema en la revisión `0025` con tareas ancladas y sin anclar
- Cuando se aplica `alembic downgrade 0024`
- Entonces las columnas `source`/`external_key` desaparecen del esquema y ninguna fila se pierde

### Requirement: Restricciones espejadas en el modelo ORM

`Task.__table_args__` DEBE declarar los dos objetos de esquema del ancla de
procedencia externa — la restricción de integridad y el índice único parcial
— con la misma condición parcial que la migración `0025`, porque el harness
de pruebas construye el esquema con `Base.metadata.create_all` en lugar de
ejecutar Alembic. El esquema resultante de `create_all` DEBE ser
indistinguible del que produce la migración.

#### Scenario: Esquema de create_all coincide con el de la migración

- Dado un motor de pruebas construido con `Base.metadata.create_all`
- Cuando se compara su esquema contra el que resulta de aplicar `alembic upgrade head`
- Entonces ambos declaran las mismas restricciones e índices sobre `tasks.source`/`external_key`

#### Scenario: La equivalencia de DDL se comprueba por definición, no por alembic check

- Dado que `alembic check` (1.14.0) no compara `postgresql_where` de índices parciales ni ninguna `CheckConstraint`, por lo que NO sirve como gate del espejado
- Cuando una prueba automatizada construye dos bases desechables (una con `Base.metadata.create_all` y otra con `alembic upgrade head`) y compara `pg_get_indexdef` de `uq_tasks_source_external_key_project` y `pg_get_constraintdef` de `ck_tasks_external_key_requires_source`
- Entonces las definiciones DDL son idénticas en ambas bases y cualquier divergencia del modelo respecto de la migración hace fallar la prueba

### Requirement: Vocabulario de `source`

`tasks.source` DEBE almacenarse como cadena libre, validada en la capa de
escritura, nunca como enumerado nativo de la base de datos. Cuando el origen
de una tarea es un conector, `source` DEBE ser exactamente el mismo valor
que identifica a ese conector en el resto del sistema (ningún valor
sintético ni renombrado). El valor `planner` NO DEBE usarse como `source`.

#### Scenario: Origen de conector coincide exactamente con el identificador del conector

- Dado un conector Microsoft 365 identificado como `microsoft365`
- Cuando se ancla una tarea proveniente de ese conector
- Entonces `tasks.source` queda exactamente en `"microsoft365"`, sin transformación

#### Scenario: `planner` no es un valor válido de `source`

- Dado un intento de anclar una tarea con `source="planner"`
- Cuando la capa de escritura valida el valor
- Entonces la escritura se rechaza, porque `planner` no pertenece al vocabulario permitido

### Requirement: Clave local y externa conviven como referencias distintas

El `task_key` local (código de proyecto + `task_number`) sigue siendo el
identificador legible de la plataforma; `external_key` DEBE exponerse como
referencia adicional de solo lectura, sin reemplazar ni alterar el cálculo
del `task_key` local. Ambos campos DEBEN aparecer en toda respuesta que
exponga una tarea completa (listado, detalle, tablero del panel de control),
sin requerir cambios adicionales en los servicios que ya construyen esa
respuesta a partir del modelo.

#### Scenario: Tarea importada expone ambas claves

- Dado una tarea importada con `task_key="SDM-42"` y `external_key="PROJ-123"`
- Cuando se consulta el detalle de la tarea
- Entonces la respuesta incluye ambas claves, cada una identificando su propio sistema

#### Scenario: Listado y tablero exponen los campos nuevos sin cambios de servicio

- Dado el listado de tareas por proyecto y el tablero del panel de control, ambos ya construidos a partir del modelo `Task`
- Cuando se consulta cualquiera de los dos tras esta migración
- Entonces ambas respuestas incluyen `source` y `external_key` sin que su lógica de construcción haya cambiado

### Requirement: Filtros de igualdad exacta por procedencia externa

`GET /projects/{id}/tasks` DEBE aceptar los parámetros opcionales `source` y
`external_key` como filtros de igualdad exacta, componibles simultáneamente
con cualquier otro filtro existente de la lista. Ninguno de los dos campos
DEBE habilitarse como criterio de ordenamiento. Este cambio NO DEBE agregar
un endpoint HTTP dedicado a la búsqueda por ancla externa.

#### Scenario: Filtro por source y external_key compone con otros filtros existentes

- Dado un proyecto con tareas de distinto `status` y distinta procedencia
- Cuando se consulta `GET /projects/{id}/tasks?status=in_progress&source=checklist_xlsx&external_key=T-05`
- Entonces solo se devuelve la tarea que cumple los tres criterios a la vez

#### Scenario: Filtro sin coincidencias devuelve colección vacía, no error

- Dado un proyecto sin ninguna tarea anclada a `source="jira"`
- Cuando se consulta `GET /projects/{id}/tasks?source=jira`
- Entonces la respuesta es una colección vacía con código `200`

### Requirement: Inmutabilidad del ancla de procedencia externa por API

`TaskCreate` y `TaskUpdate` NO DEBEN declarar `source` ni `external_key`
como campos aceptados. Cuando un cliente envía esos campos en el cuerpo de
una solicitud de creación o actualización de tarea, el sistema DEBE
ignorarlos sin producir un error de validación, y la tarea resultante DEBE
conservar el valor previo del ancla (`NULL` en creación; sin cambio en
actualización). Solo un servicio de importación, en el momento de crear la
tarea, o una operación de mantenimiento posterior DEBEN poder escribir estas
columnas.

#### Scenario: POST con external_key en el payload no lo persiste

- Dado un cliente que envía `POST /projects/{id}/tasks` con `external_key="T-05"` incluido en el cuerpo
- Cuando la tarea se crea
- Entonces la tarea resultante tiene `external_key=NULL`, sin error de validación

#### Scenario: PATCH con source no altera un ancla existente

- Dado una tarea ya anclada por un importador a `source="jira"`, `external_key="PROJ-1"`
- Cuando se hace `PATCH /tasks/{id}` incluyendo `source="mcp"` junto con un cambio válido de `status`
- Entonces el `status` se actualiza y el ancla original permanece intacta

### Requirement: Escritura del ancla reservada al caso de uso de creación

La escritura de `source`/`external_key` DEBE ocurrir por un único camino: el
caso de uso de creación de tarea, que acepta la procedencia como argumento de
palabra clave `external_origin` (el par `source`, `external_key`) ausente de
`TaskCreate` y no expuesto por el enrutador HTTP. Cuando ese argumento viene
informado, el caso de uso DEBE validar `source` contra el vocabulario
permitido, DEBE comprobar la unicidad dentro de la organización consultando la
costura de repositorio antes de insertar, y DEBE persistir ambos valores en la
misma escritura que crea la tarea, sin dejar un estado intermedio en el que la
fila exista sin su ancla. Si ya existe una tarea activa con ese par en
cualquier proyecto de la organización, la creación DEBE rechazarse con un
error de dominio de código estable y no DEBE insertar ninguna fila. Una
creación sin `external_origin` DEBE comportarse exactamente como hoy, con
ambas columnas en `NULL`. Este contrato es el que consumen los importadores de
los cambios 44 y 47; ninguno DEBE escribir el ancla por otra vía.

#### Scenario: create_task con external_origin válido persiste y expone el ancla

- Dado un proyecto sin ninguna tarea anclada a `source="jira"`, `external_key="PROJ-1"`
- Cuando el caso de uso crea una tarea pasando `external_origin=("jira", "PROJ-1")`
- Entonces la tarea persiste ambos valores y la respuesta de lectura los expone junto al `task_key` local

#### Scenario: Un ancla ya activa en la organización aborta la creación

- Dado una tarea activa anclada a `source="jira"`, `external_key="PROJ-1"` en el proyecto P1 de la organización A
- Cuando el caso de uso intenta crear otra tarea con `external_origin=("jira", "PROJ-1")` en el proyecto P2 de la misma organización A
- Entonces la creación se rechaza con un error de dominio de código estable y P2 no gana ninguna tarea

### Requirement: Costura de repositorio `TaskRepository.get_by_external_key`

`TaskRepository` DEBE exponer `get_by_external_key(organization_id, source,
external_key)`, que hace `JOIN` a `projects` y filtra por `organization_id`,
replicando el aislamiento de tenant del resto de las lecturas del
repositorio. La búsqueda DEBE excluir tanto las tareas con borrado suave como
las tareas cuyo proyecto tiene borrado suave, igual que la lectura existente
de tareas por organización. Cuando más de una fila cumple los criterios —
posible porque la garantía del motor es por proyecto — la costura DEBE
devolver siempre la misma, de forma determinista, en lugar de fallar. Esta
costura es el mecanismo que provee la garantía de unicidad org-wide
(documentada como responsabilidad del servicio, no del motor, en «Ancla de
procedencia externa»): el caso de uso de creación la consulta antes de
insertar, y todo importador DEBE consultarla antes de decidir entre crear y
reconciliar.

#### Scenario: Encuentra un ancla existente dentro de la organización

- Dado una tarea anclada a `source="jira"`, `external_key="PROJ-1"` en un proyecto de la organización A
- Cuando se llama `get_by_external_key(organization_id=A, source="jira", external_key="PROJ-1")`
- Entonces devuelve esa tarea

#### Scenario: Nunca cruza organizaciones

- Dado el mismo ancla `source="jira"`, `external_key="PROJ-1"` anclada en un proyecto de la organización A
- Cuando se llama `get_by_external_key(organization_id=B, source="jira", external_key="PROJ-1")` con una organización distinta
- Entonces no devuelve ningún resultado

#### Scenario: Excluye tareas y proyectos con borrado suave

- Dado una tarea con ese ancla que fue borrada suavemente (`is_active=false`), y otra tarea activa con ese mismo ancla cuyo proyecto fue borrado suavemente (`Project.is_active=false`)
- Cuando se llama `get_by_external_key` con la misma organización, `source` y `external_key`
- Entonces no devuelve ninguna de las dos

### Requirement: Sin seguimiento en task_history ni columnas fuera de alcance

`source` y `external_key` NO DEBEN agregarse a los campos rastreados por el
historial de cambios de la tarea, al ser inmutables por API. Este cambio NO
DEBE declarar `is_context` ni `merge_into` como columnas reales de `Task`;
ambos permanecen fuera de alcance.

#### Scenario: PATCH sin diff de procedencia externa en el historial

- Dado una tarea con `source`/`external_key` ya anclados por un importador
- Cuando se hace `PATCH /tasks/{id}` modificando un campo permitido como `status`
- Entonces el historial de la tarea no registra ninguna entrada relacionada con `source` ni `external_key`

#### Scenario: is_context y merge_into siguen fuera del modelo persistido

- Dado el modelo `Task` tras este cambio
- Cuando se inspeccionan sus columnas persistidas
- Entonces `is_context` sigue siendo un campo transitorio calculado en la respuesta y `merge_into` no existe como columna

### Requirement: Tipo de frontend para procedencia externa

La interfaz `Task` de `frontend/src/entities/workspace/workspace.model.ts`
DEBE incluir los campos opcionales `source?: string | null` y
`external_key?: string | null`. Este cambio NO DEBE agregar una insignia
visual de procedencia en la interfaz de usuario.

#### Scenario: El tipo Task incluye los campos opcionales

- Dado el tipo `Task` del frontend tras este cambio
- Cuando se compila el módulo de workspace
- Entonces `source` y `external_key` están disponibles como propiedades opcionales de tipo `string | null`

#### Scenario: TaskDetail hereda los campos sin cambios adicionales

- Dado que `TaskDetail extends Task`
- Cuando se usa una instancia de `TaskDetail` en el detalle de tarea
- Entonces `source` y `external_key` están disponibles sin ninguna edición adicional a `task-detail.model.ts`

## Referencias

- `openspec/specs/tasks/spec.md` (línea base)
- `openspec/specs/intake-items/spec.md` (precedente de ancla de procedencia)
- `agents/rules/solercia-persistence.md` (tenant obligatorio en toda lectura)
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` §5.4, §5.5, §6.5, §7
- `openspec/changes/40-jira-import-usuario/specs/tasks/spec.md:10-40` (contenido original reescrito y trasladado aquí; D7/D8)
- `openspec/changes/43-tareas-origen-externo/{proposal,exploration}.md`
