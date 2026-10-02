# Exploration: 51-importar-tareas-multiformato

> Supersedes candidate: `44-importar-checklist-xlsx` (proposal/spec/design/tasks done, `apply: pending`, **zero code on disk**).
> Source plan: `docs/plans/2026-09-05-importacion-tareas-y-conciliacion-correo.md` §2.

## Verdict first

**Narrow supersede.** Change 51 should supersede only the `checklist-import` capability (renamed `task-import`) plus the two `tasks` requirements it actually consumes (`completed_at_override`, origin badge). The other three capabilities 44 touched (`boards.excluded_from_progress`, the `project-hierarchy` roll-up denominator, the `dashboard-executive` context exclusion) are NOT import concerns and should be re-proposed as a separate small change — otherwise the roll-up debt that `openspec/specs/data-maintenance/spec.md:142` explicitly assigned to "el cambio 44" dies with 44.

Two blocking preconditions, both orchestrator/user decisions rather than research gaps:
1. **Change 50 does not exist.** There is no `openspec/changes/50-*` directory. The plan's slice 1 (project «Generales» + `POST /tasks/{id}/move` + `canonical_state`/`status_for` on every strategy) is unwritten, and 51's default project resolution, its lossless 7-column board and its status translation all depend on it.
2. **Scope of the supersede** (Q1 below): does 51 carry the consolidation subsystem (`merge_into` / `subtask_of` / `context_group` / `skip`) or leave it CLI-only?

## 1. Current state (verified on disk)

| Area | Reality |
|---|---|
| Change 44 | 40 requirements / 108 scenarios across 5 capabilities (`44/state.yaml:19-80`). `apply: pending`. Nothing implemented. |
| Change 43 | Archived and applied. `create_task(..., external_origin=(source, key))` (`tasks/service.py:241-338`), `TaskRepository.get_by_external_key` (`tasks/repository.py:191-210`), `KNOWN_TASK_SOURCES` incl. `checklist_xlsx` (`tasks/sources.py:11-22`), partial unique index per project + service-side org-wide uniqueness. |
| `Task.status` | **Free-form `String(60)`** (`tasks/models.py:124`), validated against the project's persisted board `status_key` via `BoardAwareStrategy.allowed_statuses()` (`methodology/board_aware.py:39-51`). **No canonical status enum exists.** |
| Methodology strategies | `default_columns()`, `allowed_statuses()`, `sprints_enabled`, `estimation_mode`, `has_backlog` only (`methodology/base.py:17-38`). **No `canonical_state`/`status_for`** anywhere in `backend/`. |
| «Generales» | Does not exist. `maintenance/bootstrap.py:18-22` seeds `SDM (area/planner) > SEG (proyecto/custom) + PAN (proyecto/kanban)`; SEGURIDAD gets 7 literal columns (`:25-33`), PANDORA gets kanban defaults. `upsert_intake_default_project(...)` points intake at **SEGURIDAD** (`:83`), and `INTAKE_DEFAULT_PROJECT_NAME = "Tareas Outlook"` (`config.py:333`) is only the lazy-creation fallback name. No `is_system`/`is_default` flag on `Project`. |
| Alembic head on disk | `0025_add_task_external_origin.py`. `0026`/`0027` claimed by 44, `0028` claimed by 45a with `down_revision="0027"`. |
| Reusable file parsing | `integrations/adapters/jira/file_parser.py` — `parse_csv` (`utf-8-sig`, BOM tolerated), `parse_xlsx` (`read_only=True, data_only=True`), `_guard_limits` inside the row loop, `parse_file` dispatch by extension, every `openpyxl` exception converted to a typed error. `openpyxl==3.1.5` in requirements. |
| Reusable HTTP import flow | `modules/jira_import/` — `POST .../import-file` with `UploadFile`, byte ceiling rejected **before** parsing (413, `router.py:59-63`), `require_role(admin, manager)` module-level singleton, `{data, meta}` envelope. Read-only preview: it never persists tasks. |
| Run ledger precedent | `IntakeRun` (`modules/intake/models.py:124-150`): `PkMixin + TimestampMixin + AuditMixin + TenantMixin`, **no** `SoftDeleteMixin` ("an audit log row is queried, never un-deleted"), counters + status enum + `started_at`/`finished_at`. Exactly the shape `task_import_runs` needs. |
| Frontend | No `/tasks/import` route (`app/app.routes.ts`). `@solercia/ui@0.5.0` exposes `SolFileUpload`, `SolWizard`+`SolWizardStepDirective`, `SolStepper`, `SolDataTable`, `SolEmptyState`, `SolSkeleton`, `SolProgressBar`, `SolChip(Group)`, `SolBadge`. `shared/ui/index.ts` is a pure re-export barrel — no app-local components allowed there. |
| Artifact language | **Every OpenSpec artifact in this repo is Spanish**, and `openspec/config.yaml:17-19` mandates `Dado/Cuando/Entonces` and RFC-2119 in Spanish (`DEBE/DEBERÍA/PUEDE`). `rules.apply.tdd: true` (strict TDD). The proposer MUST write `proposal.md` and `specs/` in Spanish. |

## 2. Change 44 delta map (what carries, what is superseded, what is new)

### 2.1 `checklist-import` (29 ADDED requirements) → becomes `task-import`

**Carry over unchanged (9)**

| 44 requirement | Why it survives |
|---|---|
| Guardas antibomba en la lectura del libro | Same threat; extend the same `_guard_limits` shape to CSV and JSON |
| Aceptación de celdas de fecha en `datetime` o texto | `data_only=True` still returns mixed types per column |
| Ningún conteo de filas fijado en el analizador | The sheet is a living document (135 → 139 rows already) |
| Mapeo de `Fecha Límite` a `due_date` o texto libre en la descripción | Plan §2.3 keeps it verbatim, including the `**Fecha límite (texto):**` line |
| Composición de la descripción (block order + 4000-char fail-by-row, never truncate) | Plan §2.3 cites it as "regla del 44" |
| Etiqueta `recurrente` por regla explícita | Plan does not touch it; the two sets still do not coincide |
| Etiquetas `area:` y `apoyo-ia:` | `area:` now derives from the canonical `category` field |
| `ensure_label` idempotente por proyecto (+ D-LBL-IO: search without `is_active` filter and reactivate before creating) | `uq_labels_project_name` is still a total unique constraint |
| El archivo real nunca es fixture de pruebas | Institutional data must stay out of git |
| Transacción única propiedad del caso de uso | Still the core guarantee; now also under an HTTP request (see §3.4) |

**Superseded — same intent, different contract (7)**

| 44 requirement | 51 replacement |
|---|---|
| Hoja y encabezados obligatorios **en orden exacto**, sin alias | Alias table + Unicode normalization, order-independent; XLSX sheet = «Checklist Tareas» if present, else the first sheet whose row 1 resolves all mandatory fields |
| Mapeo de `Estado` a columna del tablero (SEGURIDAD/PANDORA hardcoded) | Canonical-state translation via the destination project's strategy; also accepts the canonical literals `backlog/to_do/in_progress/in_review/done/cancelled` |
| Mapeo de `Urgencia` a prioridad | Same 4 names, but `-`/empty → **`medium`** (44 said `low`). Plan §2.3 justifies it: `-` only appears on REMOVIDAS |
| Ruteo a SEGURIDAD o PANDORA | 3-step deterministic resolution: explicit `project` column → `routing.yaml` rules → «Generales» |
| Idempotencia por ancla `('checklist_xlsx', ID)` | `source='checklist'`, format-independent |
| `--update-existing` con lista blanca (`status, priority, due_date, completed_at`, etiquetas) | Same whitelist **plus `notes`**; `title`, `description` and `project` still untouchable |
| Reporte final con conteos y advertencias | Same counters, now also grouped by project and by status, downloadable as JSON, and persisted in `task_import_runs` |
| Contrato de la CLI `import_checklist.py` | Survives as a **wrapper over the shared use case**, not as the only surface |

**Consolidation block — scope decision required (6 requirements, 44's `Formato del CSV`, `Valores por defecto verificados`, `Validación del CSV`, `--execute exige --csv-in`, `Fila fusionada creada`, `Enlace de subtareas en dos pasadas`)**

Plan §2.6 keeps the CLI "útil para la corrida inicial de 139 filas con el CSV de decisiones", which implies the consolidation vocabulary survives — but only on the CLI path. See Q1.

**Dropped / replaced by a different mechanism (2)**

| 44 requirement | Why |
|---|---|
| Usuarios sin acceso creados como `viewer` sin contraseña (`--member "Nombre=correo"`) | Plan §2.3: `assignee` by email → existing org user (error if absent); by name → exact match only; unresolved → **warning**, importer stays as assignee. No user creation. |
| `admin@solercia.com` como responsable por defecto | Replaced by "quien importa" |

**New in 51 (not in 44 at all)**

- Alias table + header normalization (NFKD accent folding, casefold, whitespace/hyphen/underscore collapse), one canonical field per file, duplicates = structure error, unknown columns = warning.
- Three input formats: XLSX, CSV (delimiter auto-detected among `;`, `,`, `\t`, `|` by "most mandatory columns resolved in row 1"), JSON (array or `{"tasks": [...]}`).
- Mandatory fields reduced to two: `external_key`, `title`. Everything else optional with defaults.
- `Vencido` explicitly ignored as a derived field.
- Two-phase execution: `validate_only` returns a per-row report (`error|warning` + code + message + planned action `create | update(fields) | no change`) with **zero writes**, then all-or-nothing import.
- `task_import_runs` table with the file SHA-256 (traceability + "this file was already imported").
- `POST /api/v1/tasks/import` (multipart or JSON), role admin/manager.
- UI page `/tasks/import` with three steps.
- Duplicate `external_key` inside the same file = error on **both** rows (44 had no such requirement).
- `source='checklist'` registered in `KNOWN_TASK_SOURCES`, `checklist_xlsx` retired.

### 2.2 The other four capabilities 44 touched

| Capability | 44 delta | Recommendation for 51 |
|---|---|---|
| `tasks` (4 ADDED) | `context_group` + `merge_into_task_id` columns; read-only exposure; `completed_at_override`; origin badge | Carry **`completed_at_override`** (required to honor «CERRADA el YYYY-MM-DD») and the **origin badge** (imported rows must be recognizable). Carry the two columns **only if** Q1 answers "consolidation stays". |
| `boards` (4 ADDED) | `excluded_from_progress` flag; PANDORA 7-column seeding; PANDORA order invariant; flags on `Removida`/`Gestionada aparte` | **Do not supersede.** PANDORA seeding is obsolete once the default target is «Generales» (change 50 seeds those 7 columns). The flag itself is a genuine roll-up concern, independent of imports. |
| `project-hierarchy` (1 MODIFIED) | Roll-up denominator by column flag instead of the dead `status != 'cancelled'` literal | **Do not supersede.** Re-propose separately; it pays the debt recorded at `openspec/specs/data-maintenance/spec.md:142`. |
| `dashboard-executive` (2 MODIFIED) | `by_assignee`/`workload`/`totals.tasks` exclude `context_group`; `at_risk` does not | Only meaningful if `context_group` exists. Follow Q1. |

**Artifact hygiene**: `data-maintenance/spec.md:142` names "el cambio 44" as the owner of the denominator debt. If 44 is archived as superseded without that work, the new owner must be named in the same wave or the reference dangles.

## 3. Code seams

### 3.1 File parsing
Reuse the shape of `integrations/adapters/jira/file_parser.py`, not the module itself (its `_REQUIRED_COLUMNS = ("Issue key",)` and `_MULTIVALUE_COLUMNS` are Jira vocabulary, and its guard reads `settings.JIRA_FILE_MAX_*` — coupling this importer's ceiling to a connector's tuning is exactly what 44's D-CFG rejected). New settings: `TASK_IMPORT_MAX_ROWS`, `TASK_IMPORT_MAX_CELLS`, `TASK_IMPORT_MAX_BYTES` (byte ceiling rejected at the router before parsing, 413, per `jira_import/router.py:59-63`).

### 3.2 Header normalization + alias table
Pure function, no I/O: `unicodedata.normalize("NFKD", s)` → strip combining marks → `casefold()` → collapse `\s`, `-`, `_` to a single space → strip. Then look up a frozen alias→canonical map.
**Placement recommendation**: the alias table lives in **code** (`headers.py`, frozen dict) because it is a contract, not tenant configuration; `routing.yaml` holds only the routing rules, which are tenant policy. Note: there are currently **zero `.yaml` files under `backend/app/`** — a versioned config file would be a new precedent, so its path must be declared in `config.py` rather than hardcoded.

### 3.3 Routing rules
`routing.yaml` versioned in the repo, path from settings. Order: explicit `project` column (matched against `Project.code` or `Project.name`, accent- and case-insensitive, active projects of the org only; no match = **error**, projects are never invented) → rules → «Generales».

### 3.4 Transaction boundary — the hardest seam
`TaskRepository.create` and `.save` **commit** (`tasks/repository.py:254-267`). That violates the persistence rule ("repositories never commit") and makes all-or-nothing impossible with the request-scoped session (`database.py:36-40` yields a plain `AsyncSessionLocal()`).

Three options:
1. **Savepoint frontier (44's D-TX, recommended)** — the service opens its own `engine.connect()`, begins an outer transaction and builds `AsyncSession(bind=conn, join_transaction_mode="create_savepoint")`. Every internal `commit()` then only releases and reopens a SAVEPOINT; the outer transaction closes at exactly one point. Proven pattern in `tests/conftest.py:88-110`. Under FastAPI the endpoint must **ignore the injected `db`** and dispose of its own connection on every path.
2. Remove the commits from `TaskRepository` — correct, but transversal to the whole `tasks` module and out of scope.
3. Compensate after partial commits — rejected: the requirement is rollback, not compensation.

### 3.5 Two-phase validation report model
Frozen dataclasses at each boundary (44's D-INTENT): `SourceRow` (verbatim) → `RowIntent` (pure, no DB) → `PlannedWrite` (`create|update|no_change`). Pydantic response schemas mirror them. `RowIntent.due_date`/`completed_at` must be **tz-aware UTC** (44's H19): openpyxl returns naive datetimes and the CSV text carries no zone; a naive value raises `TypeError` against `datetime.now(UTC)` in `dashboard/service.py`.

### 3.6 `task_import_runs` persistence
Mirror `IntakeRun` (`intake/models.py:124-150`): `PkMixin + TimestampMixin + AuditMixin + TenantMixin`, **no** `SoftDeleteMixin`. Columns: `filename`, `file_format`, `file_sha256` (indexed), `mode` (`validate|import`), counters (`rows`, `created`, `updated`, `unchanged`, `warnings`, `errors`), `status`, `report` (JSON), `started_at`, `finished_at`. Migration takes `0026` (head on disk is `0025`).

### 3.7 Endpoint placement and role guard
Recommend `backend/app/modules/task_import/` (module convention: it owns a router, a table and a repository — 44's `app/importers/checklist/` had no HTTP surface). Register in `main.py` after `tasks_router`. Guard: `require_role(MemberRole.admin, MemberRole.manager)` as a module-level singleton (ruff B008; precedent `jira_import/router.py:27`).
Routing note: literal segments must be declared before parametrized ones within the same method — `tasks/router.py` already does this (`/tasks/reorder` and `/tasks/by-key/{key}` precede `/tasks/{task_id}`). `POST /tasks/import` does not collide with any existing route (no `POST /tasks/{id}` exists), but keep the discipline.

### 3.8 Frontend
Route `/tasks/import` guarded by `authGuard`, lazy-loaded page. Compose `sol-wizard` (3 steps, progress bar, `canAdvance` predicate, back-navigation) + `sol-file-upload` + `sol-data-table` + `sol-chip-group` (level filter) + `sol-skeleton` + `sol-empty-state`. No app-local components in `shared/ui/` — that barrel is a pure re-export.

## 4. Status mapping: «Generales» vs other projects

| Destination | Mapping | Loss |
|---|---|---|
| «Generales» (custom, 7 columns = the checklist's 7 states verbatim) | **Identity.** `PENDIENTE → PENDIENTE`, etc. | **None.** This is exactly why the plan makes it the default target. |
| SEGURIDAD (custom, 7 columns) | Near-identity: only `PENDIENTE → Sin iniciar` and `COMPLETADA → Completada` differ | None, but requires a rename table or a canonical hop |
| PANDORA (kanban, 3 columns: Backlog/Doing/Done) | `DIFERIDA`, `RECURRENTE`, `GESTIONADA APARTE`, `REMOVIDA` have **no home** | **Lossy.** 44 solved it by growing PANDORA to 7 columns; 51 must not do that. |
| Any other project | Unknown until runtime — `allowed_statuses()` comes from the persisted board | Unknown |

**Assessment.** Without change 50's `canonical_state`/`status_for`, 51 has no non-lossy way to import into a project whose board does not literally contain the source state. Two acceptable v1 rules, in order of preference:

1. **Depend on change 50** (recommended, matches the plan's slice order). Every strategy exposes `canonical_state(status)` and `status_for(canonical)`; the importer translates through the canonical hop; «Generales» round-trips to identity by construction.
2. **Fail loud without 50**: resolve the destination `status_key` by normalized comparison against the destination board's `allowed_statuses()`; if there is no match, emit a **row error** naming the ID, the state and the destination project. Never collapse a state into a neighbour, and never silently drop it. This keeps 51 shippable if 50 slips, at the cost of making non-Generales targets unusable for the four extra states.

Either way: `COMPLETADA` sets `completed_at` (import date if the file gives none), which needs `completed_at_override` from 44's `tasks` delta.

## 5. Approach comparisons

### 5.1 Overall scope of the supersede

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. Full supersede** — 51 absorbs all 5 of 44's capabilities plus the new contract, endpoint and UI | One archive cycle; the roll-up debt gets paid; nothing orphaned | 44 alone forecast 2300-2700 lines / 7 chained PRs; adding 3 parsers, the alias layer, the run table, the endpoint and the UI page pushes it past 4000; couples an import change to the dashboard and to progress roll-up | High |
| **B. Narrow supersede (recommended)** — supersede `checklist-import` only, take `completed_at_override` + origin badge from `tasks`, leave `boards`/`project-hierarchy`/`dashboard-executive` to a separate change | Reviewable slices; the import contract is testable without touching the dashboard; no `context_group` migration in v1; the roll-up debt keeps a named owner | Two changes instead of one; `data-maintenance/spec.md:142` must be re-pointed | Medium |
| **C. Supersede + drop consolidation entirely** — flat import into «Generales», merges/subtasks done by hand afterwards | Smallest change; no `merge_into_task_id`/`context_group` at all | Throws away 44's verified consolidation verdicts (7 confirmed, 5 corrected, 2 rejected against the real file); 139 rows reconciled by hand | Low |

**Recommendation: B**, keeping the consolidation CSV as a CLI-only path.

### 5.2 Updates on re-import

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **Whitelist upsert** (44's D-UPD + `notes`) | Preserves manual edits (title, description, project, assignee); matches plan D5 "Command is the source of truth after import"; already specified and reasoned | Divergence in non-whitelisted fields is invisible; the file overrides an in-app completion (44's H21 warning) | Low |
| **Full replace** | File and system always identical | Destroys in-app work; contradicts D5; the checklist stops being edited after run 1, so there is nothing to replace from | Low but wrong |
| **Whitelist + validate-phase diff (recommended)** | Everything above, plus the per-row plan (`create / update(fields) / no change`) makes divergence visible **before** writing; the no-op comparison (44's H17) keeps idempotency real instead of producing 139 phantom audit mutations | One extra diff pass in the validate phase | Low |

**Recommendation:** whitelist upsert with the validate-phase diff the plan already asks for in §2.5.1. `update_existing` defaults to **false** on the API, and the UI must render it as an explicit labeled switch stating its consequence with a real number ("el archivo mandará sobre el estado de N tareas ya importadas"), N computed by the validate phase.

### 5.3 Unknown columns

| Approach | Pros | Cons |
|---|---|---|
| **Warning (recommended, plan §2.2)** | The source is a living document (`Vencido` is already ignored by design); a new column must never break the daily import; the report lists them so nothing is silent | A header typo surfaces as "unknown column" rather than "missing field" — mitigated because the two mandatory fields produce a hard structure error when absent |
| **Error** | Catches typos loudly | Any added column blocks the import; contradicts ignoring `Vencido`; forces a code change for a spreadsheet change |

**Recommendation:** warning, with three hard structure errors kept: (1) a mandatory field (`external_key`, `title`) unresolved; (2) two columns resolving to the same canonical field; (3) **zero** headers resolving to any canonical field → report "this does not look like a task file" instead of eleven unknown-column warnings.

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **Change 50 does not exist** (`openspec/changes/` holds cycle2, 33-41, 44, 45a, 47 only). No «Generales», no `is_system`, no `canonical_state`/`status_for` anywhere in `backend/`. | High | Hard dependency: create and archive 50 first, or adopt the fail-loud fallback in §4 |
| R2 | **Alembic chain break.** Head on disk is `0025`; 44 claims `0026`+`0027`; 45a claims `0028` with `down_revision="0027"`. If 44 never applies, 45a's parent never exists and `alembic upgrade head` fails with "Can't locate revision '0027'". | High | 51 takes `0026`; 45a must be re-anchored in the same wave. 45a's own Phase-0 gate already re-reads `alembic heads` live, so this is coordination, not a defect |
| R3 | **`TaskRepository.create`/`save` commit** (`repository.py:254-267`), breaking all-or-nothing under the request-scoped session | High | Savepoint frontier (§3.4) + an integration test proving a failure at row N leaves zero rows |
| R4 | **Two-phase drift**: the user validates file A and imports file B | High | The validate response returns the SHA-256; the import request must echo it and fail with a typed error on mismatch. Also yields "this file was already imported" from `task_import_runs` for free |
| R5 | **Duplicate `external_key` inside the file** — 44 has no requirement for it; the DB anchor would only catch it mid-write | Medium | Detect in the validate phase, error on **both** rows, before any write |
| R6 | **Timezone** — openpyxl returns naive datetimes; CSV text carries no zone; a naive value raises `TypeError` against `datetime.now(UTC)` in `dashboard/service.py` | Medium | Normalize in one place: civil date declared → start of day **UTC**. Never invent an `America/Bogota` conversion the source never expressed |
| R7 | **Excel serial dates** — `data_only=True` returns `datetime`/`date` for date-formatted cells, a raw `int`/`float` serial for number-formatted ones, and `str` when typed as text. The XLSX is regenerated from the CSV, so most cells are text today | Medium | Accept `datetime`, `date` and `str`; **reject a bare number** with a typed row error naming the ID — never guess the epoch (1900 vs 1904 workbook bases differ) |
| R8 | **Partial failure of a 139-row run** — one bad row aborts everything | Medium | Acceptable because `validate_only` surfaces every error at once; the UI must show all errors, not just the first |
| R9 | **`SolFileUpload` is image-shaped**: `isAcceptedType` does **exact MIME string matching** (no extension support), it always `readAsDataURL`s the file to build a preview, and its size error literally reads "La imagen pesa X MB". A `.csv` frequently arrives with `file.type === ''` or `application/vnd.ms-excel` | Medium | Either use `accept=""` (the component then accepts everything) and validate the extension in the page component, or extend `@solercia/ui` upstream. Do **not** ship a strict MIME allowlist — it will reject valid CSVs |
| R10 | **`source` vocabulary migration**: `checklist_xlsx` is registered in `tasks/sources.py:13`, described in `tasks/router.py:61`, asserted in `tests/test_migration_task_external_origin.py:252,256` and `tests/test_tasks_external_origin.py:466-517`, and appears as an illustrative literal in published scenarios (`openspec/specs/tasks/spec.md:297,420`) | Medium | Data is safe (no task was ever imported). Recommend adding `checklist` and removing `checklist_xlsx` in the same change, updating the three code/test references and emitting a `MODIFIED` delta for the two `tasks` scenarios that quote the literal |
| R11 | **Institutional data leak** — names, emails and `Observaciones` from a public entity must never enter git (44's D-USERS and its `--member` rule) | High | Synthetic fixtures only, generated in `tmp_path`; real emails live in the operational runbook, outside the repository |
| R12 | **`assignee` by name has no lookup table** — the `contacts` table is slice 4 of the plan | Low | v1 resolves by email only; a name yields a warning and the importing user stays as assignee. Never fuzzy-match |
| R13 | **Review budget** — parsers ×3 + alias layer + routing + two-phase service + run table + migration + endpoint + UI page will exceed 400 lines by a wide margin | Medium | `auto-chain` is already the cached delivery strategy; expect 5-7 chained slices. `sdd-tasks` emits the formal forecast |
| R14 | **Artifact language** — the orchestrator asked for English, but every OpenSpec artifact in this repo is Spanish and `openspec/config.yaml:17-19` mandates `Dado/Cuando/Entonces` + `DEBE/DEBERÍA/PUEDE` | Low | `proposal.md` and `specs/` must be Spanish to match the project convention and the config rules |

## 7. Open questions for the proposer

1. **Q1 (scope-defining)** — Does 51 carry the consolidation subsystem (`merge_into` / `subtask_of` / `context_group` / `skip`, plus `tasks.context_group`, `tasks.merge_into_task_id`, `boards.excluded_from_progress`, the roll-up delta and the dashboard delta), or does it supersede only parser/mapper/importer and keep consolidation on the CLI path? This decides 1 capability vs 5, and 1 migration vs 2-3.
2. **Q2** — Where does `routing.yaml` live and who may edit it: versioned file (deterministic, reviewable, needs a deploy) or a per-organization table (editable, new module)? There is no precedent for YAML under `backend/app/`. Recommendation: versioned file for v1, path declared in `config.py`.
3. **Q3** — Module placement: `backend/app/modules/task_import/` (recommended: it owns a router and a table) vs 44's `backend/app/importers/checklist/` (D9, no HTTP surface).
4. **Q4** — Confirm the assignee rule replaces 44's `--member` user creation and the `admin@solercia.com` default (§2.1, R12).
5. **Q5** — `plan_links`: keep it out of v1 (45a has no code and an unknown activity is a hard error) and retain `pspi:x.y` labels as the interim carrier, per 44's D-PSPI? The plan puts plan links in slice 3.
6. **Q6** — Endpoint shape: one `POST /tasks/import` with `validate_only` as a query param (plan §2.6), or two endpoints (`.../validate` + `.../import`)? Two read better in Swagger and make the SHA-256 echo explicit.
7. **Q7** — Who inherits the roll-up denominator debt recorded at `openspec/specs/data-maintenance/spec.md:142` once 44 is archived as superseded?

## 8. UX notes for `/tasks/import` (ux-psicologia checklist applied)

- **Nothing starts empty (goal gradient + smart defaults)**: step 2 opens with the counts already computed and every row pre-assigned a destination project («Generales» when no rule matches) — never a blank table waiting for input. The wizard reads "paso 2 de 3", never "0 %".
- **Recognition over recall**: one row per source row showing `ID · título · proyecto destino · estado destino · acción (crear / actualizar / sin cambios) · nivel`. Level filter as chips, with "errores" pre-selected whenever there is at least one error.
- **The five states, all of them**: loading (`sol-skeleton` over the table, not a spinner), legitimate empty ("el archivo no tiene filas de datos"), no results for the active filter (distinct from empty, offers to clear it), error (the backend's typed message verbatim — never a generic one), success (counts + a link to the destination project). "0 filas" must never render the same as "la validación falló".
- **Loss aversion, honestly**: `update_existing` states what it will overwrite with a real number from the validate phase, not a generic warning.
- **Hick**: step 2 offers exactly two actions (Importar / Cancelar) plus the level filter. No per-row editing in v1 — decisions belong to the CLI's CSV.
- **Never disable without explaining**: with errors present, "Importar" is disabled **and** the reason sits beside it ("hay N filas con error; corrígelas en el archivo y vuelve a subirlo"). `sol-wizard`'s `canAdvance` predicate is the right hook.
- **Peak-end**: the confirmation screen names what was created and links straight to it.
- **Accessibility**: visible focus, real labels, keyboard-navigable table, `aria-label` on icon buttons, `prefers-reduced-motion` respected.
- All user-facing copy in formal Colombian Spanish with tuteo (`selecciona`, `verifica`, `puedes`), never voseo.

## 9. Ready for proposal

**Yes, conditionally.** The codebase research is complete and no blocking unknowns remain in the code. Before `sdd-propose` runs, the orchestrator needs decisions on **Q1** (supersede scope) and on the **change-50 dependency** (create it first, or adopt the fail-loud status fallback in §4). Everything else is a recommendation the proposer can adopt as written.

---

*Engram mirror: topic `sdd/51-importar-tareas-multiformato/explore` (observation 4532). This file was materialized by the orchestrator from that observation to restore hybrid parity.*
