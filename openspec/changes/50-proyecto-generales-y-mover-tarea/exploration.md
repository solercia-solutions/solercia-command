# Exploration: system project «Generales» + explicit task move (`POST /tasks/{id}/move`)

Change: `50-proyecto-generales-y-mover-tarea` · Date: 2026-09-05 · Phase: sdd-explore (investigation only, no code changed).

Product decisions D1/D2/D3 are already taken by the owner and are NOT re-opened here. This document verifies the current code with `file:line` evidence, states what the decisions collide with, compares the remaining open implementation choices, and lists what the proposer must resolve.

> Artifact store: hybrid. This file was materialized by the orchestrator from Engram topic `sdd/50-proyecto-generales-y-mover-tarea/explore` (observation 4534).

## Executive summary

The move endpoint is feasible and small on the surface, but the codebase has **five per-project invariants** that a naive `project_id` swap breaks silently: the external anchor, `task_number`/`task_key`, parent/child containment, task dependency edges, and labels. Additionally, "done" is **positional** everywhere (`allowed_statuses()[-1]`), so the 7-column order proposed for «Generales» (COMPLETADA third) would break `completed_at`, sprint counts, subtask progress and the dashboard. Recommended shape: `is_system` column + service guards + CHECK constraint for «Generales»; canonical state resolved at the **strategy** layer (not a new `board_columns` column) with an optional explicit `status` override; move implemented as a dedicated use case that re-runs every containment rule.

## 1. Current state (verified)

### 1.1 Task ownership and the external anchor

| Fact | Evidence |
|---|---|
| `Task.project_id` is `NOT NULL`, FK `projects.id ON DELETE CASCADE`, indexed | `backend/app/modules/tasks/models.py:88-93` |
| `external_key` requires `source` | CHECK `ck_tasks_external_key_requires_source` — `tasks/models.py:68-71` |
| Anchor uniqueness is **per project**, only among active rows | partial unique index `uq_tasks_source_external_key_project` on `(source, external_key, project_id)` `WHERE source IS NOT NULL AND external_key IS NOT NULL AND is_active` — `tasks/models.py:78-85` |
| Anchor lookup is **org-wide**, not per project | `TaskRepository.get_by_external_key` joins `Project.organization_id` — `tasks/repository.py:191-212` |
| Org-wide anchor uniqueness is enforced **only at creation** (409 `task_external_anchor_conflict`) | `tasks/service.py:298-311` |
| `TaskCreate` / `TaskUpdate` expose **no** `project_id` | `tasks/schemas.py:13-43`, `62-82` |

Consequence: the DB tolerates the same `(source, external_key)` in two projects; only the create path forbids it org-wide. A move MUST re-run the org-wide check (or at minimum the target-project check), otherwise it can create the exact duplicate the create path refuses.

### 1.2 Update path and history

- `update_task` — `tasks/service.py:399-503`. Snapshot/diff of `_HISTORY_TRACKED_FIELDS` = `status, assignee_id, estimation_points, estimation_hours, sprint_id, priority` (`tasks/service.py:390-397`). **`project_id` is not tracked.**
- `_record_history_diff` → `record_task_history` — `tasks/service.py:505-528`, `app/modules/activity/recorder.py:27-57`. `TaskHistory.field` is a free string, so adding `project_id` / `task_number` rows needs no migration.
- A `status` change is routed through `BoardService.move_to_column(..., commit=False)` so the column move and the other field writes land in one transaction — `tasks/service.py:425-439`.
- `delete_task` is a soft delete — `tasks/service.py:624-630`.

### 1.3 Methodology strategies and status validation

| Strategy | `default_columns()` = `allowed_statuses()` | Evidence |
|---|---|---|
| planner | `Sin iniciar, En curso, Completada` | `app/methodology/planner.py:6` |
| kanban | `Backlog, Doing, Done` | `app/methodology/kanban.py:6` |
| scrum | `To Do, In Progress, In Review, Done` | `app/methodology/scrum.py:6` |
| custom | `[]` (empty by design) | `app/methodology/custom.py:12-16` |

- At runtime nobody uses the base strategy directly: `resolve_board_strategy(project, db)` wraps it in `BoardAwareStrategy`, whose `allowed_statuses()` returns the **persisted `board_columns.status_key`** values, falling back to the base only when the board has none — `app/methodology/board_aware.py:31-85`. Call sites: `tasks/service.py:171,217,266,419,563`, `projects/service.py:81,512`, `sprints/service.py:263`, `dashboard/service.py:447`.
- Validation of a `status` string: `_resolve_status` — `tasks/service.py:780-821` (422 `invalid_status`; 422 `board_has_no_columns` when the board has zero columns, which blocks create AND move — no permissive fallback).
- `_resolve_column_for_status` — `tasks/service.py:654-681` — same contract, resolved against live columns.

### 1.4 "Done" is positional, not semantic — no canonical state exists today

`grep canonical` over `backend/app` returns only Jira-adapter and unrelated hits. What exists instead:

| Consumer | Rule | Evidence |
|---|---|---|
| `completed_at` stamping/clearing | `status == allowed[-1]` | `tasks/service.py:823-833` |
| Subtask progress | counts subtasks whose status == `allowed[-1]` | `tasks/service.py:722-736` |
| Sprint close / burndown `done_status` | `allowed[-1]` | `sprints/service.py:271,285` |
| Executive dashboard bounds | `first = allowed[0]`, `last = allowed[-1]` | `dashboard/service.py:438-451` |

`allowed_statuses()` order == `board_columns.order`. This is why `SEGURIDAD_COLUMNS` deliberately puts `"Completada"` **last** (`app/maintenance/bootstrap.py:24-33`) and why invariant I4 freezes it (`app/maintenance/invariants.py:101-125`). Change 44 reached the same conclusion for PANDORA (`openspec/changes/44-importar-checklist-xlsx/proposal.md:92`, D4: "`Done` última").

### 1.5 `board_column_id` vs `status`

- `BoardColumn` has `name`, `status_key` (immutable), `order`, `wip_limit` — no category/canonical field — `app/modules/boards/models.py:46-73`.
- `BoardService.move_to_column` sets `board_column_id` + `status` atomically, stamps `updated_by`, enforces WIP with a row lock (409 `wip_limit_exceeded`) — `boards/service.py:66-121`.
- `TaskService.move_task_column` rejects a column not on the task's **own** project board (422 `invalid_board_column`) — `tasks/service.py:540-582`.
- `Task.board_column_id` is nullable: legacy rows and column-less custom boards have none — `tasks/models.py:105-116`.

### 1.6 Project model, API surface and «Generales» prerequisites

| Fact | Evidence |
|---|---|
| No `is_system` / `is_default` flag exists | `app/modules/projects/models.py:32-121` |
| `ProjectKind` has only `area` \| `proyecto` | `app/shared/enums.py:26-37` |
| `code` unique per organization | `uq_project_code_per_org` — `projects/models.py:38` |
| Soft delete available via mixin, but **no DELETE endpoint exists** | `projects/router.py:37,63,79,92,127,163,183,207` |
| `ProjectStatus.archived` exists but **no endpoint sets it** (`ProjectUpdate` has no `status`) | `shared/enums.py:19-23`, `projects/schemas.py:66-110` |
| `PATCH /projects/{id}` can change `name`, `description`, `code`; rejects `methodology` (422 `methodology_not_editable`) | `projects/service.py:221-293` |
| `PATCH /projects/{id}/parent` can reparent any project | `projects/router.py:127`, `projects/service.py:361-397` |

So the D2 guard is about **future-proofing plus `code` immutability and reparenting**, not about an existing delete path.

### 1.7 Maintenance bootstrap and invariants

- `bootstrap_sdmujer` creates/reuses `SDM > {SEG, PAN}` by `code`, seeds SEGURIDAD's 7 literal columns and points intake at SEGURIDAD — `app/maintenance/bootstrap.py:36-86`. It never commits; the runner owns the transaction.
- Idempotency primitives available: `find_project_by_code` (`maintenance/repository.py:379-390`), `ensure_board_columns` (adds missing columns and fixes drifted `order`, `status_key` verbatim — `repository.py:392-419`), `upsert_intake_default_project` (`repository.py:421-438`), `ProjectService._create_project_unit` (no commit — `projects/service.py:128-204`).
- Invariants touched — `app/maintenance/invariants.py`: **I3** freezes SDM/SEG/PAN shape (`:29-33`, `:73-98`); **I4** freezes SEGURIDAD's 7 columns with `Completada` last (`:101-125`); **I5** requires `intake_settings.default_project_id == SEGURIDAD` **and** zero projects named "Tareas Outlook" (`:128-142`) → **repointing intake to «Generales» turns I5 red**.

### 1.8 Intake default project

`IntakeService._ensure_default_project` — `app/modules/intake/service.py:706-724`: returns `settings_row.default_project_id` if set; otherwise **lazily creates** a project named `settings.INTAKE_DEFAULT_PROJECT_NAME` (= `"Tareas Outlook"`, `app/config.py:333`) with methodology `planner`. Called from automatic conversion (`:670`) and manual conversion (`:770`). Today only `bootstrap` prevents that lazy creation by pre-setting the FK to SEGURIDAD.

### 1.9 `task_number` / `task_key` — the sharpest hazard

- `task_number` allocated per project via `UPDATE projects SET task_counter = task_counter + 1 RETURNING` — `tasks/repository.py:234-252`.
- `task_key` composed as `f"{project_code}-{task_number}"` — `tasks/service.py:929-930`.
- `GET /tasks/by-key/{key}` resolves `(project_id, task_number)` with **`scalar_one_or_none()`** — `tasks/repository.py:214-232`, `tasks/service.py:184-226`. There is **no unique constraint** on `(project_id, task_number)`.

Consequence: moving a task while keeping its `task_number` can produce two active tasks with the same `(project_id, task_number)` → `MultipleResultsFound` → HTTP 500 on the destination project's key lookup. The frontend task detail panel is entirely key-driven (`widgets/task-detail-panel/task-detail-panel.component.ts:457,676`).

### 1.10 Other per-project invariants a naive move breaks silently

| Invariant | Enforced where | What a move does |
|---|---|---|
| Parent and child in the same project | validated **only on create** — `tasks/service.py:272-280` (422 `invalid_parent_task`) | orphans the relation; `list_subtasks` filters by `task.project_id` (`tasks/service.py:228-239`) so children disappear |
| Dependency edges join tasks of the same project | `task_links/service.py:88-90`; `task_links/repository.py:89-104` lists edges by `Task.project_id` | edges survive but become invisible/asymmetric per project |
| Labels are per project (`uq_labels_project_name`) | `labels/models.py:30,33`; `TaskLabel` link has no project scope (`labels/models.py:43-54`) | the moved task keeps labels owned by the source project |
| Sprints belong to a project | `_verify_sprint` — `tasks/service.py:878+`; `Task.sprint_id` FK `SET NULL` | must be cleared (already in D3) |
| Board column belongs to the project board | `tasks/service.py:567-573` | must be cleared/re-resolved (already in D3) |

### 1.11 Frontend surface

| Fact | Evidence |
|---|---|
| Task detail edits are single-field PATCHes; **errors only reach `console.error`** | `widgets/task-detail-panel/task-detail-panel.component.ts:753-765` |
| Existing selects: Status, Priority, Assignee, Sprint (conditional) | same file, template `:113-157` |
| `UpdateTaskPayload` has no `project_id`; `Task` has `project_id` read-only | `entities/workspace/workspace.model.ts:9-40,103-117` |
| `Project` model exposes no `project_kind` (and no `is_system`) | `entities/project/project.model.ts:21-35` |
| Project workspace: tabs `board\|backlog\|sprints\|timeline`, view modes `board\|grid`; **already has a per-task "Mover a…" menu** (sprint/backlog) | `widgets/project-workspace/project-workspace.component.ts:62-63,1458,2584-2611` |
| No multi-select / bulk action exists anywhere today | same file |
| `/projects` is a card list; the workspace is `/projects/:id` → `project-workspace` | `app/app.routes.ts:21-34`, `pages/projects/projects.component.ts:177` |

### 1.12 Migrations and tests

- Latest revision `0025_add_task_external_origin`; **next is `0026`**. Additive column pattern to copy: `0022_add_project_kind.py` (add with `server_default`, then drop it).
- The harness builds the schema with `Base.metadata.create_all` (comment at `tasks/models.py:60-67`), so any new constraint must be declared in `__table_args__` **and** in the migration, byte-identical, with a dedicated migration test (precedents `test_migration_task_external_origin.py`, `test_migration_project_kind.py`).
- Blast radius: `test_projects.py`, `test_project_update.py`, `test_project_kind_filter.py`, `test_migration_project_kind.py`, `test_tasks_crud.py`, `test_task_key.py`, `test_tasks_external_origin.py`, `test_task_links.py`, `test_subtasks.py`, `test_task_hierarchy.py`, `test_task_reorder.py`, `test_board_move_to_column.py`, `test_board_aware_call_sites.py`, `test_board_aware_strategy.py`, `test_bootstrap_hierarchy.py` (6 tests, incl. `:158`), `test_maintenance_invariants.py` (9 tests, incl. `:148`), `test_intake_classifier_endpoints.py:417`.

## 2. What a canonical-state mapping needs, per strategy

D3 requires `canonical_state(status)` / `status_for(canonical)` over `backlog | to_do | in_progress | in_review | done | cancelled`.

| Methodology | Columns are… | Round trip from the class alone? | Notes |
|---|---|---|---|
| planner | fixed 3, Spanish | Yes | `Sin iniciar→to_do`, `En curso→in_progress`, `Completada→done`; `backlog`/`in_review` fold |
| kanban | fixed 3, English | Yes | `Backlog→backlog`, `Doing→in_progress`, `Done→done`; `to_do`→`Backlog`, `in_review`→`Doing` |
| scrum | fixed 4 | Yes | 1:1 for 4 canonicals; `backlog` folds to `To Do` |
| custom | **`[]` from the class**; real values live in `board_columns.status_key` | **No** | Only `BoardAwareStrategy` sees them |

Two consequences:

1. **Where the mapping lives.** Because `custom` boards (SEGURIDAD today, «Generales» tomorrow) get statuses from the database, `canonical_state`/`status_for` cannot be pure class methods for all four methodologies. They must be defined on `MethodologyStrategy` and **overridden in `BoardAwareStrategy`** (`board_aware.py:31-51`). Touching only `planner/kanban/scrum/custom.py` silently does nothing for the very board this change targets.
2. **How custom names map.** Deterministic options: a normalized name dictionary (accent/case-insensitive: `pendiente|sin iniciar|to do|por hacer → to_do`, `en curso|doing|in progress → in_progress`, `completada|done|hecho → done`, `diferida|removida|cancelada → cancelled`) plus a **positional fallback** (`index 0 → to_do`, `last → done`, else `in_progress`). Positional alone maps `DIFERIDA/RECURRENTE/GESTIONADA APARTE/REMOVIDA` to `in_progress`, which is wrong for every consumer.

**Board-column binding.** `status` and `board_column_id` must stay consistent; the only write path that guarantees it is `BoardService.move_to_column` (`boards/service.py:114-116`). The move use case should resolve the destination column and reuse it with `commit=False`, as `update_task` does (`tasks/service.py:425-439`), inheriting WIP limits, `updated_by` and the single transaction. Corollary: a destination WIP limit can reject a move with 409; a column-less destination board rejects with 422 `board_has_no_columns`.

## 3. Migration, bootstrap and invariant impact

| Item | Needed? | Detail |
|---|---|---|
| New column `projects.is_system` | **Yes** | `BOOLEAN NOT NULL DEFAULT false`, migration `0026`, additive pattern of `0022` + migration test |
| Reuse `project_kind` instead | **No** | It encodes topology, is a public API filter value (`projects/router.py:40`) and is frozen for SDM/SEG/PAN by I3 (`invariants.py:29-33`) |
| At most one system project per org | Recommended | partial unique index `ON projects (organization_id) WHERE is_system AND is_active` |
| Bootstrap «Generales» | Yes | 4th entry resolved by `code='GENERALES'` via `find_project_by_code` + `_create_project_unit` + `ensure_board_columns`; idempotent by construction |
| Intake default → Generales | Yes (D2) | `upsert_intake_default_project(org, generales.id)` |
| Invariant I5 | **Must be modified** | today asserts `== SEG`; becomes `== GENERALES`, keeping the "no Tareas Outlook" clause |
| New invariant (I9) | Recommended | «Generales» exists per org, `is_system`, `code='GENERALES'`, active, 7 columns, done column last |
| `INTAKE_DEFAULT_PROJECT_NAME` | Review | leaving `"Tareas Outlook"` (`config.py:333`) keeps a lazy-creation path alive for any org with NULL `default_project_id` (`intake/service.py:715-720`) |
| `task_number` on move | Decide (Q3) | no schema change if reallocated with the existing `allocate_task_number` |

## 4. Approaches compared

### 4.1 Protecting «Generales»

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| A. Service guard only (`is_system` + checks in `ProjectService`) | matches existing idiom (`methodology_not_editable`, `projects/service.py:246-252`); clear Spanish codes | bypassable by direct SQL, by `maintenance` purge (`repository.py:336-341`) and by any future service | Low |
| B. DB constraints only | unbypassable by app code | a CHECK cannot stop `DELETE` → needs a trigger (no triggers exist in this repo); poor messages | Medium |
| C. Reuse `project_kind` with a `sistema` member | no new column | conflates topology with governance; changes a public enum + frontend; forces touching I3 and `test_project_kind_filter.py` | Low but wrong |
| **D. A + CHECK for the statically expressible part (recommended)** | guards give good 409/422 messages; CHECK `NOT is_system OR (code='GENERALES' AND is_active AND status='active')` makes soft delete, archiving and code renaming impossible at DB level (all three are UPDATEs); partial unique index caps one per org | hard `DELETE` still needs purge-side allowlist; constraint declared twice (model + migration) per repo convention | Medium |

**Recommendation: D.** The three operations D2 forbids are all `UPDATE`s in this codebase, so one CHECK covers them without a trigger.

### 4.2 Status handling in `POST /tasks/{id}/move`

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| 1. Explicit `status` only | trivial; reuses `_resolve_column_for_status` | caller must know destination statuses; unusable for bulk/importer; pushes methodology knowledge to the UI (violates CLAUDE.md's strategy rule) | Low |
| **2. Canonical state on the strategy layer (recommended)** — base + `BoardAwareStrategy` override, normalized-name dictionary + positional fallback, `status` optional override | satisfies D3; no migration; works for `custom` boards; reusable by change 51's importer and change 37's mapping heuristic | dictionary is heuristic for arbitrary names; needs tested fallback + 422 when nothing maps | Medium |
| 3. Persist `board_columns.canonical_state` | exact, user-correctable, kills the positional fragility, also serves 44's `excluded_from_progress` | migration + backfill + boards API/UI + spec deltas; collides with change 37; over the 800-line budget | High |
| 4. Positional only | zero new data | maps DIFERIDA/RECURRENTE/GESTIONADA APARTE/REMOVIDA to `in_progress` | Low but wrong |

**Recommendation: 2**, payload `{ project_id, status? }` where an explicit `status` wins and is validated against the destination board; return the canonical state so the UI can preview "PENDIENTE → Sin iniciar". Option 3 is the natural follow-up; change 37 should consume the same helper.

### 4.3 Move scope (not covered by D3 — proposer must decide)

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| Strict: reject when the task has subtasks, active edges or labels | never leaves broken data; smallest test surface | rejects the realistic case (imported tasks carry labels) | Low |
| **Cascade (recommended)**: move the subtree atomically, soft-delete cross-project edges, drop labels absent in the destination, report all of it in the response + `task_history` | matches user intent; auditable | bigger transaction; more tests; needs a response contract | Medium |
| Naive: swap `project_id` only | smallest diff | the five silent breakages of §1.10; possible 500 on `by-key` | Low but unsafe |

## 5. Affected areas (implementation map)

**Backend**: `projects/models.py` (`is_system` + CHECK + partial unique index), `projects/schemas.py` (expose in `ProjectRead` only), `projects/service.py` (guards in `update_project`/`reparent`), `alembic/versions/0026_*` + migration test, `methodology/{base,planner,kanban,scrum,custom,board_aware}.py` (canonical helpers — the `BoardAwareStrategy` override is load-bearing), `tasks/schemas.py` (`TaskMove`), `tasks/service.py` (new `move_task_project` + history diff incl. `project_id`), `tasks/router.py` (`POST /tasks/{id}/move` + role decision — today every task endpoint accepts `viewer`: `tasks/router.py:135,215,232`), `maintenance/{bootstrap,repository,invariants}.py`, `intake/service.py` + `config.py`.

**Frontend**: `entities/workspace/workspace.model.ts` (`MoveTaskPayload`), `entities/workspace/workspace.service.ts` + `entities/task/task-detail.service.ts`, `entities/project/project.model.ts` (`is_system`), `widgets/task-detail-panel/task-detail-panel.component.ts` (project selector + error surfacing), `widgets/project-workspace/project-workspace.component.ts` (bulk "Mover a…", extending the menu at `:2584-2611`).

## 6. UX notes (ux-psicologia)

1. Never free text for a known set: project selector lists the org's active projects, current one preselected; searchable with likely ones first (Hick). «Generales» is just another entry.
2. Show the translation before committing: destination status preselected with the canonical translation ("PENDIENTE → Sin iniciar"), editable, never blank.
3. Name what is lost: state that sprint and board column are cleared, and (if Q3 = reallocate) that the task key changes from `SEG-12` to `GEN-4`.
4. Errors must be specific: `updateField` swallows failures into `console.error` (`task-detail-panel.component.ts:763`). The move can fail with 409 `task_external_anchor_conflict`, 409 `wip_limit_exceeded`, 422 `invalid_status`, 422 `board_has_no_columns` — each backend message MUST reach the user.
5. Five states for the bulk action; the selection must survive a failed attempt.
6. All user-visible text in Colombian formal Spanish (tuteo).

## 7. Risks

1. Silent data breakage — dependency edges, labels, parent/child links and the external anchor are per project and none is re-validated on update today (§1.10).
2. HTTP 500 on `GET /tasks/by-key` if `task_number` is preserved and collides (`scalar_one_or_none`, `tasks/repository.py:214-232`).
3. Ordering conflict on the «Generales» board — D2 puts COMPLETADA third, but every "done" consumer reads `allowed_statuses()[-1]` (§1.4).
4. Maintenance invariants turn red — I5 (`invariants.py:128-142`), `test_maintenance_invariants.py:148`, `test_bootstrap_hierarchy.py:158` must change in the same PR.
5. Duplication with change 37 — `methodology-migration` already specifies a default mapping "heurística por nombre/orden" (`openspec/changes/37-cambio-metodologia/specs/methodology-migration/spec.md:32-33`).
6. Downstream dependency — change 51 (superseding 44) routes unresolved rows to «Generales», so it cannot be applied before this change.
7. Review budget — backend + frontend will exceed 800 lines; with `auto-chain`, plan two slices: (1) `is_system` + bootstrap + invariants, (2) canonical state + move endpoint + UI.
8. Permissions inconsistency — task endpoints accept `viewer` today (`tasks/router.py:135,215,232`) while project hierarchy writes require a role (`projects/router.py:96`).

## 8. Open questions for the proposer

| # | Question | Recommended default |
|---|---|---|
| Q1 | «Generales» board order: checklist reading order vs. "done = last column" | Persist COMPLETADA last (`PENDIENTE, EN CURSO, DIFERIDA, RECURRENTE, GESTIONADA APARTE, REMOVIDA, COMPLETADA`); checklist order is presentation only. **Owner confirmation required** |
| Q2 | Does the intake default flip to «Generales» for the existing SDMUJER org or only for new orgs? | Flip for all; update I5, keep its "no Tareas Outlook" clause |
| Q3 | Reallocate `task_number` on move (key changes) or preserve it (collision → 500)? | Reallocate from the destination counter; record old/new in `task_history` |
| Q4 | Move scope: strict rejection vs cascade? | Cascade (§4.3), fully reported in the response |
| Q5 | Bulk move: all-or-nothing vs per-row outcomes (WIP limits)? | Per-row outcomes with a summary; never lose the selection |
| Q6 | Role for `POST /tasks/{id}/move` | `admin \| manager \| member` (exclude `viewer`); flag the pre-existing gap as out of scope |
| Q7 | Is «Generales» a root project or a child of `SDM`? | Root (keeps I3 untouched, avoids roll-up pollution) |

## 9. Ready for proposal

**Yes**, with Q1 and Q2 answered by the owner before `sdd-propose` fixes the scope — both change persisted behaviour of an already-bootstrapped database. Everything else has a defended default in §8.

---

*Engram mirror: topic `sdd/50-proyecto-generales-y-mover-tarea/explore` (observation 4534).*
