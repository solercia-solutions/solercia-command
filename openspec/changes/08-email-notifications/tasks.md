# Tasks: 08 · Email notifications (canal email + digest configurable)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1300–1600 (diseño: engine ~600 + preferencias ~150 + migraciones ~120 + tests ~450; el corte en 3 lotes con imports/docstrings por archivo puede empujar al extremo superior) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote A (puerto+adaptadores+plantillas+policy+config) → Lote B (outbox+migración+hook+dispatch job) → Lote C (preferencias+digest+wiring final) |
| Estrategia de entrega | commits directos a main por lotes (sin PR), size:exception aceptada por el usuario |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Ajustes sobre design.md (documentados, no bloqueantes):**
1. **Migración "única" dividida en dos** (Lote B: `email_outbox` + `notifications.emailed_at`; Lote C: `notification_preferences`), en vez de una sola migración como sugiere design.md. Motivo: `alembic check` exige el modelo ORM registrado en el mismo commit que su migración (precedente `06-reminders`/T01–T03); `NotificationPreference` no existe hasta el Lote C, así que forzar una sola migración en el Lote B rompería esa invariante o adelantaría trabajo del Lote C. Ambas migraciones encadenan al head vigente en su momento — **no fijar número, verificar con `alembic heads` antes de generar cada una**.
2. **Path de preferencias**: `GET/PUT /api/v1/notification-preferences` (plano, per `specs/email-notifications/spec.md` — contrato vinculante con escenarios probados), no `/notifications/preferences` (sugerencia D6 del design). Se implementa como router nuevo sin prefijo compartido para no tocar las rutas existentes de `/notifications`.

**Serialización**: el apply de 08 corre después del apply de `07-assets-sdmujer` (state.yaml `depends_on`). `09-websocket-realtime` ya está aplicado (`app/realtime/publisher.py`/`buffer_notification` existen en el código). `down_revision` de cada migración = head vigente al momento de generarla (hoy `0009`; previsiblemente `0011` tras que 07 aplique su `0010`; la del Lote C encadena al head resultante del Lote B).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| A | Puerto `EmailSender` + adaptadores + plantillas ES + `email_class` + config | 1 — `feat(email): puerto de envio, adaptadores y plantillas` | `cd backend && pytest tests/test_email_policy.py tests/test_email_templates.py tests/test_email_sender.py -v` | N/A — unit puro, sin BD ni red (`aiosmtplib.send` mockeado) | Revert commit; nada más depende de `app/email/` todavía |
| B | Outbox transaccional + migración + hook en `create()` + job `email_dispatch` | 2 — `feat(email): outbox transaccional y job de despacho` | `cd backend && pytest tests/test_email_outbox.py tests/test_email_dispatch.py -v` | Invocación directa de `dispatch_outbox(db)`/`enqueue_immediate_email(db, n)` en tests (patrón `test_reminder_dispatch.py`), nunca esperar al scheduler | Revert commit + `alembic downgrade -1` (elimina `email_outbox` y columna `emailed_at`); `EMAIL_ENABLED=false` ya lo deja no-op sin revertir |
| C | Preferencias (modelo+endpoints) + digest + wiring final en `main.py` | 3 — `feat(email): preferencias de digest y job de resumen` | `cd backend && pytest tests/test_notification_preferences.py tests/test_email_digest.py -v` | Invocación directa de `dispatch_digest(db)` en tests; smoke manual `GET/PUT /api/v1/notification-preferences` | Revert commit + `alembic downgrade -1` (elimina `notification_preferences`); el job `email_digest` deja de registrarse, `email_dispatch` (Lote B) sigue intacto |

## Fase A — Puerto, adaptadores, plantillas y config (Commit 1)

- [x] T01 [Foundation] `app/config.py`: `EMAIL_ENABLED: bool = False`, `EMAIL_BACKEND: str = "console"` (default — la suite jamás toca red), `SMTP_HOST/PORT/USER/PASSWORD/FROM_EMAIL/FROM_NAME/USE_TLS`, `EMAIL_MAX_ATTEMPTS: int = 5`, `EMAIL_DIGEST_TZ: str = "America/Bogota"`, `EMAIL_DISPATCH_INTERVAL_MINUTES`, `EMAIL_DIGEST_INTERVAL_MINUTES`.
- [x] T02 [Foundation] `backend/requirements.txt`: añadir `aiosmtplib` (única dependencia nueva, aislada tras el adaptador `smtp`).
- [x] T03 RED `backend/tests/test_email_policy.py`: `email_class("license_expired")` → `IMMEDIATE`; el resto (`task_overdue`, `sprint_at_risk`, `license_expiring`, `mention`, `task_at_risk`, `reminder`) → `DIGESTIBLE`. [R3,R5]
- [x] T04 RED `backend/tests/test_email_templates.py`: `render_immediate(...)`/`render_digest(...)` devuelven `(subject, text_body, html_body)`; tuteo formal ("tu licencia", "verifica"/"revisa"), nunca voseo ("tenés", "verificá"); `html_body` presente para `multipart/alternative`; digest con N ítems los lista todos. [R9]
- [x] T05 RED `backend/tests/test_email_sender.py`: `ConsoleEmailSender.send()` captura el mensaje en memoria sin red; `SmtpEmailSender.send()` arma MIME `multipart/alternative` y llama `aiosmtplib.send` (mockeado) con `to`/`subject`/cuerpos correctos; `get_email_sender()` devuelve el adaptador correcto según `EMAIL_BACKEND`. [R1]
- [x] T06 VERIFY confirmar los 3 archivos RED fallando (ImportError — módulo `app.email` inexistente) antes de GREEN.
- [x] T07 GREEN `app/email/policy.py`: `EmailClass` (enum Python puro `IMMEDIATE|DIGESTIBLE`, NO persistido), `IMMEDIATE_RULE_TYPES = {"license_expired"}`, `email_class(rule_type: str) -> EmailClass`. [R3,R5]
- [x] T08 GREEN `app/email/templates.py`: funciones puras `render_immediate(notification)`/`render_digest(user, notifications)` → tupla; HTML mínimo inline, español colombiano formal (tuteo, sin Jinja). [R9]
- [x] T09 GREEN `app/email/sender.py`: `EmailSender` (Protocol), `ConsoleEmailSender` (log estructurado + captura en memoria), `SmtpEmailSender` (`aiosmtplib`, único adaptador con esa dependencia), `get_email_sender()` factory por `settings.EMAIL_BACKEND`. [R1]
- [x] T10 VERIFY `cd backend && pytest tests/test_email_policy.py tests/test_email_templates.py tests/test_email_sender.py -v` en verde; `ruff check .` y `mypy app` limpios.

## Fase B — Outbox transaccional, migración, hook y job de despacho (Commit 2)

- [x] T11 [Foundation] Migración `backend/alembic/versions/0011_add_email_outbox.py`: tabla `email_outbox` (Pk+Timestamp+Tenant: `notification_id` FK nullable ON DELETE SET NULL, `recipient_email`, `subject`, `text_body`, `html_body` nullable, `dedup_key` único indexado, `status`, `attempts` default 0, `last_error` nullable, `sent_at` nullable) + columna aditiva `notifications.emailed_at` (DateTime nullable); `down_revision="0010"` (head vigente al generarla, verificado con `alembic heads`); `downgrade` elimina la tabla y la columna. Autogenerada contra una BD temporal en `0010` y validada con `alembic check` (cero diff) antes de limpiar el formato.
- [x] T12 [Foundation] `app/shared/enums.py`: `EmailOutboxStatus` (`pending/sending/sent/failed`), `native_enum=False, length=20` (espejo `NotificationStatus`/`ReminderStatus`).
- [x] T13 [Foundation] `app/email/models.py`: `EmailOutbox` (mixins de T11). **Frontera de imports (corrección de gate)**: SOLO importa `app.modules.notifications.models` (para tipar `notification_id`/`Notification`), JAMÁS `.repository` — espejo exacto de `app/realtime/publisher.py`.
- [x] T14 [Foundation] `app/db_init.py`: importar `EmailOutbox` para que `Base.metadata.create_all` (fixture de tests) lo reconozca.
- [x] T15 RED `backend/tests/test_email_outbox.py` (fixture SAVEPOINT): `license_expired` → fila `email_outbox` `pending` + `notification.emailed_at` seteado en la MISMA tx [R3,R10]; `rule_type` no urgente → sin fila, `emailed_at IS NULL` [R5,R10]; `EMAIL_ENABLED=false` → notificación persiste igual, sin fila ni `emailed_at` [R2].
- [x] T16 RED `backend/tests/test_email_dispatch.py` (patrón `test_reminder_dispatch.py`, invocación directa de `dispatch_outbox(db)` con fake/Console sender): fila `pending` → captura 1 correo + fila `sent`+`sent_at` [R1,R6]; sender que falla → fila permanece `pending` (reintentable), la creación de la notificación queda intacta [R3]; reintentos agotados (`EMAIL_MAX_ATTEMPTS`) → `failed` terminal + log ERROR con `dedup_key`, sin más reintento, notificación sigue visible vía `GET /notifications` [R6]; reintento de fila `pending` con `attempts>0` reutiliza el mismo `dedup_key`, no duplica fila ni correo [R6]; `organization_id` de la fila nunca se cruza entre organizaciones [R8].
- [x] T17 VERIFY confirmar RED fallando (tabla/módulo inexistente) antes de GREEN. Nota: hubo que hacer DROP/CREATE de `solercia_test` una vez porque `create_all` no altera tablas existentes y no añadía `notifications.emailed_at` a la BD persistente.
- [x] T18 GREEN `app/email/outbox.py`: `enqueue_immediate_email(db, n: Notification) -> None` — no-op si `EMAIL_ENABLED=False` o `email_class(n.rule_type) != IMMEDIATE`; si no, `INSERT EmailOutbox(dedup_key=f"immediate:{n.id}", ...)` + `n.emailed_at = now()` en la MISMA tx (sin commit propio). `dispatch_outbox(db) -> int`: claim atómico `UPDATE email_outbox SET status='sending', attempts=attempts+1 WHERE id=:id AND status='pending' RETURNING id` (SQL Core, patrón `_claim_reminder`) + `db.commit()` ANTES de tocar SMTP; `EmailSender.send(...)`; marca `sent`/`sent_at` o `pending` (reintento) / `failed` terminal según `EMAIL_MAX_ATTEMPTS` + `db.commit()` final. `drain_outbox_best_effort(db)`: try/except alrededor de `dispatch_outbox`. Import SOLO `notifications.models`. [R2,R3,R6,R8]
- [x] T19 GREEN `app/modules/notifications/models.py`: columna `emailed_at: Mapped[datetime | None]` (DateTime, nullable). [R10]
- [x] T20 GREEN `app/modules/notifications/repository.py`: `create()` llama `await enqueue_immediate_email(self.db, notification)` justo después de `buffer_notification(...)`. [R10]
- [x] T21 GREEN `app/email/scheduler.py`: `register_email_jobs(scheduler)` registra SOLO el job `email_dispatch` (`IntervalTrigger(minutes=EMAIL_DISPATCH_INTERVAL_MINUTES)`, sesión propia `AsyncSessionLocal`, try/except aislado — espejo `app/reminders/scheduler.py`). **El ÚNICO despachador es este job**; el evaluador de alertas no drena outbox inline (corrección de gate). [R6]
- [x] T22 GREEN `app/main.py`: importar `register_email_jobs`; en `lifespan`, si `settings.EMAIL_ENABLED`, `register_email_jobs(scheduler)` con try/except aislado (dirección `main -> email`, nunca `alerts -> email`).
- [x] T23 VERIFY `app/alerts/evaluator.py` permanece SIN cambios (`git diff` vacío para ese archivo) — confirma que no se agregó drenaje inline (corrección vinculante del gate).
- [x] T24 VERIFY `cd backend && pytest tests/test_email_outbox.py tests/test_email_dispatch.py -v` en verde; `ruff check .` y `mypy app` limpios.

## Fase C — Preferencias, digest y wiring final (Commit 3)

- [ ] T25 [Foundation] Migración `backend/alembic/versions/00YY_add_notification_preferences.py`: tabla `notification_preferences` (Pk+Timestamp+Tenant+Audit: `user_id` FK, `UNIQUE(organization_id, user_id)`, `digest_frequency` default `none`, `digest_hour` default 8, `digest_weekday` nullable, `last_digest_at` nullable); `down_revision` = head resultante del Lote B (verificar con `alembic heads`, no fijar número).
- [ ] T26 [Foundation] `app/shared/enums.py`: `DigestFrequency` (`none/daily/weekly`), `native_enum=False, length=10`.
- [ ] T27 [Foundation] `app/modules/notifications/models.py`: `NotificationPreference` (mixins de T25).
- [ ] T28 [Foundation] `app/db_init.py`: importar `NotificationPreference`.
- [ ] T29 RED `backend/tests/test_notification_preferences.py`: `GET` sin fila previa → defaults `frequency=none` sin error [R4,R7]; `PUT` con `frequency="hourly"` → `422` con `detail` [R7]; `PUT` válido (`weekly`+hora) → persiste y un `GET` posterior lo refleja [R7]; preferencia de otra organización no accesible/editable [R8].
- [ ] T30 RED `backend/tests/test_email_digest.py` (patrón `test_reminder_dispatch.py`, invocación directa de `dispatch_digest(db)`): usuario `daily` con hora cumplida → agrupa 3 notificaciones no leídas con `emailed_at IS NULL` en 1 correo + marca `emailed_at` en las 3 + actualiza `last_digest_at` [R4,R5,R9]; doble corrida no duplica (`dedup_key` único + `emailed_at IS NULL` ya no encuentra filas) [R6]; usuario `none` → sin digest, pero sigue recibiendo urgentes inmediatos [R4]; 2 organizaciones con usuarios homónimos → cada digest resume solo su propia organización [R8]; fila outbox del digest agota `EMAIL_MAX_ATTEMPTS` → `failed` terminal + log ERROR con `dedup_key`, las notificaciones marcadas `emailed_at` NO se re-digestan pero siguen visibles vía `GET /notifications` [R6].
- [ ] T31 VERIFY confirmar RED fallando antes de GREEN.
- [ ] T32 GREEN `app/modules/notifications/schemas.py`: `NotificationPreferenceRead`/`NotificationPreferenceUpdate` (`frequency: Literal["none","daily","weekly"]`, `hour: int` 0–23, `weekday` opcional 0–6). [R7]
- [ ] T33 GREEN `app/modules/notifications/repository.py`: `NotificationPreferenceRepository` (`get_or_none`, `upsert`), scoped a `(organization_id, user_id)`. [R7,R8]
- [ ] T34 GREEN `app/modules/notifications/service.py`: `NotificationPreferenceService.get_preference` (defaults virtuales si no hay fila) / `update_preference` (valida + upsert). [R4,R7]
- [ ] T35 GREEN `app/modules/notifications/router.py`: nuevo `preferences_router = APIRouter(tags=["notifications"])` (sin prefijo compartido) con `GET`/`PUT /notification-preferences` — path plano per `specs/email-notifications/spec.md` (ver ajuste sobre D6 arriba). [R7]
- [ ] T36 GREEN `app/email/digest.py`: `dispatch_digest(db) -> int` — por cada `NotificationPreference` con `frequency != none` cuya hora (`EMAIL_DIGEST_TZ`) se cumplió desde `last_digest_at`, agrega `Notification` no leídas con `emailed_at IS NULL` del usuario, compone 1 correo vía `render_digest`, `INSERT` 1 fila `EmailOutbox(dedup_key=f"digest:{user_id}:{periodo}")`, marca `emailed_at` en cada notificación + `last_digest_at`, todo en 1 tx + `db.commit()` único. Import SOLO `notifications.models`. [R4,R5,R6,R8]
- [ ] T37 GREEN `app/email/scheduler.py`: extender `register_email_jobs(scheduler)` para registrar TAMBIÉN el job `email_digest` (`IntervalTrigger(minutes=EMAIL_DIGEST_INTERVAL_MINUTES)`, sesión propia, try/except aislado del job de dispatch). [R4]
- [ ] T38 GREEN `app/main.py`: `app.include_router(preferences_router, prefix=API_PREFIX)`.
- [ ] T39 VERIFY `cd backend && pytest tests/test_notification_preferences.py tests/test_email_digest.py -v` en verde; `ruff check .` y `mypy app` limpios.
- [ ] T40 VERIFY final `cd backend && pytest tests/ -v` — suite completa sin regresiones en `test_notifications_inapp`/`test_alert_engine`/`test_reminder_dispatch`/`test_realtime*`; documentar si persisten los mismos fallos ambientales pre-existentes (tests black-box que exigen servidor vivo + `TEST_AUTH_TOKEN`, igual criterio que `06-reminders`).

## Trazabilidad de requisitos

R1 Puerto `EmailSender` agnóstico (adaptador console + swap sin tocar dominio) · R2 Interruptor maestro `EMAIL_ENABLED` · R3 Envío inmediato de urgentes (`license_expired`) sin romper la tx · R4 Preferencia de digest por usuario (`none/daily/weekly`+hora, default `none`) · R5 Alcance y marcado del digest · R6 Idempotencia del envío (`dedup_key`, doble corrida, reintento, agotamiento→`failed`+log ERROR) · R7 CRUD de preferencias (`GET`/`PUT`, 422 en inválida) · R8 Aislamiento multi-tenant · R9 Plantillas en español colombiano formal (`specs/email-notifications`). R10 Encolado de entrega email en la creación, contrato REST intacto (`specs/notifications-inapp`).
