# Delta for email-notifications

## ADDED Requirements

### Requirement: Adaptador durable del hub sin cambios observables

El canal email MUST operar como un adaptador de política `durable` registrado en el hub de entregas (`notification-hub`), persistiendo sus intentos en `notification_deliveries` (rename de `email_outbox`) en vez de una tabla dedicada. Este cambio MUST NOT alterar ningún comportamiento observable ya especificado en este spec: `EMAIL_ENABLED`, `EMAIL_BACKEND`, el envío inmediato de tipos urgentes, el digest, la idempotencia por `dedup_key` ni el CRUD de preferencias.

#### Scenario: Comportamiento idéntico tras el refactor
- GIVEN el conjunto de escenarios ya vigentes de este spec (interruptor, envío inmediato, digest, idempotencia, preferencias, aislamiento multi-tenant)
- WHEN el canal email pasa a ser un adaptador del hub sobre `notification_deliveries`
- THEN cada uno de esos escenarios sigue cumpliéndose exactamente igual, sin cambios observables desde la API ni en el correo entregado

#### Scenario: EMAIL_ENABLED sigue neutralizando el canal durable
- GIVEN `EMAIL_ENABLED=false`
- WHEN se crea una notificación urgente
- THEN el canal email (ahora adaptador del hub) no encola ninguna fila en `notification_deliveries` ni despacha correo
