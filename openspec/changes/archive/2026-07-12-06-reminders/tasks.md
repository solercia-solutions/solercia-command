# Tasks: 06 · Reminders (recordatorios manuales y automáticos por regla)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~600–750 (2 tablas · módulo CRUD · dispatcher+strategy+scheduler+migración) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote A (CRUD + migración) → Lote B (motor de disparo + scheduler + endpoint admin) |
| Estrategia de entrega | commits directos a main por lotes (sin PR), size:exception aceptada por el usuario |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Ajuste sobre design.md**: la migración (2 tablas) se agrupa en el Lote A junto al CRUD, no en el Lote B. El CRUD y sus tests de integración no pueden correr sin las tablas, y `alembic check` exige el modelo ORM en el mismo commit que la migración (precedente `05-trabajo-realizado`/T09). El Lote B queda igual al design: solo motor de disparo + scheduler + endpoint admin.

**Serialización**: `sdd-apply` de 06 corre después del apply de `10-busqueda-global` (orden 11 → 10 → 06 → 09). `down_revision` de la migración = head vigente de Alembic al momento de aplicar (NO fijar número; hoy el head es `0007`, pero 10 puede avanzarlo antes de que 06 aplique).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| A | Migración + CRUD `Reminder`/`ReminderRule` | 1 — `feat(reminders): crud de recordatorios y reglas` | `cd backend && pytest tests/test_reminders.py -v` | N/A — CRUD puro sin integración externa, cubierto por `httpx AsyncClient` | Revert commit + `alembic downgrade -1` (elimina `reminders`/`reminder_rules`); sin efecto en otros módulos |
| B | Motor de disparo + scheduler + `/reminders/dispatch` | 2 — `feat(reminders): motor de disparo y scheduler` | `cd backend && pytest tests/test_reminder_dispatch.py -v` | Invocación directa de `dispatch_reminders(db)` en tests (nunca esperar al scheduler); smoke manual vía `POST /reminders/dispatch` admin | Revert commit; el job `reminders_dispatch` deja de registrarse; `Notification(rule_type="reminder")` ya emitidas quedan inertes (Rollback Plan del proposal) |

## Fase A — Migración + CRUD `Reminder`/`ReminderRule` (Commit 1)

- [x] T01 [Foundation] Migración `backend/alembic/versions/0009_add_reminders.py`: tablas `reminders` (Pk+Timestamp+SoftDelete+Audit+Tenant: `user_id` FK, `task_id` FK?, `remind_at`, `message`, `status`, `fired_at`) y `reminder_rules` (Pk+Timestamp+SoftDelete+Audit+Tenant: `user_id` FK, `rule_type`, `enabled`, `params` JSON default `{"lead_days":3}`); `down_revision="0008"` (head vigente al aplicar); `downgrade` elimina ambas.
- [x] T02 [Foundation] `app/shared/enums.py`: `ReminderStatus` (`scheduled/fired/skipped/cancelled`), `native_enum=False, length=20` (espejo `NotificationStatus`).
- [x] T03 [Foundation] `app/modules/reminders/models.py`: `Reminder` y `ReminderRule` (mismos mixins que T01) — registrados junto a T01 por precedente de `alembic check`; registrados también en `app/db_init.py` para que `Base.metadata.create_all` (fixture de tests) y el seed los reconozcan.
- [x] T04 RED `backend/tests/test_reminders.py`: creación válida y `remind_at` pasado→422 (R1); listado propio paginado+`?status=`, 404 en recordatorio ajeno (R2); edición válida, edición en `fired`→422, `DELETE`→`cancelled` (R3); aislamiento entre organizaciones y admin sin ver ajenos (R4); crear/deshabilitar `ReminderRule` propia (R5). Confirmado: 12/12 fallando (404, rutas inexistentes) antes de T05-T08.
- [x] T05 GREEN `reminders/schemas.py`: `ReminderCreate/Update/Response`, `ReminderRuleCreate/Update/Response`; valida `remind_at` futuro y `lead_days` entero positivo. [R1,R5]
- [x] T06 GREEN `reminders/repository.py`: CRUD scoped por `user_id` propio, `SORTABLE_FIELDS`, filtro `?status=`. [R2,R5]
- [x] T07 GREEN `reminders/service.py`: alta vía `get_actor_id`; `get/update/delete` exigen `reminder.user_id == membership.user_id` (404 si ajeno/inexistente, nunca 403); `update/delete` solo si `status=scheduled` (422 en otro status); CRUD de `ReminderRule` solo-dueño. [R1–R5]
- [x] T08 GREEN `reminders/router.py`: 8 rutas (`POST/GET/GET{id}/PATCH/DELETE /reminders`, `GET/POST/PATCH /reminder-rules`), sin `/reminders/dispatch` (Fase B); registrado en `app/main.py`. [R1–R5]
- [x] T09 VERIFY `cd backend && pytest tests/test_reminders.py -v` en verde (12/12); confirmados los 404 de aislamiento y los 422 de T04. Corrección incidental: `tests/test_migrations_baseline.py::test_migration_0008_downgrade_removes_indexes_and_extension` usaba `upgrade(cfg, "head")` + `downgrade(cfg, "-1")` — al encadenar 0009 el `-1` deshacía mi migración en vez de la 0008. Cambiado a `upgrade(cfg, "0008")` para aislar la prueba de futuras migraciones adicionales (fix real, no cosmético — sin él el suite completo regresaba).

## Fase B — Motor de disparo + scheduler + endpoint admin (Commit 2)

- [x] T10 [Foundation] `app/config.py`: `REMINDER_SCHEDULER_INTERVAL_MINUTES: int = 5`.
- [x] T11 [Foundation] `app/reminders/base.py`: `ReminderCandidate` (dataclass) y `ReminderRuleStrategy` (ABC), espejo de `alerts/base.py`.
- [x] T12 RED `backend/tests/test_reminder_dispatch.py`: disparo simple sin `task_id`→1 Notification + `fired` (R6); re-run no duplica (R6); **cancelación concurrente — reminder cancelado antes del claim, `UPDATE ... WHERE status='scheduled'` no encuentra fila, no dispara, permanece `cancelled`** (R6, corrección vinculante del gate, probada vía invocación directa de `_claim_reminder` para reproducir la interleaving determinísticamente); tarea `done`/borrada→`skipped` sin notif (R8); `task_due_soon` `lead_days=3` notifica 3 días antes y re-run no duplica (R9); tarea `done` dentro del `lead_days` no genera aviso (R9); regla `enabled=False` no genera candidatos. Invocación directa de `dispatch_reminders`/`strategy.evaluate`, patrón `test_blocked_task_alert.py`. Confirmado: 11 tests fallando (ImportError/módulo inexistente) antes de T15-T20.
- [x] T13 RED `backend/tests/test_reminders.py` (ampliación): `POST /reminders/dispatch` con rol ADMIN devuelve conteo (R7); sin rol ADMIN→403 (R7). Confirmado fallando (405, ruta inexistente).
- [x] T14 RED `backend/tests/test_reminder_dispatch.py` (ampliación): notificación disparada visible solo para su `recipient_user_id` vía `GET /notifications`; dedup por `dedup_key` (formato `reminder_manual:{id}` / `reminder_due_soon:{task_id}:{user_id}:{fecha}`) verificado en los tests de R6/R9. Confirmado fallando junto con T12.
- [x] T15 GREEN `app/reminders/strategies/task_due_soon.py`: `TaskDueSoonStrategy.evaluate` — tareas del usuario con `due_date <= ahora+lead_days`, `completed_at IS NULL`, `is_active` (espejo `task_at_risk.py`, que tampoco filtra un status "cancelled" literal — el modelo `Task` no tiene ese estado global, ver Desviaciones); `dedup_key="reminder_due_soon:{task_id}:{user_id}:{due_date:%Y-%m-%d}"`. [R9]
- [x] T16 GREEN `app/reminders/registry.py`: `get_strategy`/`registered_rule_types` (espejo `alerts/registry.py`), registra `task_due_soon`.
- [x] T17 GREEN `app/reminders/dispatcher.py::dispatch_reminders(db) -> int`: manuales vencidos vía **claim atómico condicionado por status** (`UPDATE reminders SET status='fired'|'skipped', fired_at=now() WHERE id=:id AND status='scheduled' RETURNING id`, SQL Core `session.execute` vía helper `_claim_reminder`, NUNCA `session.add()` del objeto cargado); solo si el claim devuelve fila se evalúa `exists_active(dedup_key)` y se crea `Notification(rule_type="reminder")`; luego evalúa `ReminderRule.enabled` por usuario vía `get_strategy(...).evaluate(...)`; `dedup_key` reminder manual = `reminder_manual:{reminder_id}`; `db.commit()` único. [R6,R8,R9,R10]
- [x] T18 GREEN `app/reminders/scheduler.py::_run_reminders()` + `register_reminders_job(scheduler)`: `IntervalTrigger(minutes=REMINDER_SCHEDULER_INTERVAL_MINUTES)`, job `id="reminders_dispatch"`, sesión y try/except propios (aislado de `_run_evaluation`). [R6]
- [x] T19 GREEN `app/main.py`: capturado `scheduler = start_scheduler()` → `register_reminders_job(scheduler)` en lifespan, try/except aislado (dirección `main → reminders`, nunca `alerts → reminders`).
- [x] T20 GREEN `reminders/router.py`: añadido `POST /reminders/dispatch` gateado por `require_admin` (espejo `/alerts/evaluate`), llama `dispatch_reminders(db)`, responde conteo creado. [R7]
- [x] T21 VERIFY `cd backend && pytest tests/test_reminder_dispatch.py tests/test_reminders.py -v` en verde (25/25); confirmada la cancelación concurrente (T12) y el 403 de dispatch no-admin (T13) en la primera corrida GREEN.
- [x] T22 VERIFY final `cd backend && pytest tests/ -v` → 427 passed, 12 failed (pre-existentes, ambientales: tests black-box de `test_attachments`/`test_comments`/`test_sprint_close`/`test_subtasks`/`test_task_key` requieren servidor vivo + `TEST_AUTH_TOKEN`, no configurado en este entorno; mismos 12 fallaban antes de Fase A). `ruff check .` y `mypy app` limpios. Sin regresiones: `test_notifications_inapp.py`/`test_notifications_pagination.py`/`test_mention_notifications.py`/`test_alert_engine.py`/`test_blocked_task_alert.py` → 41/41 verdes.

### Desviaciones de diseño (documentadas, no bloqueantes)

- **"status not in {done,cancelled}" (T15)**: el modelo `Task` de este código no tiene un estado global "cancelled" — `status` es un string libre validado por metodología (`app/methodology/*.py`: columnas tipo "Backlog/Doing/Done", "Sin iniciar/En curso/Completada", etc.) y ningún módulo existente (`task_at_risk.py`, `task_overdue.py`, dashboard `_StatusBounds`) filtra por un literal "cancelled". El precedente real que SÍ existe y que T15 cita explícitamente como espejo (`task_at_risk.py`) solo filtra `Task.is_active.is_(True)` y `Task.completed_at.is_(None)`. Implementado así: "completada" = `completed_at` seteado; "cancelada o borrada" = `is_active=False` (soft-delete). Cubre los 3 escenarios de R8 (`specs/reminders/spec.md`) con los dos únicos estados reales que el sistema modela.

## Trazabilidad de requisitos

R1 Creación manual · R2 Listado/consulta solo-dueño · R3 Edición/cancelación en `scheduled` · R4 Aislamiento multi-tenant/personal · R5 Config `ReminderRule` (`specs/reminders`). R6 Disparo idempotente + claim atómico anti-carrera · R7 Disparo manual admin-only · R8 Omisión por tarea completada/cancelada/borrada · R9 Disparo `task_due_soon` (`specs/reminders`). R10 Origen `"reminder"` en bandeja compartida (`specs/notifications-inapp`).
