# Delta for notifications-inapp

## ADDED Requirements

### Requirement: Publicación al canal realtime en la creación

Cuando el sistema crea una notificación (por mención o por el motor de alertas), MUST invocar, desde el punto único de creación, la publicación best-effort hacia el canal realtime (`realtime-notifications`) del `recipient_user_id`, sin alterar el modelo `Notification` ni el contrato de los endpoints REST existentes (`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`). Esto levanta la limitación de "canal único polling" documentada en la línea base.

#### Scenario: Creación dispara publicación

- GIVEN el punto único de creación de `Notification` (`NotificationRepository.create()`, usado por el evaluador de alertas y por las menciones — el service NO tiene `create()`)
- WHEN se persiste una notificación nueva y su transacción hace commit
- THEN el sistema publica (drenaje post-commit best-effort) hacia el canal realtime del destinatario además de persistir el registro

#### Scenario: REST sigue siendo autoritativo

- GIVEN el canal realtime deshabilitado o el publicador no disponible
- WHEN se crea una notificación
- THEN la notificación se persiste igual y sigue siendo recuperable vía `GET /notifications`
