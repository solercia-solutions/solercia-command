# Delta for api-conventions — Auditoría created_by / updated_by

Requisito transversal: aplica exactamente a los **11 modelos que llevan `SoftDeleteMixin`** — AlertRule, Attachment, TaskComment, Dependency, Menu, Organization, Project, Role, Sprint, Task y User —, no a un único endpoint. El criterio es mecánico ("modelo con `SoftDeleteMixin`"), NO "tenant-scoped": `Menu` es un catálogo GLOBAL sin tenant y SÍ se audita. `Notification` (sin `SoftDeleteMixin`, generada por el sistema) queda excluida.

## ADDED Requirements

### Requirement: Auditoría automática created_by / updated_by

Cada uno de los 11 modelos con `SoftDeleteMixin` DEBE incluir columnas `created_by` y `updated_by` (UUID nullable, referencia a `users.id`). El backend DEBE poblarlas automáticamente a partir del usuario autenticado resuelto por la dependency de autenticación de FastAPI; NUNCA DEBEN aceptarse como input directo del cliente.

- En creación (`POST`), el service DEBE asignar `created_by = usuario_actual.id` y `updated_by = usuario_actual.id`.
- En modificación (`PATCH`), el service DEBE asignar `updated_by = usuario_actual.id` sin alterar `created_by`.
- Los registros existentes antes de aplicar la migración DEBEN quedar con `created_by`/`updated_by` en `NULL` — no hay backfill histórico.
- La migración Alembic que agrega las columnas DEBE ser aditiva y reversible (`downgrade` elimina las columnas sin pérdida de otros datos).

#### Scenario: created_by poblado en creación

- GIVEN un usuario autenticado con id `U1`
- WHEN crea un recurso de dominio (por ejemplo, una tarea) vía `POST`
- THEN el registro persistido tiene `created_by = U1` y `updated_by = U1`

#### Scenario: updated_by poblado en modificación

- GIVEN un recurso existente creado originalmente por el usuario `U1`
- WHEN el usuario `U2` lo modifica vía `PATCH`
- THEN el registro persistido tiene `updated_by = U2`
- AND `created_by` conserva el valor original `U1`

#### Scenario: Filas preexistentes sin auditoría

- GIVEN un registro creado antes de aplicar la migración de auditoría
- WHEN se consulta ese registro después de la migración
- THEN `created_by` y `updated_by` son `NULL`
- AND la API no falla al serializar el registro (campos opcionales en la respuesta)

### Requirement: Exposición de auditoría en respuestas

Los endpoints de detalle y de lista de los modelos auditados DEBEN exponer `created_by` y `updated_by` en el `data` de la respuesta. El valor DEBE ser `null` cuando el registro no tenga auditoría poblada (fila preexistente a la migración).

#### Scenario: Respuesta de detalle incluye campos de auditoría

- GIVEN una tarea creada después de aplicar la migración de auditoría
- WHEN se consulta `GET /api/v1/tasks/{id}`
- THEN el cuerpo `data` incluye `created_by` y `updated_by` con los UUID correspondientes

#### Scenario: Respuesta de detalle con auditoría nula

- GIVEN una tarea creada antes de aplicar la migración de auditoría
- WHEN se consulta `GET /api/v1/tasks/{id}`
- THEN el cuerpo `data` incluye `created_by: null` y `updated_by: null`
