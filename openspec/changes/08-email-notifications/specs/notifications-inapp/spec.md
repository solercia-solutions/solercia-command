# Delta for notifications-inapp

## ADDED Requirements

### Requirement: Encolado de entrega email en la creación

Desde el punto único de creación (`NotificationRepository.create()`), el sistema MUST encolar la entrega por email (inmediata si el `rule_type` es urgente, o diferida al digest en caso contrario), best-effort, sin alterar el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`) ni el resto del modelo `Notification`, salvo la columna aditiva `emailed_at`.

#### Scenario: Notificación urgente se encola para envío inmediato
- GIVEN el punto único de creación de `Notification` con `rule_type="license_expired"`
- WHEN se persiste y su transacción hace commit
- THEN queda encolada en el outbox para despacho inmediato best-effort, además de persistida como siempre

#### Scenario: Notificación no urgente queda pendiente de digest
- GIVEN una notificación creada con `rule_type` no urgente (ej. mención, `task_at_risk`)
- WHEN se persiste
- THEN queda con `emailed_at IS NULL`, visible igual vía `GET /notifications`, hasta que el digest la procese (si el usuario tiene preferencia distinta de `none`)

#### Scenario: REST sigue siendo autoritativo si el email falla o está deshabilitado
- GIVEN el canal email deshabilitado (`EMAIL_ENABLED=false`) o el envío falla
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`, con contrato y campos existentes sin cambios
