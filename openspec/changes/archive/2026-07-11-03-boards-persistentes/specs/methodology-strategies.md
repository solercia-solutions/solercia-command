# Delta for methodology-strategies

## MODIFIED Requirements

### Requirement: Estados permitidos por metodología

`Task.status` DEBE validarse contra `allowed_statuses()` de la strategy del proyecto; un estado fuera de la lista DEBE rechazarse. Para las metodologías planner, kanban y scrum, `allowed_statuses()` DEBE seguir derivándose del conjunto fijo definido por cada strategy, sin cambios de comportamiento. Para la metodología custom, `allowed_statuses()` DEBE derivarse dinámicamente de los `status_key` de las `BoardColumn` persistidas del proyecto (la strategy delega en el board persistido); la strategy custom NUNCA DEBE hardcodear un conjunto de estados propio ni introducir condicionales `if methodology == ...` para resolverlo.
(Previously: `allowed_statuses()` de custom devolvía siempre una lista vacía fija, sin relación con ningún dato persistido, porque no existía `Board`/`BoardColumn`.)

#### Scenario: Validación de estado en metodología fija (sin cambios)

- DADO un proyecto con metodología planner
- CUANDO se intenta mover una tarea al estado `in_review`
- ENTONCES la operación es rechazada (estado no permitido por la strategy)

#### Scenario: allowed_statuses() de custom lee las columnas persistidas

- DADO un proyecto custom cuyo board tiene columnas con `status_key` `todo` y `doing`
- CUANDO se consulta `allowed_statuses()` de la strategy custom del proyecto
- ENTONCES devuelve exactamente `["todo", "doing"]`, leídos desde las columnas persistidas

#### Scenario: allowed_statuses() de custom vacío bloquea el proyecto

- DADO un proyecto custom cuyo board no tiene columnas
- CUANDO se consulta `allowed_statuses()`
- ENTONCES devuelve una lista vacía y la creación/movimiento de tareas del proyecto queda bloqueada (ver boards.md)

## ADDED Requirements

### Requirement: default_columns() sigue siendo la fuente de siembra para metodologías fijas

Para planner, kanban y scrum, `default_columns()` DEBE seguir siendo el mecanismo de origen de las columnas sembradas al crear el proyecto, sin cambios en su valor de retorno. custom DEBE seguir retornando `[]` desde `default_columns()` (el board nace vacío); la diferencia introducida por este cambio es que ese resultado ahora se PERSISTE como cero `BoardColumn`, en lugar de descartarse como lista efímera.

#### Scenario: default_columns() persiste columnas al crear el proyecto

- DADO un proyecto nuevo con metodología scrum
- CUANDO se crea el proyecto
- ENTONCES `default_columns()` retorna `["To Do", "In Progress", "In Review", "Done"]` y esas 4 columnas quedan persistidas en el board
