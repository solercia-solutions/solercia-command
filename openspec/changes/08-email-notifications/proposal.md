# Proposal: 08 · Email notifications (canal email + digest configurable)

## Intent

Hoy las notificaciones (`notifications-inapp`) viven solo dentro de la app: polling REST (línea base) + push WebSocket (cambio 09). No hay correo. El CLAUDE.md exige canal email con "digest: resumen diario/semanal configurable por usuario" y marca cuatro alertas como email (`task_overdue`, `sprint_at_risk`, `license_expiring`, `license_expired` — esta última "email urgente"). Sin correo, un jefe fuera de la app no se entera de un SLA vencido ni de una licencia expirada. Entregable **backend-only**; el frontend congelado no se toca.

## Scope

### In Scope
- Puerto `EmailSender` + adaptadores intercambiables por `EMAIL_BACKEND` (`console` para dev/tests, `smtp` vía aiosmtplib). Seam documentado para provider gestionado futuro (SES/SendGrid/Resend) sin tocar el dominio.
- Plantillas texto plano + HTML simple (multipart/alternative), en español colombiano formal (tuteo).
- Preferencia de digest por usuario (`none|daily|weekly` + hora) en tabla nueva `notification_preferences` (tenant-scoped por `(org, user)`).
- Envío inmediato best-effort post-commit (patrón del cambio 09) para los `rule_type` de correo; `license_expired` urgente.
- Digest programado (APScheduler) que compone el resumen desde las `Notification` no leídas del período.
- Outbox transaccional (`email_outbox`) + marca `notifications.emailed_at` para idempotencia y reintento.
- Suite TDD con adaptador de captura en memoria (sin servidor SMTP real).

### Out of Scope
- Cualquier cambio en `frontend/` (constraint `frontend-frozen`).
- Provider gestionado real, plantillas ricas/branding, tracking de aperturas.
- Preferencias granulares por tipo de alerta (MVP solo `none/daily/weekly`).
- Reemplazo del canal in-app/WS: el email complementa, no sustituye.

## Capabilities

### New Capabilities
- `email-notifications`: puerto `EmailSender` + adaptadores, render de plantillas ES, preferencia de digest, envío inmediato best-effort, digest programado y outbox idempotente.

### Modified Capabilities
- `notifications-inapp`: el punto único de creación DEBE encolar entrega email (inmediata o digestible) best-effort y marcar `emailed_at`, sin alterar el contrato REST ni el modelo (salvo columna aditiva).

## Approach

Decisiones de arquitecto (a ratificar en design):
- **Puerto + adaptadores** seleccionados por settings, espejo del `NotificationPublisher` del 09. `EMAIL_ENABLED` como master switch (off = no-op).
- **Outbox transaccional** como fuente de verdad del envío: se encola dentro de la transacción de negocio y se drena post-commit best-effort (baja latencia) más un barrido periódico (durabilidad/reintento). El envío JAMÁS bloquea ni rompe la transacción que lo origina.
- **Idempotencia doble**: `dedup_key` único en el outbox + `emailed_at` en `Notification`; el digest solo toma `emailed_at IS NULL`, así el job puede correr dos veces sin duplicar correo.
- **Clasificación por `rule_type`**: inmediato (urgente) vs digestible vs solo in-app; el mapeo vive en la capacidad email, `alert-engine` queda intacto.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/email/` | New | Puerto `EmailSender`, adaptadores, plantillas, outbox y digest job |
| `backend/app/modules/notifications/repository.py` | Modified | Encolar email tras crear + marcar `emailed_at` |
| `backend/app/config.py` | Modified | `EMAIL_ENABLED`, `EMAIL_BACKEND`, SMTP, intervalos |
| `backend/app/main.py` | Modified | Wiring del sender + scheduler de digest/outbox |
| `backend/alembic/` | New | Migración: `email_outbox`, `notification_preferences`, `notifications.emailed_at` |
| `backend/requirements.txt` | Modified | `aiosmtplib` |
| `backend/tests/` | New | Suite TDD con adaptador de captura |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Envío que bloquea/rompe la tx de negocio | Med | Outbox + drenaje post-commit best-effort; nunca en la tx |
| Doble correo si el job corre dos veces | Med | `dedup_key` único + `emailed_at`; digest solo `emailed_at IS NULL` |
| Envío perdido (marcado emailed pero SMTP falló) | Med | Payload compuesto en outbox + estado `failed` con reintento |
| Doble evaluación con múltiples réplicas | Med | Claim de filas por estado; lock Redis documentado como siguiente slice |
| Fuga de credenciales SMTP | Baja/alto | Settings desde `.env`; nunca loguear payload/credenciales |
| Nueva dependencia `aiosmtplib` | Low | Aislada tras el puerto; adaptador console no la requiere |

## Rollback Plan

Cambio aditivo. Rollback = `EMAIL_ENABLED=false` (encolado y envío quedan no-op, el digest job no corre) o revertir el merge; la migración baja (drop de tablas + columna aditiva). La bandeja in-app/WS y su fuente de verdad quedan intactas porque el email es best-effort y desacoplado.

## Dependencies

- `depends_on: 09-websocket-realtime` — reutiliza/extiende el patrón best-effort post-commit y el punto único de creación (`NotificationRepository.create()`).
- `depends_on: 07-assets-sdmujer` — orden del roadmap (AVANCE: `C06→C07→C08`); habilita los `rule_type` `license_expiring`/`license_expired` como casos de correo. Su migración es 0010; la mía toma el head vigente al apply (previsiblemente 0011).
- `depends_on: 02-contrato-api` — resolución de auth-user, auditoría y contrato de respuesta reutilizados.
- Construye sobre las líneas base `notifications-inapp` y `alert-engine`.

## Success Criteria

- [ ] `EmailSender` con adaptadores `console` y `smtp` seleccionables por `EMAIL_BACKEND`; console por defecto en dev/tests.
- [ ] Un provider gestionado futuro se enchufa como adaptador nuevo sin tocar dominio ni plantillas.
- [ ] Crear una notificación de `rule_type` urgente (`license_expired`) dispara un correo inmediato best-effort; el fallo de SMTP no rompe la creación ni la transacción.
- [ ] El digest respeta la preferencia (`none|daily|weekly` + hora) y resume las `Notification` no leídas del período; correr el job dos veces no duplica correo.
- [ ] Plantillas texto+HTML en español colombiano formal.
- [ ] Todo nace con prueba en rojo (TDD estricto) usando el adaptador de captura, sin SMTP real.
