# Spec — Motor de alertas (alert-engine)

> **Origen**: línea base as-built (2026-07-11) + cambio [04-labels-checklists-dependencias](../../changes/archive/2026-07-11-04-labels-checklists-dependencias/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Motor de alertas con Strategy pattern: reglas configurables por organización (`AlertRule`), estrategias evaluables que producen candidatos, un evaluador con deduplicación que materializa notificaciones in-app y un scheduler periódico integrado al lifespan de FastAPI.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/alert-rules | Reglas de la organización |
| PATCH | /api/v1/alert-rules/{id} | Habilitar/deshabilitar y ajustar threshold_params (admin) |
| POST | /api/v1/alerts/evaluate | Evaluación on-demand (require_admin) |

Arquitectura (`backend/app/alerts/`): `base.py` (AlertStrategy ABC: `evaluate(db, org_id, threshold_params) → list[AlertCandidate]` con org, rule_type, recipient, title, body, dedup_key, target), `registry.py`, `evaluator.py`, `scheduler.py`, `router.py`, `strategies/`.

Modelo `AlertRule` (Pk + Timestamp + SoftDelete + Tenant): rule_type, enabled, threshold_params (JSON). El seed crea 4 reglas por defecto.

Estrategias implementadas:

| rule_type | Condición | Destinatario |
|-----------|-----------|--------------|
| task_overdue | Tarea vencida sin completar | Assignee |
| task_at_risk | A ≤3 días de vencer + 3 días sin actividad | Assignee |
| sprint_at_risk | ≥75% del tiempo transcurrido con <50% de puntos | Admins |
| workload_imbalance | >8 tareas activas por usuario | Admins |
| blocked_task | Tarea bloqueada > threshold_params.days | Assignee |

Scheduler: APScheduler `AsyncIOScheduler` con `IntervalTrigger` cada `ALERT_SCHEDULER_INTERVAL_HOURS` (1 h) en el lifespan; si el arranque del scheduler falla, la app sigue operando.

## Requisitos

- **R1**: El evaluador DEBE recorrer solo las reglas `enabled` de cada organización y delegar en la estrategia registrada para su `rule_type`.
- **R2**: Antes de crear una notificación, el evaluador DEBE deduplicar con `exists_active(org, dedup_key)`.
- **R3**: `PATCH /alert-rules/{id}` DEBE permitir a un admin ajustar `enabled` y `threshold_params` sin redeploy.
- **R4**: `POST /alerts/evaluate` DEBE disparar la evaluación completa on-demand y exigir `require_admin`.

### Escenarios centrales

**R1/R2 — Evaluación con dedup**
- Dado una tarea vencida sin completar con la regla task_overdue habilitada
- Cuando corre el evaluador (scheduler u on-demand)
- Entonces el assignee recibe UNA notificación; corridas posteriores no duplican mientras siga activa.

**R3 — Regla configurable**
- Dado la regla workload_imbalance con umbral 8
- Cuando un admin la deshabilita vía PATCH
- Entonces las corridas siguientes no generan candidatos de ese tipo.

**R4 — Evaluación on-demand protegida**
- Dado un usuario sin rol admin
- Cuando llama `POST /alerts/evaluate`
- Entonces la petición es rechazada.

**R5 — Estrategia blocked_task registrada en el registry**
- Dado una tarea bloqueada por otra tarea activa desde hace más de `threshold_params.days=3` días, con la regla blocked_task habilitada
- Cuando corre el evaluador
- Entonces el assignee de la tarea bloqueada recibe una notificación in-app.

**R6 — Deduplicación de la notificación blocked_task**
- Dado una tarea bloqueada que ya generó una notificación blocked_task activa
- Cuando el evaluador corre nuevamente sin que cambie la condición de bloqueo
- Entonces no se crea una segunda notificación para el mismo `dedup_key`.

**R7 — Seed idempotente de la regla blocked_task por defecto**
- Dado una organización sin reglas de alerta
- Cuando corre el seed de reglas por defecto
- Entonces la organización queda con 5 reglas activas, incluida blocked_task.
- Y si el seed se ejecuta nuevamente, sigue habiendo exactamente una regla activa por cada `rule_type`, sin duplicados.

## Limitaciones y deuda conocida

- Lock distribuido Redis: TODO documentado en el evaluador — Redis está declarado en config y NO se usa (riesgo de doble evaluación con múltiples réplicas).
- Estrategias NO implementadas del CLAUDE.md: license_expiring, license_expired.
- Canales faltantes: sin email, sin WebSocket (solo notificación in-app).
- CERO tests del motor completo (estrategias, evaluador, scheduler, endpoints de alert-rules).

## Referencias

- backend/app/alerts/ (base.py, registry.py, evaluator.py, scheduler.py, router.py, strategies/)
- backend/app/modules/alert_rules/ (router.py, service.py, models.py)
- backend/app/config.py (ALERT_SCHEDULER_INTERVAL_HOURS, REDIS_URL sin uso)
- backend/app/db_init.py (4 reglas seed por defecto)
