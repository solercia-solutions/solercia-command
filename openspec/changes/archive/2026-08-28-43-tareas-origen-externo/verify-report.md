```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:39798bdd8cea8731e4af8c04e53913ff087d9de46aa42d1f5bc99920437dac43
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 11/11
scenarios: 26/26
test_command: "cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test pytest tests/ -v"
test_exit_code: 0
test_output_hash: sha256:d58a90599cb53c1fca585dcadf9119eeb4967f21915bef6ef90b5eee10afaeb7
build_command: "docker compose exec -T frontend npm run build"
build_exit_code: 0
build_output_hash: sha256:6a1af560e464ec6604f6537d428f2c28d2419683973fedecc23fb79a3e3edda4
```

## Verification Report

**Change**: `43-tareas-origen-externo`  
**Version**: N/A  
**Mode**: Strict TDD  
**Verified candidate**: branch `feat/43-tareas-origen-externo`, commit `e87c51454436b874ff7230bbb0456a5c8b7b6d8e`, tree `45182ef3863a6a221a846d4f051a8d3cd6c61cca`  
**Remediation binding**: `sha256:fdf2999c31a9444e3c72e259f330c10926c0aaf7acf3554670addde9eee86fb5` remediates `sha256:b5304c4be19c773dc635e3366bc6dc8820720a057e8f9991d0ce927a5e1a35b0`

### Verdict

**PASS WITH WARNINGS**. The current remediated candidate satisfies all 11 requirements and all 26 scenarios. The authoritative full backend suite now exits `0` with 1515 passing tests, the 25 focused change-43 tests pass, the three remediated Microsoft 365 clock tests pass, and the Angular container build passes. Remaining findings are non-blocking quality debt: Ruff format would reformat the remediated test file, the pre-existing six-error mypy baseline remains unchanged, and the existing frontend bundle-budget warning remains.

### Completeness

| Metric | Value |
|---|---:|
| Requirements | 11 total; 11 implemented |
| Scenarios | 26 total; 26 compliant |
| Tasks total | 78 |
| Tasks complete | 78 |
| Tasks incomplete | 0 |
| Focused change tests | 25 passed |

Counts were taken directly from `specs/tasks/spec.md` (`11` `### Requirement:` headings and `26` `#### Scenario:` headings) and `tasks.md` (`78/78` checked items).

### Build & Tests Execution

#### Authoritative full backend suite

```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test pytest tests/ -v
exit: 0
1515 passed, 2 warnings in 285.02s
sha256:d58a90599cb53c1fca585dcadf9119eeb4967f21915bef6ef90b5eee10afaeb7
```

The two warnings are the known Alembic/SQLAlchemy cycle warning for `dependencies`, `organizations`, and `users`. The production database `solercia` was not used.

#### Focused change-43 runtime suite

```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test pytest tests/test_migration_task_external_origin.py tests/test_tasks_external_origin.py -v
exit: 0
25 passed, 1 warning in 9.59s
sha256:5a550ff85584812b3921dd68798b6d71a69b939407ed175104d759c876cc791c
```

#### Focused remediation regression

```text
cd backend && pytest tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto -v
exit: 0
3 passed in 0.15s
sha256:9cc05c8531b1854f7d711a23fdd7933665317900668b282a9432cd7d1c4c7124
```

The remediation freezes only the adapter clock inside these tests. It does not skip assertions, weaken expectations, or modify production code.

#### Frontend container build

```text
docker compose exec -T frontend npm run build
exit: 0
Application bundle generation complete in 4.867s
sha256:6a1af560e464ec6604f6537d428f2c28d2419683973fedecc23fb79a3e3edda4
```

The build retains the known non-blocking initial-bundle warning: 1.04 MB, 39.73 kB over the 1.00 MB budget.

**Coverage**: skipped — `pytest-cov` is not installed and no project coverage command is configured.

### Spec Compliance Matrix

| # | Requirement | Scenario | Passing evidence | Result |
|---:|---|---|---|---|
| 1 | External-origin anchor | Duplicate in same project rejected | `test_duplicate_anchor_in_the_same_project_raises_unique_violation` | ✅ COMPLIANT |
| 2 | External-origin anchor | Multiple manual tasks coexist | `test_many_unanchored_tasks_coexist_in_the_same_project` | ✅ COMPLIANT |
| 3 | External-origin anchor | Same anchor in different projects | `test_the_same_anchor_in_two_projects_does_not_collide` | ✅ COMPLIANT |
| 4 | External-origin anchor | Key without source rejected | `test_external_key_without_source_raises_check_violation` | ✅ COMPLIANT |
| 5 | External-origin anchor | Soft delete releases anchor | `test_a_soft_deleted_task_releases_its_anchor` | ✅ COMPLIANT |
| 6 | Additive migration 0025 | Nullable columns preserve rows | `test_upgrade_adds_nullable_columns_without_touching_existing_rows` | ✅ COMPLIANT |
| 7 | Additive migration 0025 | Downgrade preserves rows | `test_downgrade_removes_the_columns_without_losing_rows` | ✅ COMPLIANT |
| 8 | ORM mirror | `create_all` matches migration | `test_create_all_and_migration_declare_the_same_anchor_ddl` | ✅ COMPLIANT |
| 9 | ORM mirror | DDL definitions compared directly | `test_anchor_objects_exist_by_name_in_both_schemas` plus direct DDL comparison | ✅ COMPLIANT |
| 10 | Source vocabulary | Connector identifier preserved | `test_every_registered_adapter_provider_is_a_known_task_source` | ✅ COMPLIANT |
| 11 | Source vocabulary | `planner` rejected | `test_planner_is_rejected_as_a_task_source` | ✅ COMPLIANT |
| 12 | Local/external keys | Detail exposes both | `test_task_detail_exposes_task_key_and_external_key_side_by_side` | ✅ COMPLIANT |
| 13 | Local/external keys | Listing/dashboard expose anchor | `test_listing_and_executive_dashboard_expose_source_and_external_key` | ✅ COMPLIANT |
| 14 | Exact filters | Source/key/status compose | `test_source_and_external_key_filters_compose_with_status` | ✅ COMPLIANT |
| 15 | Exact filters | No match returns empty 200 | `test_a_filter_without_matches_returns_an_empty_collection_with_200` | ✅ COMPLIANT |
| 16 | API immutability | POST ignores external anchor | `test_post_with_external_key_in_the_body_is_ignored_without_a_validation_error` | ✅ COMPLIANT |
| 17 | API immutability | PATCH preserves anchor | `test_patch_with_source_never_alters_an_existing_anchor` | ✅ COMPLIANT |
| 18 | Creation write seam | Valid `external_origin` persists | `test_create_task_with_external_origin_persists_and_exposes_the_anchor` | ✅ COMPLIANT |
| 19 | Creation write seam | Org-wide duplicate aborts | `test_create_task_rejects_an_anchor_already_active_in_the_organization` plus counter guard | ✅ COMPLIANT |
| 20 | Repository seam | Finds inside organization | `test_get_by_external_key_finds_an_anchor_inside_the_organization` | ✅ COMPLIANT |
| 21 | Repository seam | Never crosses organizations | `test_get_by_external_key_never_crosses_organizations` | ✅ COMPLIANT |
| 22 | Repository seam | Excludes soft-deleted task/project | `test_get_by_external_key_excludes_soft_deleted_tasks_and_projects` | ✅ COMPLIANT |
| 23 | History/out-of-scope | PATCH records no anchor history | `test_patch_records_no_history_entry_for_source_or_external_key` | ✅ COMPLIANT |
| 24 | History/out-of-scope | No persisted `is_context`/`merge_into` | `test_is_context_and_merge_into_are_not_persisted_columns` | ✅ COMPLIANT |
| 25 | Frontend type | `Task` has optional fields | Source inspection plus passing Angular build | ✅ COMPLIANT |
| 26 | Frontend type | `TaskDetail` inherits fields | `TaskDetail extends Task` inspection plus passing Angular build | ✅ COMPLIANT |

**Compliance summary**: 26/26 scenarios compliant.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| External-origin anchor | ✅ Implemented | Nullable `source`/`external_key`, CHECK, active-only unique partial index, and manual-task null semantics match the spec. |
| Migration 0025 | ✅ Implemented | `down_revision="0024"`; additive upgrade and reverse-order downgrade. |
| ORM mirror | ✅ Implemented | Model and migration use the same CHECK and partial-index predicate; direct DDL test passed. |
| Source vocabulary | ✅ Implemented | Eight allowed values, application validation, no PostgreSQL enum, `planner` excluded. |
| Local/external references | ✅ Implemented | `TaskRead` adds both fields without changing local `task_key`. |
| Exact filters | ✅ Implemented | Router → service → repository forwarding uses exact equality; fields remain absent from `SORTABLE_FIELDS`. |
| API immutability | ✅ Implemented | `TaskCreate` and `TaskUpdate` omit both fields; API extras remain ignored. |
| Creation write seam | ✅ Implemented | Keyword-only `external_origin`, validation and org-wide lookup occur before number allocation and insert. |
| Repository seam | ✅ Implemented | Project join enforces organization scope and excludes inactive task/project rows. |
| History/out-of-scope | ✅ Implemented | Anchor fields are absent from history; no persisted `merge_into`; `is_context` remains transient. |
| Frontend type | ✅ Implemented | `Task` declares optional nullable fields; `TaskDetail extends Task`. |

### Coherence (Design)

| Decision | Followed? | Evidence |
|---|---|---|
| D-A single partial index with `(source, external_key)` prefix | ✅ Yes | Migration/model define only `uq_tasks_source_external_key_project`. |
| D-B direct DDL equivalence | ✅ Yes | `pg_get_indexdef`/`pg_get_constraintdef` coverage passed. |
| D-C closed application vocabulary | ✅ Yes | `sources.py` remains dependency-light and guard-tested. |
| D-D legitimate write path only | ✅ Yes | Anchored application writes use `TaskService.create_task`. |
| D-E tenant-scoped repository seam | ✅ Yes | `JOIN Project`, `organization_id`, and active predicates are present. |
| D-F API schemas remain unchanged | ✅ Yes | Anchor fields exist only in `TaskRead`. |
| D-G one creation seam | ✅ Yes | `external_origin` is keyword-only and absent from HTTP schemas. |
| D-H additive frontend contract | ✅ Yes | Two optional fields are added to `Task`; build passes. |
| D-I soft delete releases anchor | ✅ Yes | Partial predicate and runtime tests cover active-only behavior. |

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ✅ | Five scope rows are present in full apply-progress observation `#3789`. |
| Behavioral work has tests | ✅ | 24 backend scenarios have runtime coverage; 2 frontend scenarios have source/build evidence. |
| RED confirmed | ✅ | Four behavior scopes record concrete failing pre-production states; referenced test files exist. |
| GREEN confirmed | ✅ | 25/25 focused tests, the three remediated clock tests, the full suite, and Angular build pass now. |
| Triangulation adequate | ✅ | Positive, negative, isolation, soft-delete, API immutability, composition, and no-match cases produce varied outcomes. |
| Safety net for modified files | ⚠️ | Full-suite before/after evidence exists, but apply-progress does not expose a dedicated `SAFETY NET` column. |

**TDD Compliance**: 5/6 checks fully evidenced; no TDD-critical assertion defect found.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 50 | 2 | pytest + monkeypatch/mocks |
| Integration | 21 | 2 | pytest + real PostgreSQL/ASGI harness |
| E2E | 0 | 0 | none |
| **Total** | **71 definitions** | **3 unique files** | |

The primary change-43 suite contains 25 tests (4 unit, 21 integration). The remediated Microsoft 365 file adds 46 unit-style definitions; the three affected tests were also rerun directly.

### Changed File Coverage

Coverage analysis skipped — no coverage tool detected (`pytest-cov` is not installed).

### Assertion Quality

All three created/modified test files were inspected: `test_migration_task_external_origin.py`, `test_tasks_external_origin.py`, and `test_adapter_microsoft365.py`. Empty-result assertions have non-empty companion behavior, loops cannot silently bypass the asserted production path, and the remediation changes only clock setup for existing assertions. No tautology, assertion without production execution, ghost loop, smoke-only check, or type-only-only check was found.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics

**Ruff format (9 scoped paths)**: ⚠️ exit `1`; `test_adapter_microsoft365.py` would be reformatted; `8 files already formatted`; `sha256:35f555b33a1d2d4d56d755f9174b14276a6530a615b558ed00439a7930eaa0e5`.

**Ruff lint (9 scoped paths)**: ✅ exit `0`; `All checks passed!`; `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`.

**Mypy (`mypy app`)**: ⚠️ exit `1`; six baseline errors in four files; `sha256:d498e2d3a01d0c39ee0ea286ce2f0a0fe8bdec09ecafa5db27f30f2cba41aaa6`. The output hash is byte-identical to the recorded pre-remediation baseline. The only error under a changed production module is `app/modules/tasks/service.py:145`, which predates change 43; the remediation changes no production file.

### Issues Found

**CRITICAL**: None.

**WARNING**

1. `ruff format --check` would reformat `backend/tests/test_adapter_microsoft365.py`; lint still passes and this does not invalidate runtime behavior.
2. `mypy app` retains the same six pre-existing errors in four files; no new error is attributable to the current candidate.
3. The Angular build retains the known 39.73 kB initial-bundle budget warning.
4. Apply-progress has no explicit `TRIANGULATE` or `SAFETY NET` columns; current runtime evidence establishes the substance but not the preferred table shape.

**SUGGESTION**

1. Normalize `backend/tests/test_adapter_microsoft365.py` with Ruff before delivery.
2. Track the six global mypy baseline errors separately from change 43.

### Evidence Preimage

`evidence_revision` is the SHA-256 of canonical JSON binding candidate HEAD/tree, exact proposal/spec/design/tasks hashes, authoritative counts, apply-progress observation `#3789`, the remediation lineage, and exact full-test, focused-test, remediation-test, build, Ruff, and mypy output digests. Database-bearing checks targeted only `solercia_test` and disposable test databases; production `solercia` was not touched. OpenSpec changes 44 and 45a were not read, modified, staged, or deleted.
