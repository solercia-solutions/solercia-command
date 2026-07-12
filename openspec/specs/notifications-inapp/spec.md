# Spec — Notificaciones in-app (notifications-inapp)

> **Origen**: línea base as-built (2026-07-11) + [06-reminders](../../changes/archive/2026-07-12-06-reminders/) + [09-websocket-realtime](../../changes/archive/2026-07-12-09-websocket-realtime/) + [08-email-notifications](../../changes/archive/2026-07-12-08-email-notifications/) + [12-notification-hub](../../changes/archive/2026-07-12-12-notification-hub/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Bandeja de notificaciones in-app por usuario: generadas por menciones en comentarios y por el motor de alertas, con ciclo de vida por estado y deduplicación por clave idempotente. Canal ÚNICO actual: polling REST.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/notifications | Lista de notificaciones del usuario autenticado |
| GET | /api/v1/notifications/unread-count | Conteo de no leídas (badge) |
| PATCH | /api/v1/notifications/{id} | Cambia estado: read / resolved / silenced |

Modelo `Notification` (Pk + Timestamp + Tenant; SIN soft delete — ciclo de vida por `status`):

| Campo | Descripción |
|-------|-------------|
| recipient_user_id | Destinatario |
| rule_type | Origen (mención o tipo de regla de alerta) |
| title, body | Contenido |
| target_type?, target_id? | Entidad relacionada (navegación) |
| dedup_key | Clave de idempotencia |
| status | active \| read \| resolved \| silenced |

## Requisitos

- **R1**: Cada usuario DEBE ver únicamente sus propias notificaciones.
- **R2**: `dedup_key` DEBE garantizar idempotencia: mientras exista una notificación activa con la misma clave en la organización, no se crea otra.
- **R3**: `unread-count` DEBE reflejar solo las notificaciones en estado `active` del usuario.
- **R4**: El ciclo de vida DEBE manejarse por `status` (sin borrado): active → read / resolved / silenced.

### Escenarios centrales

**R1 — Bandeja propia**
- Dado notificaciones de varios usuarios
- Cuando un usuario llama `GET /notifications`
- Entonces recibe solo las que tienen su `recipient_user_id`.

**R2 — Deduplicación**
- Dado una notificación activa con `dedup_key = "task_overdue:T1:U1"`
- Cuando el evaluador de alertas vuelve a generar el mismo candidato
- Entonces NO se crea una notificación duplicada.

**R4 — Marcar como leída**
- Dado una notificación activa
- Cuando el usuario envía `PATCH /notifications/{id}` con `read`
- Entonces el estado cambia y el `unread-count` disminuye.

### Requirement: Origen "reminder" integrado a la bandeja compartida

El sistema MUST aceptar `rule_type="reminder"` como origen válido de `Notification`, generado por el disparo de un `Reminder` manual o por la evaluación de una `ReminderRule` (`task_due_soon`). Estas notificaciones MUST cumplir el mismo contrato ya vigente de la bandeja: privacidad por `recipient_user_id` (R1), deduplicación por `dedup_key` (R2), conteo de no leídas (R3) y ciclo de vida por `status` (R4). No se requiere cambio de esquema ni de comportamiento en `Notification`; `rule_type` ya es un campo libre que admite el nuevo valor.

#### Scenario: Recordatorio manual aparece en la bandeja
- GIVEN un `Reminder` propio vencido en `scheduled`
- WHEN el scheduler de reminders lo dispara
- THEN se crea una `Notification` con `rule_type="reminder"`, visible solo para el `recipient_user_id` correspondiente vía `GET /notifications`

#### Scenario: Deduplicación aplica igual que a mención y alertas
- GIVEN una `Notification` activa con `dedup_key="reminder_due_soon:T1:U1:2026-07-15"`
- WHEN la regla `task_due_soon` vuelve a evaluar la misma condición
- THEN no se crea una segunda notificación para ese `dedup_key`

### Requirement: Publicación al canal realtime en la creación

Cuando el sistema crea una notificación (por mención o por el motor de alertas), el punto único de creación MUST delegar el fan-out en el hub de entregas (`notification-hub`), que MUST incluir al canal realtime (`realtime-notifications`) como canal registrado de política `best_effort` hacia el `recipient_user_id`, sin alterar el modelo `Notification` ni el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`). El punto de creación MUST NOT invocar el canal realtime de forma cableada.

#### Scenario: Creación dispara publicación vía el hub

- GIVEN el punto único de creación de `Notification` (`NotificationRepository.create()`, usado por el evaluador de alertas y por las menciones — el service NO tiene `create()`)
- WHEN se persiste una notificación nueva y su transacción hace commit
- THEN el hub publica (drenaje post-commit best-effort) hacia el canal realtime del destinatario, además de persistir el registro

#### Scenario: REST sigue siendo autoritativo

- GIVEN el canal realtime deshabilitado o el publicador no disponible
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`

### Requirement: Encolado de entrega email en la creación

Desde el punto único de creación (`NotificationRepository.create()`), el sistema MUST delegar en el hub de entregas la entrega por email (inmediata si el `rule_type` es urgente, o diferida al digest en caso contrario), a través del canal email registrado con política `durable` sobre `notification_deliveries`, sin alterar el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`) ni el resto del modelo `Notification`, salvo la columna aditiva `emailed_at`.

#### Scenario: Notificación urgente se encola para envío inmediato
- GIVEN el punto único de creación de `Notification` con `rule_type="license_expired"`
- WHEN se persiste y su transacción hace commit
- THEN queda encolada en `notification_deliveries` como entrega DURABLE (el job despachador la envía con reintentos y estado terminal auditable), además de persistida como siempre

#### Scenario: Notificación no urgente queda pendiente de digest
- GIVEN una notificación creada con `rule_type` no urgente (ej. mención, `task_at_risk`)
- WHEN se persiste
- THEN queda con `emailed_at IS NULL`, visible igual vía `GET /notifications`, hasta que el digest la procese (si el usuario tiene preferencia distinta de `none`)

#### Scenario: REST sigue siendo autoritativo si el email falla o está deshabilitado
- GIVEN el canal email deshabilitado (`EMAIL_ENABLED=false`) o el envío falla
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`, con contrato y campos existentes sin cambios

## Limitaciones y deuda conocida

- Canal único in-app por polling REST: sin WebSocket (tiempo real) ni email/digest previstos en CLAUDE.md.
- Sin paginación en la lista.
- Los endpoints del módulo tienen CERO tests directos (la creación por mención se cubre en test_mention_notifications).

## Referencias

- backend/app/modules/notifications/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/alerts/evaluator.py (creación por reglas de alerta)
- backend/tests/test_mention_notifications.py
