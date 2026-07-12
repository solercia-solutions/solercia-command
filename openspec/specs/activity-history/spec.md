# activity-history Specification

## Purpose

Changelog automático de mutaciones de tarea: quién cambió qué, cuándo y de qué valor a qué valor. Alimenta el historial por tarea y la actividad por usuario/día que usa el cruce "asignado vs realizado" en el dashboard. Es de solo lectura para los clientes: nadie edita ni borra el historial.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/tasks/{task_id}/history | Historial completo de una tarea (paginado) |
| GET | /api/v1/users/{user_id}/activity | Cambios que un usuario provocó, filtro por día/rango (paginado) |

Modelo `TaskHistory` (Pk + Timestamp; SIN soft delete — append-only; scope de tenant vía join a Task→Project): `task_id`, `actor_id?` (null = actor de sistema), `actor_type` (`user`|`system`), `field`, `old_value?`, `new_value?`, `changed_at`.

## Requirements

### Requirement: Captura automática en mutaciones de usuario

Cuando una tarea cambia `status`, `assignee_id`, `estimation_points`/`estimation_hours`, `sprint_id` o `priority` vía `PATCH /tasks/{id}`, el sistema MUST crear una fila de `TaskHistory` por cada campo modificado, con el `actor_id` del usuario autenticado, el campo, el valor anterior y el nuevo valor.

#### Scenario: Cambio de estado deja historial

- GIVEN una tarea en estado `to_do`
- WHEN un colaborador la mueve a `in_progress` vía `PATCH /tasks/{id}`
- THEN se crea una fila de historial con `field=status`, `old_value=to_do`, `new_value=in_progress` y `actor_id` del colaborador

#### Scenario: Múltiples campos en un solo PATCH

- GIVEN una tarea sin asignar y sin estimación
- WHEN un `PATCH` reasigna la tarea y agrega `estimation_hours` en la misma petición
- THEN se crean dos filas de historial, una por cada campo modificado

#### Scenario: Sin cambio, sin historial

- GIVEN una tarea en estado `in_progress`
- WHEN un `PATCH` envía `status=in_progress` (mismo valor)
- THEN no se crea fila de historial para ese campo

### Requirement: Captura en mutaciones generadas por el sistema

Cuando un proceso del sistema modifica los campos observados sin una petición de usuario directa (por ejemplo, el cierre de sprint que mueve tareas incompletas al backlog, o el motor de alertas cuando reescribe un campo de tarea), el sistema MUST crear historial con `actor_type=system` y `actor_id=null`.

#### Scenario: Cierre de sprint deja historial de sistema

- GIVEN un sprint activo con tareas incompletas asignadas a él
- WHEN se cierra el sprint (`POST /sprints/{id}/close`) y esas tareas vuelven al backlog
- THEN cada tarea afectada tiene una fila de historial con `field=sprint_id`, `old_value` = el sprint cerrado, `new_value=null` y `actor_type=system`

### Requirement: Historial por tarea

`GET /tasks/{id}/history` MUST devolver el listado paginado de cambios de esa tarea, ordenado por `changed_at` descendente por defecto, con `?page&size&sort&order` y `meta {page, size, total}`.

#### Scenario: Timeline de una tarea

- GIVEN una tarea con 3 cambios registrados en distintos momentos
- WHEN se consulta `GET /tasks/{id}/history`
- THEN devuelve las 3 filas ordenadas del cambio más reciente al más antiguo

### Requirement: Actividad por usuario y día

`GET /users/{id}/activity` MUST devolver los cambios que un usuario provocó como actor, filtrables por día o rango de fechas, paginado.

#### Scenario: Actividad de un día específico

- GIVEN un usuario que hizo 2 cambios el día D y 1 cambio otro día
- WHEN consulta `GET /users/{id}/activity?date=D`
- THEN devuelve solo los 2 cambios del día D

### Requirement: Historial de solo lectura

El sistema MUST NOT exponer endpoints para editar o borrar filas de `TaskHistory`; una vez creada, una fila es inmutable.

#### Scenario: Sin ruta de edición

- GIVEN una fila de historial existente
- WHEN se intenta un `PATCH` o `DELETE` sobre `/tasks/{id}/history/{history_id}`
- THEN la API no expone esa ruta (404 de enrutamiento, no de autorización)

## Limitaciones y deuda conocida

- Ninguna en este momento.

## Referencias

- backend/app/modules/activity/ (router.py, service.py, repository.py, models.py, schemas.py, recorder.py)
- backend/alembic/versions/ (migración xxxx_add_time_logs_and_task_history.py)
