# Proposal: 09 · WebSocket realtime (push in-app en tiempo real)

## Intent

Hoy la bandeja in-app (`notifications-inapp`) tiene un único canal: polling REST. El usuario solo ve una mención o una alerta del motor cuando refresca o cuando el badge se re-consulta; la latencia percibida es el intervalo de polling. El motor de alertas ya materializa notificaciones (con dedup por `dedup_key`) dentro del mismo proceso, pero no hay forma de empujarlas. Este cambio agrega un canal WebSocket que empuja la notificación en el instante de su creación, sin cambiar la fuente de verdad (REST sigue siendo autoritativa). Entregable **backend-only**: endpoint WS + contrato de mensajes documentado que el frontend congelado consumirá al descongelarse.

## Scope

### In Scope
- Endpoint `GET /api/v1/ws/notifications` (namespaced para futuros canales), autenticado en el handshake por JWT, con conexión scoped a `(organization_id, user_id)` del token.
- Puerto de publicación (`NotificationPublisher`) con implementación in-process (ConnectionManager: mapa org/usuario → set de sockets) y hook único en el punto de creación de notificaciones (evaluador de alertas + menciones + futuros reminders).
- Contrato de mensajes versionado (envelope `{v, type, ts, data}`), documentado para el frontend.
- Heartbeat ping/pong e idle-close; catch-up por REST en la reconexión.
- Suite TDD con Starlette TestClient WS (accept/reject de auth, forma del envelope, push-on-create, ping/pong, aislamiento por tenant).

### Out of Scope (non-goals)
- Cualquier cambio en `frontend/` (constraint `frontend-frozen`): solo se entrega el contrato.
- Redis pub/sub multi-réplica (seam documentado, no construido).
- Persistencia/replay de mensajes en la capa WS; garantía de entrega.
- Canal email/digest (corresponde a 08).
- Presencia, indicadores de escritura, canales de board/tablero.

## Capabilities

### New Capabilities
- `realtime-notifications`: endpoint WS, autenticación de handshake, scoping por tenant/usuario, envelope versionado y heartbeat.

### Modified Capabilities
- `notifications-inapp`: se levanta la limitación "canal único polling"; crear una notificación DEBE publicarse (best-effort) al canal realtime, sin alterar el modelo ni los endpoints REST.

## Approach

Decisiones de arquitecto (a ratificar en design):
- **Broadcast in-process detrás de un puerto para el MVP**: hoy corre un solo proceso uvicorn (el scheduler de alertas vive en el mismo lifespan/event loop). Un ConnectionManager en memoria basta, es testeable sin infra nueva y no introduce dependencia runtime de Redis. El puerto aísla el reemplazo por **Redis pub/sub** cuando haya réplicas — el mismo Redis del TODO de lock distribuido del evaluador.
- **Auth por subprotocol bearer** (`Sec-WebSocket-Protocol`) como primaria: el access token viaja en header `Authorization: Bearer`, que el `WebSocket` del navegador no puede fijar; el subprotocol mantiene el token fuera de la URL y los logs (mejor que query param) y la cookie solo porta el refresh. Se reutiliza `decode_token` + resolución de usuario; handshake inválido → close. El tradeoff del query param (fuga en logs de proxy/servidor) queda documentado como fallback.
- **Best-effort**: los sockets desconectados no rompen nada; la verdad sigue en `GET /notifications` + `unread-count`, recuperada en reconexión.
- **Testing**: Starlette TestClient (`websocket_connect`) en threadpool contra la app ASGI (determinista, sin contenedor); `websockets` contra el contenedor como smoke opcional.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/realtime/` | New | Router WS, ConnectionManager y puerto de publicación |
| `backend/app/modules/notifications/service.py` | Modified | Invocar publish tras crear la notificación |
| `backend/app/alerts/evaluator.py` | Modified | Publish tras materializar el candidato deduplicado |
| `backend/app/main.py` | Modified | Registrar router WS + wiring del publisher |
| `backend/app/config.py` | Modified | Flag `WS_ENABLED` e intervalo de heartbeat |
| `backend/tests/` | New | Suite WS con Starlette TestClient |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Auth WS mal resuelta (token en URL, fuga en logs) | Med | Subprotocol bearer; no loguear query; TLS; access token corto |
| Fan-out inválido con múltiples réplicas (in-process no cruza procesos) | Med | Puerto aislado; Redis pub/sub documentado como siguiente slice |
| Fuga de conexiones/memoria por sockets no cerrados | Med | Cleanup en disconnect + idle-close por heartbeat |
| httpx no soporta WS | Low | Starlette TestClient (ya en el stack) |
| Broadcast cross-tenant | Baja prob. / alto impacto | Scoping estricto por (org, user) del JWT + test de aislamiento |

## Rollback Plan

Cambio puramente aditivo, sin migración ni cambio de modelo. Rollback = apagar `WS_ENABLED` (el publish queda no-op y el router no se monta) o revertir el merge. La bandeja REST y su fuente de verdad quedan intactas.

## Dependencies

- `depends_on: 02-contrato-api` — resolución de auth-user y contrato de respuesta reutilizados por el payload de la notificación. Construye sobre las líneas base as-built `notifications-inapp` y `alert-engine` (ya existentes).

## Success Criteria

- [ ] El handshake WS acepta un JWT válido y rechaza/cierra el ausente o inválido, scoped a (org, user).
- [ ] Crear una notificación (mención o alerta) empuja un mensaje `notification.created` con envelope versionado al socket del destinatario.
- [ ] Un socket de otra organización/usuario NUNCA recibe la notificación.
- [ ] Ping/pong y cierre por inactividad verificados; la reconexión recupera vía REST.
- [ ] Todo nace con prueba en rojo (TDD estricto) usando Starlette TestClient WS.
