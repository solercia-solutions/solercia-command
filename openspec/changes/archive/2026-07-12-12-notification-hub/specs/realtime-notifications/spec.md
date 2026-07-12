# Delta for realtime-notifications

## ADDED Requirements

### Requirement: Adaptador best-effort del hub sin cambios observables

El canal realtime MUST operar como un adaptador de política `best_effort` registrado en el hub de entregas (`notification-hub`), sin persistir fila en `notification_deliveries`. Este cambio MUST NOT alterar ningún comportamiento observable ya especificado en este spec: handshake autenticado, scoping por organización/usuario, push en creación, best-effort ante desconexión, heartbeat ni el envelope versionado.

#### Scenario: Comportamiento idéntico tras el refactor
- GIVEN el conjunto de escenarios ya vigentes de este spec (handshake, scoping, push, best-effort, heartbeat, envelope)
- WHEN el canal realtime pasa a ser un adaptador `best_effort` del hub
- THEN cada uno de esos escenarios sigue cumpliéndose exactamente igual, sin cambios observables en el protocolo WS

#### Scenario: Falla de publicación no genera registro de fallo durable
- GIVEN un usuario sin ningún socket WS conectado
- WHEN se crea una notificación para él
- THEN el hub no persiste ninguna fila en `notification_deliveries` para el intento fallido best-effort, y la notificación sigue disponible vía `GET /notifications`
