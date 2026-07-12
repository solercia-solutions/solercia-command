# reminders Specification

## Purpose

Recordatorios personales del colaborador: instancias manuales (`Reminder`, disparo único por `remind_at`) y reglas automáticas por usuario (`ReminderRule`, `rule_type=task_due_soon`), ambos materializados como `Notification` in-app vía el scheduler existente. Son recursos estrictamente personales: solo el dueño los ve y gestiona, ni siquiera un admin de la organización.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | /api/v1/reminders | Crear recordatorio manual propio |
| GET | /api/v1/reminders | Listar recordatorios propios (paginado, filtro `?status=`) |
| GET | /api/v1/reminders/{id} | Obtener un recordatorio propio |
| PATCH | /api/v1/reminders/{id} | Editar `remind_at`/`message` (solo `scheduled`) |
| DELETE | /api/v1/reminders/{id} | Cancelar (solo `scheduled`) |
| GET | /api/v1/reminder-rules | Listar reglas propias |
| POST | /api/v1/reminder-rules | Crear regla propia |
| PATCH | /api/v1/reminder-rules/{id} | Editar `lead_days`/`enabled`/`params` |
| POST | /api/v1/reminders/dispatch | Disparo manual del dispatcher (admin RBAC, espejo de `/alerts/evaluate`) |

`Reminder` (Pk + Timestamp + SoftDelete + Tenant): `user_id` (owner), `task_id?`, `remind_at`, `message`, `status` (scheduled\|fired\|skipped\|cancelled). `ReminderRule` (Pk + Timestamp + Tenant): `user_id` (owner), `rule_type` (task_due_soon, extensible), `lead_days`, `enabled`, `params` (JSON).

## Requirements

### Requirement: Creación de recordatorio manual

El sistema MUST permitir crear un `Reminder` propio con `remind_at`, `message` y `task_id` opcional, quedando en `scheduled`. El sistema MUST rechazar con `422` una `remind_at` igual o anterior al momento actual.

#### Scenario: Creación válida
- GIVEN un usuario autenticado
- WHEN envía `POST /reminders` con `remind_at` futuro
- THEN se crea con `status=scheduled` y `created_by`/`updated_by` = el usuario

#### Scenario: remind_at en el pasado
- GIVEN un usuario autenticado
- WHEN envía `POST /reminders` con `remind_at` anterior a ahora
- THEN la API responde `422` y no crea el registro

### Requirement: Listado y consulta exclusivos del dueño

`GET /reminders` MUST devolver solo los recordatorios del usuario autenticado, paginados (`?page&size&sort&order`, `meta{total[,page,size]}`) con filtro opcional `?status=`. `GET /reminders/{id}` MUST responder `404` si el recurso no existe, está borrado o pertenece a otro usuario.

#### Scenario: Listado propio paginado y filtrado
- GIVEN un usuario con 5 recordatorios y otro usuario con 2
- WHEN el primero llama `GET /reminders?status=scheduled&page=1&size=10`
- THEN recibe solo los suyos en `scheduled`, con `meta{total,page,size}`

#### Scenario: Recordatorio ajeno
- GIVEN un recordatorio de otro usuario
- WHEN se consulta `GET /reminders/{id}`
- THEN la API responde `404` (no `403`)

### Requirement: Edición y cancelación solo en scheduled

`PATCH /reminders/{id}` MUST modificar `remind_at`/`message` únicamente si el recurso es propio y está en `scheduled`; en otro status responde `422`. `DELETE /reminders/{id}` MUST cancelar (`status=cancelled`) un recordatorio propio en `scheduled`; el scheduler MUST NOT disparar uno cancelado.

#### Scenario: Edición válida
- GIVEN un recordatorio propio en `scheduled`
- WHEN el dueño envía `PATCH` con nuevo `remind_at` futuro
- THEN se actualiza y `updated_by` refleja al usuario

#### Scenario: Edición de recordatorio ya disparado
- GIVEN un recordatorio propio en `fired`
- WHEN el dueño intenta `PATCH`
- THEN la API responde `422`

#### Scenario: Cancelación
- GIVEN un recordatorio propio en `scheduled`
- WHEN el dueño llama `DELETE /reminders/{id}`
- THEN queda `cancelled` y el scheduler lo omite en corridas posteriores

### Requirement: Aislamiento multi-tenant y personal (ni admin ve lo ajeno)

Ningún usuario, incluido un admin de la misma organización, MUST NOT ver ni gestionar recordatorios o reglas de otro usuario ni de otra organización.

#### Scenario: Aislamiento entre organizaciones
- GIVEN un recordatorio del usuario U1 en la organización A
- WHEN un usuario de la organización B intenta `GET/PATCH/DELETE` sobre ese recordatorio
- THEN la API responde `404`

#### Scenario: Admin no ve recordatorios ajenos
- GIVEN un admin en la misma organización que U1
- WHEN el admin llama `GET /reminders`
- THEN NO recibe los recordatorios de U1

### Requirement: Configuración de ReminderRule por usuario

El sistema MUST permitir a cada usuario crear, listar y editar (incluido alternar `enabled`) sus propias `ReminderRule` con `rule_type=task_due_soon` y `lead_days` entero positivo.

#### Scenario: Crear regla task_due_soon
- GIVEN un usuario sin reglas
- WHEN envía `POST /reminder-rules` con `rule_type=task_due_soon`, `lead_days=3`
- THEN se crea con `enabled=true` asociada al usuario

#### Scenario: Deshabilitar regla
- GIVEN una regla `enabled=true`
- WHEN el dueño envía `PATCH` con `enabled=false`
- THEN corridas posteriores del scheduler no generan candidatos de esa regla

### Requirement: Disparo idempotente de recordatorios manuales vencidos

En cada corrida, el scheduler MUST localizar los `Reminder` en `scheduled` con `remind_at <= ahora`, generar UNA `Notification` al owner (`rule_type=reminder`) y transicionar a `fired`. Corridas posteriores MUST NOT duplicar la notificación de un recordatorio ya `fired`.

#### Scenario: Disparo simple
- GIVEN un recordatorio `scheduled` vencido, sin `task_id`
- WHEN corre el scheduler
- THEN el owner recibe una notificación in-app y el recordatorio queda `fired`

#### Scenario: Idempotencia entre corridas
- GIVEN un recordatorio ya `fired`
- WHEN el scheduler corre nuevamente
- THEN no se genera una segunda notificación para ese recordatorio

#### Scenario: Cancelación concurrente no dispara
- GIVEN un recordatorio `scheduled` vencido que el dueño cancela mientras el dispatcher está procesando la corrida
- WHEN el dispatcher intenta reclamarlo (transición condicionada a `status=scheduled`)
- THEN el claim no encuentra el registro en `scheduled`, no se genera `Notification` y el recordatorio permanece `cancelled`

### Requirement: Disparo manual admin-only

`POST /reminders/dispatch` MUST ejecutar el dispatcher bajo demanda y MUST estar gateado por `require_admin` (RBAC), espejo de `POST /alerts/evaluate`.

#### Scenario: Disparo manual por admin
- GIVEN un usuario con rol RBAC ADMIN
- WHEN llama `POST /reminders/dispatch`
- THEN el dispatcher corre y la respuesta indica cuántas notificaciones se generaron

#### Scenario: Disparo manual rechazado a no-admin
- GIVEN un usuario sin rol RBAC ADMIN
- WHEN llama `POST /reminders/dispatch`
- THEN la API responde `403`

### Requirement: Omisión ante tarea completada, cancelada o borrada

Un `Reminder` vencido cuya `task_id` referencia una tarea `done`, `cancelled` o soft-borrada MUST transicionar a `skipped` sin generar `Notification`.

#### Scenario: Tarea completada antes del disparo
- GIVEN un recordatorio ligado a una tarea que pasó a `done` antes de `remind_at`
- WHEN corre el scheduler
- THEN el recordatorio queda `skipped` y no se genera notificación

### Requirement: Disparo de la regla task_due_soon

Para cada `ReminderRule` `enabled` de tipo `task_due_soon`, el scheduler MUST evaluar las tareas asignadas al usuario con `due_date <= ahora + lead_days` y `status` no `done`/`cancelled`, generando una `Notification` con `dedup_key` determinista (`reminder_due_soon:{task_id}:{user_id}:{due_date}`).

#### Scenario: Notificación por vencimiento próximo
- GIVEN una regla `lead_days=3` y una tarea propia con `due_date` en 2 días, `status=in_progress`
- WHEN corre el scheduler
- THEN el usuario recibe una notificación in-app sobre esa tarea

#### Scenario: Sin duplicado en corridas consecutivas
- GIVEN la notificación anterior ya activa para el mismo `dedup_key`
- WHEN el scheduler corre de nuevo sin cambios
- THEN no se crea una segunda notificación

#### Scenario: Tarea completada no genera aviso
- GIVEN una tarea con `due_date` dentro del `lead_days` pero `status=done`
- WHEN corre el scheduler
- THEN no se genera notificación para esa tarea

## Referencias

- Proposal: `openspec/changes/06-reminders/proposal.md`
- Patrón espejo: `openspec/specs/alert-engine/spec.md`
- Salida compartida: `openspec/specs/notifications-inapp/spec.md`
