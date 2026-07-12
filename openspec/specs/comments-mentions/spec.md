# Spec — Comentarios y menciones (comments-mentions)

> **Origen**: línea base as-built (2026-07-11)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Comentarios sobre tareas con menciones `@usuario`: al crear o editar un comentario se parsean las menciones y se generan notificaciones in-app para los usuarios mencionados.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/tasks/{id}/comments | Lista de comentarios de la tarea |
| POST | /api/v1/tasks/{id}/comments | Crea comentario (201); parsea @menciones → notificaciones |
| PATCH | /api/v1/comments/{id} | Edición (solo el autor); re-diff de menciones |
| DELETE | /api/v1/comments/{id} | Borrado suave (204) |

Modelo `TaskComment` (Pk + Timestamp + SoftDelete + Tenant):

| Campo | Descripción |
|-------|-------------|
| task_id, author_id | Relaciones |
| body | Texto del comentario |
| mentioned_user_ids | JSON con los usuarios mencionados |

## Requisitos

- **R1**: Al crear un comentario, cada `@mención` válida DEBE generar una notificación in-app al usuario mencionado y quedar registrada en `mentioned_user_ids`.
- **R2**: Solo el autor DEBE poder editar su comentario.
- **R3**: Al editar, las menciones DEBEN recalcularse por diferencia: solo los usuarios mencionados NUEVOS reciben notificación (sin duplicar a los ya notificados).
- **R4**: El borrado DEBE ser suave y responder 204.

### Escenarios centrales

**R1 — Mención genera notificación**
- Dado un comentario nuevo con `@maria`
- Cuando se envía `POST /tasks/{id}/comments`
- Entonces responde 201 y María recibe una notificación in-app.

**R2 — Edición restringida al autor**
- Dado un comentario de otro usuario
- Cuando alguien distinto del autor envía `PATCH /comments/{id}`
- Entonces la operación es rechazada.

**R3 — Re-diff de menciones**
- Dado un comentario que ya mencionaba a `@maria`
- Cuando el autor lo edita agregando `@pedro`
- Entonces solo Pedro recibe una notificación nueva.

## Limitaciones y deuda conocida

- Canal de notificación únicamente in-app (sin email ni tiempo real).
- Sin paginación en la lista de comentarios.
- Sin historial de ediciones del comentario.
- Cobertura: test_comments (6) y test_mention_notifications (7). Sin tests de permisos por rol.

## Referencias

- backend/app/modules/comments/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/modules/notifications/ (creación de notificaciones por mención)
- backend/tests/test_comments.py, backend/tests/test_mention_notifications.py
