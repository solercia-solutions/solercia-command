# Spec — Notificaciones in-app (notifications-inapp)

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

## Limitaciones y deuda conocida

- Canal único in-app por polling REST: sin WebSocket (tiempo real) ni email/digest previstos en CLAUDE.md.
- Sin paginación en la lista.
- Los endpoints del módulo tienen CERO tests directos (la creación por mención se cubre en test_mention_notifications).

## Referencias

- backend/app/modules/notifications/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/alerts/evaluator.py (creación por reglas de alerta)
- backend/tests/test_mention_notifications.py
