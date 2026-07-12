# Design: 11 · Blindaje de la línea base (backfill de tests as-built con TDD)

## Technical Approach

Cambio **test-only**: los specs as-built de `openspec/specs/*/spec.md` son el contrato; cada escenario Dado/Cuando/Entonces se convierte en un test que nace en rojo y congela el comportamiento vigente. Una suite nueva por capacidad en `backend/tests/`, todas sobre las fixtures in-process de `01-fundacion-tdd` (`client`/`session`/`tenant`/`user` con `ASGITransport` + `SAVEPOINT` + `NullPool`, `loop_scope="session"`). El único código de producción que se toca es un bugfix **si y solo si** un test destapa un defecto real, aislado con su propio commit y rollback. `conftest.py` se amplía (aditivo) con fixtures de segunda organización, factory de miembros por rol y grant RBAC admin. Sin funcionalidad nueva, sin `frontend/`, sin migraciones salvo que un bugfix exija esquema.

## Architecture Decisions

### Decisión: una suite por capacidad, orden por criticidad de seguridad

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Un archivo por capacidad + `test_permissions_matrix.py` transversal | Trazable al spec, PRs fragmentables, sin colisión con las 258 suites vigentes | **Elegida** |
| Mega-archivo por dominio | Difícil de revisar, rompe el presupuesto de 400 líneas | Rechazada |

Orden de implementación (primero lo sensible a seguridad): `multi-tenancy` → `auth` → `rbac-catalog` + matriz de permisos → `alert-engine` → `methodology-strategies` → `projects`/`tasks` → `notifications-inapp`/`dashboard-executive`. Archivos: `test_auth.py`, `test_users_admin.py`, `test_rbac_catalog.py`, `test_multi_tenancy.py`, `test_projects.py`, `test_tasks_crud.py`, `test_methodology_strategies.py`, `test_alert_engine.py`, `test_notifications_inapp.py`, `test_dashboard_executive.py`, `test_permissions_matrix.py`.

### Decisión: fixtures de dos organizaciones para aislamiento

**Choice**: fixtures aditivas en `conftest.py`: `second_tenant` (org B) y un `two_orgs` que puebla A y B con usuario propio, proyecto, tarea, regla de alerta y notificación en cada una (igualando el requisito vinculante de la delta spec). Clave del as-built: `get_current_membership` resuelve el tenant desde la **primera membresía por `created_at`** del usuario; por eso cada usuario de prueba pertenece a UNA sola org, garantizando scope determinista. La aserción de aislamiento: un usuario de A que lista/lee/parcha recursos de B recibe listados sin datos de B y `404` en acceso directo (nunca `200` con dato ajeno).
**Alternatives**: reutilizar un solo `tenant` y simular la 2.ª org por parámetro de cliente — imposible: el tenant jamás viaja desde el cliente (R2).
**Rationale**: cubre entidades con `TenantMixin` directo (Project, AlertRule, Notification, TaskComment, Attachment, Dependency, Role) y las scope-por-join (Task/Sprint → Project). El fixture es obligatorio en toda suite tenant-scoped (mitiga el riesgo de fugas por falta de datos de la 2.ª org); al sembrar también AlertRule y Notification en ambas orgs, las suites de alert-engine y notifications hacen sus aserciones de aislamiento con datos reales de la 2.ª org, sin seeds ad-hoc.

### Decisión: membresías por rol en fixtures (el seed no trae `manager`)

**Choice**: promover a `conftest.py` el helper ya probado en `test_time_logs.py` como fixture `make_member(session, org, role) -> (User, token)` que crea `OrganizationMember` con el `MemberRole` pedido y su token. Para endpoints `require_admin` (catálogo RBAC y `POST /alerts/evaluate`), un fixture aparte `rbac_admin(session, org, user)` crea `Role(code="ADMIN")` + `UserRole` — el `MemberRole` NO satisface `require_admin`.
**Rationale**: el seed solo tiene `admin`/`member`; los cuatro roles se fabrican en fixture. Separar `MemberRole` de RBAC `Role` es central por el doble sistema de roles vigente.

### Decisión: matriz de permisos parametrizada sobre el comportamiento VIGENTE

**Choice**: `pytest.mark.parametrize` con tuplas `(endpoint, método, actor, esperado)`. Se prueba el **gate efectivo real**, no el ideal del CLAUDE.md.

| Familia de endpoint | Gate efectivo as-built | Prueba |
|---------------------|------------------------|--------|
| `/admin/roles·menus·dependencies`, `POST /alerts/evaluate` | `require_admin` (RBAC `Role.code=='ADMIN'`) | `rbac_admin` → 2xx; `member`/`manager` sin RBAC → 403 |
| `GET /users/{id}/time-logs` (ver todos) | chequeo inline en `TimeLogService._require_visibility` (`_SUPERVISOR_ROLES`), NO `require_role()` | member/viewer → 403; admin/manager → 200 |
| `PATCH/DELETE /time-logs/{id}` | dueño estricto | no-dueño (incl. admin/manager) → 403 |
| CRUD dominio (projects, tasks) | solo membresía | los 4 MemberRole → mismo resultado |

**Rationale**: documentar el rol efectivo por endpoint (mitigación del riesgo del doble sistema). Congela lo que hay; cualquier enderezamiento del RBAC granular es roadmap, no este cambio.

### Decisión: motor de alertas sin dependencia de reloj real

**Choice**: sembrar datos que disparan cada condición e invocar `evaluate_organization(db, org_id)` **directamente** con la sesión de prueba (su `commit()` solo libera el SAVEPOINT; rollback al final). Dedup por **idempotencia**: correr el evaluador dos veces sobre la misma condición y afirmar **una** notificación (vía `exists_active(org, dedup_key)`), sin esperar tiempo. El scheduler se prueba por **inspección de registro**: `start_scheduler()` registra el job `id="alert_evaluation"` con `IntervalTrigger`, luego `stop_scheduler()` deja `_scheduler=None` — nunca se espera el intervalo ni se ejecuta `_run_evaluation` (abre su propia `AsyncSessionLocal`, fuera del SAVEPOINT).
**Alternatives**: `asyncio.sleep` hasta el disparo (flaky, lento) — rechazada.
**Rationale**: cubre las 4 estrategias sin test previo (`task_overdue`, `task_at_risk`, `sprint_at_risk`, `workload_imbalance`) + evaluador + dedup + scheduler de forma determinista (mitiga el riesgo de scheduler/dedup difíciles de testear). `blocked_task` ya está cubierta por `test_blocked_task_alert.py` (cambio 04) y NO se duplica.

### Decisión: estrategias de metodología por contrato, sin duplicar board-aware

**Choice**: tests unitarios puros (sin BD) que instancian vía `get_strategy(name)` y afirman `default_columns()`, `allowed_statuses()`, `sprints_enabled`, `estimation_mode`, `has_backlog` y la forma de `to_info()` para planner/kanban/scrum (conjuntos fijos), más `get_strategy("xp")` → 422. Para `custom` se afirma la parte estática (`default_columns()==[]`, flags); su `allowed_statuses()` board-aware ya está cubierto por `test_board_aware_strategy.py`/`test_board_column_config.py` y NO se duplica.
**Rationale**: contrato de la spec sin solapar suites existentes.

### Decisión: política de corrección mínima ante bug real

**Choice**: si un test rojo revela un defecto de producción, se documenta, se corrige **mínimo** en `router→service→repository` (nunca en el router la lógica), se entrega en commit propio con rollback propio; delta spec en esta carpeta **solo** si cambia comportamiento observable; si toca esquema, migración Alembic con `downgrade`. Correcciones en `auth`/`multi-tenancy` se revierten independientes del backfill.
**Rationale**: separa el riesgo del bugfix del cambio aditivo (rollback limpio).

## Data Flow

    spec Dado/Cuando/Entonces ─→ test rojo ─→ (código sin cambios) ─→ verde
    aislamiento:  user(orgA) ─→ endpoint ─→ get_current_membership(orgA) ─→ datos solo de A ; recurso de B ⇒ 404
    alertas:      seed condición ─→ evaluate_organization(db, org) ─→ notificación única (2ª corrida ⇒ 0 por dedup)
    scheduler:    start_scheduler() ─→ job "alert_evaluation" (IntervalTrigger) ─→ stop_scheduler()

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/tests/test_{auth,users_admin,rbac_catalog,multi_tenancy,projects,tasks_crud,methodology_strategies,alert_engine,notifications_inapp,dashboard_executive}.py` | Create | Una suite por capacidad derivada del spec |
| `backend/tests/test_permissions_matrix.py` | Create | Matriz parametrizada admin/manager/member/viewer por endpoint |
| `backend/tests/conftest.py` | Modify | Fixtures aditivas: `second_tenant`, `two_orgs`, `make_member`, `rbac_admin` |
| `backend/app/modules/*` · `backend/alembic/` | Modify (condicional) | Solo si un test destapa bug real; mínimo, documentado, con rollback |

## Interfaces / Contracts

```python
# Fixtures nuevas en conftest.py (aditivas)
async def make_member(session, org, role: MemberRole) -> tuple[User, str]: ...   # (user, token); email único generado internamente con uuid.uuid4().hex[:12] (como la fixture `user`) — sin parámetro suffix, apto para llamadas repetidas en la misma org
async def rbac_admin(session, org, user) -> None: ...   # Role(code="ADMIN") + UserRole → habilita require_admin
async def two_orgs(session) -> TwoOrgs: ...   # orgA/orgB con user, project, task, alert_rule y notification poblados en cada una
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | 4 estrategias de metodología por contrato + factory 422 | pytest sin BD, `get_strategy` |
| Unit | Estrategias de alerta producen `AlertCandidate` esperado | invocar `strategy.evaluate` con datos sembrados |
| Integration | auth (login/refresh/logout/me/menus), CRUD users/rbac/projects/tasks, notifications, dashboard | httpx `AsyncClient` in-process |
| Integration (aislamiento) | Cada endpoint tenant-scoped con dos orgs: cero cruce (listado filtrado + 404 directo) | fixture `two_orgs` |
| Integration (permisos) | Matriz por endpoint del gate efectivo (RBAC vs MemberRole vs dueño) | `parametrize` + `make_member`/`rbac_admin` |
| Integration (motor) | 4 estrategias sin test previo (`blocked_task` excluida: ya cubierta en `test_blocked_task_alert.py`) + evaluador + dedup idempotente + registro del scheduler | `evaluate_organization` directo; sin timing real |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Cambio test-only que no altera superficies de ejecución.

## Migration / Rollout

Sin migración por defecto (aditivo). Rollback = revertir los commits de test. Cualquier bugfix de producción viaja aislado con su rollback; si tocara esquema, `alembic downgrade` de esa migración puntual.

## Presupuesto y guarda de revisión

Estimación ≈ 100–110 tests nuevos (auth ~8, users-admin ~8, rbac ~12, multi-tenancy ~10, projects ~6, tasks ~8, methodology ~10, alert-engine ~14, notifications ~6, dashboard ~6, matriz ~15). Suite total ≈ 363 (258 + nuevos), debe quedar **verde** con ruff/mypy limpios. **400-line budget risk: High** (test-only, pero volumen alto) → fragmentar en PRs encadenados por capacidad (sugerido: PR1 conftest+multi-tenancy+auth; PR2 rbac+matriz; PR3 alert-engine; PR4 methodology+projects+tasks; PR5 notifications+dashboard). El desglose y el forecast formal los fija `sdd-tasks`.

## Open Questions

- [ ] Ninguna bloqueante. Si algún endpoint de dominio resulta tener un gate de rol no documentado, el test congela el comportamiento observado y se anota en la matriz.
