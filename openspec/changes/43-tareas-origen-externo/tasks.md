# Tasks: 43 · Ancla de procedencia externa en `tasks` (`source` + `external_key`)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈770–920 (`additions + deletions`), de las cuales ≈480–570 son pruebas, repartidas en 3 rebanadas |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Rebanada A → B → C (feature-branch-chain sobre el tracker `feat/43-tareas-origen-externo`) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

| Rebanada | Rama (base) | Contenido | ≈ líneas | Presupuesto (×1,2) | Intentos máx. |
|---|---|---|---|---|---|
| A | `feat/43-a-migracion` (base: tracker) | Migración `0025_add_task_external_origin.py` + espejo en `Task.__table_args__` (2 columnas + `CheckConstraint` + 1 `Index`) + `test_migration_task_external_origin.py` | 294–344 | 400 | 2 |
| B | `feat/43-b-escritura` (base: A) | `sources.py` + `get_by_external_key` + `create_task(..., external_origin=...)` (D-G) + `TaskRead.source`/`external_key` + tipo del frontend + `test_tasks_external_origin.py` (escenarios 10-13, 16-26) | 327–427 | 500 | 2 |
| C | `feat/43-c-filtros` (base: B) | Filtros `?source=`/`?external_key=` en `router → service → repository` + sus 2 pruebas | ~150 | 200 | 2 |

Ningún commit de los cambios `40-jira-import-usuario`, `44` o `47` (aún no aplicados) ni del
`48-puerto-llm` (en curso en paralelo sobre `backend/app/ai/`, `backend/tests/test_ai_*` y
`openspec/changes/48-puerto-llm/`) debe caer en estas ramas.

El reanclaje del cambio 40 (Fase 1) es edición de artefactos OpenSpec: **no cuenta** contra el
presupuesto de revisión anterior, pero es unidad de trabajo explícita y verificable (D8), aplicada
directamente sobre el tracker `feat/43-tareas-origen-externo`.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| A | Migración `0025` operativa y reversible; esquema de `create_all` idéntico al de la migración | PR A (base: tracker) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_task_external_origin.py tests/test_migrations_baseline.py` | N/A — pruebas de migración sobre bases desechables, sin servicio externo | `alembic downgrade -1` + revert de los commits de A; cero filas afectadas (columnas nulables, 0 tareas tras el 42) |
| B | Vocabulario cerrado, costura de lectura y camino de escritura del ancla operativos; exposición de solo lectura y tipo del frontend | PR B (base: rama de A) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_tasks_external_origin.py` | `cd frontend && npm run build` (D-H — sin runner de pruebas de tipos dedicado) | Revert de los commits de B; las columnas y los 2 objetos de esquema de A permanecen |
| C | Filtros `?source=`/`?external_key=` componibles con los filtros vigentes | PR C (base: rama de B) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_tasks_external_origin.py -k "source_and_external_key_filters_compose or filter_without_matches"` | N/A — filtros de solo lectura sobre datos ya sembrados por la prueba | Revert de los commits de C; 44 y 47 siguen desbloqueados (consumen la costura y el camino de escritura, no los filtros) |

## Phase 0: Verificación previa (gate)

- [x] 0.1 Confirmar que el cambio `42-purga-datos-demo` está archivado (precondición dura del `apply`; la base queda en 1 organización, 1 usuario, `SDMUJER > SEGURIDAD + PANDORA`, 0 tareas). Evidencia: precondición asumida por el orquestador al reclamar el intento; no reabierta aquí.
- [x] 0.2 Confirmar en disco `alembic heads`: única punta `0024` (`0024_add_work_calendar.py`, `down_revision="0023"`), 24 archivos en `backend/alembic/versions/`; siguiente libre `0025`. Evidencia: `alembic heads` (disco) → `0024 (head)`; `alembic current` (BD viva) → `0024 (head)`; `fd . alembic/versions -e py | wc -l` → `24` antes de crear `0025`.
- [x] 0.3 Confirmar en disco que `backend/app/modules/tasks/sources.py`, `backend/tests/test_migration_task_external_origin.py` y `backend/tests/test_tasks_external_origin.py` NO existen todavía. Evidencia: los tres `test -f` reportaron ausentes antes de escribir el archivo de la rebanada A.
- [x] 0.4 Confirmar en disco `Task.__table_args__` (`tasks/models.py:43-58`): solo los 2 índices GIN trigram, cero restricciones únicas ni `CheckConstraint` hoy. Evidencia: lectura de `models.py` antes de editar — confirmado.
- [x] 0.5 Confirmar en disco la firma vigente de `TaskService.create_task` (`service.py:252-335`): `(self, organization_id, project_id, data: TaskCreate, *, actor_id=None)`; el bloque *keyword-only* donde entra `external_origin` ya existe. Evidencia: `rg -n "async def create_task" -A 10 app/modules/tasks/service.py` — firma confirmada, sin `external_origin` todavía (llega en la rebanada B).
- [x] 0.6 Registrar la línea base de pruebas vigente en el tracker al iniciar cada rebanada. Evidencia: suite completa con `TEST_DATABASE_URL` puesta → **1496 passed / 3 failed preexistentes** (`test_adapter_microsoft365.py`, dependientes del reloj) tras agregar las 9 pruebas de la rebanada A (1487 base + 9 nuevas); requirió recrear `solercia_test` porque `create_all` no altera tablas ya existentes en una base persistida de una corrida previa.
- [x] 0.7 Confirmar en disco que `TaskCreate`/`TaskUpdate` (`schemas.py`) siguen sin `source`/`external_key`, y que ninguno de los tres esquemas de `tasks` declara `extra="forbid"`. Evidencia: `rg -n "class TaskCreate|class TaskUpdate|class TaskRead|extra="` sobre `schemas.py` — sin coincidencias de `extra=`.

## Phase 1: Reanclaje del cambio 40 — unidad de artefactos OpenSpec (D8)

> Mitigación de R1 (colisión de migraciones). Debe completarse antes de que el 40 llegue a `apply` y
> antes de cualquier `sdd-archive` de 40 o de 43. Edición pura de artefactos OpenSpec, sin código; se
> aplica directamente sobre el tracker `feat/43-tareas-origen-externo` y no cuenta contra el
> presupuesto de revisión de A/B/C.

- [x] 1.1 `40/tasks.md:47` (fila U1) — reducir objetivo y mensaje de commit a `projects`+`sprints`; restar ≈40–60 líneas de la estimación de la unidad.
- [x] 1.2 `40/tasks.md:59` (0.4) — el head real ya no es `0021_unique_org_member`: hoy es `0024`, y tras el 43 será `0025`.
- [x] 1.3 `40/tasks.md:60` (0.5) — el próximo consecutivo libre no es `0022`: es **el siguiente consecutivo libre en el momento del `apply` del 40**, que se verifica entonces con `alembic heads` y con los cambios pendientes (hoy sería `0029` si el 44 y el 45a aterrizan antes). **No se reserva ningún número por adelantado**: un `down_revision` hacia una revisión que nadie ha escrito rompe `alembic upgrade head` en despliegue.
- [x] 1.4 `40/tasks.md:64` (1.1) — renombrar a `00NN_add_external_anchor_projects_sprints.py`, donde `00NN` es el consecutivo libre que la compuerta fije en el `apply` del 40; eliminar `tasks` y `uq_tasks_project_source_external_key` de sus listas; alinear `source` de `VARCHAR(20)` a `String(50)` (D3).
- [x] 1.5 `40/tasks.md:65` (1.2) — quitar `backend/app/modules/tasks/models.py` de la lista de modelos a editar.
- [x] 1.6 `40/tasks.md:66` (1.3) — `test_external_anchor_migration.py` pierde las aserciones sobre `tasks`.
- [x] 1.7 `40/tasks.md:68-69` (1.5, 1.6) — `TaskRead` ya expone ambos campos: pasan de RED/GREEN a verificación de que siguen expuestos.
- [x] 1.8 `40/tasks.md:72` (Commit 1) — mensaje → `feat(anchors): agrega source/external_key con únicos parciales a projects/sprints`.
- [x] 1.9 `40/design.md:26-31` (D2) — marcar la fila de `tasks` como entregada por el 43; conservar la decisión para `projects`/`sprints`.
- [x] 1.10 `40/design.md:75` — `app/modules/{projects,sprints}/models.py`, sin `tasks`.
- [x] 1.11 `40/design.md:76` — `alembic/versions/00NN_add_external_anchor_projects_sprints.py`, con `00NN` resuelto por la compuerta en el `apply` del 40.
- [x] 1.12 `40/design.md:116-121` — `down_revision` real (la cabeza en vivo en el momento del `apply` del 40, verificada con `alembic heads`; no un literal fijado hoy) y alcance de dos tablas, no tres.
- [x] 1.13 `40/specs/tasks/spec.md:3-6` (preámbulo) — reescribir: el delta ya no agrega el ancla, la consume; el ancla la entrega el 43, este delta agrega solo la reconciliación idempotente del importador.
- [x] 1.14 `40/specs/tasks/spec.md:10-22` — eliminar el requisito «Ancla de procedencia externa (source + external_key)» y sus 2 escenarios.
- [x] 1.15 `40/specs/tasks/spec.md:33-40` — eliminar «Clave local y clave externa conviven como referencias distintas» y su escenario.
- [x] 1.16 `40/specs/tasks/spec.md:24-31` — conservar «Reconciliación idempotente por procedencia externa» (comportamiento del importador).
- [x] 1.17 `40/specs/tasks/spec.md:45` (referencias) — ajustar «precedente de ancla + idempotencia» → solo idempotencia; agregar `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` como origen del ancla que este delta presupone.
- [x] 1.18 `40/state.yaml:76` (`spec_notes`) — reescribir la nota: el 40 conserva solo la reconciliación idempotente; `source`/`external_key` llegan del 43.
- [x] 1.19 `40/state.yaml:72` — registrar el traslado en `spec_notes` y actualizar `last_updated`.
- [x] 1.20 Verificar: `rg -n "Ancla de procedencia" openspec/changes/40-jira-import-usuario/` no devuelve ningún requisito (solo referencias al 43 como proveedor). Evidencia: 6 coincidencias — un encabezado de decisión D2 (`design.md:26`), `proposal.md:46` (histórico, fuera del alcance de esta unidad), y el resto son las propias referencias/notas de traslado agregadas aquí (`specs/tasks/spec.md:6`, `state.yaml:53` histórico sin tocar, `state.yaml:79`, `tasks.md:144`); ninguna es un bloque `### Requirement:` en `specs/tasks/spec.md`.
- [x] 1.21 Verificar: `rg -n "0022|VARCHAR\(20\)|uq_tasks_project_source_external_key" openspec/changes/40-jira-import-usuario/` sin coincidencias. Evidencia: `0 matches`.
- [x] 1.22 Commit convencional: `docs(openspec): reancla el cambio 40 tras ceder el ancla de procedencia externa al 43`. Evidencia: commit `20ac6c3`.

## Phase 2: Migración `0025` + espejo ORM [Rebanada A]

> Spec `tasks`: «Ancla de procedencia externa» (escenarios 1-5), «Migración aditiva 0025…» (6-7),
> «Restricciones espejadas en el modelo ORM» (8-9). Design: D-A, D-B, D-I.

- [x] 2.1 RED — crear `backend/tests/test_migration_task_external_origin.py` (calco de `test_migration_project_kind.py:73-244`, base desechable `solercia_test_task_external_origin_migration`, todas síncronas con `asyncio.run` + `@skip_no_db`); `test_duplicate_anchor_in_the_same_project_raises_unique_violation` (escenario 1: `asyncpg.exceptions.UniqueViolationError` — el diseño nombraba la clase sin el sufijo `Error`; corregido contra la API real de `asyncpg`).
- [x] 2.2 RED — `test_many_unanchored_tasks_coexist_in_the_same_project` (escenario 2: 3 filas `(NULL, NULL, P)`).
- [x] 2.3 RED — `test_the_same_anchor_in_two_projects_does_not_collide` (escenario 3).
- [x] 2.4 RED — `test_external_key_without_source_raises_check_violation` (escenario 4: `asyncpg.exceptions.CheckViolationError`, mismo ajuste de nombre que 2.1).
- [x] 2.5 RED — `test_a_soft_deleted_task_releases_its_anchor` (escenario 5, D-I: ancla → `UPDATE is_active=false` → segunda fila activa con el mismo par aceptada).
- [x] 2.6 RED — `test_upgrade_adds_nullable_columns_without_touching_existing_rows` (escenario 6: `upgrade 0024` → siembra SQL cruda → `upgrade 0025` → `information_schema.columns` presentes, `is_nullable='YES'`, fila sembrada intacta con ambas `NULL`).
- [x] 2.7 RED — `test_downgrade_removes_the_columns_without_losing_rows` (escenario 7: `downgrade 0024` → columnas ausentes, fila viva).
- [x] 2.8 RED — `test_create_all_and_migration_declare_the_same_anchor_ddl`: segunda base desechable, en orden `CREATE EXTENSION IF NOT EXISTS pg_trgm` → `import app.db_init` (obligatorio, NO opcional) → `Base.metadata.create_all`; aserción de índice — `pg_get_indexdef` de `uq_tasks_source_external_key_project` idéntico entre `create_all` y `upgrade 0025` (escenario 8) — y aserción de restricción — `pg_get_constraintdef` de `ck_tasks_external_key_requires_source` idéntico en ambas (escenario 9).
- [x] 2.9 RED (apoyo, guardia) — `test_anchor_objects_exist_by_name_in_both_schemas` (lo único que `alembic check` sí cubre, D-B).
- [x] 2.10 GREEN — crear `backend/alembic/versions/0025_add_task_external_origin.py` (`down_revision="0024"`): `op.add_column` ×2 (`source VARCHAR(50)`, `external_key VARCHAR(255)`, ambas nulables, sin `server_default`), `op.create_check_constraint("ck_tasks_external_key_requires_source", "tasks", "external_key IS NULL OR source IS NOT NULL")`, `op.create_index("uq_tasks_source_external_key_project", "tasks", ["source", "external_key", "project_id"], unique=True, postgresql_where=sa.text("source IS NOT NULL AND external_key IS NOT NULL AND is_active"))`; `downgrade()` en orden inverso estricto (índice → check → `external_key` → `source`).
- [x] 2.11 GREEN — `backend/app/modules/tasks/models.py`: importar `CheckConstraint`, `text`; agregar columnas `source: Mapped[str | None] = mapped_column(String(50))` y `external_key: Mapped[str | None] = mapped_column(String(255))` (sin `index=True`); agregar el `CheckConstraint` y el `Index` único parcial a `__table_args__` con predicados byte-idénticos a la migración.
- [x] 2.12 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_task_external_origin.py tests/test_migrations_baseline.py`. Evidencia: **13 passed**.
- [x] 2.13 Confirmar `backend/alembic/versions/` con exactamente 25 archivos (24 previos + `0025_add_task_external_origin.py`). Evidencia: `fd . alembic/versions -e py | wc -l` → `25`.
- [x] 2.14 Confirmar que 2.1-2.9 ejercitan `alembic upgrade 0024` → `upgrade 0025` → `downgrade 0024` sobre la base desechable, sin dejar ningún paso manual adicional fuera del harness. Evidencia: helper `_disposable_database` + `command.upgrade`/`command.downgrade` en cada prueba, sin pasos manuales.
- [x] 2.15 Commit convencional: `feat(tasks): agrega migración 0025 y espejo ORM del ancla de procedencia externa`.

## Phase 3: Vocabulario, costura y escritura del ancla [Rebanada B]

> Spec `tasks`: «Vocabulario de source» (10-11), «Clave local y externa conviven» (12-13),
> «Inmutabilidad del ancla por API» (16-17), «Escritura del ancla reservada al caso de uso de
> creación» (18-19), «Costura get_by_external_key» (20-22), «Sin task_history…» (23-24), «Tipo de
> frontend» (25-26). Design: D-C, D-D, D-E, D-F, D-G, D-H.

- [x] 3.1 RED — crear `backend/tests/test_tasks_external_origin.py` (calco de `test_task_filters.py:1-64`); `test_planner_is_rejected_as_a_task_source` (escenario 11, unidad pura sin `@skip_no_db`: `AppException`, `code == "invalid_task_source"`, `status_code == 422`, el valor no aparece en `detail`).
- [x] 3.2 RED (mixta, queda como guardia permanente) — `test_every_registered_adapter_provider_is_a_known_task_source` (escenario 10, unidad pura: `import app.db_init` → `{a.provider for a in _ADAPTERS.values()} <= KNOWN_TASK_SOURCES`, más `validate_task_source("microsoft365") == "microsoft365"`).
- [x] 3.3 RED (guardia) — `test_is_context_and_merge_into_are_not_persisted_columns` (escenario 24, unidad pura sobre `Task.__table__.columns`).
- [x] 3.4 GREEN — crear `backend/app/modules/tasks/sources.py`: `KNOWN_TASK_SOURCES: Final[frozenset[str]]` (8 valores: `checklist_xlsx`, `microsoft365`, `google`, `jira`, `glpi`, `mcp`, `fake`, `solercia_connect`) + `validate_task_source(value) -> str` (422 `invalid_task_source`, sin eco del valor).
- [x] 3.5 Verificar en verde: `pytest -q tests/test_tasks_external_origin.py -k "planner or known_task_source or is_context_and_merge_into"`.
- [x] 3.6 RED — `test_create_task_with_external_origin_persists_and_exposes_the_anchor` (escenario 18) y `test_create_task_rejects_an_anchor_already_active_in_the_organization` (escenario 19, otro proyecto de la misma organización; `code == "task_external_anchor_conflict"`, `status_code == 409`, el conteo de tareas del segundo proyecto no cambia).
- [x] 3.7 RED — `test_get_by_external_key_finds_an_anchor_inside_the_organization` (escenario 20), `test_get_by_external_key_never_crosses_organizations` (escenario 21) y `test_get_by_external_key_excludes_soft_deleted_tasks_and_projects` (escenario 22, dos casos: `Task.is_active=false` y `Project.is_active=false`), todas sembradas con `create_task(..., external_origin=...)` una vez implementado en 3.9 — nunca con `UPDATE` crudo (D-D).
- [x] 3.8 GREEN — `backend/app/modules/tasks/repository.py`: agregar `get_by_external_key(organization_id, source, external_key) -> Task | None` con `JOIN Project`, `Project.organization_id`, `Project.is_active.is_(True)`, `Task.is_active.is_(True)`, `.order_by(Task.created_at.asc(), Task.id.asc()).limit(1).scalars().first()`; sin `commit`.
- [x] 3.9 GREEN — `backend/app/modules/tasks/service.py`: `create_task(..., *, external_origin: tuple[str, str] | None = None)`; cuando viene informado, valida con `validate_task_source`, comprueba unicidad org-wide con `self.repo.get_by_external_key`, lanza `AppException("...", code="task_external_anchor_conflict", status_code=409)` sin insertar si ya existe, y asigna `source`/`external_key` al `Task` antes de `self.repo.create(task)`.
- [x] 3.10 Verificar en verde: `pytest -q tests/test_tasks_external_origin.py -k "create_task_with_external_origin or already_active_in_the_organization or get_by_external_key"`.
- [x] 3.11 RED — `test_task_detail_exposes_task_key_and_external_key_side_by_side` (escenario 12) y `test_listing_and_executive_dashboard_expose_source_and_external_key` (escenario 13, al menos una fila anclada vía `create_task(..., external_origin=...)`, valores no nulos en `GET /projects/{id}/tasks` y `GET /dashboard/executive`).
- [x] 3.12 GREEN — `backend/app/modules/tasks/schemas.py`: agregar `source: str | None = None` y `external_key: str | None = None` a `TaskRead` (tras `task_key`); `TaskCreate`/`TaskUpdate` sin cambios.
- [x] 3.13 Verificar en verde: `pytest -q tests/test_tasks_external_origin.py -k "expose"`.
- [x] 3.14 RED — `test_post_with_external_key_in_the_body_is_ignored_without_a_validation_error` (escenario 16: 201, `external_key is None`) y `test_patch_with_source_never_alters_an_existing_anchor` (escenario 17: ancla vía `create_task(..., external_origin=...)`; `status` cambia, ancla no).
- [x] 3.15 RED (guardia) — `test_patch_records_no_history_entry_for_source_or_external_key` (escenario 23: `_HISTORY_TRACKED_FIELDS`, `service.py:387-394`, no los contiene).
- [x] 3.16 Verificar sin código nuevo requerido (D-F: `extra="ignore"` por defecto de Pydantic v2 ya cierra 16/17; `_HISTORY_TRACKED_FIELDS` ya no los declara): `pytest -q tests/test_tasks_external_origin.py -k "ignored_without_a_validation_error or never_alters_an_existing_anchor or no_history_entry"`.
- [x] 3.17 GREEN — `frontend/src/entities/workspace/workspace.model.ts`: agregar `source?: string | null` y `external_key?: string | null` a la interfaz `Task` (escenarios 25-26; `TaskDetail extends Task` los hereda sin editar `task-detail.model.ts`).
- [x] 3.18 Verificar en verde: `cd frontend && npm run build` (D-H: cambio aditivo puro; sin runner de pruebas de tipos dedicado — `tsconfig.app.json` solo compila lo alcanzable desde `main.ts` — la existencia del contrato la prueba el backend en 3.11 y este comando actúa como gate de no regresión, no de existencia).
- [x] 3.19 Verificar en verde la suite completa de la rebanada: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_tasks_external_origin.py`.
- [x] 3.20 Commits convencionales: `feat(tasks): agrega vocabulario de source y validate_task_source`, `feat(tasks): agrega get_by_external_key como costura de lectura del ancla`, `feat(tasks): agrega external_origin a create_task y expone el ancla en TaskRead`, `feat(workspace): agrega source y external_key al tipo Task del frontend`.

## Phase 4: Filtros de igualdad exacta [Rebanada C]

> Spec `tasks`: «Filtros de igualdad exacta por procedencia externa» (14-15). Design: cadena de 3
> saltos, sin novedad estructural.

- [ ] 4.1 RED — extender `test_tasks_external_origin.py`: `test_source_and_external_key_filters_compose_with_status` (escenario 14: `GET /projects/{id}/tasks?status=in_progress&source=checklist_xlsx&external_key=T-05` devuelve solo la tarea que cumple los 3 criterios).
- [ ] 4.2 RED — `test_a_filter_without_matches_returns_an_empty_collection_with_200` (escenario 15; el proyecto debe tener al menos una tarea sin ancla para que la prueba no nazca verde).
- [ ] 4.3 GREEN — `backend/app/modules/tasks/router.py`: `source: str | None = Query(default=None, description="Filtra por sistema de origen exacto (ej. 'checklist_xlsx', 'jira').")` y `external_key: str | None = Query(default=None, description="Filtra por clave exacta en el sistema de origen (ej. 'T-05').")`, reenviados a `service.list_tasks`.
- [ ] 4.4 GREEN — `backend/app/modules/tasks/service.py`: 2 kwargs más en `list_tasks` y su reenvío a `repo.list_for_project`, sin lógica adicional.
- [ ] 4.5 GREEN — `backend/app/modules/tasks/repository.py`: `if source is not None: stmt = stmt.where(Task.source == source)` y su gemelo para `external_key`, junto a los `if` existentes; **no** se agregan a `SORTABLE_FIELDS`.
- [ ] 4.6 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_tasks_external_origin.py -k "source_and_external_key_filters_compose or filter_without_matches"`.
- [ ] 4.7 Commit convencional: `feat(tasks): agrega filtros de igualdad exacta por source y external_key`.

## Phase 5: Suite completa, calidad estática y cierre

- [ ] 5.1 Ejecutar `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test pytest tests/ -v` completo; comparar contra la línea base vigente registrada en 0.6; confirmar cero regresiones nuevas más allá de los 3 fallos preexistentes de reloj.
- [ ] 5.2 Ejecutar `cd backend && ruff format --check .` y `cd backend && ruff check .`; corregir hasta cero hallazgos en `tasks/{models,sources,schemas,repository,service,router}.py` y en los 2 archivos de prueba nuevos.
- [ ] 5.3 Ejecutar `cd backend && mypy app`; corregir hasta cero errores nuevos en `app/modules/tasks/`.
- [ ] 5.4 Confirmar que `backend/alembic/versions/` sigue con exactamente 25 archivos (`0001`-`0025`), sin ninguna migración adicional fuera de `0025`.
- [ ] 5.5 Confirmar que la Fase 1 (reanclaje del 40) está completa y que las dos verificaciones `rg` (1.20, 1.21) siguen sin coincidencias indeseadas antes de cualquier `sdd-archive` de 40 o de 43.
- [ ] 5.6 Releer las 26 pruebas nombradas en la tabla de cobertura de `design.md` y confirmar que ninguna aserción quedó comentada o debilitada durante el desarrollo, en particular las 3 guardias (10, 23, 24) y `test_alembic_check_reports_no_diff_after_upgrade` (sin cambios).
- [ ] 5.7 [orquestador, NO de apply] Cadena de ramas (feature-branch-chain): tracker `feat/43-tareas-origen-externo` → `feat/43-a-migracion` (base: tracker) → `feat/43-b-escritura` (base: A) → `feat/43-c-filtros` (base: B), integradas al tracker por *fast-forward*. La Fase 1 (reanclaje del 40) se aplica directamente sobre el tracker. Solo el tracker se integra a `preview`. Confirmar que ningún commit de los cambios 40/44/47/48 cae en estas ramas.
