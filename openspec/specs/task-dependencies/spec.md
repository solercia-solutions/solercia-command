# Especificación: Dependencias tarea-tarea (task-dependencies)

> **Origen**: cambio [04-labels-checklists-dependencias](../../changes/archive/2026-07-11-04-labels-checklists-dependencias/)

## Propósito

Modelar bloqueos entre tareas del mismo proyecto (`blocks` / `is_blocked_by`) sin permitir ciclos, exponiendo el estado de bloqueo en el detalle de la tarea para alimentar la vista ejecutiva de riesgos.

## Modelo de datos

- **TaskDependency** (Pk + Timestamp + SoftDelete; módulo/tabla propios `task_links`/`task_dependencies`, clase `TaskDependency`, para no colisionar con el módulo `dependencies` de áreas organizacionales): `task_id` (origen), `depends_on_task_id` (tarea bloqueante), `type`. Se almacena una única dirección por enlace; ambos sentidos (`blocks` / `is_blocked_by`) son legibles desde cualquiera de las dos tareas relacionadas.

## Requisitos

### Requisito: Enlazar tareas del mismo proyecto

La API DEBE permitir crear un enlace de dependencia entre dos tareas activas que pertenezcan al mismo proyecto, exigiendo que ambas existan y sean distintas entre sí.

#### Escenario: Enlace válido

- DADO dos tareas activas del mismo proyecto, A y B
- CUANDO se crea el enlace "A is_blocked_by B" (equivalente a "B blocks A")
- ENTONCES la API responde 201 y ambas tareas exponen la relación desde su respectiva perspectiva

#### Escenario: Tareas de proyectos distintos

- DADO una tarea del proyecto 1 y otra del proyecto 2
- CUANDO se intenta enlazarlas
- ENTONCES la API rechaza la creación con 422

### Requisito: Prevención de ciclos directos y transitivos

Antes de persistir un enlace, la API DEBE recorrer el grafo de dependencias existente del proyecto y rechazar, con 422 y un código de error explícito, cualquier enlace que introduzca un ciclo, directo o transitivo.

#### Escenario: Ciclo directo A→B→A

- DADO un enlace existente "A is_blocked_by B"
- CUANDO se intenta crear el enlace inverso "B is_blocked_by A"
- ENTONCES la API rechaza la creación con 422 y un código de error de ciclo

#### Escenario: Ciclo transitivo A→B→C→A

- DADO los enlaces existentes "A is_blocked_by B" y "B is_blocked_by C"
- CUANDO se intenta crear el enlace "C is_blocked_by A"
- ENTONCES la API rechaza la creación con 422 y un código de error de ciclo

### Requisito: Desenlazar y listar dependencias

La API DEBE permitir eliminar (borrado suave) un enlace existente y listar, por tarea, las dependencias en ambas direcciones (tareas que bloquea y tareas que la bloquean).

#### Escenario: Listado bidireccional

- DADO el enlace "A is_blocked_by B"
- CUANDO se consulta la lista de dependencias de A y la de B
- ENTONCES A muestra a B como bloqueante y B muestra a A como bloqueada

#### Escenario: Desenlazar

- DADO el enlace activo "A is_blocked_by B"
- CUANDO se elimina el enlace
- ENTONCES A ya no reporta a B como bloqueante en su detalle

### Requisito: Estado de bloqueo en el detalle de tarea

`GET /tasks/{id}` DEBE reportar si la tarea está actualmente bloqueada, entendiendo como bloqueo la existencia de al menos un enlace `is_blocked_by` activo hacia una tarea que no está en estado completado o cancelado.

#### Escenario: Tarea bloqueada

- DADO la tarea A con un enlace `is_blocked_by` activo hacia la tarea B, B en estado `in_progress`
- CUANDO se consulta `GET /tasks/{id}` de A
- ENTONCES el detalle reporta la tarea como bloqueada

#### Escenario: Bloqueo resuelto al completar la tarea bloqueante

- DADO la tarea A bloqueada por B
- CUANDO B pasa a estado completado
- ENTONCES `GET /tasks/{id}` de A ya no reporta la tarea como bloqueada
