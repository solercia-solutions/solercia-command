# Delta for notifications-inapp

## MODIFIED Requirements

### Requirement: Publicación al canal realtime en la creación

Cuando el sistema crea una notificación (por mención o por el motor de alertas), el punto único de creación MUST delegar el fan-out en el hub de entregas (`notification-hub`), que MUST incluir al canal realtime (`realtime-notifications`) como canal registrado de política `best_effort` hacia el `recipient_user_id`, sin alterar el modelo `Notification` ni el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`). El punto de creación MUST NOT invocar el canal realtime de forma cableada.

(Previously: el punto de creación invocaba el publicador realtime directamente como llamada cableada, en vez de delegar en el registro genérico de canales del hub.)

#### Scenario: Creación dispara publicación vía el hub

- GIVEN el punto único de creación de `Notification` (`NotificationRepository.create()`, usado por el evaluador de alertas y por las menciones — el service NO tiene `create()`)
- WHEN se persiste una notificación nueva y su transacción hace commit
- THEN el hub publica (drenaje post-commit best-effort) hacia el canal realtime del destinatario, además de persistir el registro

#### Scenario: REST sigue siendo autoritativo

- GIVEN el canal realtime deshabilitado o el publicador no disponible
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`

### Requirement: Encolado de entrega email en la creación

Desde el punto único de creación (`NotificationRepository.create()`), el sistema MUST delegar en el hub de entregas la entrega por email (inmediata si el `rule_type` es urgente, o diferida al digest en caso contrario), a través del canal email registrado con política `durable` sobre `notification_deliveries`, sin alterar el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`) ni el resto del modelo `Notification`, salvo la columna aditiva `emailed_at`.

(Previously: el punto de creación llamaba `enqueue_immediate_email` de forma cableada sobre `email_outbox`, en vez de delegar en el registro genérico de canales del hub.)

#### Scenario: Notificación urgente se encola para envío inmediato
- GIVEN el punto único de creación de `Notification` con `rule_type="license_expired"`
- WHEN se persiste y su transacción hace commit
- THEN queda encolada en `notification_deliveries` como entrega DURABLE (el job despachador la envía con reintentos y estado terminal auditable), además de persistida como siempre

#### Scenario: Notificación no urgente queda pendiente de digest
- GIVEN una notificación creada con `rule_type` no urgente (ej. mención, `task_at_risk`)
- WHEN se persiste
- THEN queda con `emailed_at IS NULL`, visible igual vía `GET /notifications`, hasta que el digest la procese (si el usuario tiene preferencia distinta de `none`)

#### Scenario: REST sigue siendo autoritativo si el email falla o está deshabilitado
- GIVEN el canal email deshabilitado (`EMAIL_ENABLED=false`) o el envío falla
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`, con contrato y campos existentes sin cambios
