# Design: 06 · Reminders (recordatorios manuales y automáticos por regla)

## Technical Approach

Dos piezas backend nuevas: (1) módulo CRUD `app/modules/reminders/` (`router → service → repository`, patrón idéntico a `time_logs`) para `Reminder` y `ReminderRule`, con paginación/soft-delete/auditoría de 02 y autorización **solo-dueño**; (2) motor de disparo `app/reminders/` que **espeja `app/alerts/`** (Strategy + registry + dispatcher + job de scheduler) SIN acoplarse a `AlertRule`. El disparo materializa `Notification` reutilizando `NotificationRepository.exists_active(dedup_key)` + `create(...)` con `rule_type="reminder"`. Todo en UTC (`datetime.now(UTC)`, igual que las estrategias y `Task.due_date`). TDD estricto por invocación directa del dispatcher. Depende de 02.

## Architecture Decisions

### Decisión: segundo job propio en el MISMO `AsyncIOScheduler`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Job `reminders_dispatch` añadido a la instancia que devuelve `start_scheduler()`, con `_run_reminders()` propio (sesión + try/except aislados) | Aislamiento de fallos por job; intervalo propio; una sola instancia de scheduler | **Elegida** |
| Ampliar `_run_evaluation()` para llamar también a reminders | Más simple pero acopla dominios: un `raise` o la misma transacción arrastra alertas y reminders | Rechazada |
| Segunda instancia `AsyncIOScheduler` | Doble overhead de loop y doble teardown | Rechazada |

**Rationale**: `_run_reminders()` copia el contrato de `_run_evaluation` (abre su `AsyncSessionLocal()`, captura excepciones y loguea) → un fallo de reminders no tumba las alertas ni al revés. `main.py` orquesta: captura el scheduler de `start_scheduler()` y llama `register_reminders_job(scheduler)` (dirección de dependencia correcta: `main → reminders`, nunca `alerts → reminders`).

### Decisión: `ReminderRule` con `lead_days` DENTRO de `params` JSON (no columna dedicada)

**Choice**: `ReminderRule` espeja a `AlertRule`: `rule_type String`, `enabled bool`, `params JSON` (default `{"lead_days": 3}`), más `user_id` (es personal, no de org). `lead_days` vive en `params`.
**Alternatives**: columna `lead_days` dedicada (Integer).
**Rationale**: el cambio 07 (`license_expiring` personal) traerá params distintos (p. ej. lista de leads, campos de licencia); una columna `lead_days` sería específica de `task_due_soon` y quedaría inútil para otros `rule_type` o forzaría migración. JSON extensible = método nuevo es clase-strategy nueva + `params` nuevos, **cero migración** (cumple el riesgo del proposal).

### Decisión: `dedup_key` determinista y namespaced (sin colisión con el motor de alertas)

| Origen | Formato | Idempotencia |
|--------|---------|--------------|
| Reminder manual | `reminder_manual:{reminder_id}` | PK única + transición de status |
| ReminderRule `task_due_soon` | `reminder_due_soon:{task_id}:{user_id}:{due_date:%Y-%m-%d}` | dedup + re-dispara si cambia `due_date` |

**Rationale**: el prefijo `reminder_*` no colisiona con las claves del motor (`task_overdue:{id}`, `task_at_risk:{id}`, `blocked_task:{id}`). `user_id` en la clave de regla evita que un usuario suprima el aviso de otro; incluir `due_date` re-dispara al reprogramar la tarea. Notification.`rule_type="reminder"` es la familia origen para ambos; el `dedup_key` diferencia (no requiere cambio de código en `notifications/`: `rule_type` es `String(60)` libre, sin enum — la "capability modificada" se satisface por uso, no por código).

### Decisión: idempotencia por status + dedup; lock Redis diferido (documentado)

**Choice** (MVP mono-proceso, corregido por gate adversarial): manual → **claim atómico condicionado por status** POR reminder: `UPDATE reminders SET status='fired', fired_at=now() WHERE id=:id AND status='scheduled' RETURNING id` (SQL Core vía `session.execute`, NO `session.add()` del objeto cargado). Solo si el claim devuelve fila se crea la Notification (previo `exists_active(dedup_key)`), en la misma transacción. Si el claim no devuelve fila (el usuario canceló entre el SELECT del dispatcher y el claim), el reminder se salta silenciosamente. El paso a `skipped` usa la misma guarda (`WHERE status='scheduled'`). Regla → `exists_active(dedup_key)` (igual que las alertas). NO se implementa lock Redis.
**Rationale**: la guarda condicional cierra la carrera dispatcher-vs-cancelación bajo READ COMMITTED (el gate demostró que la "transición atómica" sin `WHERE status='scheduled'` sobrescribiría una cancelación concurrente, violando el MUST NOT de la spec). APScheduler con `max_instances=1` evita solape dentro del proceso; el doble disparo real solo aparece con múltiples réplicas — mismo TODO documentado en `alerts/`. **Camino a producción multi-réplica**: envolver `dispatch_reminders` en `redis.lock("reminders:dispatch:lock", timeout=...)` — el claim atómico ya queda implementado desde el MVP.

### Decisión: tareas completadas → `skipped`

Manual con tarea `done`/`cancelled`/borrada (`is_active=False`/inexistente) al disparo ⇒ `status=skipped`, sin Notification. `task_due_soon` filtra `Task.completed_at IS NULL`, `Task.is_active` y status ∉ {done, cancelled} (espejo de `task_at_risk`). Reminder sin `task_id` siempre dispara.

## Data Flow

    scheduler(REMINDER_SCHEDULER_INTERVAL_MINUTES) → _run_reminders() → AsyncSessionLocal → dispatch_reminders(db):
      · manuales vencidos (status=scheduled, remind_at<=now):
          task done/borrada → claim UPDATE ... SET status='skipped' WHERE id=:id AND status='scheduled'
          task ok → claim UPDATE ... SET status='fired', fired_at=now() WHERE id=:id AND status='scheduled' RETURNING id
                    → claim vacío (cancelación concurrente) ⇒ saltar · claim ok → exists_active? no → Notification.create
      · ReminderRule enabled por usuario → get_strategy(rule_type).evaluate(db, org, user_id, params) → [ReminderCandidate] → exists_active? no → Notification.create
      · db.commit()
    CRUD  POST/GET/PATCH/DELETE /api/v1/reminders y /api/v1/reminder-rules → service (solo-dueño) → repository

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/reminders/{models,schemas,repository,service,router}.py` | Create | `Reminder` (+ `ReminderRule`) CRUD; `SORTABLE_FIELDS`; paginación/soft-delete/audit de 02; autorización solo-dueño |
| `app/reminders/{base,registry,dispatcher,scheduler}.py` + `strategies/task_due_soon.py` | Create | Espejo de `alerts/`: `ReminderCandidate`, `ReminderRuleStrategy`, `dispatch_reminders`, `register_reminders_job`, `_run_reminders` |
| `app/shared/enums.py` | Modify | `ReminderStatus` (`scheduled/fired/skipped/cancelled`), `native_enum=False, length=20` (espejo de `NotificationStatus`) |
| `app/main.py` | Modify | lifespan: capturar `start_scheduler()` → `register_reminders_job(scheduler)`; incluir routers `reminders` y `reminder-rules` |
| `app/config.py` | Modify | `REMINDER_SCHEDULER_INTERVAL_MINUTES: int = 5` (intervalo propio del job `reminders_dispatch`; el motor de alertas conserva `ALERT_SCHEDULER_INTERVAL_HOURS`) |
| `alembic/versions/xxxx_add_reminders.py` | Create | Tablas `reminders` y `reminder_rules`; `down_revision` = head al aplicar |

`notifications/` y `db_init.py`: **sin cambio funcional** (desviación deliberada del proposal). `rule_type` es String libre → no requiere modificar `notifications/`. Sin seed por-usuario: la `ReminderRule` se crea on-demand vía CRUD (un usuario se une a la org dinámicamente; seed por-usuario sería frágil).

## Interfaces / Contracts

```python
# app/reminders/base.py
@dataclass
class ReminderCandidate:
    organization_id: uuid.UUID
    recipient_user_id: uuid.UUID
    title: str
    body: str
    dedup_key: str
    target_type: str | None = None      # "task" | None
    target_id: uuid.UUID | None = None
    rule_type: str = "reminder"          # familia origen en Notification

class ReminderRuleStrategy(ABC):
    rule_type: str = "base"
    async def evaluate(self, db, organization_id, user_id,
                       params: dict) -> list[ReminderCandidate]: ...

# app/reminders/dispatcher.py
async def dispatch_reminders(db) -> int: ...   # manuales + reglas; commit; nº notifs creadas

# Reminder: Pk+Timestamp+SoftDelete+Audit+Tenant · user_id FK, task_id FK?,
#   remind_at DateTime(tz), message Text, status ReminderStatus, fired_at DateTime(tz)?
# ReminderRule: Pk+Timestamp+SoftDelete+Audit+Tenant · user_id FK, rule_type String,
#   enabled bool, params JSON default {"lead_days": 3}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | formato `dedup_key` (manual/regla, sin colisión con alertas); `require_role`/solo-dueño 403; validación `lead_days` en schema | pytest sin BD |
| Integration | manual vencido → 1 Notification + `status=fired`; re-run → 0 (dedup + status); **cancelación previa al dispatch → el claim no encuentra `scheduled` y NO dispara (carrera cerrada)**; tarea done/cancelled/borrada → `skipped` sin notif; reminder sin `task_id` siempre dispara; `task_due_soon` `lead_days=3` notifica 3 días antes, re-run → 0; `POST /reminders/dispatch` admin-only (403 no-admin); CRUD paginado + soft-delete + permisos solo-dueño | httpx AsyncClient + fixtures `session/tenant/user` de 01, **invocación directa de `dispatch_reminders`/`strategy.evaluate` (nunca esperar al scheduler)** — patrón de `test_blocked_task_alert.py`, `@skip_no_db`, `loop_scope="session"` |

## Threat Matrix

N/A — no hay routing, shell, subprocess, automatización VCS/PR ni clasificación de ejecutables. El job de scheduler es asíncrono in-process (no subprocess). El único riesgo de integración es el doble disparo multi-réplica, cubierto por dedup+status y con camino a lock Redis documentado (Decisión 4).

## Migration / Rollout

Migración aditiva (2 tablas: `reminders`, `reminder_rules`, mismo set de mixins que `AlertRule`). **NO se fija número**: el 10-busqueda-global (en paralelo) también crea migración; `down_revision` = head vigente al aplicar. Los applies van **serializados: 11 → 10 → 06 → 09**. Rollback: `downgrade` elimina ambas tablas; las Notification `rule_type="reminder"` ya emitidas quedan inertes sin romper el contrato de notifications.

## Presupuesto (líneas / tests)

~600–750 líneas autoras (2 tablas · módulo CRUD · dispatcher+strategy+scheduler+migración) y ~10–14 tests. Supera el budget de 400 líneas de revisión → riesgo **Medium-Alto**: `sdd-tasks` debe evaluar cortar en 2 slices (A: módulo CRUD; B: motor de disparo + scheduler + migración), cada uno con verificación y rollback autónomos.

## Open Questions

- [x] `rule_type` de Notification para manual vs regla — RESUELTO: `"reminder"` como familia; `dedup_key` diferencia.
- [x] Seed de `ReminderRule` por defecto — RESUELTO: sin seed; on-demand vía CRUD.
- [x] ¿Un endpoint admin `POST /reminders/dispatch` (espejo de `/alerts/evaluate`) para pruebas manuales? — RESUELTO por el orquestador (gate): SÍ, admin-only (`require_admin` RBAC, mismo gate que `/alerts/evaluate`); habilita el smoke black-box del verify. Añadido a la spec.
