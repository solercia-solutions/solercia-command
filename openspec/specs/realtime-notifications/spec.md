# Spec — Notificaciones en tiempo real (realtime-notifications)

> **Origen**: cambio [09-websocket-realtime](../../changes/archive/2026-07-12-09-websocket-realtime/)

## Propósito

Canal WebSocket que empuja notificaciones in-app en el instante de su creación, complementando (no reemplazando) el polling REST de `notifications-inapp`. Best-effort: REST sigue siendo la fuente de verdad.

## Alcance

| Método | Ruta | Propósito |
|--------|------|-----------|
| WS | /api/v1/ws/notifications | Push scoped a `(organization_id, user_id)` del token |

Autenticación de handshake: subprotocolo bearer (`Sec-WebSocket-Protocol`) primario; query param como fallback documentado (riesgo de fuga en logs de proxy). Reutiliza `decode_token` + resolución de usuario existentes.

## Requirements

### Requirement: Handshake autenticado

El sistema MUST aceptar la conexión solo si el token del handshake (subprotocolo bearer o, como fallback, query param) es válido y resuelve a un usuario activo, enviando `connection.ack` como primer mensaje. Con token ausente o inválido, MUST cerrar la conexión sin enviar `connection.ack`.

#### Scenario: Token válido

- GIVEN un cliente que se conecta con un JWT válido
- WHEN el servidor completa el handshake
- THEN acepta la conexión y envía `connection.ack` como primer mensaje

#### Scenario: Token ausente o inválido

- GIVEN un cliente sin token o con un JWT inválido/expirado
- WHEN el servidor evalúa el handshake
- THEN cierra la conexión con código de error, sin enviar `connection.ack`

### Requirement: Scoping estricto por organización y usuario

El sistema MUST asociar cada conexión aceptada a `(organization_id, user_id)` resuelto del token y MUST NOT entregar por esa conexión ningún mensaje que pertenezca a otra organización o a otro usuario.

#### Scenario: Aislamiento entre dos organizaciones

- GIVEN un usuario A en la organización 1 y un usuario B en la organización 2, ambos conectados
- WHEN se crea una notificación para A
- THEN solo el socket de A la recibe; el socket de B no recibe nada

#### Scenario: Aislamiento entre usuarios de la misma organización

- GIVEN dos usuarios conectados en la misma organización
- WHEN se crea una notificación dirigida a uno de ellos
- THEN solo el socket del destinatario la recibe

### Requirement: Push en creación de notificación

Cuando se crea una notificación por mención o por el motor de alertas, el sistema MUST intentar publicar `notification.created` a todas las conexiones abiertas del destinatario, con el payload de la notificación creada.

#### Scenario: Mención genera push

- GIVEN un usuario mencionado con un socket abierto y autenticado
- WHEN se crea su notificación de mención
- THEN su socket recibe `notification.created` con los datos de la notificación

#### Scenario: Alerta del motor genera push

- GIVEN un usuario con socket abierto
- WHEN el evaluador de alertas materializa un candidato deduplicado como notificación para él
- THEN su socket recibe `notification.created`

### Requirement: Best-effort ante desconexión

La ausencia de un socket conectado o un fallo al publicar MUST NOT impedir ni afectar la creación/persistencia de la notificación.

#### Scenario: Usuario desconectado

- GIVEN un usuario sin ningún socket WS abierto
- WHEN se crea una notificación para él
- THEN la notificación se persiste igual y queda disponible vía `GET /notifications` al reconectar

### Requirement: Heartbeat y cierre por inactividad

El sistema MUST enviar `ping` periódico a cada conexión abierta y MUST cerrarla si no recibe `pong` dentro del intervalo configurado.

#### Scenario: Cliente responde a tiempo

- GIVEN una conexión abierta
- WHEN el servidor envía `ping` y el cliente responde `pong` a tiempo
- THEN la conexión permanece abierta

#### Scenario: Cliente inactivo se cierra

- GIVEN una conexión abierta
- WHEN el cliente no responde `pong` dentro del intervalo configurado
- THEN el servidor cierra la conexión

### Requirement: Envelope de mensajes versionado

Todo mensaje MUST incluir al menos `v` (versión entera del contrato) y `type` (uno del catálogo: `connection.ack`, `notification.created`, `ping`, `pong`, `error`), y `data` (payload, u objeto vacío/`null` cuando el tipo no lleva payload). El envelope MAY incluir metadatos adicionales (por ejemplo, timestamp) sin romper compatibilidad hacia adelante.

#### Scenario: Forma del envelope en push

- GIVEN una notificación creada para un usuario conectado
- WHEN el servidor publica el mensaje
- THEN el mensaje cumple `{v: 1, type: "notification.created", data: {...}}`

## Limitaciones y deuda conocida

- Implementación in-process con ConnectionManager en memoria; séquelo por Redis pub/sub cuando haya réplicas.
- Best-effort: sockets desconectados no rompen nada; verdad en GET /notifications + unread-count, recuperada en reconexión.
- Sin persistencia/replay en la capa WS (aterrizaje en aislamiento tenant o punto de creación).

## Referencias

- backend/app/modules/realtime/ (router WS, ConnectionManager, publisher port)
- backend/app/modules/notifications/service.py (publicación en creación)
- backend/app/alerts/evaluator.py (publicación al materializar candidato)
- backend/tests/test_realtime_ws_auth.py, test_realtime_push.py (suite WS)
