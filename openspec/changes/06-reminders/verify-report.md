# Verify Report: 06 · Reminders (recordatorios manuales y automáticos por regla)

**Fecha**: 2026-07-12
**Veredicto final**: **PASS**

## Completitud de tareas

`tasks.md`: 22/22 tareas marcadas `[x]` (T01–T22, Fase A + Fase B). Ambos commits existen en `main`:

- `5d3ba38` — `feat(reminders): crud de recordatorios y reglas` (Fase A: migración 0009 + módulo CRUD)
- `c4b1157` — `feat(reminders): motor de disparo y scheduler` (Fase B: dispatcher + scheduler + endpoint admin)

No quedan tareas pendientes ni parciales. `state.yaml` reporta `apply: done` antes de este verify.

## Evidencia de ejecución — suite completa

Contenedor `backend` reconstruido (`docker compose up -d --build backend`); el entrypoint corrió `alembic upgrade head` automáticamente en el arranque (log: `Running upgrade 0008 -> 0009, add_reminders`). `alembic current` = `0009 (head)`. `alembic check` = "No new upgrade operations detected." (sin diff de esquema).

Token admin fresco generado vía `POST /api/v1/auth/login` (`admin@solercia.com` / `Admin123*`) inmediatamente antes de la corrida.

```
cd backend && source .venv/bin/activate
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
API_BASE_URL=http://localhost:8000/api/v1 \
TEST_AUTH_TOKEN=<fresco> \
python -m pytest tests/ -q
```

**Resultado: 439 passed, 0 failed, 1 warning (116.77s)** — coincide exactamente con lo esperado (427 in-process + 12 black-box, todos verdes con el token vigente). El único warning es un `SAWarning` preexistente de `alembic/env.py` sobre ciclos de FK al ordenar tablas (`dependencies`, `organizations`, `users`) — no relacionado con este cambio, no bloqueante.

`ruff check .` → **No issues found**.
`mypy app` → **No issues found**.

## Contrato black-box contra el contenedor (obligatorio)

Todas las llamadas ejecutadas contra `http://localhost:8000/api/v1` sobre el contenedor reconstruido, con `admin@solercia.com` (rol ADMIN) y `carlos@solercia.com` (rol MEMBER, sin ADMIN — seed `_DEMO_MEMBERS` de `db_init.py`):

| Llamada | Esperado | Obtenido |
|---|---|---|
| `POST /reminders` con `remind_at` futuro | `201`, `status=scheduled` | `201`, `status=scheduled` ✓ |
| `POST /reminders` con `remind_at` pasado | `422`, `code=validation_error` | `422`, mensaje "remind_at debe ser una fecha futura." ✓ |
| `GET /reminders` | `200`, envelope `{data,message,meta}` | `200`, `meta.total=1` ✓ |
| `POST /reminders/dispatch` (admin) | `200`, conteo | `200`, `{"created":0}` (correcto: el único recordatorio del smoke aún no vencía) ✓ |
| `POST /reminders/dispatch` (no-admin, `carlos@solercia.com`) | `403` | `403`, `code=forbidden` ✓ |
| `GET /notifications` (smoke de regresión) | `200` | `200`, envelope correcto ✓ |

Los recordatorios creados durante el smoke fueron cancelados (`DELETE /reminders/{id}`) para no dejar datos residuales en la base de desarrollo.

## Matriz de cumplimiento — `specs/reminders/spec.md`

| Requirement | Escenario | Test cubridor | Estado |
|---|---|---|---|
| Creación de recordatorio manual | Creación válida | `test_create_reminder_valid_returns_scheduled` | PASS |
| Creación de recordatorio manual | `remind_at` en el pasado → 422 | `test_create_reminder_past_remind_at_rejected` + black-box | PASS |
| Listado/consulta exclusivos del dueño | Listado propio paginado y filtrado | `test_list_reminders_paginated_and_filtered_by_status` | PASS |
| Listado/consulta exclusivos del dueño | Recordatorio ajeno → 404 | `test_get_other_users_reminder_returns_404` | PASS |
| Edición y cancelación solo en `scheduled` | Edición válida | `test_owner_can_edit_scheduled_reminder` | PASS |
| Edición y cancelación solo en `scheduled` | Edición de recordatorio `fired` → 422 | `test_edit_fired_reminder_rejected` | PASS |
| Edición y cancelación solo en `scheduled` | Cancelación → `cancelled` | `test_delete_scheduled_reminder_cancels_it` | PASS |
| Aislamiento multi-tenant y personal | Aislamiento entre organizaciones | `test_cross_org_reminder_access_returns_404` | PASS |
| Aislamiento multi-tenant y personal | Admin no ve recordatorios ajenos | `test_admin_does_not_see_other_users_reminders` | PASS |
| Configuración de `ReminderRule` por usuario | Crear regla `task_due_soon` | `test_create_reminder_rule_task_due_soon` | PASS |
| Configuración de `ReminderRule` por usuario | Deshabilitar regla | `test_disable_reminder_rule` | PASS |
| Disparo idempotente de recordatorios manuales vencidos | Disparo simple | `test_dispatch_fires_simple_reminder_without_task` | PASS |
| Disparo idempotente de recordatorios manuales vencidos | Idempotencia entre corridas | `test_dispatch_is_idempotent_across_runs` | PASS |
| Disparo idempotente de recordatorios manuales vencidos | Cancelación concurrente no dispara | `test_claim_reminder_rejects_concurrently_cancelled_reminder` + `test_dispatch_does_not_fire_reminder_cancelled_before_run` | PASS |
| Disparo manual admin-only | Disparo manual por admin | `test_dispatch_endpoint_admin_returns_count` + black-box | PASS |
| Disparo manual admin-only | Rechazo a no-admin (403) | `test_dispatch_endpoint_rejects_non_admin` + black-box | PASS |
| Omisión ante tarea completada/cancelada/borrada | Tarea completada antes del disparo | `test_dispatch_skips_reminder_linked_to_completed_task` + `test_dispatch_skips_reminder_linked_to_deleted_task` | PASS |
| Disparo de la regla `task_due_soon` | Notificación por vencimiento próximo | `test_task_due_soon_notifies_within_lead_days` | PASS |
| Disparo de la regla `task_due_soon` | Sin duplicado en corridas consecutivas | `test_task_due_soon_rerun_does_not_duplicate` | PASS |
| Disparo de la regla `task_due_soon` | Tarea completada no genera aviso | `test_task_due_soon_completed_task_no_notification` | PASS |
| (implícito) Regla `enabled=False` no genera candidatos | — | `test_task_due_soon_rule_disabled_produces_no_candidates` | PASS |

21/21 escenarios (9 requirements) de `specs/reminders/spec.md` con evidencia de test en verde. `lead_days` entero positivo también cubierto (`test_reminder_rule_rejects_non_positive_lead_days`).

## Matriz de cumplimiento — `specs/notifications-inapp/spec.md` (delta)

| Requirement | Escenario | Test cubridor | Estado |
|---|---|---|---|
| Origen `"reminder"` integrado a la bandeja compartida | Recordatorio manual aparece en la bandeja | `test_dispatched_notification_visible_only_to_recipient` | PASS |
| Origen `"reminder"` integrado a la bandeja compartida | Deduplicación aplica igual que a mención y alertas | `test_task_due_soon_rerun_does_not_duplicate` (dedup_key `reminder_due_soon:*`) + `test_dispatch_is_idempotent_across_runs` (dedup_key `reminder_manual:*`) | PASS |

No hay regresión: `test_notifications_inapp.py`, `test_notifications_pagination.py`, `test_mention_notifications.py`, `test_alert_engine.py`, `test_blocked_task_alert.py` — todos verdes dentro de los 439.

## Coherencia de diseño

- **Segundo job en el mismo `AsyncIOScheduler`**: confirmado en `app/main.py` (`scheduler = start_scheduler()` → `register_reminders_job(scheduler)`, `try/except` aislado) y en logs de arranque del contenedor (`Added job "Reminder Dispatch"` junto a `"Alert Engine Evaluation"`).
- **`lead_days` dentro de `params` JSON**: confirmado en `ReminderRuleService.create_rule`/`update_rule` (`params={"lead_days": ...}`).
- **`dedup_key` namespaced**: confirmado en `dispatcher.py` (`reminder_manual:{id}`) y `task_due_soon.py` (`reminder_due_soon:{task_id}:{user_id}:{fecha}`).
- **Claim atómico condicionado por status**: confirmado en `_claim_reminder` (`UPDATE ... WHERE id=:id AND status='scheduled' RETURNING id` vía SQL Core, nunca `session.add()` sobre el objeto cargado) — código coincide exactamente con la Decisión 4 de `design.md` y con el test dedicado de la carrera.
- **Tareas completadas → `skipped`**: confirmado en `_dispatch_manual_reminders` (`task.is_active` / `task.completed_at is not None`).

### Desviación documentada verificada

`tasks.md` documenta que `TaskDueSoonStrategy` no filtra un literal `status not in {done,cancelled}` porque el modelo `Task` de este código no tiene un estado global "cancelled" (`status` es un string libre por metodología). Se verificó contra el código:

- `app/reminders/strategies/task_due_soon.py` filtra únicamente `Project.is_active`, `Task.is_active`, `Task.completed_at.is_(None)`.
- El precedente citado como espejo, `app/alerts/strategies/task_at_risk.py`, filtra exactamente los mismos dos campos (`Task.is_active.is_(True)`, `Task.completed_at.is_(None)`), sin ningún filtro de `status` literal.

La desviación es **correcta y no bloqueante**: es fiel al patrón real del código base, no a una interpretación errónea de la spec, y los 3 escenarios de R8 quedan cubiertos con los dos estados reales que el sistema modela (`completed_at` para completada, `is_active=False` para cancelada/borrada).

## Hallazgos

**CRITICAL**: ninguno.

**WARNING**: ninguno.

**SUGGESTION** (no bloqueantes):
1. `docs/API.md` no fue actualizado con las 9 rutas nuevas de `/reminders` y `/reminder-rules` (mismo patrón de deuda documentado en el verify de `10-busqueda-global`). Recomendado resolver en `archive` o en un cambio de documentación posterior.
2. El FK `reminders.user_id → users.id` usa `ondelete="SET NULL"` sobre una columna `nullable=False` (igual patrón preexistente en `0007_add_time_logs_and_task_history.py` para `TaskTimeLog.user_id`) — inconsistencia latente ya presente en el código base antes de este cambio, no introducida por 06; solo se materializaría si algún día se permite el borrado físico de usuarios (hoy el sistema es soft-delete-only).

## Conclusión

**PASS**. 439/439 tests verdes (0 fallos), ruff y mypy limpios, migración 0009 aplicada sin diff de esquema, 22/22 tareas completas con commits verificables, 21/21 escenarios de `specs/reminders/spec.md` y 2/2 de la delta `specs/notifications-inapp/spec.md` con evidencia runtime real, contrato black-box contra el contenedor reconstruido confirmado (incluyendo el 403 RBAC de un usuario no-admin real), y la única desviación de diseño documentada se verificó como fiel al patrón existente del código base. Listo para `sdd-archive`.
