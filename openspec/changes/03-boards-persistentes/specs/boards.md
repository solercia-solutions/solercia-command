# Boards — Especificación (nueva)

## Propósito

Persistir el tablero por proyecto (`Board` + `BoardColumn`) sembrado desde `strategy.default_columns()`, habilitar el movimiento de tareas entre columnas, aplicar límites WIP y exponer una API de configuración de columnas en runtime que hace usable la metodología `custom`.

## Requirements

### Requirement: Siembra del board al crear el proyecto

El sistema DEBE crear exactamente un `Board` por proyecto en el momento de creación, con una `BoardColumn` por cada elemento devuelto por `strategy.default_columns()`, en el mismo orden, cada una con `status_key` derivado de la strategy y `wip_limit` nulo por defecto.

#### Scenario: Siembra para metodología con columnas fijas

- DADO un proyecto nuevo con metodología kanban
- CUANDO se crea el proyecto
- ENTONCES se persiste un `Board` con las columnas `Backlog`, `Doing`, `Done` en ese orden, cada una con su `status_key` correspondiente

#### Scenario: Siembra vacía para custom

- DADO un proyecto nuevo con metodología custom
- CUANDO se crea el proyecto
- ENTONCES se persiste un `Board` con cero `BoardColumn`

### Requirement: Estructura de BoardColumn

Cada `BoardColumn` DEBE tener `name` (texto visible), `status_key` (estado que adopta la tarea al entrar), `order` (entero, posición en el board) y `wip_limit` (entero opcional, nulo = sin límite).

#### Scenario: Columna sin límite WIP no restringe movimientos

- DADO una columna con `wip_limit` nulo
- CUANDO se mueven tareas a esa columna, sin importar la cantidad
- ENTONCES ningún movimiento se rechaza por WIP

### Requirement: Bloqueo de custom sin columnas

Mientras el `Board` de un proyecto tenga cero `BoardColumn`, el sistema DEBE rechazar tanto la creación de tareas como el movimiento de tareas en ese proyecto, con un error explícito indicando que el board no tiene columnas configuradas.

#### Scenario: Creación bloqueada sin columnas

- DADO un proyecto custom cuyo board no tiene columnas
- CUANDO se intenta crear una tarea
- ENTONCES la API rechaza la creación con un error explícito (board sin columnas)

#### Scenario: Custom queda usable tras configurar la primera columna

- DADO un proyecto custom cuyo board tiene 0 columnas
- CUANDO se agrega la primera columna vía la API de configuración runtime
- ENTONCES la creación de tareas en ese proyecto queda habilitada

### Requirement: Configuración runtime de columnas

El sistema DEBE exponer una API para renombrar, reordenar, agregar y quitar columnas de un board existente, en cualquier metodología.

#### Scenario: Renombrar columna no afecta tareas asignadas

- DADO un board con una columna `Doing` (status_key `doing`) con tareas asignadas
- CUANDO se renombra la columna a `En progreso`
- ENTONCES el nombre se actualiza y las tareas asignadas conservan su `status_key` sin cambios

#### Scenario: Reordenar columnas

- DADO un board con columnas `[A, B, C]` en ese orden
- CUANDO se solicita el nuevo orden `[C, A, B]`
- ENTONCES una consulta posterior del board devuelve las columnas en el orden `[C, A, B]`

#### Scenario: Agregar columna a un board custom vacío

- DADO un board custom sin columnas
- CUANDO se agrega una columna `Backlog` con `status_key` `backlog`
- ENTONCES el board queda con una columna y admite creación de tareas

### Requirement: Reglas de eliminación de columnas con tareas

Eliminar una columna sin tareas asignadas DEBE completarse sin restricciones. Eliminar una columna que aún tiene tareas asignadas DEBE rechazarse por defecto; DEBE aceptarse únicamente si la solicitud indica una columna destino válida del mismo board, en cuyo caso las tareas afectadas DEBEN reasignarse a esa columna (actualizando `board_column_id` y `status`) antes de completar la eliminación.

#### Scenario: Eliminar columna vacía

- DADO una columna sin tareas asignadas
- CUANDO se solicita eliminarla
- ENTONCES la columna se elimina y el board queda con una columna menos

#### Scenario: Eliminar columna con tareas sin destino de reasignación

- DADO una columna con al menos una tarea asignada
- CUANDO se solicita eliminarla sin indicar columna destino
- ENTONCES la operación se rechaza con un error explícito (409/422)

#### Scenario: Eliminar columna con tareas y destino de reasignación válido

- DADO una columna con tareas asignadas y una columna destino válida indicada en la solicitud
- CUANDO se solicita eliminarla
- ENTONCES las tareas se reasignan a la columna destino y la columna original se elimina

### Requirement: Límite WIP al mover tareas

En columnas con `wip_limit` no nulo, el sistema DEBE contar las tareas activas ya asignadas a la columna destino al momento del movimiento y DEBE rechazar el movimiento (409/422) si aceptarlo excede el `wip_limit`.

#### Scenario: Movimiento rechazado por exceder el WIP

- DADO una columna kanban con `wip_limit = 3` y 3 tareas activas ya asignadas
- CUANDO se intenta mover una cuarta tarea a esa columna
- ENTONCES la operación se rechaza con un error explícito indicando que se excede el límite WIP

#### Scenario: Movimiento aceptado dentro del WIP

- DADO una columna con `wip_limit = 3` y 2 tareas activas
- CUANDO se mueve una tercera tarea a esa columna
- ENTONCES el movimiento se acepta
