# Delta for tasks

> Base: `openspec/specs/tasks/spec.md`. Este delta AGREGA el ancla de
> procedencia externa (`source` + `external_key`) que permite reimportar
> tareas desde sistemas externos sin duplicar. Los requisitos «Ancla de
> procedencia externa» y «Clave local y externa conviven como referencias
> distintas», originalmente esbozados en
> `openspec/changes/40-jira-import-usuario/specs/tasks/spec.md:10-40`, quedan
> reescritos y trasladados aquí (decisión D7): el texto original del 40
> prometía unicidad org-wide sin distinguir motor de servicio; este delta
> corrige esa brecha explicitando qué garantiza cada capa. El requisito
> «Reconciliación idempotente por procedencia externa» permanece en el 40 por
> ser comportamiento del importador, no del modelo de datos. No modifica
> ningún requisito existente de clave legible, estados, boards o filtros
> previos.
>
> El requisito «Escritura del ancla reservada al caso de uso de creación» es el
> registro durable de la forma `external_origin` que consumen los cambios 44 y
> 47: sin él, el validador de vocabulario no tendría llamador y cada importador
> inventaría su propia manera de persistir la procedencia.

## ADDED Requirements

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
