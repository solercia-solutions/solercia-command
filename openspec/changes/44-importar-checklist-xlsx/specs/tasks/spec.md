# Delta for tasks

> Base: `openspec/specs/tasks/spec.md`. Este delta AGREGA `context_group` y
> `merge_into_task_id` como columnas nulables de `Task` (migración `0027`),
> el tercer parámetro de palabra clave `completed_at_override` en el caso de
> uso de creación (réplica exacta del patrón `external_origin` del cambio
> 43), y la insignia de procedencia en el frontend que el cambio 43 difirió
> explícitamente (D6 de `43/exploration.md`) por no existir todavía ninguna
> tarea anclada. `TaskCreate` y `TaskUpdate` NO se tocan: ni el ancla externa,
> ni `context_group`, ni `merge_into_task_id`, ni `completed_at` se vuelven
> escribibles por API. El campo transitorio `is_context` (calculado en
> `TaskService._to_read` bajo el filtro `assignee_id`, documentado en
> `openspec/specs/tasks/spec.md:234-246`) permanece INTACTO con su
> significado actual; este cambio NUNCA lo convierte en columna ni reutiliza
> su nombre para `context_group`.

## ADDED Requirements

### Requirement: Columnas context_group y merge_into_task_id

`Task` DEBE tener las columnas nulables `context_group VARCHAR(80)` y `merge_into_task_id UUID` (auto-FK a `tasks.id`, `ondelete="SET NULL"`, con la misma forma que `parent_task_id`), agregadas por la migración Alembic aditiva `0027` (`down_revision="0026"`) y espejadas en `Task.__table_args__`, porque el harness de pruebas construye el esquema con `Base.metadata.create_all`. `context_group` no nulo indica que la tarea es de contexto (agrupación de referencia sobre trabajo ya cubierto por otra tarea, no un ítem de trabajo real); su valor es el nombre del grupo. Ninguna de las dos columnas afecta el cálculo existente de `is_context` transitorio en `TaskRead`, que permanece intacto con su significado actual.

#### Scenario: Migración agrega ambas columnas sin afectar tareas existentes

- DADO un esquema en la revisión `0026` con tareas ya existentes
- CUANDO se aplica `alembic upgrade 0027`
- ENTONCES las tareas existentes conservan sus valores y ambas columnas nuevas quedan en `NULL`

#### Scenario: Downgrade limpio conserva las filas

- DADO el esquema en la revisión `0027` con tareas de contexto y tareas fusionadas
- CUANDO se aplica `alembic downgrade 0026`
- ENTONCES `context_group` y `merge_into_task_id` desaparecen del esquema y ninguna fila se pierde

#### Scenario: Borrar la tarea superviviente libera el puntero de la fusionada

- DADO una tarea `A` con `merge_into_task_id` apuntando a la tarea superviviente `B`
- CUANDO `B` se elimina (borrado físico, fuera del alcance HTTP normal)
- ENTONCES `A.merge_into_task_id` queda en `NULL` (`ondelete="SET NULL"`)

#### Scenario: is_context transitorio sigue funcionando igual

- DADO un listado filtrado por `assignee_id` con un padre de contexto (semántica existente de `is_context`, `openspec/specs/tasks/spec.md:234-246`)
- CUANDO se consulta tras esta migración
- ENTONCES el comportamiento de `is_context` es idéntico al que tenía antes de este cambio

### Requirement: Exposición de solo lectura de context_group y merge_into_task_id

`TaskRead` DEBE incluir `context_group` y `merge_into_task_id` como campos de solo lectura. `TaskCreate` y `TaskUpdate` NUNCA DEBEN aceptar ninguno de los dos campos; si un cliente los envía en el cuerpo de una solicitud de creación o actualización, el sistema DEBE ignorarlos sin producir un error de validación, y la tarea resultante DEBE conservar su valor previo (`NULL` en creación; sin cambio en actualización).

#### Scenario: El detalle de una tarea de contexto expone context_group

- DADO una tarea con `context_group="Operación DLP/SearchInform"`
- CUANDO se consulta su detalle
- ENTONCES la respuesta incluye `context_group="Operación DLP/SearchInform"`

#### Scenario: POST con context_group en el payload no lo persiste

- DADO un cliente que envía `POST /projects/{id}/tasks` con `context_group="X"` incluido en el cuerpo
- CUANDO la tarea se crea
- ENTONCES la tarea resultante tiene `context_group=NULL`, sin error de validación

#### Scenario: PATCH con merge_into_task_id no altera un vínculo existente

- DADO una tarea ya anclada por el importador con `merge_into_task_id` apuntando a otra tarea
- CUANDO se hace `PATCH /tasks/{id}` incluyendo un `merge_into_task_id` distinto junto con un cambio válido de `status`
- ENTONCES el `status` se actualiza y `merge_into_task_id` permanece intacto

### Requirement: completed_at_override keyword-only aplicado solo en el estado de cierre

`TaskService.create_task` DEBE aceptar el argumento de palabra clave `completed_at_override: datetime | None = None`, ausente de `TaskCreate` y no expuesto por el enrutador HTTP. Cuando se informa y el estado resuelto de la tarea creada ES el estado de cierre de la strategy de metodología del proyecto (`allowed_statuses()[-1]`), el caso de uso DEBE persistir `completed_at` con ese valor en lugar de `datetime.now(UTC)`. Cuando el estado resuelto NO es el de cierre, `completed_at_override` DEBE ignorarse.

#### Scenario: Crear en la columna de cierre con override persiste la fecha exacta

- DADO una creación de tarea con `completed_at_override=2026-08-16T00:00:00Z` cuyo estado resuelto es el de cierre del proyecto
- CUANDO se crea la tarea
- ENTONCES `completed_at` queda fijado exactamente en `2026-08-16T00:00:00Z`, no en la fecha de creación

#### Scenario: Crear en otra columna con override informado lo ignora

- DADO una creación de tarea con `completed_at_override` informado cuyo estado resuelto NO es el de cierre
- CUANDO se crea la tarea
- ENTONCES `completed_at` queda `NULL`, sin aplicar el valor informado

#### Scenario: Crear sin override en la columna de cierre se comporta igual que hoy

- DADO una creación de tarea sin `completed_at_override` cuyo estado resuelto es el de cierre
- CUANDO se crea la tarea
- ENTONCES `completed_at` queda fijado en la fecha y hora de creación, exactamente igual que antes de este cambio

### Requirement: Insignia de procedencia de solo lectura junto al task_key

El frontend DEBE mostrar una insignia de solo lectura junto al `task_key`, visible ÚNICAMENTE cuando `external_key` no es nulo, con un `aria-label` que identifica el sistema de origen (`source`). La insignia NUNCA DEBE ser editable ni convertirse en un control interactivo más allá de mostrar información.

#### Scenario: Tarea importada muestra la insignia con el origen

- DADO una tarea con `external_key="T-05"` y `source="checklist_xlsx"`
- CUANDO se renderiza su `task_key`
- ENTONCES aparece la insignia de procedencia junto a él, con un `aria-label` que identifica `checklist_xlsx` como origen

#### Scenario: Tarea creada manualmente no muestra insignia

- DADO una tarea creada manualmente, con `external_key=NULL`
- CUANDO se renderiza su `task_key`
- ENTONCES no aparece ninguna insignia de procedencia junto a él

## Referencias

- `openspec/specs/tasks/spec.md` (línea base)
- `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` (ancla `external_origin`, `get_by_external_key`, patrón de argumento keyword-only replicado por `completed_at_override`)
- `openspec/changes/44-importar-checklist-xlsx/specs/{project-hierarchy,boards,dashboard-executive}/spec.md` (consumo de `context_group` y `excluded_from_progress`)
- `~/.claude/rules/ux-front.md` (revisión `ux-psicologia` obligatoria antes de cerrar la insignia)
- `agents/rules/solercia-persistence.md`
- `openspec/changes/44-importar-checklist-xlsx/{proposal,exploration}.md`
