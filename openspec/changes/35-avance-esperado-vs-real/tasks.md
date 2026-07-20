# Tasks: 35 · Avance esperado vs. real (semáforo, tendencia y refuerzo)

## Reconciliación aplicada (orquestador)

1. **Fórmula del esperado**: el "escalón por due date" de `design.md` D1
   (`due_date <= hoy` → peso completo, si no 0) y el "binario por `due_date`"
   de `specs/project-progress/spec.md` son literalmente el mismo enunciado —
   se usa la redacción de la spec (contrato testeable). **Corrección numérica
   necesaria en el peso**: `design.md` D1 usa `weight(task) = estimation_hours
   or 1` de forma uniforme, pero `specs/project-progress/spec.md` ("Peso de
   cada tarea") exige que en un alcance con horas MIXTAS las tareas SIN horas
   pesen `0` (no `1`); solo si NINGUNA tarea del alcance tiene horas se usa
   conteo (peso 1). Aplicando la regla de la spec al ejemplo de `design.md`
   D1 (T1=10h due 07-10 hecha, T2=6h due 07-15, T3=4h due 07-31, T4 sin
   horas/sin due; hoy=2026-07-20, calendario 8h L-V): `total=20` (T4 pesa 0,
   no 1 como en `design.md`), `expected_pct=80%` (antes 79%), `real_pct=50%`
   (antes 48%), `deviation=30%` (antes 31%) — semáforo sigue `rojo` en ambos
   casos, pero el número exacto cambia. Tarea 2.11 fija este caso corregido
   como test de contrato.
2. **Destinatarios de `project_reinforcement`**: UNIÓN de admin/manager de la
   organización (patrón `sprint_at_risk`, único destinatario que menciona el
   delta de `alert-engine`) MÁS `lead_user_id` del proyecto si existe y es
   miembro activo (aporte de `design.md` D5, que solo mencionaba lead→admin).
   Dedup por `user_id`: si el lead ya es admin/manager, recibe una sola
   notificación.
3. **Snapshot semanal**: persiste el valor YA consolidado por subárbol
   (spec.md, "incluidas áreas, con su valor YA consolidado por subárbol");
   el nombre de campo es `week_start` (lunes ISO, como fija `design.md` D2),
   no `captured_week` (mención suelta en la prosa de `spec.md`, misma
   columna renombrada).

### Reconciliaciones adicionales (identificadas al redactar tasks, no en las 3 anteriores — confirmar en `apply` si el equipo discrepa)

4. **Nombre de tabla**: `project_progress_snapshots` (plural) — todas las
   tablas existentes son plurales (`organizations`, `projects`, `tasks`,
   `boards`, `sprints`); `design.md`/`spec.md` la nombran en singular en
   prosa. Modelo ORM: `ProjectProgressSnapshot` (singular, patrón Python).
5. **Rutas de los endpoints**: se usan las rutas por-recurso de
   `specs/project-progress/spec.md` (`GET /progress/projects/{id}`,
   `GET /progress/monthly-cut?area_id=&month=`), coincidentes con
   `state.yaml.spec_notes`. `design.md` D4 describe una ruta de colección
   alternativa (`GET /progress/projects?project_id=...`,
   `GET /progress/monthly-report`); `ProgressService.list_cards()` de
   `design.md` queda como método interno (reutilizable por `dashboard`), sin
   ruta pública nueva fuera del alcance de la spec.
6. **Columnas de umbral**: se usan los nombres de `design.md` (Interfaces/
   File Changes) — `threshold_green_pct`/`threshold_amber_pct` en el modelo,
   `green_max_pct`/`amber_max_pct` en el body `PUT` — sobre la prosa de
   `spec.md` (`progress_threshold_green`/`progress_threshold_yellow`), mismo
   criterio que la reconciliación 1 del cambio 34 (el contrato técnico manda
   sobre la prosa).
7. **Rollup por defecto**: `spec.md` no expone un toggle; `GET
   /progress/projects/{id}` SIEMPRE agrega el subárbol de `{id}` (trivial en
   hojas). El parámetro `rollup: bool` de `ProgressService.card()`
   (`design.md`) se invoca siempre en `True` desde el router, sin exponerlo
   como query param.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1400–1650 (producción ~850–950: 2 migraciones ~90, `progress/{models,schemas,repository,service,router}.py` ~500-600, cambios en `organizations`/`alerts`/`dashboard` ~200, frontend ~150; tests ~600-700: fórmula, endpoints, snapshots, alerta, migración, dashboard) |
| 400-line budget risk | High — módulo nuevo completo + 2 migraciones + estrategia de alerta + UI, muy por encima del presupuesto |
| Chained PRs recommended | No — instrucción explícita: single-pr, merge local a `preview` (mismo patrón que 25/27/28/34: commits escalonados dentro de una sola integración) |
| Suggested split | Fase 0 gate 27+28→35 → Fase 1 migraciones → Fase 2 fórmulas (`ProgressService`) → Fase 3 endpoints → Fase 4 snapshots+job → Fase 5 alerta `project_reinforcement` → Fase 6 UI → Fase 7 suite completa + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U0 | Fase 0 — confirmar `alembic current` (head real) y que 27/28 están aplicados en disco | (sin commit propio) | `cd backend && .venv/bin/alembic current` | N/A — solo lectura de disco/BD | N/A |
| U1 | Fase 1 — migraciones aditivas (umbrales + tabla snapshots) | 1 — `feat(progress): agrega umbrales y tabla de snapshots de avance` | `pytest -q backend/tests/test_migrations_progress.py` | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` contra Postgres de test | Revert commit; columnas/tabla nuevas sin consumidores todavía |
| U2 | Fase 2 — `ProgressService` con fórmulas esperado/real/semáforo | 2 — `feat(progress): calcula esperado, real, desviación y semáforo` | `pytest -q backend/tests/test_progress_formula.py` | Pytest, servicio puro + fixtures de calendario/árbol | Revert commit; módulo `progress` aislado sin router aún |
| U3 | Fase 3 — endpoints tarjeta/corte mensual/umbrales | 3 — `feat(progress): expone tarjeta, corte mensual y umbrales por API` | `pytest -q backend/tests/test_progress_endpoints.py` | Pytest contra Postgres real de test (`client`) | Revert commit; router nuevo, sin tocar `dashboard`/`alerts` |
| U4 | Fase 4 — snapshots semanales + job del scheduler | 4 — `feat(progress): persiste snapshots semanales y calcula la tendencia` | `pytest -q backend/tests/test_progress_snapshots.py` | Job real vía `AsyncIOScheduler`/`CronTrigger` invocado en el test | Revert commit; job adicional, no reemplaza el existente (`IntervalTrigger` horario intacto) |
| U5 | Fase 5 — alerta `project_reinforcement` + seed 7→8 | 5 — `feat(alertas): agrega el refuerzo de proyecto al motor` | `pytest -q backend/tests/test_alert_project_reinforcement.py` | `evaluate_organization` real contra Postgres de test | Revert commit; estrategia nueva registrada, resto del motor intacto |
| U6 | Fase 6 — enriquecer `dashboard` + UI de tarjetas/corte mensual | 6 — `feat(executive): agrega tarjetas de avance esperado vs real` | `pytest -q backend/tests/test_dashboard_executive.py` | `cd frontend && npm run build` (build real) | Revert commit; `percent_done` sigue igual, campos nuevos aditivos |
| U7 | Fase 7 — suite completa + commit de cierre si aplica | 7 — `fix(progress): cierra hallazgos de la suite completa` (condicional) | `pytest -q` (backend completo) | Ídem + `npm run build` | Revert commit aislado; sin commit si no hubo hallazgos |

## Fase 0 — Precondición: 27 y 28 aplicados + head real (sin commit)

- [ ] 0.1 Ejecutar `cd backend && .venv/bin/alembic current` para obtener el head real en disco.
- [ ] 0.2 Confirmar `project_kind` en `backend/app/modules/projects/models.py` (27) y `backend/app/modules/work_calendar/{resolver,schemas}.py` (28) existentes: `rg "project_kind" backend/app/modules/projects/models.py` y `ls backend/app/modules/work_calendar/{resolver,schemas}.py`. Si falta cualquiera, DETENER y aplicar primero 27/28.
- [ ] 0.3 Confirmar las firmas reales: `WorkCalendarResolver.resolve(organization_id, project_id) -> ResolvedCalendar` (`working_hours_per_day`, `working_days`, `source`) y `ProjectKind.area`/`ProjectKind.proyecto`; ajustar las Fases 2-6 si 27/28 aplicaron con cambios respecto a su `design.md`.
- [ ] 0.4 Fijar `down_revision` de las migraciones de la Fase 1 al head real de 0.1 (no al valor especulativo de `state.yaml`).

## Fase 1 — Migración: umbrales + tabla de snapshots (Commit 1)

- [ ] 1.1 [RED] Crear `backend/tests/test_migrations_progress.py`: upgrade añade `organizations.threshold_green_pct`/`threshold_amber_pct` (`Numeric(5,2)` NOT NULL, default `5`/`15`) y la tabla `project_progress_snapshots` (`organization_id`, `project_id`, `week_start Date` NOT NULL, `expected_pct`, `real_pct`, `deviation`, `created_at`) con `UNIQUE(project_id, week_start)`; downgrade elimina ambos sin perder filas preexistentes. Hoy falla: no existen. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_migrations_progress.py` → falla.
- [ ] 1.2 [GREEN] Crear `backend/alembic/versions/00XXa_add_progress_thresholds.py` (`down_revision` = head real de 0.1): `threshold_green_pct`/`threshold_amber_pct` NOT NULL `server_default` `5`/`15`, retira el `server_default` tras el backfill implícito (patrón `0024`). Downgrade elimina ambas columnas.
- [ ] 1.3 [GREEN] Crear `backend/alembic/versions/00XXb_add_project_progress_snapshots.py` (`down_revision` = 00XXa): tabla `project_progress_snapshots` + `UNIQUE(project_id, week_start)` + índice por `organization_id`. Downgrade `DROP TABLE`.
- [ ] 1.4 [GREEN] `backend/app/modules/organizations/models.py`: añadir `threshold_green_pct`/`threshold_amber_pct` (`Numeric(5,2)`, NOT NULL, default `Decimal("5")`/`Decimal("15")`), mismo patrón aditivo de `theme`.
- [ ] 1.5 [GREEN] Crear `backend/app/modules/progress/models.py`: `ProjectProgressSnapshot(PkMixin, TimestampMixin, Base)` → `project_progress_snapshots`, campos `organization_id`, `project_id`, `week_start: Mapped[date]`, `expected_pct: Mapped[Decimal | None]`, `real_pct: Mapped[Decimal | None]`, `deviation: Mapped[Decimal | None]`, `UniqueConstraint("project_id", "week_start")`.
- [ ] 1.6 Suite dirigida verde + ciclo real de migración. Verify: `pytest -q backend/tests/test_migrations_progress.py` y `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head`.

Commit 1: `feat(progress): agrega umbrales y tabla de snapshots de avance`

## Fase 2 — `ProgressService`: fórmulas con tests de contrato numéricos (Commit 2)

- [ ] 2.1 [RED] Crear `backend/tests/test_progress_formula.py`: `test_weight_mixed_hours_zeroes_out_hourless` (Scenario "horas mixtas"): tarea de 10h + tarea sin horas → pesos `10` y `0`. Hoy falla: `app.modules.progress` no existe. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_progress_formula.py` → error de import.
- [ ] 2.2 [RED] `test_weight_no_hours_falls_back_to_count` (Scenario "sin ninguna hora"): ninguna tarea con `estimation_hours` → cada una pesa `1`.
- [ ] 2.3 [GREEN] Crear `backend/app/modules/progress/{__init__,service}.py`: `ProgressService._weight(tasks) -> dict[uuid.UUID, Decimal]` implementando la regla de la spec (NO la de `design.md` D1 uniforme — reconciliación 1). Verify: 2.1-2.2.
- [ ] 2.4 [RED] `test_expected_pct_standard_calendar` (Scenario "calendario L-V"): `rango_inicio=2026-06-01`, T(10h, due 06-12 vencida), T(10h, due 06-26 futura), T(20h sin due); calendario 8h `[1..5]`; hoy=2026-06-12 → `expected_pct=50`.
- [ ] 2.5 [RED] `test_expected_pct_weekend_calendar` (Scenario "fin de semana"): mismo caso con `working_days=[1..7]` → `expected_pct=48`.
- [ ] 2.6 [RED] `test_expected_pct_none_when_no_due_dates` (Scenario "sin ninguna tarea con `due_date`"): `expected_pct is None`, sin error.
- [ ] 2.7 [GREEN] Implementar `_expected_pct(tasks, calendar, today) -> Decimal | None`: `exp_dated` (escalón `due_date <= today`), `exp_undated` (lineal en días laborales del rango usando `ResolvedCalendar.working_days`); `None` si ninguna tarea del alcance tiene `due_date`. Verify: 2.4-2.6.
- [ ] 2.8 [RED] `test_real_pct_weighted_by_hours` (Scenario "real ponderado por horas"): 10h completada + 30h no completada → `real_pct=25`.
- [ ] 2.9 [RED] `test_real_pct_rollup_subtree_area` (Scenario "rollup de área"): área sin tareas propias + dos proyectos hijos (20/40 y 40/40 completadas) → `real_pct=75` sobre el peso agregado (60/80), usando `ProjectRepository._subtree_ids_select`.
- [ ] 2.10 [GREEN] Implementar `_real_pct(tasks) -> Decimal | None`: peso completado/peso total; "completada" = último estado permitido de la metodología PROPIA de cada proyecto del alcance (reusar `resolve_board_strategy`, mismo criterio que `rollup_progress`); excluye `cancelled`; `None` sin tareas en el alcance.
- [ ] 2.11 [RED] `test_design_d1_worked_example_corrected` (reconciliación 1): T1(10h, due 07-10, hecha), T2(6h, due 07-15), T3(4h, due 07-31), T4(sin horas, sin due); hoy=2026-07-20, calendario 8h L-V → `total=20` (T4 pesa 0), `expected_pct=80`, `real_pct=50`, `deviation=30`, `semaphore="rojo"`. Docstring del test documenta explícitamente la corrección frente al 79/48/31 de `design.md`.
- [ ] 2.12 [RED] `test_semaphore_red_by_high_deviation` (rojo, `expected=70/real=40/deviation=30`, umbrales default); `test_semaphore_green_when_ahead` (adelantado, `deviation=-20` → verde); `test_progress_thresholds_rejects_inverted` (`green=20, amber=10` → error de validación).
- [ ] 2.13 [GREEN] Crear `backend/app/modules/progress/schemas.py`: `Semaphore(str, Enum)` (`green/amber/red`), `TrendPoint`, `ProgressCard`, `ProgressThresholds` (`green_max_pct`, `amber_max_pct`, `Field(ge=0, le=100)`, validator `amber_max_pct > green_max_pct`); `_semaphore(deviation, green, amber) -> Semaphore` en `service.py`. Verify: 2.12.
- [ ] 2.14 [GREEN] Ensamblar `ProgressService.card(organization_id, project_id) -> ProgressCard`: `ProjectRepository._subtree_ids_select` (rollup SIEMPRE — reconciliación 7), `TaskRepository` (excluye `cancelled`), `WorkCalendarResolver.resolve` (calendario del alcance); compone `expected_pct`/`real_pct`/`deviation`/`semaphore`; `trend=[]` (la llena la Fase 4).
- [ ] 2.15 Suite dirigida verde. Verify: `pytest -q backend/tests/test_progress_formula.py`.

Commit 2: `feat(progress): calcula esperado, real, desviación y semáforo`

## Fase 3 — Endpoints: tarjeta, corte mensual, umbrales (Commit 3)

- [ ] 3.1 [RED] Crear `backend/tests/test_progress_endpoints.py`: `test_member_gets_project_card`: `GET /progress/projects/{id}` member → `200` con `expected_pct/real_pct/deviation/semaphore/trend=[]` (sin snapshots aún). `test_area_card_rolls_up_subtree`: `project_kind=area` agrega su subárbol.
- [ ] 3.2 [RED] `test_monthly_cut_classifies_three_projects` (Scenario spec): área con desviaciones `-10, 3, 25` (umbrales default 5/15) → `adelantado`, `llega`, `necesita_refuerzo`. `test_monthly_cut_closed_month_uses_nearest_snapshot`: mes cerrado usa el snapshot semanal más cercano a su cierre (no la tarjeta on-demand).
- [ ] 3.3 [RED] `test_monthly_cut_cross_tenant_returns_404`: área de otra organización → `404`, igual que el resto de endpoints de `projects`.
- [ ] 3.4 [RED] `test_get_thresholds_open_to_member`; `test_put_thresholds_requires_admin` (`403` manager/member); `test_put_thresholds_rejects_inverted` (`green>=amber` → `422`, no persiste).
- [ ] 3.5 [GREEN] Crear `backend/app/modules/progress/{repository,router}.py`: `SnapshotRepository` (upsert semanal, `last_4`); router con `GET /progress/projects/{id}` y `GET /progress/monthly-cut?area_id=&month=` (envelope `{data}`); registrar en `backend/app/main.py`.
- [ ] 3.6 [GREEN] `backend/app/modules/organizations/{schemas,router}.py`: `GET/PUT /organizations/me/progress-thresholds` (patrón `/me/theme`); GET cualquier miembro, PUT `require_admin`, envelope `{data, message}`.
- [ ] 3.7 Suite dirigida verde. Verify: `pytest -q backend/tests/test_progress_endpoints.py`.

Commit 3: `feat(progress): expone tarjeta, corte mensual y umbrales por API`

## Fase 4 — Snapshots semanales + job del scheduler (Commit 4)

- [ ] 4.1 [RED] Crear `backend/tests/test_progress_snapshots.py`: `test_snapshot_week_upserts_per_project`: `snapshot_week(org_id)` crea/actualiza una fila por proyecto activo (incluidas áreas, valor consolidado) para el lunes ISO en curso; re-ejecutar la misma semana hace upsert (`UNIQUE(project_id, week_start)` respetado, sin duplicar).
- [ ] 4.2 [RED] `test_trend_shows_four_chronological_points` (Scenario "tendencia con 4 snapshots"); `test_new_project_without_snapshots_has_empty_trend` (Scenario "proyecto nuevo").
- [ ] 4.3 [RED] `test_backfill_reconstructs_real_only`: backfill reconstruye `real_pct` histórico por `completed_at`; `expected_pct` de semanas previas a la primera captura queda `None` ("sin dato", no revisionista).
- [ ] 4.4 [GREEN] Implementar `ProgressService.snapshot_week(organization_id) -> int` + `SnapshotRepository.upsert`/`last_4`; función de backfill on-demand `backfill_real(organization_id, since)`.
- [ ] 4.5 [GREEN] `backend/app/alerts/scheduler.py`: añadir `_scheduler.add_job(_run_progress_snapshot, trigger=CronTrigger(day_of_week="mon"), id="progress_snapshot_weekly", ...)` junto al job horario existente, sin modificar el `IntervalTrigger` de alertas.
- [ ] 4.6 Suite dirigida verde. Verify: `pytest -q backend/tests/test_progress_snapshots.py`.

Commit 4: `feat(progress): persiste snapshots semanales y calcula la tendencia`

## Fase 5 — Alerta `project_reinforcement` (Commit 5)

- [ ] 5.1 [RED] Crear `backend/tests/test_alert_project_reinforcement.py`: `test_reinforcement_candidate_with_concrete_hours` (Scenario alert-engine): semáforo `rojo`, 40h pendientes, `due_date` máximo a 2 semanas laborales → candidato con "20 horas" (40/2) por cada admin/manager.
- [ ] 5.2 [RED] `test_reinforcement_last_week_requests_full_hours` (Scenario "última semana"): 15h pendientes, `due_date` dentro de la semana ISO en curso → pide las 15h completas (mínimo 1 semana).
- [ ] 5.3 [RED] `test_no_reinforcement_when_semaphore_green` (Scenario "sin refuerzo").
- [ ] 5.4 [RED] `test_reinforcement_dedup_weekly_per_recipient` (Scenario "dedup"): `dedup_key=project_reinforcement:{project_id}:{iso_week}:{recipient}` no duplica en la misma semana.
- [ ] 5.5 [RED] `test_reinforcement_recipients_union_admin_manager_and_lead` (reconciliación 2): destinatarios = admin∪manager de la organización MÁS `lead_user_id` si existe y es miembro; un lead que también es admin recibe una sola notificación (dedup por `user_id`).
- [ ] 5.6 [GREEN] Crear `backend/app/alerts/strategies/project_reinforcement.py`: `ProjectReinforcementStrategy(rule_type="project_reinforcement")`; usa `ProgressService.card` por proyecto activo; `N = ceil(horas_pendientes / semanas_laborales_restantes_hasta_due_date_máximo)` (mínimo 1 semana); arma `AlertCandidate` por destinatario deduplicado. Verify: 5.1-5.5.
- [ ] 5.7 [GREEN] `backend/app/alerts/registry.py`: registrar `"project_reinforcement": ProjectReinforcementStrategy` en `_STRATEGIES`.
- [ ] 5.8 [RED] `test_seed_default_alert_rules_includes_project_reinforcement` (Scenario "seed inicial con 8 reglas"): organización nueva → 8 reglas activas, una por `rule_type`. `test_seed_rerun_does_not_duplicate` (Scenario "seed re-ejecutado").
- [ ] 5.9 [GREEN] `backend/app/db_init.py`: añadir `("project_reinforcement", True, {"min_deviation": None})` a `_DEFAULT_ALERT_RULES`. Verify: 5.8.
- [ ] 5.10 Suite dirigida verde. Verify: `pytest -q backend/tests/test_alert_project_reinforcement.py`.

Commit 5: `feat(alertas): agrega el refuerzo de proyecto al motor`

## Fase 6 — Dashboard enriquecido + UI (Commit 6)

- [ ] 6.1 [RED] Extender/crear `backend/tests/test_dashboard_executive.py`: `test_projects_progress_includes_expected_real_semaphore` (Scenario "tarjeta enriquecida"); `test_percent_done_unchanged` (Scenario "percent_done existente no cambia").
- [ ] 6.2 [GREEN] `backend/app/modules/dashboard/service.py`: `_build_projects_progress` llama `ProgressService.card` por proyecto raíz y añade `expected_pct/real_pct/deviation/semaphore` sin tocar `percent_done`.
- [ ] 6.3 Crear `frontend/src/entities/progress/{progress.model,progress.service}.ts`: cliente para `GET /progress/projects/{id}`, `GET /progress/monthly-cut`, `GET/PUT /organizations/me/progress-thresholds`.
- [ ] 6.4 Crear `frontend/src/widgets/progress-cards/progress-cards.component.ts`: tarjeta con semáforo (verde/amarillo/rojo) + lista de hasta 4 puntos de `trend`; se integra en `frontend/src/pages/executive/executive.component.ts`.
- [ ] 6.5 Crear `frontend/src/pages/progress-report/progress-report.component.ts`: corte mensual por área (adelantado/llega/necesita_refuerzo), lazy-loaded en el router de la app.
- [ ] 6.6 Build de frontend verde. Verify: `cd frontend && npm run build`.

Commit 6: `feat(executive): agrega tarjetas de avance esperado vs real`

## Fase 7 — Suite completa + commits (Commit 7 condicional)

- [ ] 7.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`.
- [ ] 7.2 Confirmar aislamiento multi-tenant intacto en `progress`/umbrales/alerta. Verify: `pytest -q backend/tests/test_cross_tenant_isolation.py -k "progress or threshold"` (confirmar el nombre exacto del archivo con `ls backend/tests/ | rg cross_tenant`).
- [ ] 7.3 Confirmar `GET /dashboard/executive` intacto salvo el enriquecimiento aditivo (Scenario "percent_done existente no cambia" ya cubierto en 6.1).
- [ ] 7.4 Build de frontend verde (repetir tras cualquier ajuste de la Fase 6). Verify: `cd frontend && npm run build`.
- [ ] 7.5 Commit final (solo si 7.1-7.3 generaron correcciones no cubiertas por los commits 1-6).

Commit 7 (solo si 7.5 generó cambios): `fix(progress): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Peso por horas/conteo (mixto=0, sin horas=conteo) · 2.1,2.2,2.3
- Esperado: escalón por `due_date`, fallback lineal en días laborales, calendario L-V y fin de semana, sin dato sin `due_date` · 2.4,2.5,2.6,2.7
- Real ponderado por horas, rollup por subárbol/área · 2.8,2.9,2.10
- Caso numérico corregido de `design.md` D1 (reconciliación 1) · 2.11
- Desviación, semáforo, umbrales validados (invertidos, rango) · 2.12,2.13
- Tarjeta consolidada por proyecto/área (rollup siempre) · 2.14,3.1
- Corte mensual (clasificación, mes cerrado, aislamiento de tenant) · 3.2,3.3
- Permisos GET abierto / PUT admin en umbrales · 3.4,3.6
- Tendencia 4 semanas, snapshot semanal (upsert, backfill del real, esperado histórico sin dato) · 4.1,4.2,4.3,4.4,4.5
- Alerta `project_reinforcement`: candidato, última semana, sin refuerzo en verde, dedup semanal, destinatarios unión+lead (reconciliación 2) · 5.1,5.2,5.3,5.4,5.5,5.6,5.7
- Seed 7→8 reglas, sin duplicar · 5.8,5.9
- Dashboard enriquecido sin romper `percent_done` · 6.1,6.2
- UI tarjetas + corte mensual · 6.3,6.4,6.5,6.6
- Gate 27+28→35 y reanclaje de migración al head real · 0.1,0.2,0.3,0.4
- Migración aditiva/reversible (umbrales + tabla snapshots) · 1.1-1.6
- No regresión y commits escalonados · 7.1,7.2,7.3,7.4,7.5

## Risks

- **Reconciliaciones adicionales (4-7) no mandatadas explícitamente por el orquestador**: nombre de tabla en plural, rutas de endpoints, nombres de columnas de umbral y el rollup siempre-activo son decisiones tomadas para que las tareas queden concretas y sin ambigüedad; si el equipo prefiere otra convención, es una revisión a hacer antes o durante `apply`, no bloqueante.
- **Peso corregido (reconciliación 1) cambia números frente a `design.md`**: cualquier lectura literal de `design.md` D1 durante `apply` puede generar confusión con el 79%/48%/31% original; la Fase 2 (tarea 2.11) fija el número corregido (80/50/30) como contrato de test — usar ese valor, no el de `design.md`.
- **Dependencia dura de 27 y 28**: ambos con `apply: pending` en su `state.yaml` a la fecha de este documento; si su implementación real difiere de sus `design.md` (nombres de campos, firma del resolver), la Fase 0 debe detectarlo antes de escribir código de las Fases 2-6.
- **Cálculo pesado en árboles grandes** (proposal.md): mitigado por `_subtree_ids_select` (CTE ya existente) + snapshots que evitan recomputar la tendencia; no hay tarea de rendimiento dedicada en este documento — vigilar en `verify` si el árbol de una organización crece mucho.
