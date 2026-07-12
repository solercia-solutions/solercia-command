# Spec — Hub de entrega de notificaciones (notification-hub)

> **Origen**: cambio [12-notification-hub](../../changes/12-notification-hub/)

## Propósito

Punto único de fan-out para toda `Notification` creada. El núcleo entrega a todos los canales de comunicación registrados mediante un puerto común, sin conocer los detalles de cada canal. Los canales de política `durable` quedan auditables por entrega (canal, estado, intentos); los `best_effort` no. Reemplaza el cableado manual actual (`buffer_notification` + `enqueue_immediate_email` invocados a mano desde `create()`).

## Alcance

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/notifications/{id}/deliveries | Auditoría de entregas por canal de una notificación (rol admin/manager) |

Modelo `notification_deliveries` (rename de `email_outbox`, agnóstico al canal):

| Campo | Descripción |
|-------|-------------|
| notification_id | FK → Notification (nulo cuando la entrega agrega varias, ej. digest) |
| channel | Nombre del canal que generó la entrega |
| status | pending \| sent \| failed |
| attempts | Intentos de despacho realizados |
| last_error | Último error registrado, si lo hubo |
| dedup_key | Clave de idempotencia del intento |
| payload | JSONB con los datos específicos del canal (ej. asunto/cuerpos de email) |
| sent_at | Momento del envío exitoso |

## Requisitos

### Requirement: Puerto `DeliveryChannel` y registro extensible

Todo canal de entrega MUST implementar un contrato común (`name`, `policy` ∈ `durable`\|`best_effort`, render/despacho del payload). Registrar un canal nuevo MUST NOT requerir cambios en el núcleo del hub ni en el punto único de creación de `Notification`.

#### Scenario: Canal de prueba recibe el fan-out sin tocar el núcleo
- GIVEN un canal `fake` registrado en el registro de canales solo para la prueba, con `policy=best_effort`
- WHEN se crea una `Notification`
- THEN el canal `fake` recibe la notificación en el fan-out, sin que el punto de creación ni el hub hayan requerido cambios de código

### Requirement: Fan-out único a todos los canales aplicables

Al crearse una `Notification`, el hub MUST entregarla a TODOS los canales registrados aplicables. El fallo de un canal MUST NOT afectar a otro canal ni a la transacción de negocio que originó la notificación.

#### Scenario: Canal durable encola en la misma transacción
- GIVEN un canal con `policy=durable` registrado
- WHEN se crea una `Notification` y su transacción hace commit
- THEN existe una fila en `notification_deliveries` para ese canal, encolada dentro de la misma transacción de negocio

#### Scenario: Canal best_effort publica post-commit
- GIVEN un canal con `policy=best_effort` registrado
- WHEN se crea una `Notification` y su transacción hace commit
- THEN el canal recibe la publicación después del commit, sin registro de fallo en `notification_deliveries`

#### Scenario: Falla de un canal no afecta a los demás ni a la transacción
- GIVEN dos canales registrados, uno de los cuales falla al entregar
- WHEN se crea una `Notification`
- THEN el canal que no falló entrega normalmente y la transacción de negocio de la notificación se completa igual

### Requirement: Entrega durable en `notification_deliveries`

Para canales `durable`, el sistema MUST persistir una fila por intento con `channel`, `status`, `attempts`, `last_error`, `dedup_key` y `payload` JSONB. El despachador MUST reclamar filas de forma atómica antes de intentar el envío y MUST reintentar hasta un máximo configurable; al agotarlo, la fila MUST quedar en estado terminal `failed` con un log de ERROR y MUST NOT reintentarse más. Ejecutar el despacho dos veces sobre el mismo estado MUST NOT producir un envío ni una fila duplicada.

#### Scenario: Claim atómico antes de enviar
- GIVEN filas `pending` en `notification_deliveries` de distintos canales
- WHEN el despachador corre
- THEN reclama cada fila antes de invocar el envío del canal correspondiente, evitando doble despacho concurrente

#### Scenario: Agotamiento de reintentos termina en failed
- GIVEN una fila cuyo envío falló el máximo de intentos configurado para su canal
- WHEN el despachador corre nuevamente
- THEN la fila queda en `failed` terminal, se registra un log de ERROR con su `dedup_key`, y no se reintenta más

#### Scenario: Re-corrida del despacho es idempotente
- GIVEN una fila ya en estado `sent`
- WHEN el despachador vuelve a correr
- THEN no reintenta esa fila ni genera un segundo envío para el mismo `dedup_key`

### Requirement: Auditoría de entregas por notificación

`GET /api/v1/notifications/{id}/deliveries` MUST devolver las entregas de la notificación indicada (canal, estado, intentos, `last_error`, `sent_at`), restringido a usuarios con rol `admin` o `manager` de la organización de la notificación. MUST operar exclusivamente dentro de la organización del solicitante y MUST responder `404` si la notificación pertenece a otra organización.

#### Scenario: Admin lista las entregas de una notificación
- GIVEN una notificación con una entrega `sent` por email
- WHEN un admin de la organización llama `GET /notifications/{id}/deliveries`
- THEN recibe las entregas registradas con su canal, estado, intentos y `last_error`

#### Scenario: Aislamiento entre organizaciones
- GIVEN una notificación de la organización 1 y un admin de la organización 2
- WHEN el admin de la organización 2 llama `GET /notifications/{id}/deliveries` con ese `id`
- THEN recibe `404`

#### Scenario: Rol sin permiso no accede
- GIVEN un usuario con rol `member` de la organización dueña de la notificación
- WHEN llama `GET /notifications/{id}/deliveries`
- THEN recibe `403`

### Requirement: Tolerancia a la atribución de entregas de digest

Las entregas generadas por un despacho que agrega varias notificaciones (ej. digest de email) MAY reportarse en el endpoint de auditoría sin vínculo exacto 1:1 por `notification_id`, hasta que el diseño defina un puente notificación↔entrega. Esta ambigüedad MUST NOT causar error ni afectar la atribución de entregas inmediatas 1:1 existentes.

#### Scenario: Entrega agregada de digest no rompe el endpoint
- GIVEN una entrega generada por el digest que agrupó 3 notificaciones de un mismo usuario
- WHEN se consulta `GET /notifications/{id}/deliveries` para una de esas 3 notificaciones
- THEN el endpoint responde sin error, con la atribución agregada o exacta según defina el diseño

#### Scenario: Entrega inmediata conserva atribución exacta
- GIVEN una notificación urgente con una entrega inmediata registrada 1:1
- WHEN se consulta el endpoint para esa notificación
- THEN la entrega aparece vinculada exactamente a esa notificación

### Requirement: Extensibilidad para canales futuros sin tocar el núcleo

El contrato `DeliveryChannel` MUST bastar para incorporar adaptadores durables futuros (push móvil FCM/APNs, SMS, webhooks) declarando `policy=durable` sobre `notification_deliveries`, sin requerir cambios en el núcleo del hub ni en el punto único de creación de `Notification`.

#### Scenario: Adaptador futuro hipotético no requiere cambios en el núcleo
- GIVEN un adaptador hipotético `push_fcm` que implementa `DeliveryChannel` con `policy=durable`
- WHEN se registra en el hub
- THEN reutiliza el mismo mecanismo de fan-out, claim atómico y reintentos ya existente, sin tocar `create()` ni el despachador genérico

## Limitaciones y deuda conocida

- No se implementan adaptadores nuevos reales en este cambio (solo se declara la frontera de extensión).
- La atribución exacta de entregas de digest queda pendiente de definición en el diseño (ver Requirement de tolerancia).
- El núcleo NUNCA MUST importar `notifications.repository` (regla de ciclo heredada de `app/email/`).

## Referencias

- `openspec/changes/12-notification-hub/proposal.md`
- `openspec/specs/notifications-inapp/spec.md` (punto único de creación que dispara el fan-out)
- `openspec/specs/email-notifications/spec.md` (adaptador durable de referencia)
- `openspec/specs/realtime-notifications/spec.md` (adaptador best-effort de referencia)
