# Design: 12 · Notification Hub (entrega agnóstica al canal)

## Technical Approach

Engine top-level nuevo `app/notify/` (hermano de `app/email/`, `app/realtime/`, `app/alerts/`; **no** bajo `modules/`): puerto `DeliveryChannel` + `DeliveryPolicy`, registro import-time (precedente `app/alerts/registry.py`), store port sobre `notification_deliveries` (rename de `email_outbox`) y despachador genérico. `NotificationRepository.create()` deja de cablear 2 llamadas y **itera el registro**: por cada canal `durable` llama `enqueue(db, n)`, por cada `best_effort` llama `buffer(db, n)`. El drenaje post-commit (`flush_pending`) queda intacto en sus 2 call-sites (`alerts/evaluator.py:68`, `comments/service.py:278`). Refactor sin cambio de comportamiento: email→adaptador `durable`, WS→adaptador `best_effort`; in-app queda FUERA del hub como fuente de verdad. Hereda la frontera de imports de `app/email` (el núcleo NUNCA importa `notifications.repository`).

## Architecture Decisions

### D1 — Ubicación y nombre: engine `app/notify/`
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `app/notify/` (puerto, registro, store, despachador) | Palabra única, sibling de email/realtime (precedente 08-D1/09), sin colisión visual con la entidad | **Elegida** |
| `app/notifications_hub/` (propuesta) | snake_case largo rompe la convención de engines de una palabra | Rechazada |
| dentro de `modules/notifications/` | `modules/` es para entidades CRUD; el transporte no es entidad (mismo criterio 08-D1) | Rechazada |

### D2 — Contrato: DOS protocolos por política (no uno con métodos opcionales)
`durable` y `best_effort` tienen ciclos y métodos disjuntos (outbox durable vs `db.info` volátil). Un protocolo único con métodos opcionales invita a `None`-checks y canales a medio implementar; dos protocolos hacen de la política un TIPO, no una rama en runtime, y el despachador particiona por política.
- `enqueue(db, n)` (no `build_payload(n)`): la aplicabilidad de email exige BD (resuelve destinatario) y tiene efecto de dominio en la misma tx (`emailed_at`), que una función pura `build_payload(n)` no expresa. La fila la INSERTa el **store port** del hub, no el canal → canal desacoplado de la tabla.
- `deliver(payload)` puro (payload autocontenido) → el despachador genérico no conoce nada específico del canal.
- `best_effort` conserva `buffer` (pre-commit) + `flush_pending` externo (post-commit): renombrar a un `publish(db,n)` único publicaría ANTES del commit o forzaría retargetear 2 call-sites sin ganancia.

### D3 — Outbox generalizado + despachador genérico (rename 0013)
`email_outbox` → `notification_deliveries` **renombrada en sitio** (preserva PK/FK/índices/filas vivas): `+channel` (default `'email'`, NOT NULL), `+payload` JSONB poblado desde las columnas típadas, `drop` de `recipient_email/subject/text_body/html_body`. Se rechaza tabla-nueva+copia (duplica superficie, arriesga drift de índices). El status es `native_enum=False` (VARCHAR+CHECK): sin churn de enum PG. `dispatch_outbox`→`dispatch_deliveries(db)` reusa el contrato transaccional probado byte a byte (claim atómico `pending→sending` + `commit()` ANTES del send + `sent`/`pending`/`failed` terminal); itera pending y despacha por `row.channel` al `deliver` registrado.

### D4 — Gating del job (sin flag nuevo)
`EMAIL_ENABLED` sigue gateando SOLO el canal email (su `enqueue` es no-op si off). No se agrega `NOTIFY_ENABLED` (segundo master switch ambiguo). El job de despacho se renombra `email_dispatch`→`delivery_dispatch` y se registra bajo el helper `has_active_durable_channel()` — hoy `== EMAIL_ENABLED`, misma condición observable de arranque. El **digest sigue siendo job de dominio email** (`email_digest`, agrega N notificaciones en UN correo) que ENCOLA en la tabla generalizada vía el store port.

### D5 — Los 3 canales
| Canal | Política | Refactor |
|-------|----------|----------|
| **InApp** | — (NO es canal) | La persistencia de `Notification` ES la creación y la fuente de verdad REST; hacerla canal sería circular (crearía la fila que dispara el fan-out). El hub maneja canales ADICIONALES tras `flush/refresh`. |
| **WebSocket** | best_effort | `WebSocketChannel.buffer` delega en `buffer_notification`; `flush_pending` intacto. Cero cambio de comportamiento. |
| **Email** | durable | `EmailChannel.enqueue` = cuerpo de `enqueue_immediate_email` (email_class + resolución destinatario + render + `emailed_at`), INSERT delegado a `store.enqueue_delivery(channel='email', payload={recipient_email,subject,bodies}, dedup_key=f"immediate:{n.id}")`; `EmailChannel.deliver(payload)` = cuerpo del send de `dispatch_outbox`. |

### D6 — Endpoint `GET /notifications/{id}/deliveries` + atribución del digest
Gate (corrección de gate adversarial — ratificado por el orquestador y fijado dos veces en el proposal): **SOLO rol admin|manager** (`MemberRole`, chequeo inline patrón `_SUPERVISOR_ROLES` de `time_logs`), SIN excepción de dueño — es un endpoint de auditoría operativa cuyo payload expone `recipient_email` y `last_error`; el dueño ya conoce su notificación vía `GET /notifications`. Solo canales `durable` aparecen (best_effort no tiene store, por definición). **Digest = opción (b)**: la fila digest mantiene `notification_id=NULL` + `emailed_at` como marcador por-notificación; el endpoint muestra entregas inmediatas (match por `notification_id`) y deriva `digested = emailed_at IS NOT NULL AND sin fila inmediata`. Se rechaza el puente M:N (a): auditabilidad total pero tabla nueva + N inserts por digest para una feature no-MVP. El puente queda como frontera futura.

## Data Flow

    create() ─▶ persist Notification (flush/refresh)  = in-app (fuente de verdad)
             └▶ for ch in get_channels():                       # AISLAMIENTO DE FALLOS (corrección de gate):
                   try:                                          # cada canal va en try/except + log ERROR —
                     durable    → ch.enqueue(db,n)  → store.enqueue_delivery(row pending, misma tx)
                     best_effort→ ch.buffer(db,n)   → db.info    # la excepción de un canal JAMÁS rompe la
                   except → log.exception(canal)                 # creación ni afecta a los demás canales;
                                                                 # la entrega perdida queda auditada en el log
    commit() ✔   (owner)  ─▶ flush_pending(db)  (WS, best-effort, sin cambios)
    job delivery_dispatch ─▶ dispatch_deliveries: claim+COMMIT ─▶ ch.deliver(payload) ─▶ sent/pending/failed+COMMIT
    job email_digest ─▶ store.enqueue_delivery(channel='email', notification_id=NULL) + emailed_at

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/notify/{__init__,ports,registry,store,dispatcher}.py` | Create | `DeliveryChannel`/`DeliveryPolicy`, registro import-time, `enqueue_delivery`, `dispatch_deliveries`, `has_active_durable_channel` |
| `app/notify/models.py` (o mover a store) | Create | `NotificationDelivery` (generaliza `EmailOutbox`) |
| `app/email/models.py` | **Delete** (corrección de gate) | `EmailOutbox` desaparece — reemplazado por `NotificationDelivery`; todos sus imports (db_init, digest, outbox, tests) migran al modelo nuevo |
| `app/email/{outbox,scheduler}.py` | Modify | `EmailChannel` (enqueue/deliver) sobre store; `register_delivery_jobs` |
| `app/email/digest.py` | Modify (corrección de gate) | Construye la entrega vía `store.enqueue_delivery(channel='email', notification_id=NULL, payload=JSONB)` — HOY instancia `EmailOutbox` con las columnas típadas (`recipient_email/subject/text_body/html_body`) que la 0013 elimina; sin este cambio el digest fallaría silenciosamente dentro del try/except del job |
| `app/db_init.py` | Modify (corrección de gate) | Importa `NotificationDelivery` en lugar de `EmailOutbox` (registro en Base.metadata para create_all/alembic env) |
| `app/realtime/publisher.py` | Modify | `WebSocketChannel.buffer` envuelve `buffer_notification` (flush_pending intacto) |
| `app/modules/notifications/repository.py` | Modify | `create()` itera `get_channels()` |
| `app/modules/notifications/{router,service,schemas}.py` | Modify | `GET /{id}/deliveries` |
| `app/shared/enums.py` | Modify | `DeliveryStatus` con alias `EmailOutboxStatus` (tests verdes sin editar imports) |
| `app/main.py` | Modify | `register_delivery_jobs` bajo `has_active_durable_channel()` |
| `alembic/versions/0013_*.py` | Create | rename + channel + payload + copia datos + downgrade completo |

## Interfaces / Contracts

```python
class DeliveryPolicy(StrEnum): durable="durable"; best_effort="best_effort"

class DeliveryChannel(Protocol):
    name: str; policy: DeliveryPolicy

class DurableChannel(DeliveryChannel, Protocol):
    async def enqueue(self, db, n: Notification) -> None: ...   # aplica? + payload + side-effects + store
    async def deliver(self, payload: dict) -> None: ...          # despachador envía payload autocontenido

class BestEffortChannel(DeliveryChannel, Protocol):
    def buffer(self, db, n: Notification) -> None: ...           # db.info; flush post-commit externo

def register_channel(c) -> None; def get_channels() -> list[DeliveryChannel]
async def enqueue_delivery(db, *, channel, notification_id, organization_id, dedup_key, payload) -> None
async def dispatch_deliveries(db) -> int
```

## Fronteras de extracción futura

El núcleo `app/notify/` importa SOLO `notifications.models` + `app.shared.*`; NUNCA `notifications.repository` (regla heredada de `app/email`). Los canales viven en su dominio (email en `app/email`, WS en `app/realtime`) y se REGISTRAN en el hub; el hub no importa internos de dominio — los dominios importan los puertos del hub. Puertos a extraer luego: **store** (persistencia de entregas), **scheduler** (registro de jobs), **resolución de destinatario** (hoy el canal email hace `select(User.email)` → futuro `resolve_recipient(n, channel)`). NO se extrae ahora: la entidad `Notification`/su repository (in-app, fuente de verdad) ni el render/send de cada dominio. NO se extrae paquete instalable (ratificado).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | registro (register/get, partición por política); `create()` fan-out (canal fake `durable`→`enqueue`, `best_effort`→`buffer`); **aislamiento de fallos: canal fake que LANZA junto a canal sano → el sano recibe, la Notification persiste y la tx sobrevive (corrección de gate)** | fixture que snapshotea `_CHANNELS`, añade fake, restaura |
| Integration (adapta) | `test_email_outbox`: `emailed_at`+fila pending SIN cambio de aserción de status/dedup; payload desde `row.payload['...']`. `test_email_dispatch`: `dispatch_outbox`→`dispatch_deliveries`, seed con `channel='email'`+payload; status/attempts/sent_at SIN cambio. `test_email_digest`: encola vía store, `emailed_at`/idempotencia SIN cambio | alias `EmailOutboxStatus` evita editar imports de status |
| Integration (NO cambia) | `test_realtime_manager`: `buffer_notification`/`flush_pending` (pop atómico, no-republish, swallow) — aserciones idénticas; `test_mention_notifications`: call-site intacto | el canal WS envuelve las MISMAS funciones |
| Integration (nuevo) | `GET /{id}/deliveries`: member (incluido el DUEÑO de la notificación) → 403; admin/manager → 200; notif digestida `digested:true` sin fila inmediata; WS ausente; aislamiento dos orgs → 404 | httpx AsyncClient |
| Migration | fila `email_outbox` pre-migración sobrevive upgrade con `channel='email'`+payload poblado; downgrade restaura columnas típadas | ciclo upgrade/downgrade |

## Threat Matrix

N/A — sin routing, shell, subprocess, automatización VCS/PR ni clasificación de ejecutables (refactor interno + 1 GET + migración; `aiosmtplib` es cliente de red). Superficie real: **fuga de payload/credenciales** (nunca loguear payload/`to`) y **aislamiento cross-tenant** (store, dispatcher, digest y `/deliveries` filtran por `organization_id`) — cubiertas como requisitos con RED tests, mismo criterio que 08/09.

## Migration / Rollout

Migración única `0013` encadenada al head `0012`, downgrade completo (rename inverso + re-add columnas típadas back-filled desde `payload` + drop channel/payload) probado sin pérdida de filas. Rollout = refactor sin cambio de comportamiento; `EMAIL_ENABLED=false` sigue neutralizando el canal durable; in-app/WS y su fuente de verdad REST intactas. **Presupuesto**: ~700-900 líneas autoras (núcleo ~250 + adaptadores ~150 + migración ~150 + endpoint ~80 + tests ~250). `Decision needed before apply: Yes` · `Chained PRs recommended: Yes` · `400-line budget risk: High`. Corte a sdd-tasks: (1) migración 0013 + `NotificationDelivery` + store + test de migración; (2) puertos+registro+despachador genérico + refactor Email/WS channels + `create()` itera + adaptar tests email/realtime; (3) endpoint `/deliveries` + tests + fronteras de extracción.

## Open Questions

- [x] Gate de `/deliveries` — RESUELTO por el orquestador (gate adversarial): SOLO admin|manager, sin excepción de dueño (D6 corregido).
- [x] CHECK `email_outbox_status` — RESUELTO: conservar valores + alias Python `EmailOutboxStatus` (ratificado).
