# Spec — Canal email y digest configurable (email-notifications)

> **Origen**: cambio 08-email-notifications

## Propósito

Canal de correo electrónico, agnóstico al proveedor, que complementa (no reemplaza) la bandeja in-app. Envía inmediato best-effort para tipos urgentes y agrupa el resto en un digest configurable por usuario, con idempotencia garantizada por outbox + `emailed_at`.

## Requisitos

### Requirement: Puerto `EmailSender` agnóstico al proveedor

El dominio (outbox, digest, preferencias) MUST depender exclusivamente de un puerto `EmailSender`. La implementación concreta MUST seleccionarse por configuración (`EMAIL_BACKEND`), nunca por lógica de dominio. Cambiar `EMAIL_BACKEND` MUST NOT requerir cambios en código de dominio ni en sus pruebas.

#### Scenario: Adaptador console en desarrollo/tests
- GIVEN `EMAIL_BACKEND=console`
- WHEN el sistema despacha un correo
- THEN el adaptador registra el mensaje en memoria sin enviarlo por red

#### Scenario: Cambiar de adaptador no toca el dominio
- GIVEN una organización con `EMAIL_BACKEND=smtp`
- WHEN se cambia a un adaptador nuevo (ej. proveedor gestionado futuro)
- THEN solo cambia la configuración; el código de outbox, digest y preferencias permanece intacto

### Requirement: Interruptor maestro `EMAIL_ENABLED`

Si `EMAIL_ENABLED=false`, el sistema MUST NOT encolar ni despachar ningún correo, sin afectar la creación ni persistencia de notificaciones in-app.

#### Scenario: Interruptor apagado
- GIVEN `EMAIL_ENABLED=false`
- WHEN se crea una notificación de `rule_type` urgente
- THEN la notificación se persiste igual y no se genera ningún envío ni fila de outbox

### Requirement: Envío inmediato de tipos urgentes

El sistema MUST mantener una clasificación de `rule_type` → urgente; `license_expired` MUST estar clasificado como urgente. Al crearse una notificación urgente, el sistema MUST encolarla en el outbox dentro de la misma transacción de negocio y despacharla post-commit best-effort. Un fallo del envío MUST NOT revertir ni bloquear la transacción que originó la notificación.

#### Scenario: Licencia vencida dispara correo inmediato
- GIVEN una notificación con `rule_type="license_expired"`
- WHEN su transacción de creación hace commit
- THEN el sistema despacha un correo inmediato best-effort al destinatario

#### Scenario: Fallo de envío no rompe la operación de negocio
- GIVEN el backend de envío no disponible (ej. SMTP caído)
- WHEN se crea una notificación urgente
- THEN la notificación queda persistida y la transacción de negocio se completa; el reintento queda a cargo del job periódico

### Requirement: Preferencia de digest por usuario

El sistema MUST exponer una preferencia de digest por `(organization_id, user_id)` con frecuencia `none|daily|weekly` y hora configurable. Si el usuario no tiene registro, MUST aplicar defaults sensatos (`none`). `none` MUST significar que el usuario nunca recibe digest, aunque igual recibe los urgentes inmediatos.

#### Scenario: Usuario con digest diario
- GIVEN un usuario con preferencia `daily` a las 08:00
- WHEN el job de digest corre a esa hora
- THEN recibe un único correo resumen de sus no leídas del período

#### Scenario: Usuario sin digest sigue recibiendo urgentes
- GIVEN un usuario con preferencia `none`
- WHEN se le crea una notificación `license_expired`
- THEN igual recibe el correo inmediato; el job de digest nunca le envía nada

### Requirement: Alcance y marcado del digest

El job de digest, para cada usuario con frecuencia distinta de `none` cuya hora configurada corresponda al período evaluado, MUST tomar TODAS las `Notification` no leídas del usuario con `emailed_at IS NULL`, componer un único correo resumen y, tras el envío, marcar `emailed_at` en cada notificación incluida.

#### Scenario: Digest agrupa orígenes distintos en un solo correo
- GIVEN un usuario con 3 notificaciones no leídas sin `emailed_at` (mención, alerta, recordatorio)
- WHEN corre su digest
- THEN recibe un solo correo que las resume todas y las 3 quedan con `emailed_at` asignado

### Requirement: Idempotencia del envío

Cada intento de envío MUST corresponder a una fila del outbox con `dedup_key` único. Ejecutar el job de digest o el drenaje del outbox dos veces sobre el mismo estado MUST NOT producir un segundo correo ni una segunda marca.

#### Scenario: Digest corrido dos veces no duplica
- GIVEN un digest ya despachado y sus notificaciones marcadas con `emailed_at`
- WHEN el job de digest vuelve a correr para el mismo usuario y período
- THEN no encuentra notificaciones con `emailed_at IS NULL` y no envía correo

#### Scenario: Reintento de outbox no duplica
- GIVEN una fila `pending` en el outbox cuyo envío anterior falló (attempts > 0)
- WHEN el job de despacho la reintenta
- THEN usa el mismo `dedup_key`; no se crea una fila ni un correo duplicado

#### Scenario: Agotamiento de reintentos termina en failed sin reintento infinito
- GIVEN una fila del outbox cuyo envío falló `EMAIL_MAX_ATTEMPTS` veces
- WHEN el job de despacho corre nuevamente
- THEN la fila queda en estado terminal `failed`, se registra un log de ERROR con su `dedup_key`, no se reintenta más, y las notificaciones asociadas permanecen visibles vía `GET /notifications` (la fuente de verdad no se pierde)

### Requirement: CRUD de preferencias de notificación

`GET /api/v1/notification-preferences` MUST devolver la preferencia del usuario autenticado (o defaults si no existe registro). `PUT /api/v1/notification-preferences` MUST crear o actualizar la preferencia del usuario autenticado, validando `frequency ∈ {none, daily, weekly}` y la hora. Una preferencia inválida MUST responder `422` con `detail`.

#### Scenario: GET sin registro previo devuelve defaults
- GIVEN un usuario sin fila en `notification_preferences`
- WHEN llama `GET /notification-preferences`
- THEN recibe `frequency=none` sin error

#### Scenario: PUT con frecuencia inválida
- GIVEN un usuario autenticado
- WHEN envía `PUT /notification-preferences` con `frequency="hourly"`
- THEN recibe `422` con el detalle del campo inválido

#### Scenario: PUT válido persiste y es legible
- GIVEN un usuario autenticado
- WHEN envía `PUT /notification-preferences` con `frequency="weekly"` y hora válida
- THEN un `GET` posterior refleja el cambio

### Requirement: Aislamiento multi-tenant

El outbox, `notification_preferences` y el digest MUST operar exclusivamente dentro del `organization_id` del destinatario. Un usuario de una organización MUST NOT ver ni recibir en su digest notificaciones de otra organización.

#### Scenario: Digest aislado entre dos organizaciones
- GIVEN usuarios homónimos en dos organizaciones distintas, cada uno con notificaciones no leídas propias
- WHEN corre el digest de ambos
- THEN cada correo resume únicamente las notificaciones de su propia organización

### Requirement: Plantillas en español colombiano formal

Todo asunto y cuerpo (texto plano + HTML) MUST estar redactado en español colombiano formal con tuteo, sin voseo rioplatense.

#### Scenario: Correo urgente usa tuteo formal
- GIVEN un correo inmediato de `license_expired`
- WHEN se compone el cuerpo
- THEN usa formas como "tu licencia" y "verifica" o "revisa", nunca voseo ("tenés", "verificá")

## Referencias

- `openspec/changes/08-email-notifications/proposal.md`
- `openspec/specs/notifications-inapp/spec.md` (punto único de creación)
- `openspec/specs/realtime-notifications/spec.md` (patrón best-effort post-commit del que este canal reutiliza el seam)
