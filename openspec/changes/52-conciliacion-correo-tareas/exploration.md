## Exploration: 52-conciliacion-correo-tareas (deterministic mail↔task reconciliation)

Artifact language: English (SDD contract). User-facing UI strings produced by this change MUST be Colombian formal Spanish (tuteo), per project rules.

### Executive summary

The reconciliation rules E1–E4 / P1–P6 are implementable and genuinely deterministic, but **none of the signals they depend on reach the database today**. Solercia Connect already emits `conversation_id`, `internet_message_id`, `folder`, `cc`, `has_attachments` and `attachments`; Command's adapter mapper drops all of them. Slice 0 of this change is therefore a widening of the mail DTO and `raw_payload`, plus a backfill — not a rules engine. The rules engine itself belongs in a new `app/modules/reconciliation/` module with a pure rule evaluator mirroring `intake/classifier.py`, and it must not write the task anchor, must write status only through change 50's canonical-state seam, and must never auto-apply anything except the owner's own convention.

---

## Current State

### 1. Mail ingestion path (verified end to end)

```
Connect record (solercia.connect/record/v1)
  → map_mail_message()            backend/app/integrations/adapters/solercia_connect/mapper.py:68
  → MailMessage (7 fields)        backend/app/integrations/dtos.py:11
  → _dto_to_item()                backend/app/modules/intake/service.py:171
  → IntakeItem.raw_payload JSONB  = _jsonable(dataclasses.asdict(dto))
```

`raw_payload` is literally the DTO's own fields, so **the DTO is the bottleneck**: anything absent from `MailMessage` is absent from the database forever.

### 2. Fields Connect emits vs. fields Command stores

Connect's `MailMessage` (`solercia-connect/src/solercia_connect/domain.py:259`, ratified by `openspec/specs/mail-record-contract/spec.md`):
`id, subject, sent_at, sender, to, cc, body, body_format, conversation_id, has_attachments, provenance, attachments, internet_message_id, folder, received_at`.

| Connect field | Reaches `IntakeItem.raw_payload`? | Needed by |
|---|---|---|
| `id` | yes → `external_id` | idempotency |
| `subject` | yes | E1, E4, convention |
| `body` | yes → `snippet` (280 chars) + `body_text` | E1, P1–P5 markers |
| `sender.address` | yes → `sender` / `origin_actor` | direction, E4, P5, P6 |
| `to[].address` | yes → `recipients` | E4, P5 (`To:` vs `CC:`) |
| `sent_at` | yes → `received_at` (renamed) | ordering |
| **`conversation_id`** | **dropped** | **E2 (threading) — the strongest non-anchor signal** |
| **`internet_message_id`** | **dropped** | **evidence citation for the convention** |
| **`folder`** (`inbox`/`sent`) | **dropped** | **`intake_items.direction`; P1–P5 all branch on it** |
| **`cc`** | **dropped** | **P5 (`To:` only, not CC)** |
| **`has_attachments` / `attachments`** | **dropped** | **P1 (`complete` when the reply carries attachments)** |
| `received_at` (real receipt instant) | dropped (Connect's `sent_at` is reused) | inbox chronology |
| `provenance`, `body_format` | dropped | audit of route (api vs browser) |

Confirmed by memory #4488: "`raw_payload` de los items no conserva la carpeta (inbox/sent) porque el DTO MailMessage no tiene ese campo".

### 3. Direction is recoverable two independent ways

- `SolerciaConnectMailPort.list_messages` (`adapter.py:297`) reads folders in a **known order** `(mail.inbox.list, mail.sent.list)` for `outlook`, then merges and discards folder identity. Connect's spec now requires an explicit `folder` on the record and forbids deriving it from `provenance.endpoint` — so Command should read `record["folder"]`, not re-infer it.
- `ConnectedAccount.external_account_id` holds the canonical mailbox address (`adapter._canonical(account)`), and `ConnectedAccount.user_id` is `NOT NULL`. So `sender == external_account_id` ⇒ `outbound`, **and** it yields the exact `User` who authored an auto-applied convention command. This is the deterministic actor the plan needs and it already exists.

### 4. Task anchor: read-only for this change

`openspec/specs/tasks/spec.md:429-495`. `source`/`external_key` are absent from `TaskCreate`/`TaskUpdate`, writable only by `create_task(..., external_origin=(source, key))`, unique per project among active rows via `uq_tasks_source_external_key_project`, org-wide uniqueness enforced by the service through `TaskRepository.get_by_external_key`. **Reconciliation must never write the anchor**; E1 consumes `get_by_external_key(org, "checklist", "T-137")` and every other relation lives in a new `task_mail_links` row. `KNOWN_TASK_SOURCES` (`backend/app/modules/tasks/sources.py`) still says `checklist_xlsx`; change 51 renames it to `checklist`, and E1's lookup key depends on that rename.

### 5. Status writes need change 50 — this is a hard dependency, not a preference

`Task.status` is a free-form `String(60)` validated against `BoardAwareStrategy.allowed_statuses()` (the project's persisted board columns). `TaskService._resolve_completed_at` (`service.py:824`) defines "done" as **`allowed_statuses()[-1]`**. For the planned «Generales» project (methodology `custom`, 7 checklist columns ending in `REMOVIDA`), the last status is `REMOVIDA`, not `COMPLETADA`. A mail-driven `complete` written today would stamp `completed_at` on `REMOVIDA` and leave `COMPLETADA` un-stamped. `canonical_state` / `status_for` **do not exist in the codebase** (grep: only the plan document mentions them). 52 cannot write status correctly before 50 lands.

### 6. History and comments

- `record_task_history(db, org_id, task_id, actor_id, actor_type, {field: (old, new)})` (`backend/app/modules/activity/recorder.py`) stages rows without committing; its docstring already mandates that *every* future system-originated task mutation route through it with `ACTOR_TYPE_SYSTEM`.
- `TaskHistory` columns are `task_id, actor_id, actor_type, field, old_value, new_value, created_at` — **there is no evidence/reason column**. The plan's "queda en `task_history` con el `internet_message_id` como evidencia" is not expressible today. Recommended: keep `task_history` for the field diff only and put the evidence in `task_mail_links` (`intake_item_id`, `rule_code`, `internet_message_id`) — no migration on an audit table, and the link row is the auditable join anyway.
- `TaskComment.author_id` is `NOT NULL`. A `comment` proposal needs a real user: the accepting member for manual acceptance, `connected_account.user_id` for auto-applied convention.

### 7. Re-sync is not re-evaluation (idempotency gotcha)

`IntakeItemRepository.upsert_item` returns the **existing row untouched** on a duplicate `(org, connector, external_id)`, and `_ingest_account_items` classifies **only `new_items`**. Consequences:
- Widening `raw_payload` does **not** backfill the items already stored (11 real rows from the verified sync, memory #4488). A one-off backfill/refresh path is required, or those items are permanently un-reconcilable.
- The reconciliation engine cannot live only inside the ingest loop: it needs an explicit, re-runnable entry point over stored items (`POST /intake/reconcile`, or evaluation on demand), and re-running must be a no-op on already-decided items.

### 8. Privacy posture today (pre-existing, and this change widens it)

`IntakeItemRead` (`intake/schemas.py:11`) returns the whole `raw_payload` — including `body_text`, the **full mail body** — and `GET /intake/items` is open to **any authenticated organization member** (`get_current_membership`, not the owning user). Bodies are stored unencrypted in JSONB with no retention policy. Adding `cc`, `conversation_id` and attachment names makes a member-readable mirror of the owner's mailbox richer. This must be resolved inside 52, not deferred.

### 9. Frontend

- No `/intake` route (`frontend/src/app/app.routes.ts`); pages are lazy-loaded standalone components under `@pages/`.
- `@shared/ui` is a pure re-export of `@solercia/ui` 0.5.0 (`frontend/src/shared/ui/index.ts`) — no app-local atoms to fork.
- The Connect card's sync already produces `{items_new, items_duplicated, tasks_created}` and its `ToastStore` supports `action: { label, run }` (`solercia-connect-card.component.ts:742-764`). «Sincronizar ahora» → «Ver bandeja» is a toast action plus a router navigation, not new plumbing.

### 10. No YAML in the backend

`pyyaml` is **not** in `backend/requirements.txt` and no `app/` module imports yaml. The plan's `reconciliation.yaml` would add a dependency and a new configuration idiom. The codebase's own precedent for closed vocabularies is a frozen Python constant module (`tasks/sources.py`, `adapter._MAIL_FOLDERS_BY_TARGET`).

---

## Affected Areas

| Path | Why |
|---|---|
| `backend/app/integrations/dtos.py` | `MailMessage` gains `conversation_id`, `internet_message_id`, `folder`, `cc`, `has_attachments`, `attachment_names` (all optional, defaults) |
| `backend/app/integrations/adapters/solercia_connect/mapper.py` | stop discarding those fields; read `folder` from the record, never infer it |
| `backend/app/integrations/adapters/microsoft365/mappers.py`, `adapters/google/mail.py`, `adapters/fake.py` | positional `MailMessage` construction must keep compiling; new fields default to `None`/`()` |
| `backend/app/modules/intake/models.py` | new `direction` column (`inbound`/`outbound`, nullable for legacy rows) |
| `backend/app/modules/intake/service.py` | `_dto_to_item` sets `direction`; a re-runnable reconcile entry point; backfill of stored rows |
| `backend/app/modules/intake/schemas.py`, `router.py` | stop leaking `body_text` in list responses; scope item reads to the owning account's user + admin |
| `backend/app/modules/reconciliation/` (new) | `models.py`, `repository.py`, `service.py`, `rules.py` (pure), `config.py`, `router.py` |
| `backend/alembic/versions/0026_*.py` (new) | `contacts`, `task_mail_links`, `intake_proposals`, `intake_items.direction` |
| `backend/app/modules/tasks/service.py` | consumer of change 50's `canonical_state`/`status_for`; no anchor writes |
| `backend/app/modules/tasks/sources.py` | `checklist` (arrives with change 51) is the source E1 looks up |
| `backend/app/modules/comments/service.py` | `comment` proposals create a `TaskComment` with a real author |
| `frontend/src/app/app.routes.ts`, `frontend/src/pages/intake/` (new) | the triage screen |
| `frontend/src/widgets/solercia-connect-card/solercia-connect-card.component.ts` | sync toast action → `/intake` |
| `backend/tests/test_intake_*.py` | existing suite is the characterization baseline for the widened DTO |

---

## Where the logic should live

**New module `app/modules/reconciliation/`, HTTP surface mounted under `/intake/*`.**

- `rules.py` is **pure**, mirroring `intake/classifier.py`: no DB, no HTTP, no clock. Signature shape `evaluate(item, context, config, evaluated_at) -> list[ProposalDraft]`, where `context` carries the pre-loaded candidate tasks, contacts and existing links. This preserves the documented seam for the change-48 LLM port (Level 2 orders/labels, never decides) exactly as `ClassifierPort` does.
- `service.py` owns the transaction (persistence skill: repositories never commit); `repository.py` exposes aggregate-specific, tenant-scoped methods — never a bare `get(id)`.
- Keep the module separate from `intake` because the two answer different questions: `intake/classifier.py` routes a *new* insumo to a *new* task (tema→respondiente); reconciliation relates an insumo to *existing* tasks. Merging them would put two vocabularies in one strategy.
- Keep the HTTP paths inside `/intake/*` (`GET /intake/proposals`, `POST /intake/proposals/{id}/accept|reject`, `GET /intake/items/{id}/links`) because `IntakeItem` is the aggregate root the proposals hang from and the screen the user knows is the bandeja de insumos.

### Persistence sketch

| Table | Mixins | Key constraints |
|---|---|---|
| `contacts` | Pk, Timestamp, SoftDelete, Audit, Tenant | `UNIQUE(organization_id, normalized_email)`; separate `UNIQUE(organization_id, normalized_name)` only if 51 does not already own this table |
| `task_mail_links` | Pk, Timestamp, SoftDelete, Audit, Tenant | `UNIQUE(organization_id, task_id, intake_item_id, role)` → re-running the engine is idempotent; FKs `ON DELETE CASCADE` to tasks/intake_items |
| `intake_proposals` | Pk, Timestamp, Audit, Tenant (no SoftDelete — audit row, `IntakeRun` precedent) | partial `UNIQUE(organization_id, intake_item_id, task_id, action) WHERE status='pending'` → never two identical pending proposals |
| `intake_items.direction` | — | nullable `String(10)`; legacy rows stay `NULL` until backfilled, never guessed |

Tenant scoping: every read/update/delete filters `organization_id`; accepting a proposal re-verifies the task belongs to the same organization before touching it.

### Accepting a proposal — the exact write sequence

1. Load proposal + item + task, all scoped by `organization_id`; reject if the task moved to another org or was soft-deleted.
2. Resolve the target status through change 50's `status_for(canonical)` on the **task's own project strategy** (never `allowed_statuses()[-1]`).
3. `record_task_history(..., actor_type="user", actor_id=<accepting member>, {"status": (old, new)})` — staged, not committed.
4. Insert `task_mail_links` row (`role='closure'|'evidence'|'anchor'|...`, `rule_code`, `internet_message_id`).
5. Mark `intake_proposals.status='accepted'`, `decided_by`, `decided_at`.
6. One commit, owned by the service. The task anchor is never touched.

---

## Deterministic rules assessed against the real structure

**Definition adopted**: a rule is deterministic when it is a pure function of (persisted item fields, the task snapshot read at evaluation time, the versioned rule configuration, an explicitly injected `evaluated_at`). No wall-clock inside `rules.py` — the Microsoft365 clock stabilization (commit `e87c514`) is the precedent. Same inputs ⇒ same proposal set; re-running never duplicates a row and never revisits a decided proposal. Because task state changes over time, each proposal persists `rule_codes`, the quoted `evidence` fragment, the task status at evaluation and the config revision, so a past decision stays explainable.

| Rule | Verdict | Concrete constraint discovered |
|---|---|---|
| **E1 anchor** `\bT-\d{2,3}\b` | works today on `subject` + `body_text` | must look up `("checklist", key)` after change 51's rename; require non-alphanumeric neighbours; cap anchors per message; store the citation. **Reality check: the 2026-08-31 cut had 71 messages and zero valid anchors (#4298) — E1 yields nothing on historical mail.** Its value is forward-looking, together with the convention. |
| **E2 thread** `conversation_id` | strong, deterministic | blocked until the DTO is widened. Connect types it `str \| None`; when `None` the rule must **skip**, never fall back to subject matching |
| **E3 origin** | available now | backfill `task_mail_links(role='origin')` from existing `IntakeItem.created_task_id`; idempotent by the unique constraint |
| **E4 probable** (contact + Jaccard ≥ 0.6) | highest false-link risk | needs a name→email catalog. Requester lives **only in the task description text** today (change 51 adds the contacts catalog per #4508) — so E4 either depends on 51 or 52 owns `contacts`. Normalization must reuse `classifier._fold` (NFKD + ASCII + casefold), iteratively strip `RE:/RV:/FW:/FWD:`, drop a versioned stopword list, drop tokens < 3 chars, and **require at least 2 shared tokens** — otherwise a 1-token subject («Informe») scores 1.0 against everything. Candidate tasks must be pre-filtered by contact email before any Jaccard pass (see volume risk) |
| **P1/P3/P4 lexical markers** | workable with one added constraint | Connect's `body` includes the **quoted reply history**; searching markers over the whole body will match text the sender never wrote. Restrict every marker search to the *new* content: up to the first quote delimiter (`De:`, `From:`, `-----Mensaje original-----`, a long underscore rule) or a bounded prefix, both declared in config. This also makes P3's «last paragraph» unreliable — use the **first paragraph of the new content** instead, consistently with P1/P4 |
| **P1 attachments** | blocked until DTO widened | `has_attachments` is dropped today |
| **P5 direct inbound** | partially blocked | `cc` is dropped today (`To:`-only is unenforceable). **Auto-reply detection cannot use `Auto-Submitted`: Connect exposes no headers.** Fall back to a marker list («Respuesta automática», «Automatic reply», «Out of Office») plus a sender-local-part deny list (`no-reply`, `noreply`, `notificaciones`), and record a Connect follow-up for header passthrough |
| **P6 exclusions** | trivial | sender/domain deny list in config |
| **Convention** `[T-137] #cerrar\|#reabrir\|#nueva` | genuinely auto-applicable | guard = `direction == outbound` **AND** `sender == connected_account.external_account_id` **AND** the tag appears in the subject or the first line of new content. Actor = `connected_account.user_id` (so `actor_type='user'`, not `system` — the owner literally authored the instruction). `#cerrar` on an already-done task is a recorded no-op, not an error |

### Configuration: do not add YAML

`reconciliation.yaml` would introduce `pyyaml` and a new configuration idiom into a backend that has neither. Recommended split:
- **Frozen Python constants** (`app/modules/reconciliation/config.py`, `tasks/sources.py` precedent) for the structural parts: anchor regex, convention tags, stopwords, marker lists, quote delimiters, Jaccard threshold and minimum shared tokens. Versioned by a `CONFIG_REVISION` string persisted on every proposal.
- **A per-organization DB row** (extend `IntakeSettings`, already `UNIQUE(organization_id)`) for the tenant-tunable parts the plan wants editable in slice 5: allowed domains, sender exclusions.

---

## Triage UI `/intake`

**The one thing the person comes here to do**: decide, in minutes, what each new message means for their tasks.

Design brief (ux-psicologia applied):

- **Five states, all distinct**: loading (skeleton rows, not a spinner), legitimate empty («No hay insumos pendientes. Sincroniza desde Conexiones» + the action), no results for the active filter (offers to clear it), error (the backend's own message, never a generic one), success (visible confirmation of what was decided).
- **Nothing starts empty (smart defaults)**: the screen opens on `pending` proposals grouped by proposed action, with the most probable target task **pre-selected**; the header shows the already-decided count so progress never reads 0 (goal gradient).
- **Recognition over recall**: each row shows sender, subject, the quoted evidence fragment, the candidate task (key + title) and the rule codes that fired. The user never has to open the mail client to decide.
- **Hick**: group by proposed action (Completar / Reabrir / Crear / Comentar / Solo enlazar) so each group is one kind of decision; per row at most three actions — «Aceptar», «Rechazar», «Cambiar tarea…».
- **The system knows the valid set**: «Cambiar tarea…» is a searchable picker over the organization's open tasks, never a free-text field.
- **Bulk accept** is limited to the convention group, where the action is unambiguous, and it states exactly how many items it will apply to before running.
- **Fitts / destructive distance**: «Aceptar» is the large primary action; anything that changes a task state shows the resulting status before confirming.
- **Never lose work**: a rejected item stays visible with an undo window rather than disappearing.
- Reuse `@solercia/ui` (`@shared/ui` barrel) for card, badge, button, dropdown, checkbox and the existing `ToastStore`; no new atoms. All strings in Colombian formal Spanish (tuteo).

---

## Approaches

### A. Where proposals live

1. **Persisted `intake_proposals` table** *(recommended)* — proposals computed once at ingest/reconcile, stored with `rule_codes`, evidence, config revision and decision.
   - Pros: decisions are auditable; accept/reject is a simple state transition; the LLM port (48) can order stored rows without touching the engine; partial unique index gives idempotency for free; the triage list is one indexed query.
   - Cons: rows can go stale when the task changes after evaluation; needs a re-evaluation policy for stale pending rows.
   - Effort: Medium.
2. **Compute on the fly at `GET /intake/proposals`** — no proposal table, only `task_mail_links` and decisions.
   - Pros: never stale; less schema.
   - Cons: no audit trail of what was proposed and rejected; expensive per request (O(pending items × open tasks)); the LLM port would have nothing to order; "accept" would have to re-derive the proposal and could act on a different one than the user saw — a correctness hazard, not just a performance one.
   - Effort: Low to build, High to make safe.
3. **Hybrid** — persist accepted/rejected decisions only, compute pending live.
   - Pros: smaller table.
   - Cons: keeps hazard (2)'s re-derivation gap for the accept path; two code paths for the same shape.
   - Effort: Medium.

### B. Auto-apply policy

1. **Never auto-apply; everything goes through triage.**
   - Pros: zero risk of a wrong state change; simplest to reason about.
   - Cons: the owner must confirm even the commands they themselves wrote; the daily flow the plan describes loses its point.
   - Effort: Low.
2. **Auto-apply only the owner's convention in their own sent mail** *(recommended)* — `[T-xx] #cerrar|#reabrir|#nueva`, guarded by `direction=outbound` and `sender == connected_account.external_account_id`.
   - Pros: the only signal that is an explicit instruction rather than an inference; the actor is a known `User`; fully auditable via `task_mail_links` + `task_history`; everything else still requires confirmation.
   - Cons: depends on the owner actually adopting the convention (plan question 2, still unanswered).
   - Effort: Low on top of the engine.
3. **Auto-apply high-confidence inferred rules** (e.g. E1 anchor + P1 closing markers).
   - Pros: fewer clicks.
   - Cons: a wrong close is silent and only discovered later; contradicts the plan's own principle and the 2026-08-31 evidence (zero anchors); no way to distinguish "the sender said adjunto" from "the quoted history said adjunto".
   - Effort: Low to build, unbounded to trust.

---

## Recommendation

**A1 + B2**, sequenced so that no slice can write a wrong task state:

1. **Slice 0 — signals.** Widen `MailMessage` (optional fields, defaults, other adapters unchanged), stop discarding them in the Connect mapper, add `intake_items.direction`, backfill stored items and existing `created_task_id` origins. No rules yet. This slice is verifiable on its own: re-sync and assert the new keys appear in `raw_payload`.
2. **Slice 1 — links (E1–E4).** `contacts` (if 51 does not own it), `task_mail_links`, the pure evaluator, a re-runnable reconcile entry point. Links change nothing about a task; the risk surface is zero.
3. **Slice 2 — proposals (P1–P6) + `/intake`.** `intake_proposals`, accept/reject/change-task, the triage screen. Accepting writes status through change 50's canonical state.
4. **Slice 3 — convention auto-apply.** Only after slice 2 has proven the write path by hand.

Do not start before change 50 exposes `canonical_state`/`status_for`, and align E1's source key with change 51's `checklist` rename. Slices 1–3 each carry migrations, backend and (for 2) a full page: the 800-line review budget is at **High** risk of being exceeded by a single PR, so chained PRs along the slice boundaries above are the expected shape.

---

## Risks

1. **False links from E4.** Jaccard on short institutional subjects is prone to spurious matches. Mitigations: minimum 2 shared tokens, mandatory stopword removal, candidates pre-filtered by contact email, and `probable` links **always** requiring confirmation.
2. **Mail bodies at rest and over the API.** `GET /intake/items` returns full `body_text` to any authenticated org member, unencrypted, with no retention policy — and this change makes the mirror richer. Must be fixed here: scope item reads to the owning account's user plus admin, drop `body_text` from list responses (detail only), and add a retention setting that purges the body while keeping snippet, hashes and links.
3. **Backfill gap.** `upsert_item` never refreshes an existing row, so items already ingested carry no `conversation_id`/`folder`. Without an explicit backfill they are permanently un-reconcilable.
4. **Re-sync / re-run idempotency.** Guaranteed only by the two unique constraints above (`task_mail_links` 4-tuple, partial unique on pending proposals). Without them, every sync duplicates proposals.
5. **Hard dependency on change 50.** Writing `complete` before `canonical_state` exists stamps `completed_at` on the `custom` board's last column (`REMOVIDA`), silently corrupting completion metrics.
6. **Cross-change coupling with 51.** Owns `contacts` (E4's only name→email path) and the `checklist` source rename (E1's lookup key). If 51 slips, 52 must absorb `contacts` or ship without E4.
7. **Auto-reply detection is weaker than the plan assumes.** No `Auto-Submitted` header is available from Connect; marker-based detection will miss some automated senders, so P5 will occasionally propose a task for a bot message. Confirmation-only for P5 contains the damage.
8. **Quoted reply text.** Without a bounded "new content" window, P1/P3/P4 markers and E4 tokens will fire on quoted history.
9. **Volume and cost.** ~71 messages per 2 days for one account; four accounts with daily sync is roughly 10–13k items/year. Fine for Postgres, but naive E4 is O(items × open tasks) — the contact pre-filter is not an optimization, it is a requirement.
10. **Multi-account (change 53).** `direction` is relative to *the account that ingested the item*, not to "the user". Every rule must compare against `item.connected_account`, never a global notion of the owner's mailbox.

---

## Open Questions for the proposer

1. Does the owner adopt `[T-xx] #cerrar/#reabrir/#nueva` in their own sent mail? (Plan question 2 — this decides whether slice 3 exists at all.)
2. Does `contacts` belong to change 51 or to 52?
3. Seed values: allowed domains (`sdmujer.gov.co` + which others) and the sender exclusion list.
4. Retention and visibility policy for mail bodies — how long, and visible to whom?
5. Does P2 (outbound request → create «seguimiento» task) ship in the first proposal slice? It is the highest-volume and lowest-precision creator in the set.
6. Configuration home: frozen Python constants + per-org DB row (recommended, no new dependency) or `reconciliation.yaml` with a new `pyyaml` dependency?

## Ready for Proposal

**Yes, with conditions.** The technical path is clear and evidence-backed. The proposer should record change 50 (canonical state) and change 51 (`contacts`, `checklist` source) as hard prerequisites, resolve open questions 1–4 before scoping, and treat slice 0 (signal widening + backfill) as non-negotiable groundwork rather than part of the rules engine.

---

*Engram mirror: topic `sdd/52-conciliacion-correo-tareas/explore` (observation 4531). This file was materialized by the orchestrator from that observation to restore hybrid parity.*
