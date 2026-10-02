# Tasks: 45a · Planes institucionales (Decreto 612) — modelo y API

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈3 020 (`additions + deletions`), de las cuales ≈1 200 son pruebas, repartidas en 7 rebanadas |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | A1 → A2 → B → C → D → E → F (feature-branch-chain sobre el tracker `feat/45a-planes-modelo-api`) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

| # | Rama → destino | Contenido | ≈ líneas | Presupuesto | Escenarios | Reversa |
|---|---|---|---:|---:|---|---|
| A1 | `feat/45a-a1-migracion` → tracker | Migración `0028_add_institutional_plans` (5 tablas, 10 FKs, 5 únicos, 9 índices, 1 `CHECK`) + `test_migration_institutional_plans.py` con andamiaje completo, siembra por SQL crudo y `upgrade`/`downgrade` sobre base desechable | ~515 | 600 | 3, 7 (motor), 10 (motor) | `alembic downgrade -1` + revert; cero tablas preexistentes tocadas |
| A2 | `feat/45a-a2-modelos-ddl` → A1 | 5 modelos con `__table_args__` espejados + import en `db_init.py` (`# noqa: F401`) + equivalencia de DDL añadida al archivo de A1 | ~420 | 500 | 4 | Revert; tablas sin mapeo ORM, migración permanece |
| B | `feat/45a-b-vocabularios-esquemas` → A2 | `vocabularies.py`, `progress.py`, `schemas.py` completo, `router.py` vacío + `include_router` en `main.py` | ~440 | 500 | 30, 31, 32 | Revert; mapeo ORM permanece |
| C | `feat/45a-c-repositorio` → B | `_activity_scope`/`_require_activity`, roll-up cruzado, `list_activity_tasks`, `count_activities_by_group`, 5 `upsert_*`, `delete_*` + `test_plans_repository.py` | ~460 | 600 | 2, 5, 6, 8 (repo), 9, 12 (repo), 13, 14, 28 | Revert; modelo permanece |
| D | `feat/45a-d-servicio` → C | `activity_key`, doble avance, `is_confirmed`, vocabularios, transacción, `IntegrityError` → 409 + `test_plans_service.py` (fakes) | ~355 | 400 | 7 (svc), 8 (`is_confirmed`), 11, 15 | Revert; repositorio permanece |
| E | `feat/45a-e-api-lectura` → D | 5 `GET`, orden de rutas D-L, paginación opt-in + `test_plans_endpoints.py` (lectura) | ~420 | 500 | 1, 12 (API), 16, 17, 19, 20, 21, 29 | Revert; 45b sigue desbloqueado |
| F | `feat/45a-f-api-escritura` → E | `PUT` reporte, `POST`/`DELETE` de enlaces (×2), `require_role` singleton, idempotencia | ~410 | 500 | 10 (API), 18, 22, 23, 24, 25, 26, 27 | Revert; lectura permanece |

Presupuesto = estimación × 1,2 + ≈50 líneas de marcas de `tasks.md`, truncado a la centena. El ledger cuenta todo el diff, incluidas pruebas, documentación y las marcas de este archivo. **Ningún commit de los cambios `43-tareas-origen-externo`, `44-importar-checklist-xlsx` o `40-jira-import-usuario` debe caer en estas ramas.** Al terminar **D**, el 45b (modelo + costura de escritura) queda desbloqueado sin esperar a E ni a F.

**Contingencia**: si F desborda, se parte en F1 (reporte + enlace tarea↔actividad) y F2 (enlaces actividad↔actividad manuales, pospostergable). A1 no admite partición: su presupuesto de 600 es excepción explícita.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| A1 | Migración `0028` operativa y reversible sobre base desechable | PR A1 (base: tracker) | `cd backend && TEST_DATABASE_URL=... pytest -q tests/test_migration_institutional_plans.py` | N/A — bases desechables, sin servicio externo | `alembic downgrade -1` + revert; cero filas de otro agregado afectadas |
| A2 | 5 modelos con DDL idéntico a la migración (`create_all` ≡ `upgrade head`) | PR A2 (base: A1) | `pytest -q tests/test_migration_institutional_plans.py tests/test_migrations_baseline.py` | N/A — bases desechables | Revert; tablas sin mapeo ORM, migración de A1 permanece |
| B | Vocabularios, criterio de exclusión y esquemas completos, con las 3 guardias de alcance excluido en verde | PR B (base: A2) | `pytest -q tests/test_plans_service.py` | N/A — pruebas de unidad puras, sin base | Revert; el mapeo ORM de A2 permanece |
| C | Repositorio con tenant centralizado, roll-up sin N+1 y costura idempotente | PR C (base: B) | `pytest -q tests/test_plans_repository.py` | N/A — PostgreSQL real de pruebas vía fixture `session`, sin servicio externo | Revert; el modelo y los esquemas permanecen |
| D | Servicio con `null ≠ 0`, `activity_key`, `is_confirmed` y traducción de errores a 404/409/422 | PR D (base: C) | `pytest -q tests/test_plans_service.py` | N/A — fakes del repositorio, sin base | Revert; el repositorio permanece. **El 45b queda desbloqueado desde aquí** |
| E | Los 5 `GET` con orden de rutas correcto y aislamiento de tenant por endpoint | PR E (base: D) | `pytest -q tests/test_plans_endpoints.py` | `GET /api/v1/plans/activities` manual contra el backend en `./gestion.sh on` (verificación de orden de rutas) | Revert; el 45c puede consumir solo lectura si F se retrasa |
| F | `PUT`/`POST`/`DELETE` con RBAC, idempotencia y carrera de enlaces resuelta como 409 | PR F (base: E) | `pytest -q tests/test_plans_endpoints.py` | N/A — cliente `httpx.AsyncClient` in-process, sin servicio externo | Revert; la lectura de E permanece intacta |

## Fase 0: Verificación previa (gate)

> Obligatoria y completa solo antes de **A1** (compuerta de numeración, R2/D8/D-A). En A2–F solo se
> repite 0.5. Ningún paso de esta fase se salta ni se supone.

- [x] 0.1 [A1] `cd backend && .venv/bin/python -m alembic heads` en vivo. Criterio de salida: una sola cabeza. Si hay bifurcación o la cabeza no es `0027`, detener y reportar antes de escribir la migración.
- [x] 0.2 [A1] Inventario de `backend/alembic/versions/`: confirmar el número real del último consecutivo en disco.
- [x] 0.3 [A1] Revisar en los `tasks.md`/`design.md` de los cambios que **efectivamente entran en esta ola** (43, 44) cuántas revisiones reclama cada uno: 43 → `0025`; 44 → `0026` (`board_columns`) + `0027` (`tasks`). El 40 queda **fuera**: no se le reserva número.
- [x] 0.4 [A1] Re-anclar `revision`/`down_revision` en el archivo de migración a los valores confirmados por 0.1–0.3 (hoy `0028`/`0027`). Solo cambian dos literales y el docstring; el diseño no se renegocia. — APLICADO: re-anclado a `0027`/`down_revision="0026"` (cabeza viva `0026`; el 44 no está implementado).
- [ ] 0.5 [Toda rebanada] Re-medir la línea base de pruebas vigente en el tracker con `TEST_DATABASE_URL` configurada antes de iniciar la rebanada. Referencia al momento de este `tasks.md`: **1487 passed / 3 failed preexistentes** en `tests/test_adapter_microsoft365.py` (dependientes del reloj). `tests/test_connectors_oauth_redirect.py` es flaky por orden de ejecución: si falla, reejecutar en aislamiento antes de declarar regresión. No congelar esta cifra: el 44 agrega pruebas en paralelo. — NO medida: la suite completa queda fuera de esta corrida por restricción del orquestador (solo pruebas del cambio).
- [x] 0.6 [A1] Confirmar en disco que `backend/app/modules/plans/` y los cuatro archivos de prueba (`test_migration_institutional_plans.py`, `test_plans_repository.py`, `test_plans_service.py`, `test_plans_endpoints.py`) NO existen todavía.

## Fase 1: Migración `0028` [Rebanada A1]

> Spec `institutional-plans`: «Modelo persistido de planes y actividades» (escenario 3), «Enlace
> actividad↔actividad» (escenario 7, capa motor), «Enlace N:N tarea↔actividad» (escenario 10, capa
> motor). Design: D-A (cinco `op.create_table`), D-B (gate real es equivalencia de DDL, no
> `alembic check`).

- [x] 1.1 RED — crear `backend/tests/test_migration_institutional_plans.py` con el andamiaje calcado de `test_migration_project_kind.py` (`_sync_dsn`/`_admin_dsn`/`_recreate_*_database`/`_alembic_config`, base desechable dedicada, todo síncrono con `asyncio.run` + `@skip_no_db`); `test_upgrade_adds_the_five_tables_without_touching_existing_rows` (`upgrade 0027` → siembra por SQL crudo con `asyncpg` de organización + usuario + proyecto + tarea, con `is_active` **explícito** por el gotcha de `SoftDeleteMixin` — D-A — → `upgrade 0028` → `information_schema` confirma las 5 tablas, 5 únicos, el `CHECK` y los 9 índices → la fila de `tasks` sembrada sigue intacta).
- [x] 1.2 RED — `test_downgrade_drops_the_five_tables_without_losing_seeded_rows` (escenario 3: `downgrade 0027` sobre el esquema sembrado en 1.1 → las cinco tablas nuevas ausentes → `organizations`/`users`/`projects`/`tasks` intactas con sus filas).
- [x] 1.3 RED — sembrar un plan con dos actividades y `test_self_link_raises_check_violation` (escenario 7, capa motor: `INSERT INTO plan_activity_links` con `from_activity_id == to_activity_id` levanta `asyncpg.exceptions.CheckViolation`).
- [x] 1.4 RED — sembrar un enlace `task_plan_activities` y `test_duplicate_task_activity_pair_raises_unique_violation` (escenario 10, capa motor: segundo `INSERT` del mismo `(task_id, plan_activity_id)` levanta `asyncpg.exceptions.UniqueViolation`).
- [x] 1.5 GREEN — crear `backend/alembic/versions/0028_add_institutional_plans.py` (`down_revision="0027"`, re-anclado por 0.1–0.4): cinco `op.create_table` en orden de dependencia (`plans` → `plan_activities` → `plan_activity_reports` → `plan_activity_links` → `task_plan_activities`) con FKs/PK/únicos/`CheckConstraint` declarados **dentro** de cada tabla, índices con `op.create_index(op.f(...))` después, `downgrade()` en orden inverso estricto (drop de índices → drop de tabla, de la quinta a la primera). Docstring que cita el cambio SDD, la sección «Migración `0028`» de `design.md` y la verificación en vivo de la Fase 0.
- [x] 1.6 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_institutional_plans.py`. — OBSERVADO contra PostgreSQL desechable propio en `127.0.0.1:55433` (NO `5434`, que es la base real): 4 passed.
- [x] 1.7 Confirmar que `backend/alembic/versions/` suma exactamente un archivo nuevo (`0028_add_institutional_plans.py`) respecto al inventario de la Fase 0.
- [ ] 1.8 Commit convencional: `feat(plans): agrega migración 0028 de planes institucionales`. — OMITIDO por restricción: sin commits ni cambios al índice; mensaje propuesto en el informe.

## Fase 2: Modelos y equivalencia de DDL [Rebanada A2]

> Spec `institutional-plans`: «El esquema migrado es equivalente al construido en pruebas»
> (escenario 4). Design: D-C (sin `SoftDeleteMixin` en las tres tablas hijas), D-H (cero
> `relationship()`), D-B (`pg_trgm` → `import app.db_init` → `create_all`, orden obligatorio).

- [x] 2.1 RED — extender `test_migration_institutional_plans.py` con `test_create_all_and_migration_declare_the_same_plans_ddl`: levantar una **segunda** base desechable, `CREATE EXTENSION IF NOT EXISTS pg_trgm` → `import app.db_init` → `Base.metadata.create_all`, y comparar `pg_get_indexdef` de los **9** índices y `pg_get_constraintdef` de los 5 únicos + el `CHECK` contra los de la base de A1 construida con `alembic upgrade head`. Confirmar rojo por `ModuleNotFoundError: app.modules.plans.models`.
- [x] 2.2 GREEN — crear `backend/app/modules/plans/__init__.py` (vacío) y `backend/app/modules/plans/models.py`: cinco modelos con mixins en el orden canónico (`plans`: `TenantMixin, PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin`; `plan_activities`: los mismos sin `TenantMixin`; `plan_activity_reports`/`plan_activity_links`/`task_plan_activities`: `PkMixin, TimestampMixin, AuditMixin`, sin `SoftDeleteMixin` — D-C), `__table_args__` espejado byte-idéntico a la migración (incluido `ck_plan_activity_links_no_self`), cero `relationship()` (D-H).
- [x] 2.3 GREEN — `backend/app/db_init.py:41-96`: agregar el import de los cinco modelos con `# noqa: F401` (puebla `Base.metadata` para `create_all`, no por `relationship()` — D-H).
- [x] 2.4 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_institutional_plans.py tests/test_migrations_baseline.py` (el segundo archivo no cambia; su prueba `test_alembic_check_reports_no_diff_after_upgrade` se conserva como guardia de existencia por nombre — D-B).
- [ ] 2.5 Commit convencional: `feat(plans): agrega los 5 modelos con DDL equivalente a la migración`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.

## Fase 3: Vocabularios, criterio de exclusión y esquemas [Rebanada B]

> Spec `institutional-plans`: «Frontera con Solercia Security» (escenario 30), «Alcance excluido de
> este cambio» (escenarios 31, 32). Design: D-J (vocabularios), D-E (`progress_denominator()`), D-I
> (esquemas con campos derivados transitorios), D-N (frontera en el esquema).
>
> **Nota de archivo de prueba**: los tres escenarios de esta rebanada son unidades puras sin base de
> datos ni servicio; para respetar la convención de cuatro archivos fijada por el orquestador
> (`test_migration_institutional_plans.py` / `test_plans_repository.py` / `test_plans_service.py` /
> `test_plans_endpoints.py`), **B crea `test_plans_service.py`** con estas tres guardias, y **D**
> (Fase 5) le agrega las pruebas de `PlansService` con fakes. Es una precisión de ejecución, no una
> reapertura de `design.md`.

- [x] 3.1 RED — crear `backend/tests/test_plans_service.py`; `test_plans_module_has_no_importer_or_cli` (escenario 31: el módulo `plans` contiene exactamente **siete módulos sin contar `__init__.py`** — `models`, `vocabularies`, `progress`, `schemas`, `repository`, `service`, `router` — es decir ocho archivos `.py`; cero importaciones de `zipfile`, `openpyxl`, `docx` o `argparse` en el módulo).
- [x] 3.2 RED — `test_no_plans_menu_entry_and_no_frontend_route` (escenario 32: `_MENU_SEED` de `db_init.py` sin entrada «Planes»; `frontend/src` sin ninguna ruta `/plans` — D13).
- [x] 3.3 RED — `test_report_schema_has_no_second_or_third_line_fields` (escenario 30: `PlanActivityReportUpsert.model_fields` tiene exactamente los cinco campos de negocio — `reported_progress`, `qualitative_summary`, `evidence_refs`, `is_met`, `met_on_time` —, y `PlanActivityReport.__table__.columns` no contiene monitoreo cualitativo, evaluación independiente ni observaciones-recomendaciones — D-N/ADR 0009). Confirmar rojo por ausencia de `schemas.py`.
- [x] 3.4 GREEN — crear `backend/app/modules/plans/vocabularies.py`: seis `frozenset[str]` de módulo (`PLAN_TYPES`, `PLAN_STATUSES`, `REPORT_PERIODS`, `TASK_LINK_ROLES`, `ACTIVITY_LINK_TYPES`, `LINK_RESOLUTIONS`) + `validate_reported_progress(value)` (D-J, precedente `search/schemas.py:15`).
- [x] 3.5 GREEN — crear `backend/app/modules/plans/progress.py`: `ProgressDenominator` (`predicate` + `extra_joins`) y `progress_denominator()` con el criterio vigente `Task.status != "cancelled"` (D-E; único punto que el 44 editará si aplica después).
- [x] 3.6 GREEN — crear `backend/app/modules/plans/schemas.py` completo: `PlanRead`, `PlanActivityGroupCount`, `PlanDetailRead` (D-I/H13); `PlanActivityRead` con `activity_key`/`calculated_progress`/`primary_task_count`/`contributing_task_count`/`reported_progress`/`reported_period` como campos derivados transitorios; `PlanActivityDetailRead(PlanActivityRead)` con `reports`/`links_out`/`links_in`; `PlanActivityLinkRead` con `is_confirmed` derivado (D-I/H3); `ActivityTaskRead` con `counts_toward_progress` (D-I/H4); `PlanActivityReportUpsert` (D-N, exactamente cinco campos); `TaskLinkCreate`; `ActivityLinkCreate` **sin** `resolution` (D14); `PlanUpsert`/`PlanActivityUpsert` de costura, sin ruta HTTP (D10).
- [x] 3.7 GREEN — crear `backend/app/modules/plans/router.py` con `APIRouter(prefix="/plans", tags=["plans"])` vacío (sin endpoints todavía; E y F los agregan).
- [x] 3.8 GREEN — `backend/app/main.py:14-53,158-192`: agregar el import de `plans_router` y `app.include_router(plans_router, prefix=API_PREFIX)` **después** de `assistant_router` (`:192`, ya en HEAD desde el 48). — `app/main.py` ya traía cambios sin confirmar de otras personas; solo se agregaron el import y el `include_router`.
- [x] 3.9 Verificar en verde: `cd backend && pytest -q tests/test_plans_service.py`.
- [ ] 3.10 Commit convencional: `feat(plans): agrega vocabularios, criterio de exclusión del avance y esquemas`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.

## Fase 4: Repositorio [Rebanada C]

> Spec `institutional-plans`: «Modelo persistido» (escenario 2), «Reporte de autoevaluación por
> periodo» (escenarios 5, 6), «Enlace actividad↔actividad» (escenario 8, capa repositorio), «Enlace
> N:N tarea↔actividad» (escenario 9), «Doble avance» (escenarios 12 capa repositorio, 13, 14),
> «Costura de escritura idempotente» (escenario 28). Design: D-D (alcance de tenant compuesto),
> D-G (roll-up cruzado por lote), D-M (costura sin commit).

- [x] 4.1 RED — crear `backend/tests/test_plans_repository.py` sobre la fixture `session` (PostgreSQL real, aislamiento por `SAVEPOINT`); `test_activity_keeps_both_external_codes_after_roundtrip` (escenario 2: `["OM-05", "OM-08"]` sembrados y leídos desde JSONB sin perder ninguno).
- [x] 4.2 RED — `test_a_period_without_a_report_has_no_row` (escenario 5).
- [x] 4.3 RED — `test_upsert_report_replaces_the_period_value_without_duplicating` (escenario 6).
- [x] 4.4 RED — `test_conflict_link_is_listed_but_never_counted_as_confirmed` (escenario 8, capa repositorio: el enlace `conflict` aparece en `links_out`/`links_in` con su `resolution`, y el roll-up del avance devuelve el mismo resultado con y sin él, porque no visita `plan_activity_links` — D-G).
- [x] 4.5 RED — `test_a_task_can_be_primary_of_two_activities` (escenario 9).
- [x] 4.6 RED — `test_calculated_progress_is_none_without_primary_links` (escenario 12, capa repositorio).
- [x] 4.7 RED — sembrar **dos** proyectos con **dos** boards de columnas distintas y dos tareas `primary` de la misma actividad, una en cada proyecto; `test_rollup_uses_each_tasks_own_board_last_column` (escenario 13, el caso que motiva R3).
- [x] 4.8 RED — `test_contributes_links_stay_out_of_the_ratio_and_only_feed_the_count` (escenario 14: un `primary` completo + tres `contributes` sin completar ⇒ `1.0` y `contributing_task_count == 3`).
- [x] 4.9 RED — `test_reupserting_plan_and_activity_creates_no_new_rows` (escenario 28: conteo antes/después idéntico; verifica además que `upsert_plan`/`upsert_activity` **no** comitean — D-M).
- [x] 4.10 RED (apoyo, H4) — `test_list_activity_tasks_is_a_single_query`: contar sentencias emitidas con `before_cursor_execute` de SQLAlchemy sobre la conexión de la fixture y exigir exactamente **una**; comprobar además que `counts_toward_progress` coincide, tarea a tarea, con lo que `progress_denominator()` deja dentro del denominador.
- [x] 4.11 GREEN — crear `backend/app/modules/plans/repository.py`: `_activity_scope(organization_id)` (JOIN `plans` + `organization_id` + `is_active` de plan y actividad) y `_require_activity(organization_id, activity_id)` gemelo puntual (D-D).
- [x] 4.12 GREEN — `rollup_activity_progress(organization_id, activity_ids)`: CTE `last_column` (`DISTINCT ON (board.project_id) ORDER BY column_order DESC, created_at DESC`), `count(...) FILTER` con `progress_denominator()`, tenant comprobado dos veces (`plans.organization_id` y `projects.organization_id`), sin commit (D-G).
- [x] 4.13 GREEN — `list_activity_tasks(organization_id, activity_id, role=None)`: una consulta con `JOIN Project` (`Project.organization_id` en el `WHERE`), `outerjoin` del mismo CTE `last_column`, predicado y `extra_joins` de `progress_denominator()` (D-I/H4).
- [x] 4.14 GREEN — `count_activities_by_group(organization_id, plan_id)`: `GROUP BY (group_code, group_name)` con `count(*)` sobre `_activity_scope` (D-I/H13, sin contar en Python).
- [x] 4.15 GREEN — `list_plans`, `get_plan`, `list_activities`, `get_activity`, `list_links`, `get_link`, `list_reports_for_period`: todas parten de `_activity_scope`/`_require_activity`, `Select` **sin** `order_by` previo (R12/D-L), `SORTABLE_FIELDS` por listado.
- [x] 4.16 GREEN — cinco `upsert_*` idempotentes (`upsert_plan`, `upsert_activity`, `upsert_report`, `upsert_activity_link`, `upsert_task_link`) por su único de alcance, sin `commit`/`rollback`/`flush` autónomo (D10/D-M); `delete_task_link`/`delete_activity_link` físicos (D-C).
- [x] 4.17 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_plans_repository.py`.
- [ ] 4.18 Commit convencional: `feat(plans): agrega repositorio con alcance de tenant, roll-up cruzado y costura idempotente`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.

## Fase 5: Servicio [Rebanada D]

> Spec `institutional-plans`: «Enlace actividad↔actividad» (escenario 7, capa servicio), «Enlace
> actividad↔actividad» (escenario 8, `is_confirmed`), «Identificador legible derivado» (escenario
> 11), «Doble avance» (escenario 15). Design: D-F (`null` con una sola regla, periodo no adivinado),
> D-I/H3 (`is_confirmed`), D-K (códigos de error), D-M (transacción del caso de uso).

- [x] 5.1 RED — extender `backend/tests/test_plans_service.py` (creado en B) con un doble/fake del repositorio; `test_self_link_is_rejected_with_plan_activity_self_link` (escenario 7, capa servicio: 422 `plan_activity_self_link` sin llegar al motor).
- [x] 5.2 RED — `test_conflict_link_serializes_is_confirmed_false` (escenario 8: `is_confirmed = resolution != "conflict"`, D-I/H3).
- [x] 5.3 RED — `test_activity_key_is_derived_and_is_not_a_column` (escenario 11: unidad pura — `"code" in PlanActivity.__table__.columns` y `"activity_key" not in PlanActivity.__table__.columns` —, más el armado `f"{plan.code}/{activity.code}"` en el servicio).
- [x] 5.4 RED — `test_reported_progress_is_none_for_a_period_without_report` (escenario 15, incluido el caso sin `?period=`: `reported_progress` y `reported_period` ambos `None` — D-F).
- [x] 5.5 GREEN — crear `backend/app/modules/plans/service.py`: `PlansService` con `activity_key` derivado, doble avance (`calculated_progress = None if primary_task_count == 0 else done / primary_task_count` — D-F), `is_confirmed` derivado, validación de vocabularios (D12/D-J), `resolution="manual"` impuesto en creación de enlaces (D14), transacción propiedad del caso de uso (`await self.db.commit()` — D-M).
- [x] 5.6 GREEN — códigos de error `lower_snake_case` (D-K): `plan_not_found`, `plan_activity_not_found`, `plan_task_not_found`, `plan_task_link_not_found`, `plan_activity_link_not_found` (404); `plan_task_link_duplicate`, `plan_activity_link_duplicate` (409); `plan_activity_self_link`, `plan_period_invalid`, `plan_progress_out_of_range`, `plan_task_link_role_invalid`, `plan_activity_link_type_invalid`, `plan_type_invalid`, `plan_status_invalid`, `plan_resolution_invalid` (422).
- [x] 5.7 Verificar en verde: `cd backend && pytest -q tests/test_plans_service.py`.
- [ ] 5.8 Commit convencional: `feat(plans): agrega servicio con doble avance, is_confirmed y vocabularios validados`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.
- [ ] 5.9 [MANUAL — orquestador] Confirmar que el 45b puede arrancar desde aquí: modelo, vocabularios y costura de escritura idempotente ya están completos y probados; no requiere esperar a E ni a F.

## Fase 6: API de lectura [Rebanada E]

> Spec `institutional-plans`: «Modelo persistido» (escenario 1), «Doble avance» (escenario 12, capa
> API), «Aislamiento de tenant» (escenario 16, 17), «Lectura de planes y actividades» (escenarios
> 19, 20, 21), «Costura de escritura idempotente» (escenario 29). Design: D-L (orden de rutas), D9
> (sin `TaskRead`), D10 (sin `POST /plans`).

- [ ] 6.0 [Fase 0 de la rebanada] Re-medir la línea base de pruebas vigente en el tracker con `TEST_DATABASE_URL` configurada.
- [x] 6.1 RED — crear `backend/tests/test_plans_endpoints.py` (API real in-process con `httpx.AsyncClient`, patrón `test_project_hierarchy_endpoints.py`; helpers `_auth`, `_seed_plan`, `_link_task` sembrando **por la costura del repositorio**, nunca por `INSERT` crudo — D10/D-M); `test_plan_detail_exposes_code_type_year_and_group_counts` (escenario 1: `PlanDetailRead.groups` alimentado por `count_activities_by_group`).
- [x] 6.2 RED — `test_activity_without_primary_links_serializes_calculated_progress_as_null` (escenario 12, capa API: `null` literal en el JSON, no `0`).
- [x] 6.3 RED — `test_activity_of_another_organization_returns_404` (escenario 16).
- [x] 6.4 RED — `test_no_read_endpoint_ever_returns_rows_of_another_organization` (escenario 17, **paramétrica sobre los 5 endpoints de lectura**, no una sola aserción global).
- [x] 6.5 RED — `test_member_can_read_every_plans_endpoint` (escenario 19).
- [x] 6.6 RED — `test_activities_filtered_by_task_id_return_both_links` (escenario 20, mitad RED: `?task_id=` devuelve ambas actividades).
- [x] 6.7 RED (guardia, escenario 20 mitad) — `test_task_read_declares_no_plan_field` (unidad pura sobre `TaskRead.model_fields`, sin cambios en `tasks/schemas.py` — D9).
- [x] 6.8 RED — `test_activities_route_is_declared_before_plan_detail` (escenario 21: `GET /plans/activities` responde 200 con la lista, no 422 por intento de convertir `"activities"` en `UUID` — D-L).
- [x] 6.9 RED — `test_no_registered_route_creates_a_plan_or_an_activity` (escenario 29: recorrer `app.routes` bajo `/api/v1/plans`; ningún `POST` cuyo `path` termine en `/plans` o `/activities` — D10).
- [x] 6.10 GREEN — `backend/app/modules/plans/router.py`: declarar en **este** orden literal (D-L) `GET /plans/activities`, `GET /plans/activities/{activity_id}`, `GET /plans/activities/{activity_id}/tasks`, luego `GET /plans`, `GET /plans/{plan_id}` — todas con `Depends(get_current_membership)`, sin `require_role`.
- [x] 6.11 GREEN — paginación opt-in (`shared/pagination.py`) sobre `GET /plans` y `GET /plans/activities`; el repositorio construye el `Select` sin `order_by` previo y decide después según el camino (R12/D-L).
- [x] 6.12 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_plans_endpoints.py`.
- [ ] 6.13 Commit convencional: `feat(plans): agrega los 5 endpoints de lectura con orden de rutas y aislamiento de tenant`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.

## Fase 7: API de escritura [Rebanada F]

> Spec `institutional-plans`: «Enlace N:N tarea↔actividad» (escenario 10, capa API), «Aislamiento de
> tenant» (escenario 18), «Escritura del reporte de periodo» (escenarios 22, 23), «Escritura de
> enlaces por API» (escenarios 24, 25), «Autorización» (escenarios 26, 27). Design: D-K
> (`IntegrityError` → 409, H10; destino validado, H11), D-L (`require_role` singleton), D11 (`PUT`
> idempotente), D14 (`resolution='manual'`).

- [ ] 7.0 [Fase 0 de la rebanada] Re-medir la línea base de pruebas vigente en el tracker con `TEST_DATABASE_URL` configurada.
- [x] 7.1 RED — extender `test_plans_endpoints.py`; `test_duplicate_task_link_returns_409_plan_task_link_duplicate` (escenario 10, capa API: dominio, no motor).
- [x] 7.2 RED — `test_cross_tenant_task_link_is_rejected` (escenario 18: actividad ajena ⇒ `plan_activity_not_found`; tarea ajena ⇒ `plan_task_not_found`).
- [x] 7.3 RED — `test_two_consecutive_puts_leave_one_report_row_with_the_second_value` (escenario 22).
- [x] 7.4 RED — `test_reported_progress_out_of_range_is_rejected` (escenario 23: `150` ⇒ 422 `plan_progress_out_of_range`, sin fila creada).
- [x] 7.5 RED — `test_api_forces_resolution_manual_whatever_the_client_sends` (escenario 24: cuerpo con `"resolution": "exact"` ⇒ fila con `manual`, sin error de validación — D-I/D14); **más la aserción de destino ajeno (H11)**: un `to_activity_id` de otra organización responde `plan_activity_not_found` 404 sin crear fila.
- [x] 7.6 RED — `test_duplicate_task_link_conflicts_and_deleting_a_missing_link_returns_404` (escenario 25).
- [x] 7.7 RED — `test_member_is_forbidden_on_every_write_endpoint` (escenario 26, paramétrica con `member` **y** `viewer` sobre los 5 endpoints de escritura).
- [x] 7.8 RED — `test_manager_can_write_a_period_report` (escenario 27).
- [x] 7.9 RED (apoyo, H10) — `test_concurrent_duplicate_link_surfaces_409_not_500`: simular la carrera insertando el mismo par por una segunda sesión entre la consulta previa del servicio y su `INSERT`.
- [x] 7.10 GREEN — `backend/app/modules/plans/router.py`: insertar, en el orden literal de D-L, `PUT /plans/activities/{activity_id}/reports/{period}`, `POST`/`DELETE /plans/activities/{activity_id}/tasks[/{task_id}]`, `POST`/`DELETE /plans/activities/{activity_id}/links[/{link_id}]` — **entre** `GET .../tasks` y `GET /plans`, preservando la posición 4-8 de la tabla D-L. `require_role(MemberRole.admin, MemberRole.manager)` como singleton de módulo (`intake/router.py:30-34`). Los dos `DELETE` responden 204 sin cuerpo.
- [x] 7.11 GREEN — `backend/app/modules/plans/service.py`: envolver el `flush`/`commit` de los dos `POST` de enlace en `try/except IntegrityError` → `rollback()` → el mismo `AppException` de dominio (`plan_task_link_duplicate`/`plan_activity_link_duplicate` 409, H10); `to_activity_id` validado por el mismo `_require_activity(organization_id, to_activity_id)` que el origen (H11).
- [x] 7.12 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_plans_endpoints.py`.
- [ ] 7.13 Commit convencional: `feat(plans): agrega los 5 endpoints de escritura con RBAC, idempotencia y carrera resuelta como 409`. — OMITIDO por restricción (sin commits); mensaje propuesto en el informe.

## Fase 8: Suite completa, calidad estática y cierre

- [x] 8.1 Ejecutar la suite completa: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_institutional_plans.py tests/test_plans_repository.py tests/test_plans_service.py tests/test_plans_endpoints.py tests/test_migrations_baseline.py`. Confirmar cero regresiones frente a la línea base re-medida al iniciar la última rebanada, además de los 3 fallos preexistentes de `test_adapter_microsoft365.py`. — OBSERVADO en `127.0.0.1:55433`: 60 passed (migración 9, repositorio 12, servicio 12, endpoints 27). Los 3 fallos de `test_adapter_microsoft365.py` no se ejecutaron (fuera de alcance).
- [ ] 8.2 Ejecutar `cd backend && pytest tests/ -v` completo con `TEST_DATABASE_URL` configurada; comparar contra la línea base de la Fase 0. — NO ejecutada por restricción del orquestador (solo pruebas relevantes).
- [x] 8.3 `cd backend && ruff format --check .` y `ruff check .` sobre `app/modules/plans/`, `app/main.py`, `app/db_init.py` y los 4 archivos de prueba nuevos: cero hallazgos nuevos. — `ruff check` y `ruff format --check` limpios sobre `app/modules/plans/`, `app/db_init.py`, la migración y los 4 archivos de prueba; `app/main.py` conserva hallazgos E501 preexistentes ajenos al cambio.
- [x] 8.4 `cd backend && mypy app` — cero errores nuevos en `app/modules/plans/`. — `mypy app/modules/plans`: Success, 0 errores.
- [x] 8.5 Confirmar que `backend/alembic/versions/` suma exactamente **una** migración nueva de este cambio (`0028_add_institutional_plans.py`) respecto al inventario de la Fase 0.
- [x] 8.6 Releer las 32 pruebas nombradas en la tabla de cobertura de `design.md` y las 4 de apoyo (`test_progress_denominator_matches_the_current_criterion`, `test_alembic_check_reports_no_diff_after_upgrade`, `test_list_activity_tasks_is_a_single_query`, `test_concurrent_duplicate_link_surfaces_409_not_500`): ninguna aserción comentada ni debilitada. Confirmar en particular las guardias (20 mitad, 30, 31, 32).
- [ ] 8.7 [MANUAL — orquestador, NO de apply] Cadena de ramas (feature-branch-chain): tracker `feat/45a-planes-modelo-api` (punta `9641a1e`) → `feat/45a-a1-migracion` → `feat/45a-a2-modelos-ddl` → `feat/45a-b-vocabularios-esquemas` → `feat/45a-c-repositorio` → `feat/45a-d-servicio` → `feat/45a-e-api-lectura` → `feat/45a-f-api-escritura`, integradas al tracker por *fast-forward*. Solo el tracker se integra a `preview`. Confirmar que ningún commit de los cambios 43/44/40 cae en estas ramas.
