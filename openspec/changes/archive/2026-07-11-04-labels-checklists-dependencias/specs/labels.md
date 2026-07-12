# Especificación: Labels (etiquetas de tarea)

## Propósito

Etiquetas configurables por proyecto para clasificar y filtrar tareas, con un vínculo M:N reversible que no afecta la tarea cuando la etiqueta se elimina.

## Modelo de datos

- **Label** (Pk + Timestamp + SoftDelete; scope de proyecto vía `project_id`): `name` (str), `color` (str). El `name` DEBE ser único entre las etiquetas activas de un mismo proyecto.
- **TaskLabel** (Pk + Timestamp + SoftDelete): `task_id`, `label_id` — M:N Task↔Label; la etiqueta y la tarea DEBEN pertenecer al mismo proyecto.

## Requisitos

### Requisito: CRUD de etiquetas con nombre único por proyecto

La API DEBE permitir crear, listar, actualizar y eliminar (borrado suave) etiquetas con scope de proyecto (`name`, `color`). El `name` DEBE ser único entre las etiquetas activas de un mismo proyecto; el mismo `name` PUEDE repetirse en proyectos distintos.

#### Escenario: Creación exitosa

- DADO un proyecto sin etiquetas
- CUANDO se crea una etiqueta con `name="Urgente"` y `color="#FF0000"`
- ENTONCES la API responde 201 con la etiqueta creada

#### Escenario: Nombre duplicado en el mismo proyecto

- DADO un proyecto con la etiqueta activa "Urgente"
- CUANDO se intenta crear otra etiqueta con `name="Urgente"` en el mismo proyecto
- ENTONCES la API rechaza la creación con 422

#### Escenario: Mismo nombre en proyectos distintos

- DADO dos proyectos distintos sin relación entre sí
- CUANDO cada uno crea una etiqueta con `name="Urgente"`
- ENTONCES ambas creaciones son exitosas

### Requisito: Asignación y desasignación de etiquetas a tareas

La API DEBE permitir vincular (asignar) y desvincular (desasignar) una etiqueta a una tarea mediante `TaskLabel`, exigiendo que la etiqueta y la tarea pertenezcan al mismo proyecto.

#### Escenario: Asignar etiqueta a tarea del mismo proyecto

- DADO una tarea y una etiqueta activas del mismo proyecto
- CUANDO se asigna la etiqueta a la tarea
- ENTONCES la tarea queda vinculada y la etiqueta aparece en su detalle

#### Escenario: Asignar etiqueta de otro proyecto

- DADO una tarea del proyecto A y una etiqueta del proyecto B
- CUANDO se intenta asignar la etiqueta a la tarea
- ENTONCES la API rechaza la asignación con 422

#### Escenario: Desasignar etiqueta

- DADO una tarea con la etiqueta "Urgente" asignada
- CUANDO se desasigna la etiqueta
- ENTONCES la tarea deja de listar esa etiqueta en su detalle

### Requisito: Filtro de tareas por etiqueta

`GET /projects/{id}/tasks` DEBE aceptar un filtro `label_id` y devolver únicamente las tareas activas vinculadas a esa etiqueta.

#### Escenario: Filtrado por etiqueta

- DADO un proyecto con 5 tareas, 2 con la etiqueta "Urgente" y 3 sin ella
- CUANDO se consulta la lista con `label_id` de "Urgente"
- ENTONCES la respuesta incluye únicamente las 2 tareas etiquetadas

### Requisito: Eliminación de etiqueta sin afectar tareas

Eliminar (borrado suave) una etiqueta DEBE desvincularla de todas sus tareas (borrado suave de los `TaskLabel` asociados) sin eliminar ni modificar las tareas mismas.

#### Escenario: Borrado de etiqueta con tareas vinculadas

- DADO una etiqueta vinculada a 3 tareas activas
- CUANDO se elimina la etiqueta
- ENTONCES las 3 tareas permanecen activas e intactas, y la etiqueta ya no aparece en su detalle ni en el filtro por `label_id`
