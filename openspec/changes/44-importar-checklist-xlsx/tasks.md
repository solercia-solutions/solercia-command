# Tasks: 44 · Importador idempotente de `CHECKLIST_TAREAS.xlsx`

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈2 160–2 560 (`additions + deletions`), ~55 % pruebas, repartidas en 7 rebanadas |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | A → B → C → D → E → F → G (feature-branch-chain sobre el tracker `feat/44-importar-checklist-xlsx`) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

| # | Rama → destino | Contenido | ≈ líneas | Presupuesto | Escenarios | Reversa |
|---|---|---|---:|---:|---|---|
| A | `feat/44-a-avance` → tracker | Gate D-REV · Migración `0026` (`board_columns.excluded_from_progress`, `down_revision="0025"`) + espejo · `outerjoin` nuevo y `in_denominator` (1er término) en `rollup_progress` · `PANDORA_COLUMNS`/`EXCLUDED_FROM_PROGRESS_COLUMNS` + `mark_columns_excluded_from_progress` · invariante `_i9_pandora_columns` | 300–360 | 500 | 75, 76, 78–91 (16) | `alembic downgrade -1` solo mientras B no esté aplicada; con `0027` encima, `-2` |
| B | `feat/44-b-contexto` → A | Migración `0027` (`tasks.context_group` + `tasks.merge_into_task_id`, `down_revision="0026"`) + espejo · `TaskRead` · 2º término de `in_denominator` (contexto) · exclusión de contexto en `_build_by_assignee`/`_build_workload`/`totals.tasks` · `origin-badge` + 2 usos | 280–340 | 400 | 77, 92–98, 102–108 (15) | `alembic downgrade -1` + revert; A permanece |
| C | `feat/44-c-completado` → B | `create_task(..., *, completed_at_override=)` keyword-only | 100–140 | 200 | 99–101 (3) | Revert; sin la costura, `now()` en vez de fecha histórica |
| D | `feat/44-d-parser` → C | `importers/checklist/{errors,parser,mapping}.py` puros, sin BD · 2 ajustes en `config.py` | 400–460 | 600 | 1–26, 28–34, 73 (34)¹ | Revert; no toca el esquema |
| E | `feat/44-e-consolidacion` → D | `seeds.py` (advisorio) + `consolidation.py` (escritura/lectura/validación del CSV, `utf-8-sig` con reintento `cp1252`) | 380–440 | 600 | 39–48 (10) | Revert; no toca el esquema |
| F | `feat/44-f-importador` → E | `importer.py` (D-TX con `SAVEPOINT`, activo en `--dry-run`), `ensure_users`, `ensure_label` con reactivación, dos pasadas, fusiones, `--update-existing` · `report.py` | 440–500 | 600 | 27, 35–38, 51–66, 69–72, 74 (26)¹ | Revert; no toca el esquema |
| G | `feat/44-g-cli` → F | `scripts/import_checklist.py` (D-EXIT) + extremo a extremo de idempotencia | 260–320 | 400 | 49, 50, 67, 68 (4) | Revert; no toca el esquema |

¹ **Corrección de coherencia respecto al ledger de `design.md`**: la tabla de rebanadas de `design.md` (línea 1199) lista el escenario 73 dentro del rango `69–74` de **F**, pero la tabla de cobertura del mismo diseño (línea 1062) asigna su prueba, `test_no_test_references_the_real_checklist_file`, al archivo `test_checklist_parser.py`, creado en **D**. `F` no crea ese archivo (su único archivo de prueba es `test_checklist_importer.py`). Esta tabla resuelve la contradicción según el archivo de prueba real: **73 vive en D** (34 escenarios, no 33) y **F queda en 26** (no 27), sin alterar el total de 108. Ver «Riesgos» al final de este documento.

Presupuesto = estimación × 1,2 + ≈50 líneas de marcas de `tasks.md`, redondeado a la centena (total 3300, igual a `state.yaml.delivery.total_budget`). El ledger cuenta todo el diff, incluidas pruebas, documentación y las marcas de este archivo. **Ningún commit de los cambios `43-tareas-origen-externo` o `40-jira-import-usuario` debe caer en estas ramas.** Solo el tracker se integra a `preview`.

**Contingencia declarada para B**: si el diff supera 400 líneas, extraer la insignia de procedencia (tareas 2.20–2.21, 2.24 abajo) a `feat/44-b2-insignia` (escenarios 102–103, ≈80 líneas); no bloquea C–G, porque nada del importador depende de la interfaz.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| A | Gate de migración + bandera de columna en el roll-up + 7 columnas de PANDORA + invariante | PR A (base: tracker `feat/44-importar-checklist-xlsx`) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_board_progress_flag.py tests/test_progress_rollup_exclusions.py tests/test_bootstrap_hierarchy.py tests/test_project_hierarchy_endpoints.py` | `cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url <host>` (dry-run) para observar `_i9_pandora_columns` contra datos reales | `alembic downgrade -1` (solo mientras B no esté aplicada; con `0027` encima, `-2`) + revert; la CTE vuelve al literal `cancelled` (cero efecto observable hoy); columnas de PANDORA aditivas e idempotentes |
| B | Migración de contexto/fusión + término de contexto en el roll-up + exclusión de contexto en el dashboard + insignia | PR B (base: rama A) | `cd backend && TEST_DATABASE_URL=... pytest -q tests/test_migration_task_context.py tests/test_tasks_context_fields.py tests/test_progress_rollup_exclusions.py tests/test_dashboard_context_exclusion.py` + `cd frontend && npm run build` | Revisión `ux-psicologia` manual del diff de `origin-badge` contra `http://localhost:4242` | `alembic downgrade -1` + revert; A permanece intacto |
| C | `completed_at_override` keyword-only en `create_task` | PR C (base: rama B) | `cd backend && pytest -q tests/test_task_completed_at_override.py` | N/A — unidad de servicio, sin conexión externa | Revert; sin la costura las tareas cerradas nacen con `now()`: dato inexacto, no corrupción |
| D | Parser y mapeo puros del XLSX, sin BD | PR D (base: rama C) | `cd backend && pytest -q tests/test_checklist_parser.py tests/test_checklist_mapping.py` | N/A — pruebas puras con `openpyxl` sobre `tmp_path` | Revert; no toca el esquema |
| E | Semillas advisorias + consolidación del CSV | PR E (base: rama D) | `cd backend && pytest -q tests/test_checklist_consolidation.py` | N/A — pruebas puras con `csv`/`tmp_path` | Revert; no toca el esquema |
| F | Importador: frontera D-TX, usuarios, etiquetas, dos pasadas, `--update-existing` | PR F (base: rama E) | `cd backend && TEST_DATABASE_URL=... pytest -q tests/test_checklist_importer.py` | N/A — fixture `session` con `SAVEPOINT`, sin servicio externo | Revert; no toca el esquema |
| G | CLI `import_checklist.py` + extremo a extremo de idempotencia | PR G (base: rama F) | `cd backend && TEST_DATABASE_URL=... pytest -q tests/test_import_checklist_cli.py` | `python -m scripts.import_checklist --dry-run --file <XLSX de prueba> --database-url <test>` como subproceso real | Revert; no toca el esquema |

## Fase 0: Verificación previa (gate)

> Obligatoria y completa solo antes de **A** (D-REV, dependency_gating). En B–G solo se repite 0.5.

- [ ] 0.1 [A] Confirmar que el cambio `43-tareas-origen-externo` está **ARCHIVADO** (no solo aplicado): entrega `external_origin`, `TaskRepository.get_by_external_key` y `checklist_xlsx` en `KNOWN_TASK_SOURCES`. Si no lo está, detener: `state.yaml.dependency_gating` lo declara dependencia dura.
- [ ] 0.2 [A] `cd backend && .venv/bin/python -m alembic heads` en vivo (lee el **directorio** de versiones). Criterio: una sola cabeza, `0025`.
- [ ] 0.3 [A] `cd backend && .venv/bin/python -m alembic current` en vivo contra la base objetivo (lee la **base**, D-REV/H14). Criterio: también `0025`. `heads` y `current` son DOS comandos distintos; ambos deben coincidir antes de escribir `0026`.
- [ ] 0.4 [A] Si la cabeza real no es `0025`, re-anclar `revision`/`down_revision` de la migración de A y corregir, en el MISMO commit, los TRES deltas que citan el número (`boards`, `tasks`, `project-hierarchy`); el diseño no se renegocia.
- [ ] 0.5 [Toda rebanada] Re-medir la línea base de pruebas vigente en el tracker con `TEST_DATABASE_URL` configurada antes de iniciar cada rebanada. Referencia al momento de este `tasks.md`: **1487 passed / 3 failed preexistentes** en `tests/test_adapter_microsoft365.py` (dependientes del reloj). `tests/test_connectors_oauth_redirect.py` es flaky por orden: reejecutar aislado antes de declarar regresión. No congelar esta cifra: el cambio `48-puerto-llm` escribe pruebas en paralelo.
- [ ] 0.6 [A] Confirmar en disco que `backend/app/importers/checklist/` y `backend/scripts/import_checklist.py` **no existen todavía**, y que `backend/alembic/versions/` no tiene `0026` ni `0027`.
- [ ] 0.7 [A] Confirmar en disco los 5 deltas de spec: 40 requisitos / 108 escenarios (`checklist-import` 29/74, `project-hierarchy` 1/5, `boards` 4/12, `tasks` 4/12, `dashboard-executive` 2/5) — re-contado con `rg '^### Requirement:'` / `rg '^#### Scenario:'` sobre `specs/`.

## Fase 1: Avance con banderas de columna [Rebanada A]

> Spec `boards`: «Bandera `excluded_from_progress` en `BoardColumn`», «Sembrado idempotente de las 7
> columnas de PANDORA», «Invariante de columnas y orden de PANDORA», «Banderas de exclusión en
> Removida y Gestionada aparte de ambos proyectos». Spec `project-hierarchy`: «Avance consolidado por
> conteo de tareas (roll-up)» (solo el término de columna; el de contexto es de B). Design: D-CTE,
> D-SEED, D4, D6, D-CTE-MIG (sin migración de datos).

- [ ] 1.1 RED — crear `backend/tests/test_migration_board_progress_flag.py` (calco de `test_migration_project_kind.py:73-244`); `test_upgrade_adds_the_flag_defaulting_to_false_without_touching_rows` (escenario 80).
- [ ] 1.2 RED — `test_downgrade_removes_the_flag_without_losing_rows` (escenario 81).
- [ ] 1.3 RED — `test_create_all_and_migration_declare_the_same_flag_ddl` (equivalencia de DDL, escenario 82).
- [ ] 1.4 RED — extender `backend/tests/test_bootstrap_hierarchy.py`; `test_first_seed_adds_the_four_missing_pandora_columns_in_order` (escenario 83).
- [ ] 1.5 RED — `test_second_seed_on_a_complete_board_is_a_noop` (escenario 84).
- [ ] 1.6 RED — `test_new_pandora_status_keys_are_verbatim` (contraste con `BoardService.add_column`, escenario 85).
- [ ] 1.7 RED — `test_pandora_with_its_seven_columns_passes_the_invariant` (escenario 86).
- [ ] 1.8 RED — `test_done_out_of_last_position_fails_the_invariant_and_the_runner_exits_nonzero` (invariante roja **y** `EXIT_INVARIANT_FAILED` de `purge_demo_data.py:53`, escenario 87).
- [ ] 1.9 RED — `test_a_slugified_status_key_fails_the_invariant_and_the_runner_exits_nonzero` (misma aserción doble, escenario 88).
- [ ] 1.10 RED — `test_seguridad_removida_and_gestionada_aparte_are_excluded` (escenario 89).
- [ ] 1.11 RED — `test_pandora_removida_and_gestionada_aparte_are_excluded` (escenario 90).
- [ ] 1.12 RED — `test_diferida_and_recurrente_stay_in_the_denominator_in_both_projects` (escenario 91).
- [ ] 1.13 RED — crear `backend/tests/test_progress_rollup_exclusions.py`; `test_tasks_in_excluded_columns_leave_the_denominator` (reemplaza a `test_progress_endpoint_excludes_cancelled_tasks_from_denominator:141`, escenario 76).
- [ ] 1.14 RED (guardia nueva) — extender `backend/tests/test_project_hierarchy_endpoints.py`; `test_mixed_methodologies_use_each_projects_last_status` (escenario 78).
- [ ] 1.15 Guardia — confirmar sin modificar `test_progress_endpoint_reproduces_the_18_of_20_business_example` (`:106`, escenario 75) y `test_progress_endpoint_of_another_org_project_returns_404` (`:219`, escenario 79) en verde.
- [ ] 1.16 GREEN — crear `backend/alembic/versions/0026_add_board_column_progress_flag.py` (`down_revision="0025"`, re-anclado por la Fase 0): `board_columns.excluded_from_progress BOOLEAN NOT NULL DEFAULT false`, aditiva, sin backfill (D-CTE-MIG).
- [ ] 1.17 GREEN — espejar en `backend/app/modules/boards/models.py` (tras `wip_limit`): `excluded_from_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false(), default=False)`.
- [ ] 1.18 GREEN — `backend/app/modules/projects/repository.py:290-350` (`rollup_progress`): `outerjoin` nuevo y aliasado a `BoardColumn` sobre `Task.board_column_id`; `in_denominator = coalesce(not_(task_column.excluded_from_progress), true())` sustituye a `not_cancelled` en LOS DOS términos (`:335` total, `:337` done — H15).
- [ ] 1.19 GREEN — `backend/app/maintenance/bootstrap.py`: `PANDORA_COLUMNS` (7 literales verbatim, `Done` última) y `EXCLUDED_FROM_PROGRESS_COLUMNS = ("Removida", "Gestionada aparte")`; `bootstrap_sdmujer` repite para `PAN` el bloque de `ensure_board_columns` que hoy solo corre para `SEG`, y marca ambas banderas en los dos proyectos.
- [ ] 1.20 GREEN — `backend/app/maintenance/repository.py`: `mark_columns_excluded_from_progress(board_id, status_keys)` — `UPDATE` acotado por `board_id` + `status_key IN (...)`, idempotente, sin `commit`.
- [ ] 1.21 GREEN — `backend/app/maintenance/invariants.py`: `_i9_pandora_columns` (comparación de **tupla completa** contra `PANDORA_COLUMNS`) añadida a `collect_invariants`.
- [ ] 1.22 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_board_progress_flag.py tests/test_progress_rollup_exclusions.py tests/test_bootstrap_hierarchy.py tests/test_project_hierarchy_endpoints.py`.
- [ ] 1.23 Confirmar que `backend/alembic/versions/` suma exactamente un archivo nuevo (`0026_add_board_column_progress_flag.py`) respecto al inventario de la Fase 0.
- [ ] 1.24 Commit convencional: `feat(boards): agrega bandera excluded_from_progress y siembra las 7 columnas de PANDORA`.

## Fase 2: Contexto, fusión y exclusión del dashboard [Rebanada B]

> Spec `tasks`: «Columnas `context_group` y `merge_into_task_id`», «Exposición de solo lectura de
> `context_group` y `merge_into_task_id`», «Insignia de procedencia de solo lectura junto al
> `task_key`». Spec `project-hierarchy` (segundo término del roll-up). Spec `dashboard-executive`:
> «R1 — La agrupación por persona excluye tareas de contexto», «R3 — Carga por persona y totales
> excluyen tareas de contexto». Design: D-COL, D5, D3/H7, D-BADGE-UI/H3.

- [ ] 2.1 RED — crear `backend/tests/test_migration_task_context.py` (mismo molde que 1.1); `test_upgrade_adds_both_nullable_columns_without_touching_tasks` (escenario 92).
- [ ] 2.2 RED — `test_downgrade_removes_both_columns_without_losing_rows` (escenario 93).
- [ ] 2.3 RED — `test_deleting_the_surviving_task_nulls_the_merge_pointer` (`ondelete="SET NULL"`, escenario 94).
- [ ] 2.4 Guardia — crear `backend/tests/test_tasks_context_fields.py`; `test_is_context_transient_behaves_identically_after_the_migration` (afirmado sobre la API bajo `assignee_id`, no sobre `information_schema` — escenario 95).
- [ ] 2.5 RED — `test_context_task_detail_exposes_context_group` (escenario 96).
- [ ] 2.6 RED — `test_post_with_context_group_in_the_body_does_not_persist_it` (escenario 97).
- [ ] 2.7 RED — `test_patch_with_merge_into_task_id_never_alters_the_link` (escenario 98).
- [ ] 2.8 RED — extender `backend/tests/test_progress_rollup_exclusions.py` (de A); `test_context_tasks_leave_the_denominator` (escenario 77).
- [ ] 2.9 RED — crear `backend/tests/test_dashboard_context_exclusion.py`; `test_context_task_is_excluded_from_workload` (escenario 104).
- [ ] 2.10 RED — `test_context_task_is_excluded_from_totals` (escenario 105).
- [ ] 2.11 RED — `test_overdue_context_task_still_appears_in_at_risk` (y `totals.at_risk == len(at_risk)`, escenario 106).
- [ ] 2.12 RED — `test_context_task_is_excluded_from_by_assignee` (escenario 107).
- [ ] 2.13 RED — `test_assignee_with_only_context_tasks_disappears_from_by_assignee` (escenario 108).
- [ ] 2.14 GREEN — crear `backend/alembic/versions/0027_add_task_context_and_merge.py` (`down_revision="0026"`): `tasks.context_group VARCHAR(80) NULL`, `tasks.merge_into_task_id UUID NULL` con auto-FK `ondelete="SET NULL"` (misma forma que `parent_task_id`), sin índice en ninguna (D-COL).
- [ ] 2.15 GREEN — espejar en `backend/app/modules/tasks/models.py`.
- [ ] 2.16 GREEN — `backend/app/modules/tasks/schemas.py`: `TaskRead.context_group`, `TaskRead.merge_into_task_id` (solo lectura); `TaskCreate`/`TaskUpdate` intactos.
- [ ] 2.17 GREEN — `backend/app/modules/projects/repository.py`: añadir el término de contexto (`Task.context_group.is_(None)`) a la MISMA expresión `in_denominator` de A, sin tocar el primer término.
- [ ] 2.18 GREEN — `backend/app/modules/dashboard/service.py`: excluir `context_group IS NOT NULL` en `_build_by_assignee` (`:184-220`), `_build_workload` (`:234-259`) y el conteo `tasks` de `_build_totals` (`:297-316`); `_build_at_risk` y `totals.overdue`/`totals.at_risk` **no** cambian.
- [ ] 2.19 GREEN — `frontend/src/entities/workspace/workspace.model.ts`: agregar `context_group?`, `merge_into_task_id?`.
- [ ] 2.20 GREEN — crear `frontend/src/entities/task/ui/origin-badge/origin-badge.component.ts` (standalone, entradas `source`/`externalKey`, sin `output`/`click`/`routerLink`) componiendo `<sol-badge variant="neutral" size="sm" [attr.aria-label]="originAria()">{{ externalKey() }}</sol-badge>`.
- [ ] 2.21 GREEN — usar la insignia en `frontend/src/widgets/project-workspace/project-workspace.component.ts:285-291` y `frontend/src/widgets/task-detail-panel/task-detail-panel.component.ts:93-95`, visible solo con `external_key` no nulo (`@if`).
- [ ] 2.22 Verificar backend en verde: `cd backend && TEST_DATABASE_URL=... .venv/bin/python -m pytest -q tests/test_migration_task_context.py tests/test_tasks_context_fields.py tests/test_progress_rollup_exclusions.py tests/test_dashboard_context_exclusion.py`.
- [ ] 2.23 `cd frontend && npm run build` — cero errores (base necesaria para el escenario 102/103).
- [ ] 2.24 Revisión `ux-psicologia` OBLIGATORIA sobre el diff de la insignia antes de cerrar B (escenarios 102 y 103): confirma que no arranca vacía con marcador de relleno, aria-label «Origen: `<source>` `<externalKey>`», contraste en tema claro y oscuro.
- [ ] 2.25 Confirmar que `backend/alembic/versions/` suma `0027` respecto al inventario tras A.
- [ ] 2.26 Commit convencional: `feat(tasks): agrega context_group, merge_into_task_id y excluye contexto del avance y del dashboard`.
- [ ] 2.27 [Contingencia, condicional] Si el diff supera el presupuesto de 400 líneas: extraer 2.20–2.21 y 2.24 a `feat/44-b2-insignia` (base: rama B sin la insignia); no bloquea C–G.

## Fase 3: `completed_at_override` [Rebanada C]

> Spec `tasks`: «`completed_at_override` keyword-only aplicado solo en el estado de cierre». Design:
> D8, línea `tasks/service.py:328`.

- [ ] 3.1 RED — crear `backend/tests/test_task_completed_at_override.py`; `test_create_in_the_closing_column_with_override_persists_the_exact_date` (escenario 99).
- [ ] 3.2 RED — `test_override_is_ignored_outside_the_closing_column` (escenario 100).
- [ ] 3.3 Guardia — `test_create_without_override_behaves_exactly_as_today` (escenario 101).
- [ ] 3.4 RED (apoyo, D8) — `test_completed_at_override_is_absent_from_taskcreate_and_the_router` (unidad pura sobre `TaskCreate.model_fields` y la firma del router).
- [ ] 3.5 GREEN — `backend/app/modules/tasks/service.py:252-335`: `create_task(..., *, completed_at_override: datetime | None = None)` keyword-only; `completed_at=self._resolve_completed_at(strategy, status, completed_at_override)` en `:328` (aplica solo cuando el estado resuelto es el de cierre).
- [ ] 3.6 Verificar en verde: `cd backend && pytest -q tests/test_task_completed_at_override.py`.
- [ ] 3.7 Commit convencional: `feat(tasks): agrega completed_at_override keyword-only en create_task`.

## Fase 4: Parser y mapeo puros [Rebanada D]

> Spec `checklist-import`: «Hoja y encabezados obligatorios», «Guardas antibomba», «Aceptación de
> celdas de fecha», «Ningún conteo de filas fijado», «Mapeo de Estado a columna», «Mapeo de Urgencia a
> prioridad», «Mapeo de Fecha Límite», «Etiqueta `recurrente`», «Etiquetas `area:`/`apoyo-ia:`»,
> «Etiqueta `pspi:x.y`» (parcial), «Ruteo a SEGURIDAD o PANDORA», «Composición de la descripción»
> (parcial), «El archivo real nunca es fixture de pruebas» (escenario 73). Design: D-ERR, D-CFG,
> D-INTENT/H19.

- [ ] 4.1 RED — crear `backend/tests/test_checklist_parser.py`; `test_parses_rows_when_sheet_and_headers_match_exactly` (escenario 1).
- [ ] 4.2 RED — `test_missing_sheet_raises_typed_error_before_reading_rows` (escenario 2).
- [ ] 4.3 RED — `test_missing_or_reordered_header_raises_typed_error` (escenario 3).
- [ ] 4.4 RED — `test_non_xlsx_bytes_raise_a_typed_importer_error_not_openpyxl` (escenario 4).
- [ ] 4.5 RED — `test_row_or_cell_limit_stops_iteration_with_a_typed_error` (escenario 5).
- [ ] 4.6 RED — `test_date_cell_as_date_and_as_iso_string_produce_the_same_due_date` (escenario 6).
- [ ] 4.7 RED — `test_mixed_cell_types_in_one_column_parse_without_error` (escenario 7).
- [ ] 4.8 RED — `test_parser_processes_exactly_the_rows_present` (escenario 8).
- [ ] 4.9 RED — `test_two_files_with_different_row_counts_both_parse` (escenario 9).
- [ ] 4.10 Guardia — `test_no_test_references_the_real_checklist_file` (unidad pura sobre `backend/tests/`: falla si alguna ruta menciona `CHECKLIST_TAREAS`, escenario 73; ver nota¹ arriba sobre su rebanada real).
- [ ] 4.11 RED — crear `backend/tests/test_checklist_mapping.py`; `test_seven_states_map_to_seguridad_columns` (escenario 10).
- [ ] 4.12 RED — `test_seven_states_map_to_pandora_columns` (escenario 11).
- [ ] 4.13 RED — `test_status_mapping_is_pure_and_deterministic` (escenario 12).
- [ ] 4.14 RED — `test_four_named_urgencies_map_to_priority` (escenario 13).
- [ ] 4.15 RED — `test_empty_or_dash_urgency_maps_to_low` (escenario 14).
- [ ] 4.16 RED — `test_iso_date_maps_to_due_date` (escenario 15).
- [ ] 4.17 RED — `test_literal_recurrente_leaves_due_date_null_and_adds_the_text_line` (escenario 16).
- [ ] 4.18 RED — `test_literal_sin_fecha_leaves_due_date_null_and_adds_the_text_line` (escenario 17).
- [ ] 4.19 RED — `test_literal_dash_leaves_due_date_null_and_adds_the_text_line` (escenario 18).
- [ ] 4.20 RED — `test_state_recurrente_with_iso_date_gets_the_label` (escenario 19).
- [ ] 4.21 RED — `test_literal_recurrente_date_with_another_state_gets_the_label` (escenario 20).
- [ ] 4.22 RED — `test_neither_condition_never_gets_the_label` (escenario 21).
- [ ] 4.23 RED — `test_case_and_spacing_variants_normalize_to_the_same_area_label` (escenario 22).
- [ ] 4.24 RED — `test_full_category_never_becomes_a_label_name` (escenario 23).
- [ ] 4.25 RED — `test_dash_apoyo_ia_produces_no_label` (escenario 24).
- [ ] 4.26 RED — `test_named_apoyo_ia_values_produce_their_label` (escenario 25).
- [ ] 4.27 RED — `test_pspi_prefix_produces_the_matching_label` (escenario 26).
- [ ] 4.28 RED — `test_row_without_prefix_or_plan_links_gets_no_pspi_label` (escenario 28).
- [ ] 4.29 RED — `test_pandora_in_category_routes_to_pandora` (escenario 29).
- [ ] 4.30 RED — `test_hu_prefix_routes_to_pandora` (escenario 30).
- [ ] 4.31 RED — `test_forced_ids_route_to_pandora_with_their_cross_area_label` (`T-69`/`T-70`/`T-73`, escenario 31).
- [ ] 4.32 RED — `test_row_without_signals_routes_to_seguridad` (escenario 32).
- [ ] 4.33 RED — `test_description_composes_in_the_specified_order` (escenario 33).
- [ ] 4.34 RED — `test_row_without_observaciones_omits_the_section` (escenario 34).
- [ ] 4.35 GREEN — `backend/app/config.py`: `CHECKLIST_FILE_MAX_ROWS=10_000`, `CHECKLIST_FILE_MAX_CELLS=200_000` (D-CFG, independientes de `JIRA_FILE_MAX_*`).
- [ ] 4.36 GREEN — crear `backend/app/importers/checklist/__init__.py`.
- [ ] 4.37 GREEN — crear `backend/app/importers/checklist/errors.py`: `ChecklistImportError` (`code` + `row_id`) con `ChecklistFileError`, `ChecklistSheetError`, `ChecklistHeaderError`, `ChecklistTooLargeError`, `ChecklistRowError`, `ChecklistConsolidationError` (D-ERR, sin `AppException`).
- [ ] 4.38 GREEN — crear `backend/app/importers/checklist/parser.py`: `load_workbook(read_only=True, data_only=True)`, validación de hoja/encabezado, `_guard_limits` **dentro** de `iter_rows` con los límites de `config.py`, `ChecklistRow` (dataclass congelada, D-INTENT).
- [ ] 4.39 GREEN — crear `backend/app/importers/checklist/mapping.py`: `ChecklistRow -> RowIntent` (dataclass congelada, puro), mapeo de 7 estados / 4 urgencias / 3 formas de Fecha Límite, etiqueta `recurrente` por regla explícita, `area:`/`apoyo-ia:`/`pspi:` (parcial), ruteo SEGURIDAD/PANDORA, composición de descripción; `due_date`/`completed_at` tz-aware en UTC (H19).
- [ ] 4.40 Verificar en verde: `cd backend && pytest -q tests/test_checklist_parser.py tests/test_checklist_mapping.py`.
- [ ] 4.41 Commit convencional: `feat(importers): agrega parser y mapeo puros del checklist XLSX`.

## Fase 5: Semillas y consolidación del CSV [Rebanada E]

> Spec `checklist-import`: «Formato del CSV de consolidación», «Valores por defecto del CSV según los
> veredictos verificados», «Validación del CSV antes de escribir cualquier fila». Design: D-SEEDS/H10,
> D-CSVIO/H9, D-VAL/H6, D-PASS (ruteo cruzado).

- [ ] 5.1 RED — crear `backend/tests/test_checklist_consolidation.py`; `test_dry_run_csv_has_one_row_per_source_row_and_seven_columns` (escenario 39).
- [ ] 5.2 RED — `test_action_outside_the_closed_vocabulary_is_rejected` (escenario 40).
- [ ] 5.3 RED — `test_t81_defaults_to_merge_into_t05` (escenario 41).
- [ ] 5.4 RED — `test_t23_defaults_to_subtask_of_t77` (escenario 42).
- [ ] 5.5 RED — `test_t94_and_t99_default_to_merge_into_and_the_rest_of_pspi_to_import` (escenario 43).
- [ ] 5.6 RED — `test_t74_is_never_proposed_as_context_group` (escenario 44).
- [ ] 5.7 RED — `test_detected_contradictions_are_recorded_as_notes_only` (escenario 45).
- [ ] 5.8 RED — `test_undecided_row_aborts_before_any_write` (escenario 46).
- [ ] 5.9 RED — `test_reference_to_an_unknown_id_aborts_before_any_write` (escenario 47).
- [ ] 5.10 RED — `test_a_cycle_in_the_subtask_graph_aborts_before_any_write` (escenario 48).
- [ ] 5.11 RED (apoyo, D-SEEDS/H10) — `test_seed_ids_absent_from_the_sheet_produce_a_warning_not_an_error`.
- [ ] 5.12 RED (apoyo, D-PASS) — `test_cross_project_links_are_rejected_before_any_write` (`subtask_of:`/`merge_into:` cruzando SEGURIDAD/PANDORA).
- [ ] 5.13 RED (apoyo, D-VAL/H6a) — `test_chained_subtask_of_is_rejected_with_the_service_error_code` (mismo código que `subtask_nesting_not_allowed`).
- [ ] 5.14 RED (apoyo, D-VAL/H6b) — `test_reference_to_a_skipped_or_merged_row_is_rejected_before_any_write`.
- [ ] 5.15 RED (apoyo, D-CSVIO/H9) — `test_csv_in_cp1252_is_read_with_a_warning_and_undecodable_bytes_exit_two`.
- [ ] 5.16 GREEN — crear `backend/app/importers/checklist/seeds.py`: `SeedDecision` (frozen, `action`+`note`), `CONSOLIDATION_DEFAULTS` — veredictos verificados de la exploración, advisorios (D-SEEDS).
- [ ] 5.17 GREEN — crear `backend/app/importers/checklist/consolidation.py`: escritura del CSV (`utf-8-sig`, `newline=''`, 7 columnas), lectura tolerante (utf-8-sig → reintento `cp1252` con advertencia → `ChecklistConsolidationError` salida `2`), `Decision` (dataclass congelada), `validate()` con las seis reglas (fila decidida, referencia existente, sin ciclos, sin enlaces entre proyectos, sin anidamiento encadenado, sin referencia a `skip`/`merge_into:`).
- [ ] 5.18 Verificar en verde: `cd backend && pytest -q tests/test_checklist_consolidation.py`.
- [ ] 5.19 Commit convencional: `feat(importers): agrega semillas advisorias y consolidación validada del CSV`.

## Fase 6: Importador [Rebanada F]

> Spec `checklist-import`: «Etiqueta `pspi:x.y`» (escenario 27), «Composición de la descripción»
> (escenario 35), «Extracción de `completed_at` desde Observaciones», «Idempotencia por ancla»,
> «Por defecto `--execute` solo crea lo que falta», «`--update-existing` con lista blanca explícita»,
> «Fila fusionada creada, nunca omitida», «Enlace de subtareas en dos pasadas», «Usuarios sin acceso
> creados como `viewer` sin contraseña», «`admin@solercia.com` como responsable por defecto»,
> «`ensure_label` idempotente por proyecto», «Reporte final con conteos y advertencias»,
> «Transacción única propiedad del caso de uso», «El archivo real nunca es fixture» (escenario 74).
> Design: D-TX/H1, D-PASS/H11, D-UPD/H4/H17, D-LBL-IO/H5, D-USERS/H8.

- [ ] 6.1 RED — crear `backend/tests/test_checklist_importer.py` sobre la fixture `session` (SAVEPOINT, `conftest.py:88-110`); `test_plan_links_in_the_csv_produces_the_pspi_label` (escenario 27).
- [ ] 6.2 RED — `test_description_over_4000_chars_fails_naming_the_row_id_without_creating_the_task` (D-DESC, escenario 35).
- [ ] 6.3 RED — `test_closed_row_with_the_pattern_sets_completed_at_override` (escenario 36).
- [ ] 6.4 RED — `test_same_pattern_on_a_non_closed_row_is_not_applied` (escenario 37).
- [ ] 6.5 RED — `test_row_without_the_pattern_uses_the_default_completed_at` (escenario 38).
- [ ] 6.6 RED — `test_first_run_creates_tasks_anchored_by_external_key` (escenario 51).
- [ ] 6.7 RED — `test_second_identical_run_reports_zero_changes` (escenario 52).
- [ ] 6.8 RED — `test_existing_anchored_task_is_untouched_without_update_existing` (escenario 53).
- [ ] 6.9 RED — `test_manually_edited_title_survives_update_existing` (escenario 54).
- [ ] 6.10 RED — `test_status_is_reconciled_with_update_existing` (escenario 55).
- [ ] 6.11 RED — `test_labels_are_reconciled_with_update_existing` (escenario 56).
- [ ] 6.12 RED — `test_merged_row_is_created_with_its_own_anchor_in_removida` (escenario 57).
- [ ] 6.13 RED — `test_second_run_does_not_recreate_the_merged_row` (escenario 58).
- [ ] 6.14 RED — `test_subtask_row_preceding_its_parent_is_created_without_error` (escenario 59).
- [ ] 6.15 RED — `test_second_pass_links_every_subtask_to_its_parent_in_the_same_project` (escenario 60).
- [ ] 6.16 RED — `test_first_import_creates_the_two_viewer_users_without_password` (correos ficticios de dominio de ejemplo, escenario 61).
- [ ] 6.17 RED — `test_second_run_does_not_duplicate_those_users` (escenario 62).
- [ ] 6.18 Guardia — `test_login_with_a_passwordless_account_is_rejected_generically` (`auth/service.py:27` ya lo hace, escenario 63).
- [ ] 6.19 RED — `test_unresolvable_solicitante_falls_back_to_the_admin_user` (escenario 64).
- [ ] 6.20 RED — `test_two_rows_with_the_same_area_reuse_one_label_row` (escenario 65).
- [ ] 6.21 Guardia — `test_reassigning_the_same_label_creates_no_second_link` (`assign_label` ya idempotente, `labels/service.py:120-122`, escenario 66).
- [ ] 6.22 RED — `test_dry_run_report_shows_the_planned_counts` (escenario 69).
- [ ] 6.23 RED — `test_execute_report_shows_the_counts_actually_applied` (escenario 70).
- [ ] 6.24 RED — `test_a_mid_run_failure_rolls_back_the_whole_transaction` (escenario 71).
- [ ] 6.25 RED — `test_dry_run_never_commits` (escenario 72).
- [ ] 6.26 Guardia — `test_the_synthetic_fixture_covers_the_relevant_cases_in_few_rows` (fixture de 6-10 filas, escenario 74).
- [ ] 6.27 RED (apoyo, D-LBL-IO/H5) — `test_ensure_label_reactivates_a_soft_deleted_label_instead_of_creating`.
- [ ] 6.28 RED (apoyo, D-UPD/H17) — `test_update_existing_without_differences_does_not_call_update_task`.
- [ ] 6.29 GREEN — crear `backend/app/importers/checklist/importer.py`: frontera D-TX (sesión ligada a una conexión con `join_transaction_mode="create_savepoint"` sobre una transacción externa, activa también en `--dry-run`); `ensure_users` (viewer sin contraseña vía `--member`); `ensure_label` (busca sin filtro de `is_active`, reactiva antes de crear); pasada 1 (ancla — `get_by_external_key`/`create_task` con `external_origin` + `completed_at_override`; filas `merge_into:` se crean con `status="Removida"`); pasada 2 (los CINCO atributos directos sobre la entidad ORM — `parent_task_id`, `task_type="subtask"`, `merge_into_task_id`, `context_group`, la nota «Consolidada en `SEG-N` (`T-xx`)» en `description` —, cada uno con regla de no-op); `--update-existing` (lista blanca de 4 campos con comparación previa antes de llamar `update_task`, reconciliación de etiquetas derivadas con `unassign_label`).
- [ ] 6.30 GREEN — crear `backend/app/importers/checklist/report.py`: conteos de `--dry-run` y `--execute` (creadas/actualizadas/fusionadas/enlazadas/advertencias).
- [ ] 6.31 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_checklist_importer.py`.
- [ ] 6.32 Commit convencional: `feat(importers): agrega el importador con transacción D-TX, usuarios y dos pasadas`.

## Fase 7: CLI [Rebanada G]

> Spec `checklist-import`: «`--execute` exige `--csv-in`», «Contrato de la CLI
> `import_checklist.py`». Design: D-EXIT/H2, D-USERS/H8.

- [ ] 7.1 RED — crear `backend/tests/test_import_checklist_cli.py` (calco de `test_purge_cli.py`); `test_execute_without_csv_in_exits_nonzero_without_touching_the_database` (escenario 49).
- [ ] 7.2 RED — `test_execute_with_a_valid_csv_in_applies_the_decisions` (escenario 50).
- [ ] 7.3 RED — `test_minimal_invocation_runs_in_dry_run_and_writes_the_csv` (escenario 67).
- [ ] 7.4 RED — `test_exit_codes_distinguish_csv_validation_from_database_failure` (por código, no por texto — escenario 68).
- [ ] 7.5 RED (apoyo, D-USERS/H8) — `test_a_member_without_mapped_email_exits_one_before_writing`.
- [ ] 7.6 GREEN — crear `backend/scripts/import_checklist.py`: `import app.db_init`, `argparse` (`--file`, `--dry-run` por defecto **exige conexión**, `--csv-out` por defecto `checklist_consolidation.csv`, `--execute --csv-in <ruta>`, `--update-existing`, `--member "Nombre=correo"` repetible, `--database-url`), engine propio con `dispose()`, `redact_database_url`, códigos de salida 0/1/2/3/4 según D-EXIT.
- [ ] 7.7 RED/GREEN — prueba extremo a extremo por subproceso (molde `test_purge_cli.py`): lanza `python -m scripts.import_checklist` contra `TEST_DATABASE_URL` con un XLSX generado en `tmp_path`, corrida dos veces para confirmar 0 creadas/0 actualizadas/0 cambios en la segunda (verifica end-to-end los escenarios 51/52; prueba adicional exigida por el diseño, sin escenario nuevo propio).
- [ ] 7.8 Verificar en verde: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_import_checklist_cli.py`.
- [ ] 7.9 Confirmar que `backend/alembic/versions/` suma exactamente **dos** migraciones nuevas del cambio 44 (`0026`, `0027`) respecto al inventario de la Fase 0.
- [ ] 7.10 Commit convencional: `feat(importers): agrega la CLI import_checklist con códigos de salida D-EXIT`.

## Fase 8: Suite completa, calidad estática y cierre

- [ ] 8.1 Ejecutar la suite completa: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q`. Confirmar cero regresiones frente a la línea base re-medida al iniciar la última rebanada, además de los 3 fallos preexistentes de `test_adapter_microsoft365.py`.
- [ ] 8.2 `cd backend && ruff format --check .` y `ruff check .` sobre `app/importers/checklist/`, `app/modules/{boards,projects,tasks,dashboard}/`, `app/maintenance/`, `app/config.py`, `scripts/import_checklist.py` y los 11 archivos de prueba nuevos: cero hallazgos nuevos.
- [ ] 8.3 `cd backend && mypy app` — cero errores nuevos.
- [ ] 8.4 `cd frontend && npm run build` — confirmación final (ya corrido en 2.23).
- [ ] 8.5 Confirmar que `backend/alembic/versions/` suma exactamente **dos** migraciones nuevas de este cambio (`0026_add_board_column_progress_flag.py`, `0027_add_task_context_and_merge.py`) respecto al inventario de la Fase 0.
- [ ] 8.6 Releer las 108 pruebas nombradas en la tabla de cobertura de `design.md` más las 9 de apoyo: ninguna aserción comentada ni debilitada. Confirmar en particular las guardias 63, 66, 73, 74, 75, 78, 79, 95, 101 en verde.
- [ ] 8.7 [MANUAL — orquestador, NO de apply] Cadena de ramas (feature-branch-chain): tracker `feat/44-importar-checklist-xlsx` → `feat/44-a-avance` → `feat/44-b-contexto` (+ `feat/44-b2-insignia` si aplicó la contingencia) → `feat/44-c-completado` → `feat/44-d-parser` → `feat/44-e-consolidacion` → `feat/44-f-importador` → `feat/44-g-cli`, integradas al tracker por *fast-forward*. Solo el tracker se integra a `preview`. Confirmar que ningún commit de los cambios 43/40 cae en estas ramas.

## Fase 9: Ejecución operativa del importador [MANUAL — orquestador, fuera de `pytest`]

> Posterior al `apply` completo (Fase 8) y anterior al `archive`. Runbook de `design.md` §«Migración /
> despliegue», paso 3. Los correos reales **nunca** se escriben en este repositorio.

- [ ] 9.1 [MANUAL] `alembic upgrade head` tras A (`0026`) y tras B (`0027`); ambas aditivas, sin ventana de mantenimiento.
- [ ] 9.2 [MANUAL] Respaldo y sembrado de PANDORA (una sola vez, tras A): `pg_dump ... > respaldo.sql` → `cd backend && .venv/bin/python -m scripts.purge_demo_data --execute --backup-file respaldo.sql --database-url <host>`.
- [ ] 9.3 [MANUAL] `--dry-run` con el archivo real (EXIGE conexión a BD, D-TX/H1): `.venv/bin/python -m scripts.import_checklist --file <ruta al XLSX real> --dry-run --csv-out checklist_consolidation.csv --database-url <host> --member "Jason Rizo=<correo real>" --member "Santiago Carreño=<correo real>"`.
- [ ] 9.4 [MANUAL] Revisión humana del CSV: fusiones, subtareas, grupos de contexto, notas. Guardar desde Excel como «CSV UTF-8 (delimitado por comas)»; abrir con Datos → Desde texto/CSV, delimitador coma, origen UTF-8 (D-CSVIO/H9 — en es-CO el doble clic puede interpretar `;` y dejar el archivo en una sola columna).
- [ ] 9.5 [MANUAL] `--execute --csv-in checklist_consolidation.csv --database-url <host> --member ...`; verificar en `http://localhost:4242`: tableros de SEGURIDAD y PANDORA, avance consolidado, vista ejecutiva (`by_assignee`/`workload` sin contexto, `at_risk` con él) y filtros `area:*`.
- [ ] 9.6 [MANUAL] Segunda corrida idéntica: confirmar 0 creadas / 0 actualizadas / 0 cambios.
- [ ] 9.7 [MANUAL] Advertencia `--update-existing` (H21): con esa bandera el XLSX manda sobre `status`; una tarea completada en la aplicación pero `PENDIENTE` en la hoja vuelve a «Sin iniciar». Usar solo cuando la hoja esté recién actualizada contra la realidad.
- [ ] 9.8 [MANUAL] Confirmar que ningún correo real quedó en el repositorio ni en este `tasks.md`: viven solo en la invocación de 9.3/9.5 y en el runbook operativo externo del equipo.

## Riesgos

- **Contradicción de coherencia en `design.md` (escenario 73)**: la tabla de rebanadas (línea 1199) cuenta el escenario 73 dentro del rango `69–74` de F, pero su prueba nombrada vive en `test_checklist_parser.py` (archivo creado en D). Resuelto en esta tabla asignando 73 a D (34 escenarios) y ajustando F a 26; el total 108 no cambia. Requiere confirmación del orquestador antes de cerrar D/F, o corrección formal de `design.md` si se prefiere mantener la cita textual «69–74».
- **R1** (43 pendiente de archive) sigue vigente en la Fase 0: si el cambio 43 no está archivado, A no puede iniciar.
- **R13/D-REV**: si `alembic heads` o `alembic current` no devuelven `0025`, la migración de A no se escribe hasta re-anclar los tres deltas afectados.
- **Contingencia B**: la rebanada absorbe migración + roll-up + dashboard + insignia; si el diff mide más de 400 líneas, extraer la insignia a `feat/44-b2-insignia` (2.27).
