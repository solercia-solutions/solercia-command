# Proposal: 06 · Reminders (recordatorios manuales y automáticos por regla)

## Intent

CLAUDE.md declara `Reminder` como capacidad transversal: "recordatorios programables por usuario o automáticos por regla". Hoy no existe. El colaborador no puede programar un aviso propio ("recuérdame revisar esta tarea el jueves") ni recibir avisos personales anticipados de sus vencimientos. El motor de alertas cubre señales a nivel organización según política del jefe (task_overdue, task_at_risk), pero NO recordatorios personales que el propio usuario configura para sí mismo. Este cambio construye la entidad Reminder y su disparo, reutilizando la bandeja in-app y el scheduler ya existentes.

## Scope

### In Scope
- **Reminder manual**: instancia programada por el usuario (`remind_at`, `message`, `task_id?` opcional), disparo único, ciclo de vida por `status`. CRUD `/api/v1/reminders` con paginación estándar, soft delete y auditoría.
- **ReminderRule por usuario**: regla automática configurable (`rule_type = task_due_soon`, `lead_days`, `enabled`, `params` JSON). GET/POST/PATCH `/api/v1/reminder-rules` (paralelo a `/alert-rules`).
- **Disparo vía scheduler existente (APScheduler)**: job periódico que (a) materializa notificación in-app de los Reminders vencidos y (b) evalúa las ReminderRule generando notificaciones por vencimiento próximo, ambos con deduplicación idempotente.
- **Migración Alembic 0008** (aditiva, con `downgrade`).

### Out of Scope (non-goals)
- Recordatorios por vencimiento de licencia de activo → cambio **07** (el módulo assets no existe aún); el `rule_type` queda extensible sin migración para acogerlo después.
- Recurrencia/repetición ("cada lunes", cron): el MVP dispara una sola vez.
- Recordatorios delegados a terceros (`recipient ≠ creador`).
- Canal email/WebSocket (cambios 08/09): solo in-app.
- Cambios en `frontend/` (constraint `frontend-frozen`).

## Capabilities

### New Capabilities
- `reminders`: recordatorios manuales (entidad Reminder) y automáticos por regla (ReminderRule), disparados por scheduler y materializados como notificaciones in-app.

### Modified Capabilities
- `notifications-inapp`: nuevo origen `rule_type = "reminder"` como fuente de notificaciones (además de mención y reglas de alerta).

## Approach

Módulo nuevo `backend/app/reminders/` que espeja la estructura de `backend/app/alerts/` (evaluator + job de scheduler + registry extensible) SIN acoplarse a `AlertRule`.

**Decisión clave — entidad propia, no una AlertRule.** `AlertRule` es configuración a nivel organización con estrategias de política del jefe; un recordatorio es un ítem personal del colaborador (`remind_at` concreto, o preferencia `lead_days`). Se reutiliza la SALIDA: el modelo `Notification`, su `dedup_key` (`exists_active`) y su bandeja/lifecycle — el disparo crea una `Notification` con `rule_type="reminder"`. El scheduler existente hospeda un segundo job (`IntervalTrigger`).

**Idempotencia.** Los Reminder manuales disparan exactamente una vez por transición de `status` (`scheduled → fired`) más `dedup_key`; las ReminderRule usan `dedup_key` determinista (`reminder_due_soon:{task_id}:{user}:{due_date}`), igual que las alertas. Se hereda el TODO de lock Redis (riesgo de doble evaluación con réplicas).

**Tareas completadas.** Un Reminder cuya tarea asociada esté `done`/`cancelled` o borrada al momento del disparo se OMITE (`status=skipped`, sin notificación); las ReminderRule ignoran tareas `done`/`cancelled`. Los reminders sin `task_id` siempre disparan. TDD estricto.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/reminders/` | New | Módulo espejo de `alerts/`: evaluator, scheduler job, registry, strategies |
| `backend/app/modules/reminders/` | New | Modelo Reminder + ReminderRule, router, service, repository, schemas |
| `backend/app/main.py` (lifespan) | Modified | Registrar el job de reminders en el scheduler existente |
| `backend/app/modules/notifications/` | Modified | Aceptar origen `rule_type="reminder"` (reutiliza dedup y lifecycle) |
| `backend/app/db_init.py` | Modified | Seed idempotente opcional de ReminderRule por defecto por usuario |
| `backend/alembic/` | New | Migración 0008: tablas `reminders` y `reminder_rules` (con downgrade) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Doble disparo con múltiples réplicas (sin lock Redis) | Med | Guard por `status` + `dedup_key` en Notification; hereda TODO de lock del evaluador de alertas |
| Modelar mal la extensibilidad y bloquear el rule_type de licencias (07) | Med | `rule_type` enum + `params` JSON extensibles; decidir contrato en design sin implementar la de licencias |
| Reminders huérfanos al borrar/completar la tarea asociada | Low | Omitir en disparo si la tarea está done/cancelled/borrada; test explícito |
| Colisión de responsabilidad con `task_at_risk` (alertas) | Low | ReminderRule es personal y configurable por usuario; alertas son política de org — dominios separados |

## Rollback Plan

Cambio aditivo. Revertir el merge de código y bajar (`downgrade`) la migración Alembic 0008 que crea `reminders` y `reminder_rules`; el job del scheduler y los endpoints nuevos desaparecen. Las notificaciones ya emitidas (`rule_type="reminder"`) quedan inertes en la bandeja sin romper el contrato de notifications.

## Dependencies

- `depends_on: 02-contrato-api` — paginación estándar, auditoría `created_by`/`updated_by` y resolución de auth-user para las listas nuevas.
- Reutiliza (línea base as-built, no es dependencia SDD): `notifications-inapp` (Notification + dedup + lifecycle) y `alert-engine` (patrón de scheduler APScheduler en el lifespan).

## Success Criteria

- [ ] CRUD `/api/v1/reminders` (manual) con paginación, soft delete y auditoría; tests happy path, error y permisos (solo el dueño).
- [ ] `/api/v1/reminder-rules` permite a cada usuario configurar `lead_days` y `enabled` de `task_due_soon`.
- [ ] Al correr el scheduler, un Reminder vencido genera UNA notificación in-app; corridas posteriores no duplican (dedup + transición de status).
- [ ] Una ReminderRule `task_due_soon` con `lead_days=3` notifica al usuario 3 días antes del `due_date` de sus tareas no completadas, sin duplicar.
- [ ] Un Reminder cuya tarea asociada está `done`/`cancelled` no dispara notificación (queda `skipped`).
- [ ] `rule_type`/`params` quedan extensibles para el recordatorio de licencias del cambio 07, sin implementarlo aquí.
- [ ] Todo el código nace con prueba en rojo (TDD estricto).
