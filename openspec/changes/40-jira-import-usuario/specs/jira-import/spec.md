# Delta for jira-import

> Base: `openspec/specs/jira-import/spec.md`. Este delta AGREGA el flujo real de
> importación (listar proyectos, previsualizar, persistir de forma idempotente)
> sobre el adaptador Jira solo-lectura del cambio 18; MODIFICA la frontera de
> solo lectura para acotarla a los endpoints de extracción genérica (`import`,
> `import-file`), dejando `import-project` como la única vía que persiste.

## ADDED Requirements

### Requirement: Listado de proyectos Jira accesibles

`GET /connectors/{connector_id}/jira/projects` DEBE listar, vía `/rest/api/3/project/search`, los proyectos Jira accesibles con la cuenta conectada del usuario que llama. El endpoint DEBE restringirse a roles `admin`/`manager` (mismo RBAC que el resto de `jira_import`), DEBE responder `404` si el conector es de otra organización, y DEBE responder un error controlado en español colombiano formal si el usuario no tiene cuenta conectada o si sus credenciales están vencidas.

#### Scenario: Lista de proyectos accesibles
- Dado un conector Jira con cuenta conectada activa del usuario que llama
- Cuando llama `GET /connectors/{id}/jira/projects`
- Entonces recibe la lista de proyectos Jira accesibles con esa cuenta

#### Scenario: Sin cuenta conectada o credenciales vencidas
- Dado un usuario sin cuenta conectada o con credenciales vencidas
- Cuando llama `GET /connectors/{id}/jira/projects`
- Entonces recibe un error controlado en español colombiano formal, sin exponer el token

### Requirement: Previsualización sin persistir

`POST /connectors/{connector_id}/jira/preview` DEBE recibir un proyecto Jira y devolver conteos por tipo (épicas/historias/subtareas/bugs), sprints detectados y el mapeo propuesto de estados/tipos/estimaciones hacia la metodología destino (scrum). Este endpoint NUNCA DEBE crear, actualizar ni eliminar ninguna fila de la plataforma.

#### Scenario: Preview devuelve conteos y mapeo sin efectos
- Dado un proyecto Jira con épicas, historias, subtareas, bugs y sprints
- Cuando se llama `POST /connectors/{id}/jira/preview`
- Entonces la respuesta incluye los conteos por tipo, los sprints y el mapeo propuesto, y no se crea ninguna fila en la base de datos

#### Scenario: Proyecto ya no accesible al previsualizar
- Dado un proyecto Jira que dejó de ser accesible con la cuenta conectada
- Cuando se llama `POST /connectors/{id}/jira/preview` sobre ese proyecto
- Entonces la API responde un error controlado sin generar ningún dato

### Requirement: Conversión de la estimación original a horas y puntos

`NormalizedJiraIssue` DEBE incluir `original_estimate_seconds` (extraído de `timeoriginalestimate`); el flujo de preview/import DEBE convertirlo a horas con `seconds_to_hours` (cambio 34) para `estimation_hours`, y los story points existentes DEBEN mapearse a `estimation_points`.

#### Scenario: Estimación en segundos se convierte a horas
- Dado un issue Jira con `timeoriginalestimate = 14400` (segundos)
- Cuando se normaliza para preview o import
- Entonces `estimation_hours = 4` y los story points del issue quedan en `estimation_points`

### Requirement: Importación con jerarquía y clave local atómica

`POST /connectors/{connector_id}/jira/import-project` DEBE crear, por defecto, un proyecto local nuevo con metodología `scrum` (nombre/código editables desde el preview) y persistir épicas/historias/subtareas/bugs como `Task`, enlazando la jerarquía epic→story→subtask por `parent_task_id` en dos pasadas (crear todo, luego enlazar por clave padre). Una subtarea cuyo padre no esté en el conjunto importado DEBE quedar sin padre con una nota en el resumen. Cada tarea DEBE recibir su `task_key` local vía el contador atómico del proyecto (`task_counter`), conservando la clave Jira original como referencia visible.

#### Scenario: Jerarquía completa se enlaza correctamente
- Dado un proyecto Jira con una épica, dos historias hijas y una subtarea de cada historia
- Cuando se ejecuta el import
- Entonces las historias quedan con `parent_task_id` apuntando a la épica y las subtareas a su historia, cada una con `task_key` local y la clave Jira visible como referencia

#### Scenario: Subtarea huérfana
- Dado una subtarea cuyo padre no forma parte del proyecto importado
- Cuando se ejecuta el import
- Entonces la subtarea se crea sin padre y el resumen registra el caso

### Requirement: Idempotencia y reconciliación al reimportar

La importación DEBE anclar cada `Project`/`Sprint`/`Task` creado a `(source='jira', external_key)`, único dentro de la organización activa. Reimportar el mismo proyecto Jira DEBE reconciliar (actualizar título/estado/estimación/sprint) los ítems ya anclados en lugar de duplicarlos, y el resumen final DEBE distinguir creados/actualizados/omitidos/errores. Un conflicto ambiguo (mismo `external_key` con datos incompatibles) DEBE rechazarse con un mensaje claro, sin dejar el import a medias.

#### Scenario: Reimportar no duplica
- Dado un proyecto Jira ya importado previamente
- Cuando se ejecuta el import nuevamente sobre el mismo proyecto
- Entonces las tareas/sprints ya anclados se actualizan y el resumen reporta actualizados, sin crear filas nuevas

### Requirement: Mapeo de estado y de sprint a la metodología destino vía strategy

El estado Jira de cada issue DEBE mapearse a un estado permitido por la strategy de la metodología destino (scrum, vía `allowed_statuses()`), sin condicionales `if methodology == ...`; un estado sin homologación DEBE usar el fallback existente y quedar en el `NormalizationReport` del cambio 18. El estado de cada sprint Jira DEBE mapearse `future→draft`, `active→active`, `closed→closed` (estados de sprint del cambio 29), preservando sus fechas.

#### Scenario: Sprint future se importa como borrador
- Dado un sprint Jira en estado `future` con fechas planificadas
- Cuando se importa
- Entonces el sprint local nace `draft` con las mismas fechas

### Requirement: Homologación de asignado por email

El asignado de cada issue DEBE homologarse por coincidencia exacta de `emailAddress` contra los miembros de la organización activa. Si no hay coincidencia, la tarea DEBE crearse sin asignar, con una nota en la descripción indicando el asignado original de Jira.

#### Scenario: Asignado sin coincidencia
- Dado un issue Jira con un `emailAddress` que no corresponde a ningún miembro de la organización
- Cuando se importa
- Entonces la tarea se crea sin asignar y su descripción incluye una nota con el asignado original de Jira

## MODIFIED Requirements

### Requirement: Frontera solo-lectura estricta

`GET /connectors/{id}/jira/projects`, `POST /connectors/{id}/jira/preview`, `import` (JQL) e `import-file` DEBEN seguir siendo de solo lectura hacia la plataforma: NINGUNO de ellos DEBE crear `Task`, sprints, labels ni proyectos. La única excepción es `POST /connectors/{id}/jira/import-project` (cambio 40), que SÍ persiste de forma idempotente según los requisitos de este delta; fuera de esa vía explícita, ningún otro endpoint del módulo debe tener efectos secundarios en la base de datos.
(Previously: el import completo del módulo era de solo lectura sin excepción; no existía ninguna vía que persistiera `Project`/`Sprint`/`Task`.)

#### Scenario: Ningún efecto secundario en la plataforma
- Dado un import completado por `import` (JQL) o `import-file`
- Cuando se revisa el estado de la base de datos tras el import
- Entonces no existen nuevos `Task`, `Sprint`, `Label` ni filas de insumos persistidos originados por ese import

#### Scenario: import-project es la única vía que persiste
- Dado un import ejecutado vía `POST /connectors/{id}/jira/import-project`
- Cuando se revisa el estado de la base de datos
- Entonces existen los `Project`/`Sprint`/`Task` creados o reconciliados por esa llamada, y ningún otro endpoint del módulo generó efectos

## Referencias

- `openspec/specs/jira-import/spec.md` (línea base, cambio 18)
- `openspec/changes/40-jira-import-usuario/specs/tasks/spec.md` (ancla de procedencia externa)
- `openspec/changes/39-conector-capacidades/specs/connectors/spec.md` (RBAC y credenciales)
- `openspec/changes/29-sprint-borrador/specs/sprints/spec.md` (estado `draft`)
