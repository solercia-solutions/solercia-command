# Delta for notifications-inapp

## ADDED Requirements

### Requirement: Origen "reminder" integrado a la bandeja compartida

El sistema MUST aceptar `rule_type="reminder"` como origen válido de `Notification`, generado por el disparo de un `Reminder` manual o por la evaluación de una `ReminderRule` (`task_due_soon`). Estas notificaciones MUST cumplir el mismo contrato ya vigente de la bandeja: privacidad por `recipient_user_id` (R1), deduplicación por `dedup_key` (R2), conteo de no leídas (R3) y ciclo de vida por `status` (R4). No se requiere cambio de esquema ni de comportamiento en `Notification`; `rule_type` ya es un campo libre que admite el nuevo valor.

#### Scenario: Recordatorio manual aparece en la bandeja
- GIVEN un `Reminder` propio vencido en `scheduled`
- WHEN el scheduler de reminders lo dispara
- THEN se crea una `Notification` con `rule_type="reminder"`, visible solo para el `recipient_user_id` correspondiente vía `GET /notifications`

#### Scenario: Deduplicación aplica igual que a mención y alertas
- GIVEN una `Notification` activa con `dedup_key="reminder_due_soon:T1:U1:2026-07-15"`
- WHEN la regla `task_due_soon` vuelve a evaluar la misma condición
- THEN no se crea una segunda notificación para ese `dedup_key`
