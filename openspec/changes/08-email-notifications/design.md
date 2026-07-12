# Design: 08 · Email notifications (canal email + digest configurable)

## Technical Approach

Engine top-level nuevo `app/email/` (hermano de `app/realtime/`, `app/alerts/`, `app/reminders/`; **no** bajo `modules/`): puerto `EmailSender` + adaptadores `console`/`smtp` seleccionados por settings, plantillas ES, outbox transaccional y jobs de despacho/digest en el **mismo** `AsyncIOScheduler`. Reutiliza el seam del cambio 09: el punto ÚNICO de nacimiento sigue siendo `NotificationRepository.create()`, que ya bufferiza para WS; ahí se **encola el correo inmediato dentro de la misma transacción** y el envío se **drena tras el commit** best-effort. Aditivo, tras `EMAIL_ENABLED` (default off). TDD estricto con adaptador de captura, sin SMTP real. Depende de 09 (seam create/drain), 07 (`rule_type` `license_*`), 02 (auth-user, `NotificationRead`).

## Architecture Decisions

### D1 — Ubicación: engine `app/email/`; preferencias en `modules/notifications/`
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Engine top-level `app/email/` (sender, outbox, templates, policy, digest, scheduler, `models.EmailOutbox`) | Coincide con el precedente 09-D1: engines fuera de `modules/`; el puerto lo consumen notifications+alerts+reminders | **Elegida** |
| `app/modules/email/` (path del proposal) | `modules/` es para entidades CRUD; el transporte no es entidad | Rechazada |
| `NotificationPreference` bajo `app/email/` | Tiene REST (GET/PUT) → es entidad CRUD; va con la bandeja | Rechazada → vive en `app/modules/notifications/` |

**Rationale**: refina el path del proposal siguiendo Screaming Architecture (engines vs entidades), igual que 09.

### D2 — Outbox transaccional como fuente de verdad (hook único en `create()`)
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `create()` llama `enqueue_immediate_email(db, n)`: si `email_class(rule_type)=IMMEDIATE`, INSERTa una fila `email_outbox` (payload compuesto) y marca `notifications.emailed_at` en la MISMA tx | Encolado atómico con la notificación (durable ante crash); `emailed_at` en tx evita doble correo con el digest; una sola línea nueva en `create()`, simétrica a `buffer_notification` | **Elegida** |
| Bufferizar en `db.info` como el WS del 09 | El WS lo necesita por no tener store; el email SÍ tiene tabla → la volátil pierde durabilidad | Rechazada |
| Que el job pueble el outbox leyendo `notifications` | Reimplementa el "punto único" fuera de `create()` y retrasa lo urgente al intervalo | Rechazada |

**Rationale**: seam idéntico al 09 (repo importa `email_class`/`enqueue_immediate_email` de `app/email`, como importa `buffer_notification` de `app/realtime`). Render/SMTP quedan dentro del engine; el repo no los conoce. `EMAIL_ENABLED=off` → `enqueue_immediate_email` es no-op. **Frontera de imports (corrección de gate)**: `app/email/*.py` SOLO puede importar `app.modules.notifications.models` (jamás `.repository`) — espejo exacto del precedente `app/realtime/publisher.py`; violar esto crea el ciclo `notifications.repository → app.email → notifications.repository`.

### D3 — Despacho: SOLO el job APScheduler con sesión y commits propios (corrección de gate)
**El ÚNICO despachador es el job `email_dispatch`** (cada `EMAIL_DISPATCH_INTERVAL_MINUTES`). PROHIBIDO el drain inline en el evaluador de alertas: el gate demostró que las transiciones del outbox escritas sobre la sesión del evaluador tras el commit de la última organización quedan en una transacción implícita que jamás se commitea (`_run_evaluation` cierra sin commit final) → la fila revierte a `pending` y el correo se reenvía de forma determinista. La latencia máxima de un urgente = intervalo del job (aceptado; los urgentes nacen en el evaluador, que ya es un job periódico).
Contrato transaccional de `dispatch_outbox` (SIEMPRE con sesión propia `AsyncSessionLocal` y commits explícitos): (1) claim atómico por fila `UPDATE email_outbox SET status='sending', attempts=attempts+1 WHERE id=:id AND status='pending' RETURNING` + **`db.commit()` del claim ANTES de tocar SMTP** (el envío es efecto externo irreversible: el estado que lo autoriza debe estar durable); (2) `EmailSender.send`; (3) marca `sent`/`sent_at` o `pending` (reintento) / `failed` terminal según `EMAIL_MAX_ATTEMPTS` + `db.commit()` final. Filas `sending` viejas (crash entre commits) se reclaman por timeout (`updated_at` antiguo). Entrega **at-least-once** (`dedup_key` UNIQUE evita doble encolado; duplicado de envío solo en la ventana de crash entre send y el commit de `sent`, aceptado MVP y ahora sí acotado a esa ventana).

### D4 — Digest configurable con doble idempotencia
Job `email_digest` (cada `EMAIL_DIGEST_INTERVAL_MINUTES`): por cada `notification_preferences` con `daily`/`weekly` cuya hora (`EMAIL_DIGEST_TZ`, default `America/Bogota`) se cumplió desde `last_digest_at`, agrega TODAS las `Notification` no leídas con `emailed_at IS NULL` (channel-agnostic: menciones+alertas+reminders), compone UN correo, INSERTa 1 fila outbox con `dedup_key=f"digest:{user_id}:{periodo}"`, marca `emailed_at` de esas notificaciones y `last_digest_at`, todo en UNA tx. Doble corrida = no duplica: `dedup_key` UNIQUE + filtro `emailed_at IS NULL`. `none` → sin digest; los urgentes siguen inmediatos. **Fallo permanente (corrección de gate)**: si la fila outbox del digest alcanza `failed` terminal (agotó `EMAIL_MAX_ATTEMPTS`), las notificaciones marcadas `emailed_at` NO se re-digestan — pérdida del correo resumen aceptada y ACOTADA: se emite log ERROR con el `dedup_key` y las notificaciones siguen visibles vía REST (fuente de verdad); recuperación manual documentada = reset de la fila a `pending`. Escenario de spec dedicado al agotamiento de reintentos.

### D5 — Clasificación por `rule_type` (mapeo puro `email_class`)
`IMMEDIATE = {license_expired}` (activo vencido = riesgo de cumplimiento, siempre correo sin importar preferencia). Los demás (`task_overdue`, `sprint_at_risk`, `license_expiring`, menciones, reminders) llegan por el **digest** si el usuario optó — evita spam del evaluador horario y honra "digest configurable". Per-rule inmediato futuro = fila de preferencia, fuera de MVP. `alert-engine` intacto.

### D6 — Plantillas Python puras ES (sin Jinja) · D7 — Preferencias default `none`
`app/email/templates.py`: funciones puras `render_immediate(...)`/`render_digest(...)` → `(subject, text_body, html_body)`, HTML mínimo inline `multipart/alternative`, español colombiano formal (tuteo, regla dura). Sin Jinja (2 correos simples; menos dependencias, más testeable). `NotificationPreference` (org, user UNIQUE): `digest_frequency none|daily|weekly` **default `none`** (opt-in, no sorprender), `digest_hour`, `digest_weekday`, `last_digest_at`. Endpoints `GET`/`PUT /notifications/preferences` del propio usuario; defaults virtuales, fila creada al `PUT`.

### D8 — Puerto `EmailSender` + adaptadores
`console` (log estructurado + captura en memoria para tests, cero deps) y `smtp` (`aiosmtplib`, única dependencia nueva y SOLO en ese adaptador). `get_email_sender()` factory por `EMAIL_BACKEND`. Provider gestionado (SES/SendGrid/Resend) = adaptador nuevo, cero cambios en dominio/plantillas (documentado en docstring del puerto).

## Data Flow

    create() ─IMMEDIATE?─▶ INSERT email_outbox(pending) + notif.emailed_at   (misma tx de negocio)
    commit() ✔                                                               (el outbox queda durable con la tx)
    job email_dispatch (ÚNICO despachador, sesión propia) ─▶ dispatch_outbox:
        claim(pending→sending) + COMMIT ─▶ EmailSender.send ─▶ marca sent/pending/failed + COMMIT
    job email_digest ─▶ unread & emailed_at IS NULL ─▶ 1 outbox(digest) + marca emailed_at (1 tx + commit propio)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/email/{__init__,sender,policy,templates,outbox,digest,scheduler,models}.py` | Create | Puerto+adaptadores, `email_class`, render ES, `enqueue_immediate_email`/`dispatch_outbox`, digest, `register_email_jobs`, `EmailOutbox` |
| `app/modules/notifications/repository.py` | Modify | `create()` llama `enqueue_immediate_email(db, n)` |
| `app/modules/notifications/{models,schemas,repository,router}.py` | Modify/Create | `NotificationPreference` + GET/PUT preferencias; columna `emailed_at` |
| `app/alerts/evaluator.py` | **Sin cambios** (corrección de gate) | El drain inline se eliminó: el job `email_dispatch` es el único despachador |
| `app/main.py` | Modify | `register_email_jobs(scheduler)` si `EMAIL_ENABLED` |
| `app/config.py` | Modify | `EMAIL_ENABLED`(False), `EMAIL_BACKEND` **default `"console"`** (jamás toca red — garantiza que la suite de tests nunca alcanza SMTP sin fixture especial; `smtp` solo por config explícita), SMTP\_\*, intervalos, `EMAIL_MAX_ATTEMPTS`, `EMAIL_DIGEST_TZ` |
| `app/db_init.py` | Modify | Importar `EmailOutbox`/`NotificationPreference` |
| `alembic/versions/00XX_*.py` | Create | `email_outbox` + `notification_preferences` + `notifications.emailed_at` (encadena al head vigente; NO fijar número) |
| `requirements.txt` | Modify | `aiosmtplib` |
| `backend/tests/test_email_*.py` | Create | Suite TDD con captura |

## Interfaces / Contracts

```python
class EmailSender(Protocol):
    async def send(self, to: str, subject: str, text_body: str,
                   html_body: str | None = None) -> None: ...
def get_email_sender() -> EmailSender: ...                 # por EMAIL_BACKEND
def email_class(rule_type: str) -> EmailClass: ...          # IMMEDIATE | DIGESTIBLE
async def enqueue_immediate_email(db, n: Notification) -> None: ...  # INSERT outbox + emailed_at, en tx; no-op si off
async def dispatch_outbox(db) -> int: ...                   # claim atómico + send; compartido drain/sweep
async def drain_outbox_best_effort(db) -> None: ...         # try/except dispatch_outbox tras commit
async def dispatch_digest(db) -> int: ...                   # 1 correo/usuario, marca emailed_at
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | `email_class`; render ES (tuteo, sin voseo, `multipart/alternative`); `ConsoleEmailSender` captura; `SmtpEmailSender` arma MIME (mock `aiosmtplib.send`) | pytest, sin BD |
| Integration | `license_expired`→fila `pending`+`emailed_at` en tx; `drain`→captura 1 correo+`sent`; **SMTP falla→creación intacta, fila `pending`/`failed` reintentable**; no-inmediato→sin fila, `emailed_at NULL` | fixture SAVEPOINT + fake sender |
| Integration (digest) | pref `daily` hora cumplida→1 correo/usuario+`emailed_at`; **doble corrida no duplica** (`dedup_key`+`emailed_at`); `none`→sin digest pero urgente inmediato | invocar `dispatch_digest`/`dispatch_outbox` directo (patrón `test_reminder_dispatch.py`) |

## Threat Matrix

N/A — sin routing shell, subprocess, automatización VCS/PR ni clasificación de ejecutables (`aiosmtplib` es cliente de red, no subproceso). Superficie real: **fuga de credenciales/payload SMTP** (nunca loguear `to`/cuerpo/credenciales; settings desde `.env`) y **aislamiento cross-tenant del `to`** (outbox y digest siempre filtran por `organization_id`+`recipient_user_id`) — cubiertas como requisitos con RED tests, no como filas de esta matriz orientada a shell/git (mismo criterio que 09).

## Migration / Rollout

Migración única aditiva encadenada al **head vigente** (07 aplica antes; no fijar número). `downgrade()` = drop de ambas tablas + drop de la columna `emailed_at`; paridad Alembic autogenerate limpia. Rollout tras `EMAIL_ENABLED=false` (encolado y jobs no-op). Rollback = flag off o revertir merge; bandeja in-app/WS intacta (email desacoplado y best-effort). **Presupuesto**: ~1300-1400 líneas autoras (engine ~600 + preferencias ~150 + migración ~120 + tests ~450). `Decision needed before apply: Yes` · `Chained PRs recommended: Yes` · `400-line budget risk: High`. Corte sugerido a sdd-tasks: (1) puerto+adaptadores+plantillas+policy+config, (2) outbox+migración+hook+drain+sweep, (3) preferencias+digest+wiring; migraciones lineales al head.

## Open Questions

- [ ] Drain inmediato inline en jobs del scheduler; en flujos originados por request (menciones) se confía en el barrido para no bloquear la respuesta. ¿Aceptado?
- [ ] `EMAIL_DIGEST_TZ` fija por app en MVP vs. tz por usuario (futuro). Propuesta: fija `America/Bogota`.
