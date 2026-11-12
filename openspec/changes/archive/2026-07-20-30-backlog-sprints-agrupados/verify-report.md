```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:35ca7cb91dc84d5a6cc7ec553249b509112f2ea0
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 9/9
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:ec6d0809f38612cab6caf5e9ffa4aa7facb1c6117b926160fd2405496d98e7a7
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:31b4d0c3fd224f9821659502c4a0fc6f0444a3ba083233d4adb41e697d0f0957
```

## Verification Report

**Change**: 30-backlog-sprints-agrupados
**Branch**: `feat/backlog-sprints-agrupados` (HEAD `35ca7cb`)
**Version**: N/A (no capability version pin in `openspec/specs/sprints/spec.md`)
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 29 |
| Tasks complete | 29 |
| Tasks incomplete | 0 |

### Build & Tests Execution

**Tests**: ✅ 1337 passed / ❌ 0 failed / ⚠️ 0 skipped (378s / 373s / 376s — 3 independent full runs, all identical result)
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
...
1337 passed, 1 warning in 373.79s (0:06:13)
```
Matches the apply report's claim exactly (1332 baseline + 5 new in `test_sprint_backlog_aggregates.py`). The lone warning is a pre-existing SQLAlchemy `SAWarning` about FK ordering in `alembic/env.py`, unrelated to this change.

**Build**: ✅ Passed (frontend, `ng build`, 5.98s)
```text
source ~/.nvm/nvm.sh && nvm use 22.22.3 && cd frontend && npm run build
Application bundle generation complete. [5.983 seconds]
```

**Lint**: ✅ `npm run lint` → "ESLint: No issues found"

**Coverage**: ➖ Not available (no coverage tool configured in `backend/pytest.ini`/`frontend/package.json`)

### Fase 4 Finding — Legitimacy Judgment (explicit verdict requested)

`git show 35ca7cb -- backend/tests/test_catalog_pagination.py` shows two previously-existing tests
(`test_list_sprints_without_params_is_byte_compatible`,
`test_list_sprints_page_and_size_returns_correct_slice`) had their `meta` equality assertion
widened from `{"total": 2}` / `{"page": 2, "size": 2, "total": 5}` to also include
`"backlog": {"story_count": 0, "estimation_hours_sum": 0}`.

**Verdict: legitimate, not a masked regression.**
- `specs/sprints/spec.md` ("Agregados por sprint y por Backlog en la lista") explicitly REQUIRES
  `meta.backlog` on every `GET /projects/{id}/sprints` response, unconditionally — this is an
  intentional, spec-mandated additive contract change, not incidental behavior.
- `design.md` D2 states the contract is additive-only and only `SprintRead` (used by
  `burndown`/`close`/`PATCH`) must stay untouched — `meta` on the *list* endpoint was never
  covered by that invariant.
- The fix did not loosen the assertions to something weaker (e.g. `"backlog" in meta` or
  dict-subset checks) — it kept strict `==` equality and hardcoded the exact expected values
  (`story_count: 0, estimation_hours_sum: 0`), which is correct because those two tests' fixtures
  (`_create_project` + `_create_sprints`, no loose tasks) never populate the project backlog. I
  verified this against the fixture helpers directly — both tests create only sprints, zero
  tasks, so `{0, 0}` is the true expected value, not a rubber-stamped placeholder.
- No other assertion in either test was touched (page/size/total slicing, `data` ordering by
  name — all still asserted exactly as before).
- A dedicated regression guard (`test_sprint_read_burndown_and_close_payloads_unchanged_by_aggregates`,
  1.9/4.2) independently proves `SprintRead` truly never grows these fields on `burndown`/`close`,
  which is the actual non-regression invariant the spec cares about.

### Spec Compliance Matrix
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Agregados por sprint y por Backlog | Conteo y suma con tareas mixtas y sprint vacío | `test_sprint_backlog_aggregates.py::test_list_sprints_reports_story_count_and_hours_sum_never_null` | ✅ COMPLIANT |
| Agregados por sprint y por Backlog | Backlog con y sin tareas sueltas | `test_sprint_backlog_aggregates.py::test_list_sprints_meta_includes_backlog_aggregate_with_and_without_tasks` | ✅ COMPLIANT |
| Permisos de la lectura de agregados | Aislamiento de tenant y autenticación | `test_sprint_backlog_aggregates.py::test_list_sprints_aggregates_respect_tenant_scoping_auth_and_permissions` | ✅ COMPLIANT |
| Orden/visibilidad/vacíos del Backlog agrupado | Orden mixto con cerrado oculto | (no FE test runner — source read: `openSprintSections`/`closedSprints` computed, `project-workspace.component.ts:1328-1339`) | ⚠️ PARTIAL |
| Orden/visibilidad/vacíos del Backlog agrupado | Tres vacíos distintos | (no FE test runner — source read: lines 328-330, 387-390, 485-488) | ⚠️ PARTIAL |
| Cabecera de sección y acción contextual | Acción correcta por estado | (no FE test runner — source read: template lines 449-480, `canStartSprint` at 1809) | ⚠️ PARTIAL |
| Persistencia del colapso por proyecto y sección | Colapsar, recargar y aislar entre proyectos | (no FE test runner — source read: `readPersistedSections`/`persistSections`, keyed `sp-backlog-sections-<project_id>`, lines 2049-2069) | ⚠️ PARTIAL |
| Ids estables por sección (seam 31) | Identificador estable tras recarga | (no FE test runner — source read: `sectionId()`, pure function of `sprint.id`, lines 2006-2008) | ⚠️ PARTIAL |
| No regresión del listado y acciones existentes | Suite en verde con agregados nuevos | Full suite (1337 passed) + `test_sprint_backlog_aggregates.py::test_sprint_read_burndown_and_close_payloads_unchanged_by_aggregates` | ✅ COMPLIANT |

**Compliance summary**: 4/9 scenarios COMPLIANT with a runtime-passing covering test; 5/9 PARTIAL
(frontend-only requirements, evidence limited to source inspection + green `ng build`/`eslint`,
never a behavioral runtime test). `frontend/package.json` has **no `test` script at all** —
confirmed directly by reading the file (only `ng`, `start`, `build`, `lint`, `watch`). This is a
pre-existing, project-wide constraint (identical pattern already flagged and accepted in the
verify reports for changes 28 and 29 in this same repo), not new debt introduced by 30. `tasks.md`
itself declares `npm run build` as the explicit Runtime harness for Work Units U2/U3, so this was
accepted at the tasks phase, not discovered now. Downgraded to WARNING, not CRITICAL.

### Correctness (Static + Runtime Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Una sola query agrupada, no N+1 | ✅ Implemented + tested | `SprintRepository.aggregate_tasks_by_sprint` (`repository.py:240-267`): single `SELECT ... GROUP BY sprint_id` covering every sprint AND the backlog row (`sprint_id IS NULL`) in one pass. Proven at runtime by `test_aggregate_tasks_by_sprint_called_exactly_once_regardless_of_sprint_count` (spy via plain `async def` function, not `AsyncMock`, to preserve the descriptor/binding protocol — a real gotcha correctly worked around) — `call_count == 1` for a project with 3 sprints + backlog tasks. |
| `SprintRead` intact (retrocompatibilidad) | ✅ Implemented + tested | `schemas.py:61-79` unchanged in shape; `SprintListItem(SprintRead)` (`schemas.py:82-91`) is additive-only; `burndown`/`close` still emit plain `SprintRead` (verified by `test_sprint_read_burndown_and_close_payloads_unchanged_by_aggregates`). |
| `meta.backlog` present | ✅ Implemented + tested | `router.py:43` — `build_list_meta(pagination, total, base={"backlog": backlog})`; never null (`BacklogAggregate` defaults `story_count=0, estimation_hours_sum=0`, coalesced in SQL). |
| Deleted tasks excluded from aggregates | ✅ Implemented + tested | `Task.is_active.is_(True)` filter in the grouped query; proven by the "deleted task" branch of `test_list_sprints_reports_story_count_and_hours_sum_never_null` (2 active tasks counted, 1 soft-deleted excluded). |
| Orden y visibilidad (active→draft asc→Backlog; closed oculto) | ✅ Implemented (source) | `openSprintSections` computed filters `active` + `draft` (sorted `created_at` ascending via `localeCompare`), excludes `closed`; `closedSprints` computed is rendered only behind the "Ver sprints cerrados" toggle (`showClosedSprints`, default `false`); the Backlog section is a fixed block always rendered last. |
| Ids estables `sprint-<uuid>`/`backlog` | ✅ Implemented (source) | `sectionId(sprint: Sprint \| null): string { return sprint ? \`sprint-${sprint.id}\` : 'backlog'; }` — pure function of stable data, used as both the DOM `[id]` and the `localStorage` collapse key. |
| Colapso en localStorage con clave del design | ✅ Implemented (source) | Key `sp-backlog-sections-${projectId}` (matches design.md D6 exactly); `try/catch` degrades to in-memory on quota/private-mode failures (mirrors `layout-shell.component.ts` pattern); default expanded (empty `Set`) when no prior key. |
| Matriz estado→acción | ✅ Implemented (source) | Template (`project-workspace.component.ts:449-480`): `active` → "Completar sprint" (`openCloseSprint`, always); `draft` + `canStartSprint(sprint)` (both dates present) → "Iniciar sprint" (`startSprint`); `draft` without both dates → "Añadir fechas" (`openAddDates`). Matches design.md D5 exactly. `closed` sections render `readOnly` with no action button. |
| Textos es-CO formal tuteo | ✅ Implemented | `es-CO.json` `workspace.backlog` block: 12 keys (8 from tasks.md 3.4 + `noDates`, `add`, `addAria`, `empty` reused/pre-existing), all in español colombiano formal with correct tildes/eñes, zero voseo. |
| Review workload budget | ⚠️ Over budget, pre-accepted | Actual diff (4 feature commits, excluding openspec docs): **705 insertions / 30 deletions across 10 files**. `tasks.md`'s own forecast (~480-520 estimated) undershot the real total but explicitly flagged `400-line budget risk: High` and pre-accepted `Chain strategy: size-exception` with `Decision needed before apply: No`. Not a new finding — already resolved at the tasks phase. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 — one grouped query, no N+1 | ✅ Yes | `aggregate_tasks_by_sprint`, proven by spy test. |
| D2 — `SprintListItem` additive, `SprintRead` intact | ✅ Yes | Confirmed by schema diff and the dedicated guard test. |
| D3 — collapsible section as app-local composition | ✅ Yes | No `@solercia/ui` accordion added; signals/computed composition in the component, as designed. |
| D4 — order & visibility (active→draft→Backlog, closed hidden) | ✅ Yes | `openSprintSections`/`closedSprints` computed match exactly. |
| D5 — contextual action reuses 29's seams | ✅ Yes | `canStartSprint`/`startSprint`/`openAddDates` are the same functions introduced by 29, not reimplemented. |
| D6 — collapse state in `localStorage`, default expanded | ✅ Yes | Key format and `try/catch` degradation match the design text verbatim. |
| D7 — stable ids as seam for 31, no drag&drop added | ✅ Yes | `sectionId()` present; no `cdkDropList`/DnD handlers found in the diff. |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `tasks.md` tags every backend task `[RED]`/`[GREEN]`/`[TEST]` with an explicit `Verify:` command and the failure mode it fixes (`KeyError`, `AttributeError`) — functions as the TDD Cycle Evidence table for this change. |
| All tasks have tests | ✅ | 5/5 backend RED/GREEN tasks (1.1-1.9) map 1:1 to test functions in `test_sprint_backlog_aggregates.py`; frontend tasks (2.x/3.x) have no dedicated test file, consistent with the repo-wide FE test-runner gap. |
| RED confirmed (tests exist) | ✅ | 5/5 test functions exist in `backend/tests/test_sprint_backlog_aggregates.py`, verified by direct read. |
| GREEN confirmed (tests pass) | ✅ | 5/5 pass on 3 independent full-suite runs (1337 passed, 0 failed each time). |
| Triangulation adequate | ✅ | `test_list_sprints_reports_story_count_and_hours_sum_never_null` triangulates 2/3/5 (mixed) vs 0/0 (empty) in one test; `test_list_sprints_meta_includes_backlog_aggregate_with_and_without_tasks` triangulates 2-tasks/5h vs 0/0 across two projects. |
| Safety Net for modified files | ✅ | `test_catalog_pagination.py`'s 2 modified tests were part of the pre-existing 1332-test baseline and are re-run every full suite execution (all 3 runs green). |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Integration (HTTP via `AsyncClient` + real Postgres) | 5 new + 2 modified | `test_sprint_backlog_aggregates.py`, `test_catalog_pagination.py` | pytest + pytest-asyncio + httpx |
| Unit | 0 new | — | — |
| E2E | 0 | — | not installed |
| **Total** | **7** | **2** | |

Frontend has zero automated tests of any layer for this change (no test runner configured repo-wide).

---

### Changed File Coverage
Coverage analysis skipped — no coverage tool detected in `backend/pytest.ini` or `frontend/package.json`.

---

### Assertion Quality
Read `test_sprint_backlog_aggregates.py` in full (262 lines) and the diff of `test_catalog_pagination.py`. Scanned for tautologies, orphan empty-only checks without a companion non-empty case, type-only-only assertions, ghost loops, smoke-test-only patterns, and mock/assertion ratio.

**Assertion quality**: ✅ All assertions verify real behavior. Every test calls the real endpoint through `AsyncClient` against a real Postgres test database (no mocking of production logic except the one intentional spy on `aggregate_tasks_by_sprint`, which wraps and calls through to the real implementation via `wraps=original`, not stubbing it). Empty-collection assertions (`story_count == 0`) always have a companion non-empty case in the same or a sibling test (2/0, 2/0, 1). No tautologies, no ghost loops, no implementation-detail coupling (no CSS class or mock-call-count assertions).

---

### Quality Metrics
**Linter**: ✅ No errors (`eslint .` → "ESLint: No issues found")
**Type Checker**: ✅ No errors (`ng build` performs full AOT type-checking; build succeeded)

### Issues Found

**CRITICAL**: None

**WARNING**:
1. 5/9 spec scenarios (all frontend: order/visibility/empty-states, header action mapping, localStorage collapse persistence, stable ids) have no automated runtime test — only source inspection + green `ng build`/`eslint`. Root cause: `frontend/package.json` has no `test` script at all (pre-existing, project-wide constraint; same pattern already accepted in changes 28 and 29's verify reports). Not new debt introduced by this change, but still a real coverage gap for future regressions in this area (drag & drop, change 31, will touch these exact sections).
2. Actual authored diff (705+/30-, 735 lines across 4 commits) exceeds the 400-line review budget and even the plan's own forecast (~480-520). Already resolved at the tasks phase via explicit `size:exception`/`Decision needed before apply: No` — not a blocker, but worth a maintainer's awareness before merge.

**SUGGESTION**:
1. `showClosedSprints` toggle state is in-memory only (not persisted to `localStorage` like `collapsedSections`) — resets to hidden on every tab reload. Explicitly documented as an accepted, non-blocking risk in `tasks.md`'s Risks section; no spec requirement mandates persistence for it.

### Verdict
**PASS WITH WARNINGS**
Backend contract (aggregates, no N+1, `SprintRead` retrocompatibility, tenant isolation) is fully implemented and proven by 3 independent green full-suite runs (1337/1337). The Fase 4 pagination-test edit is a legitimate, spec-mandated additive-contract update, not a masked regression. Frontend requirements are correctly implemented per source inspection and a green typed build, but remain untested at the behavioral/runtime layer due to a pre-existing, project-wide absence of a frontend test runner — flagged as WARNING, not CRITICAL, consistent with this repo's own precedent (changes 28, 29). No CRITICAL findings; nothing blocks `sdd-archive`.
