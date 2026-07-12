# Especificación: Checklists de tarea

> **Origen**: cambio [04-labels-checklists-dependencias](../../changes/archive/2026-07-11-04-labels-checklists-dependencias/)

## Propósito

Desglose interno del "cómo" ejecutar una tarea sin crear subtareas formales, mediante checklists con ítems marcables y progreso agregado visible en el detalle de la tarea.

## Modelo de datos

- **TaskChecklist** (Pk + Timestamp + SoftDelete): `task_id`, `title`, `order`.
- **ChecklistItem** (Pk + Timestamp + SoftDelete): `checklist_id`, `text`, `is_done` (bool, default `false`), `order`.

## Requisitos

### Requisito: CRUD de checklists por tarea

La API DEBE permitir crear, listar, actualizar y eliminar (borrado suave) checklists (`TaskChecklist`) asociados a una tarea, cada uno con un título.

#### Escenario: Creación de checklist

- DADO una tarea sin checklists
- CUANDO se crea un checklist con `title="Antes de publicar"`
- ENTONCES la API responde 201 y el checklist aparece en el detalle de la tarea

### Requisito: CRUD y marcado de ítems de checklist

La API DEBE permitir crear, actualizar, eliminar (borrado suave) y reordenar ítems (`ChecklistItem`: `text`, `order`) dentro de un checklist, y marcar o desmarcar `is_done` mediante un endpoint de toggle.

#### Escenario: Alternar estado de un ítem

- DADO un ítem con `is_done=false`
- CUANDO se invoca el toggle del ítem
- ENTONCES `is_done` pasa a `true`

#### Escenario: Reordenar ítems

- DADO un checklist con 3 ítems en orden 1, 2, 3
- CUANDO se actualiza el `order` de uno de ellos
- ENTONCES la lista de ítems refleja el nuevo orden

### Requisito: Progreso agregado en el detalle de tarea

`GET /tasks/{id}` DEBE reportar, por cada checklist, la cuenta de ítems completados sobre el total (`done/total`), y un agregado global sumando todos los checklists de la tarea.

#### Escenario: Progreso de un checklist

- DADO un checklist con 5 ítems, 2 marcados como `is_done=true`
- CUANDO se consulta `GET /tasks/{id}`
- ENTONCES el detalle reporta el progreso del checklist como 2/5

#### Escenario: Progreso agregado con varios checklists

- DADO una tarea con dos checklists: uno con progreso 2/5 y otro con 1/2
- CUANDO se consulta `GET /tasks/{id}`
- ENTONCES el detalle reporta, además del progreso por checklist, un total agregado de 3/7
