# Design: 09 · WebSocket realtime (push in-app en tiempo real)

## Technical Approach

Engine top-level nuevo `app/realtime/` (hermano de `app/alerts/`, **no** bajo `modules/`): transporte WS + `ConnectionManager` in-process + puerto `NotificationPublisher`. El punto ÚNICO de nacimiento de una notificación es `NotificationRepository.create()` (el evaluador y las menciones lo usan directo; el `NotificationService` solo lee/actualiza). Ahí se **bufferiza** un payload serializado; el push se **drena tras el commit** con un helper compartido `flush_pending(db)`, invocado una vez por cada dueño de transacción. Best-effort: REST sigue autoritativo y ningún socket muerto rompe la creación. Aditivo, **sin migración**. TDD estricto con Starlette TestClient WS. Depende de 02 (auth-user, contrato `NotificationRead`).

## Architecture Decisions

### D1 — Ubicación: engine top-level `app/realtime/`
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `app/realtime/` (sibling de `alerts/`) | Coincide con el precedente: `alerts/` es engine cross-cutting fuera de `modules/`; el puerto lo consumen notifications+comments+alerts+reminders futuros | **Elegida** |
| `app/modules/realtime/` (path del proposal) | `modules/` es para entidades CRUD con model/repo/schema; el transporte no es una entidad | Rechazada |
| Dentro de `notifications/` | Fuerza imports cross-módulo desde comments/alerts hacia internals de un sibling; difumina el límite "notifications = CRUD REST" | Rechazada |

**Rationale**: Screaming Architecture del repo separa engines (`alerts/`) de entidades (`modules/*`). Realtime es un engine de entrega. Refinamiento ratificado del path del proposal.

### D2 — Hook único de publicación: buffer en `create()` + drain tras commit
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `create()` bufferiza payload serializado; `flush_pending(db)` drena tras `commit()` | Único punto de "qué publicar" (DRY para evaluador+menciones+reminders); publica solo lo commiteado | **Elegida** |
| Publicar dentro de `create()` | `create()` hace `flush()`, NO commit → anunciaría antes del commit (viola D5) | Rechazada |
| Evento SQLAlchemy `after_commit` | El repo ya rechazó listeners en design 05 (bulk UPDATE los salta; sin actor); + puente sync-event→loop async frágil | Rechazada |
| Publicar en cada call-site | Duplica la construcción del payload → drift (justo lo que "único punto" prohíbe) | Rechazada |

**Rationale**: sigue el precedente vinculante del repo (asignación explícita, no listeners). `create()` serializa el envelope al bufferizar (evita expiry ORM post-commit). Manejo de error: `flush_pending` envuelve todo en try/except + log; corre DESPUÉS del commit, así que jamás rompe la creación. Rollback → nunca se llama al drain (la verdad queda en REST); en ese caso el buffer huérfano se descarta en el siguiente drain-pop o muere con la sesión. **Contrato del drain (corrección de gate)**: `flush_pending` hace `pending = db.info.pop("realtime_pending", [])` ANTES de publicar — vacía el buffer atómicamente. Esto es obligatorio porque `evaluate_all_organizations` reutiliza UNA sesión para N organizaciones con un ciclo commit+drain por organización: sin el pop, los payloads de la org 1 se re-publicarían en los drains de las siguientes.

### D3 — ConnectionManager
Índice `dict[(org_id, user_id), set[WebSocket]]` (clave tupla → aísla por tenant por construcción; `set` soporta múltiples pestañas del mismo usuario). **Sin `asyncio.Lock`**: el event loop es mono-hilo; `register`/`unregister` son mutaciones síncronas sin `await` intermedio (atómicas); `publish` itera sobre un **snapshot** `list(sockets)` para tolerar desconexiones concurrentes. Cleanup en `disconnect` (descarta el socket y purga la clave vacía) evita fugas.

### D4 — Auth WS: validar ANTES de accept
Flujo: leer token del header `Sec-WebSocket-Protocol` (`"bearer, <token>"`) o, como fallback documentado, `?token=` (tradeoff: fuga en logs de proxy). Validar reutilizando un helper extraído `authenticate_access_token(db, token) -> User` que **lanza las mismas `AppException` que hoy** (`invalid_token` para decode/subject/UUID inválidos; `user_not_found` para usuario inexistente/inactivo) — corrección de gate: la firma `-> User | None` colapsaría códigos de error que REST distingue. `get_current_user` delega en él sin alterar códigos ni mensajes (cero regresión REST); el router WS lo envuelve en try/except `AppException` → rechazo pre-accept. Org scope = primera membresía (idéntico a REST).
- **Inválido/ausente → `close()` ANTES de `accept()`**: Starlette responde **HTTP 403** al handshake, sin upgrade 101. Menor privilegio, semántica REST-like, el front cae a REST.
- **Válido → `accept(subprotocol="bearer")`** (eco obligatorio para el navegador) → `connection.ack` → `manager.register`.
- Alternativa registrada: `accept`+`close(4401/1008)` da código leíble por el cliente pero upgradea a un no-autenticado; se descarta para el MVP.

### D5 — Timing push vs commit
`create()` bufferiza en `flush`; el push ocurre solo en `flush_pending(db)` tras `commit()`. Evaluador: un único `commit()` al final de `evaluate_organization` → un drain publica todo lo bufferizado. Menciones: `commit()` en `_dispatch_mention_notifications` → drain. El buffer guarda datos serializados, no ORM, así que el expiry post-commit es irrelevante.

## Data Flow

    create() ──buffer(payload)──▶ db.info["realtime_pending"]        (en flush, no publica)
    commit() ✔ ──▶ flush_pending(db) ──▶ manager.publish(org,user,envelope)
                                            └─ list(set[WS] de (org,user)) → send_json (try/except+log)

    WS connect ─▶ token(subprotocol|?token) ─▶ authenticate_access_token
        inválido → close ANTES de accept (HTTP 403)
        válido   → accept(subprotocol="bearer") → connection.ack → register(org,user,ws)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/realtime/{__init__,manager,publisher,router,schemas}.py` | Create | `ConnectionManager` singleton; puerto `NotificationPublisher`+`buffer_notification`/`flush_pending`; endpoint WS+auth+heartbeat; envelope |
| `app/modules/notifications/repository.py` | Modify | `create()` llama `buffer_notification(db, notification)` |
| `app/alerts/evaluator.py` | Modify | `await flush_pending(db)` tras `db.commit()` |
| `app/modules/comments/service.py` | Modify | `await flush_pending(self._db)` tras el commit de menciones |
| `app/main.py` | Modify | Montar router WS si `WS_ENABLED` |
| `app/config.py` | Modify | `WS_ENABLED`, `WS_HEARTBEAT_SECONDS`, `WS_IDLE_TIMEOUT_SECONDS` |
| `app/dependencies.py` | Modify | Extraer `authenticate_access_token(db, token)`; `get_current_user` delega |
| `backend/tests/test_realtime_*.py` | Create | Unit + integración WS + e2e push |

## Interfaces / Contracts

```python
class NotificationPublisher(Protocol):
    async def publish(self, org_id: UUID, user_id: UUID, envelope: dict) -> None: ...

def buffer_notification(db: AsyncSession, n: Notification) -> None: ...   # serializa NotificationRead
async def flush_pending(db: AsyncSession) -> None: ...   # pop atómico de db.info["realtime_pending"] + publish; best-effort
async def authenticate_access_token(db, token: str) -> User: ...   # lanza AppException (invalid_token | user_not_found); reutilizado por get_current_user y WS
```

Envelope `{"v":1,"type":<t>,"ts":<iso8601>,"data":<obj>}`; tipos: `connection.ack`, `notification.created` (`data` = `NotificationRead`), `ping`/`pong`, `error`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | ConnectionManager register/unregister/publish; **aislamiento tenant** (publish a (orgA,userX) nunca llega a socket (orgB,userY)); **multi-pestaña** (2 sockets, ambos reciben); best-effort (un send que lanza no bloquea al otro ni propaga) | pytest-asyncio con WebSocket doubles, sin BD |
| Integration (WS) | Handshake acepta subprotocol bearer válido; **cierra antes de accept** si falta/inválido; `connection.ack` + `v`; ping/pong; idle-close | Starlette `TestClient.websocket_connect(subprotocols=["bearer", token])` |
| E2E (push) | WS conectado + crear notificación (mención vía REST / alerta) por el **mismo TestClient** → `notification.created`; segundo WS de otro user/org **no** recibe | TestClient WS + REST (mismo portal/loop). **Gotcha**: NO mezclar con la fixture async SAVEPOINT (TestClient corre su propio loop/sesiones). **Corrección de gate — BD**: PROHIBIDO usar el `get_db` real ligado a `settings.DATABASE_URL` (apuntaría a la BD de desarrollo `solercia` o fallaría por DNS fuera de compose). El test E2E instala `app.dependency_overrides[get_db]` con un factory que crea, DENTRO del loop del TestClient, un engine propio `NullPool` sobre `TEST_DATABASE_URL` (`solercia_test`, mismo origen que conftest) y sesiones sobre él; limpieza explícita (DELETE de las filas creadas) en teardown y `dispose()` del engine |
| Smoke (opt, verify) | `websockets` contra el contenedor `ws://localhost:8000/api/v1/ws/notifications` con token real | Black-box opcional |

## Threat Matrix

N/A — sin routing shell, subprocess, automatización VCS/PR ni clasificación de ejecutables. La superficie de seguridad real (bypass de auth en handshake, fuga cross-tenant) se cubre como requisitos de D3/D4 con RED tests dedicados en Testing Strategy, no como filas de esta matriz orientada a shell/git.

## Migration / Rollout

**Sin migración** (confirmado): no hay cambios de modelo, tablas ni columnas; `Notification` intacto. Rollout tras flag `WS_ENABLED` (off → router no montado y `flush_pending` no-op por ausencia de sockets). Rollback = apagar el flag o revertir el merge; REST y su fuente de verdad intactos. **Presupuesto**: ~500-600 líneas autoras (engine ~220 + hooks ~30 + tests ~300). `400-line budget risk: Medium` — feature cohesiva y aditiva tras flag; entregable como PR único o slice si el gate lo exige (lo decide sdd-tasks).

## Open Questions

- [ ] ¿`WS_ENABLED` default `True` o `False` en el primer merge? Propuesta: `True` (el front congelado no lo consume aún; sin riesgo).
- [ ] ¿El envelope `notification.created` embebe `NotificationRead` completo o un subconjunto? Propuesta: completo, para una sola forma de payload que el front reutilice.
