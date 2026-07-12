# Proposal: 12 · Notification Hub (entrega agnóstica al canal)

## Intent

Hoy `NotificationRepository.create()` es el punto único de creación pero hace **fan-out cableado a mano** a dos canales: `buffer_notification` (WS best-effort) y `enqueue_immediate_email` (email durable con outbox). Sumar un canal (push móvil FCM/APNs, SMS, webhook) exige editar ese método y esparcir conocimiento de cada canal. Además no hay forma de auditar "¿le llegó la notificación, por qué canal, en cuántos intentos?": el estado de entrega solo existe para email (`email_outbox`) y es invisible para WS. Se busca estandarizar un **hub agnóstico al canal**, reutilizable en otros sistemas: la notificación se dispara UNA vez y el hub entrega por N canales, verifica, reintenta cuando el canal lo amerita y deja registro auditable enviado/fallido por canal. Entregable **backend-only**; frontend congelado no se toca.

## Scope

### In Scope
- Puerto `DeliveryChannel` + registro de canales. Cada canal declara `name` y `policy` (`durable` = outbox + reintentos + estado terminal; `best_effort` = fire-and-forget post-commit sin registro de fallo). `create()` itera el registro en vez de 2 llamadas cableadas.
- Adaptar los canales vivos como implementaciones del puerto sin cambiar su comportamiento: email → `durable`, WS → `best_effort`.
- Outbox generalizado: renombrar `email_outbox` → `notification_deliveries` con columna `channel` y `payload` JSONB agnóstico; conservar el contrato transaccional probado (claim atómico + commits, `attempts`, `last_error`, `dedup_key`, estado terminal). Job despachador genérico por canal `durable`.
- Endpoint de auditoría `GET /notifications/{id}/deliveries` (admin/manager): estado, canal, intentos, `last_error`, `sent_at`.
- Declarar las **fronteras de extracción futura**: puertos que aíslan persistencia de entregas, resolución de destinatarios y scheduler; qué NO puede importar el núcleo (nunca `notifications.repository`).

### Out of Scope
- Extraer paquete instalable (decisión ratificada: estandarizar interno primero, extraer con segundo consumidor).
- Adaptadores nuevos reales (FCM/APNs/SMS/webhook): el diseño DEBE poder recibirlos sin tocar el núcleo, pero no se implementan aquí.
- Cualquier cambio en `frontend/`; provider gestionado real; contratos REST/WS/email vivos.

## Capabilities

### New Capabilities
- `notification-hub`: puerto `DeliveryChannel` + registro + `DeliveryPolicy`, outbox generalizado `notification_deliveries`, despachador genérico y endpoint de auditoría de entregas.

### Modified Capabilities
- `notifications-inapp`: el punto único de creación DEBE iterar el registro de canales (comportamiento preservado), no llamadas cableadas.
- `email-notifications`: el canal email pasa a ser un adaptador `durable` del hub sobre `notification_deliveries` (rename de `email_outbox`); contrato, `EMAIL_ENABLED`/`EMAIL_BACKEND`, digest e idempotencia sin cambios observables.
- `realtime-notifications`: el push WS pasa a ser un adaptador `best_effort` del hub; contrato y semántica best-effort preservados.

## Approach

Decisiones de arquitecto (a ratificar en design):
- **Puerto + registro**: `DeliveryChannel` declara `name` + `policy`. El fan-out de `create()` recorre el registro; `durable` encola una fila `notification_deliveries` en la MISMA transacción de negocio, `best_effort` bufferea para drenaje post-commit. Canal nuevo = clase nueva registrada, cero cambios en `create()`.
- **Outbox como payload agnóstico**: columnas de estado comunes (channel, status, attempts, last_error, dedup_key, sent_at, notification_id) + `payload` JSONB con lo específico del canal (email: subject/bodies/recipient). El despachador genérico reusa el claim atómico + commit-antes-del-send ya probado.
- **Fronteras de extracción**: el núcleo depende solo de puertos (store de entregas, resolución de destinatario, scheduler) y NUNCA importa `notifications.repository` (regla de ciclo ya vigente en `app/email/`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/notifications_hub/` (o equivalente) | New | Puerto `DeliveryChannel`, registro, despachador genérico |
| `backend/app/modules/notifications/repository.py` | Modified | `create()` itera registro en vez de 2 llamadas cableadas |
| `backend/app/email/` | Modified | Email como adaptador `durable`; outbox → `notification_deliveries` |
| `backend/app/realtime/publisher.py` | Modified | WS como adaptador `best_effort` |
| `backend/app/modules/notifications/router.py` | Modified | `GET /notifications/{id}/deliveries` |
| `backend/alembic/` | New | Migración: rename + `channel` + `payload` JSONB + copia de datos, con downgrade |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Migración de datos del outbox con filas vivas | Med | Copia dentro de la migración; downgrade recrea `email_outbox` y revierte columnas típadas |
| Romper alguno de los 539 tests / contratos vivos | Med | Comportamiento preservado; tests de `email_outbox` adaptados al rename y documentados |
| Regresión en el orden claim-antes-del-send | Med | Reusar el despachador probado; TDD estricto por canal `durable` |
| Atribución de digest (1 fila agrega N notificaciones, `notification_id=NULL`) | Med | Decidir en design cómo lo expone `/deliveries`; no bloquea el rename |
| Sobre-generalizar el núcleo | Low | No implementar adaptadores nuevos; solo declarar fronteras |

## Rollback Plan

Refactor sin cambio de comportamiento. Rollback = revertir el merge; la migración baja recrea `email_outbox` con columnas típadas y copia de vuelta las filas desde `notification_deliveries`. `EMAIL_ENABLED=false` sigue neutralizando el canal durable. La bandeja in-app/WS y su fuente de verdad REST quedan intactas por ser el email/WS best-effort/desacoplados.

## Dependencies

- `depends_on: 08-email-notifications` — generaliza su outbox transaccional y su patrón durable; head Alembic 0012.
- `depends_on: 09-websocket-realtime` — el push WS es la referencia del canal `best_effort`.
- `depends_on: 02-contrato-api` — auth-user, auditoría y contrato de respuesta reutilizados por `/deliveries`.

## Success Criteria

- [ ] Un canal nuevo se registra como clase que implementa `DeliveryChannel` sin tocar `create()`.
- [ ] `email_outbox` renombrado a `notification_deliveries` con `channel`/`payload`; email funciona idéntico (`EMAIL_BACKEND`/`EMAIL_ENABLED`/digest sin cambios observables).
- [ ] `GET /notifications/{id}/deliveries` devuelve estado por canal (enviado/fallido/intentos) con permisos admin/manager.
- [ ] Los 539 tests siguen verdes (los de outbox adaptados al rename, documentado); contratos REST/WS/email vivos sin cambios.
- [ ] Migración con ciclo downgrade/upgrade probado y sin pérdida de filas.

## Ronda de preguntas de propuesta

> No pude preguntar en vivo (ejecutor delegado). Supuestos que conviene ratificar antes de spec/design:

1. **Payload agnóstico**: ¿`payload` JSONB único (recomendado, extensible a SMS/push) o mantener columnas típadas de email + JSON solo para canales nuevos? Asumo JSONB.
2. **Atribución de digest en `/deliveries`**: el digest agrupa N notificaciones en 1 fila con `notification_id=NULL`. ¿El endpoint muestra solo entregas inmediatas por-notificación (asumido MVP) o se agrega un puente notificación↔entrega para el digest?
3. **Nombre/ubicación del núcleo**: ¿`app/notifications_hub/` como paquete propio (recomendado, aísla fronteras de extracción) o dentro de `app/modules/notifications/`? Asumo paquete propio.
