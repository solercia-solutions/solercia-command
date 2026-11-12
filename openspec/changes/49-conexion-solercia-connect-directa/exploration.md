# Exploration — 49-conexion-solercia-connect-directa

> SDD `explore` phase. Artifact store: hybrid (Engram topic `sdd/49-conexion-solercia-connect-directa/explore` + this file, materialized by the orchestrator from observation 4533).
> Evidence is `path:line`, read on branch `feat/conexion-solercia-connect` (Command) and `feat/http-interactive-login` (Connect) on 2026-09-05.
> This change is a **retro-specification**: the behaviour below is already implemented and was verified live. Nothing here proposes new runtime behaviour.

## 0. Why this change exists

Change `47-solercia-connect-operativo` designed the Command↔Connect connection with one-use fallback grants, a Redis grant store, a hardened SQLite session store and an append-only lifecycle-event table. Its `design_gate` is `failed` after 6 attempts with one live contradiction left (`47/state.yaml:42-69`). The owner instead shipped a narrower, pragmatic route on two branches. Change 49 must (a) write down what actually exists as delta specs, (b) close 38 and 47 without merging their unimplemented deltas, and (c) re-anchor 39 onto 49.

---

## 1. Current state (as-built)

### 1.1 Command HTTP facade — `backend/app/modules/connectors/router.py`

| Method | Route | RBAC | Success | Service entry |
|---|---|---|---|---|
| POST | `/connectors/solercia-connect` | `require_connector_write_role` (admin/manager) | `201` | `register` (`router.py:398-422`) |
| GET | `/connectors/{connector_id}/solercia-connect/status` | `get_current_membership` (any member) | `200` | `status` (`router.py:425-445`) |
| POST | `/connectors/{connector_id}/solercia-connect/connect` | admin/manager | `202` | `start_connect` (`router.py:448-472`) |
| GET | `/connectors/{connector_id}/solercia-connect/sessions/{session_id}` | any member | `200` | `session` (`router.py:475-497`) |
| POST | `/connectors/{connector_id}/solercia-connect/sync` | admin/manager | `200` | `sync` (`router.py:500-525`) |

All responses use the standard envelope (`{"data": ..., "message": ...}`); writes carry `message`, reads do not.

### 1.2 Facade service — `backend/app/modules/connectors/solercia_connect_service.py`

- **Register** (`:197-264`): probes `GET /v1/health` **before** any write; creates or reuses the organization's single `solercia_connect` connector (`_create_or_reuse_connector:266-294`, keyed on `uq_connectors_organization_provider` via `repo.get_by_provider`); stores non-secret config under `connectors.settings["solercia_connect"]` (`SETTINGS_KEY:76`); registers the runtime API key through the generic `register_api_token_credentials` path as an encrypted JSON blob containing `connector_id/base_url/api_key/account/target/allow_browser_fallback` (`:235-246`); then soft-deletes every other account of the connector (`_retire_other_accounts:296-307`) → **one account per connector, by construction**.
- **Server-held secret** (`_server_api_key:698-706`): `settings.SOLERCIA_CONNECT_API_KEY` (`SecretStr`), never accepted from the client, never returned. Decrypted for exactly one call in `_runtime_access:774-793`.
- **Status state machine** (`status:311-403`, `_map_test_response:405-464`): a Connect-side failure **is** the answer, never an exception.

  | `status.state` | Trigger | Account row side effect (`_STATE_TO_ACCOUNT_STATUS:88-93`) |
  |---|---|---|
  | `connected` | `ok` and Connect `status ∈ {connected_browser, connected_official}` (`:78`) | `AccountStatus.active` |
  | `needs_login` | `409 action_required` **and** runtime health says `interactive_login=true` | `expired` |
  | `interactive_disabled` | `409 action_required` and `interactive_login` falsy | (untouched) |
  | `misconfigured` | Connect `configuration_error`, unusable stored `base_url`, no config/account/credentials, or Connect `503` | `error` |
  | `runtime_unavailable` | transport failure (`SolerciaConnectUnavailableError`) | (untouched) |
  | `runtime_unauthorized` | Connect `401/403` | (untouched) |
  | `error` | `interactive_session_busy`, protocol failure, anything else | `error` |

  `route` is echoed verbatim from Connect's envelope (`:415-416`). `runtime.reachable` is tri-state: `None` means "never probed" (`schemas.py:219-229`).
- **Start login** (`start_connect:468-523`): refuses with `409 solercia_connect_fallback_not_allowed` when the connector was registered without browser fallback; maps `202`/`started` → `session_id`; `409 interactive_session_busy` → `409 solercia_connect_busy` with `meta.session_id`; `409 action_required` → `409 solercia_connect_interactive_disabled`; `422` → `solercia_connect_invalid_request`.
- **Poll** (`session:527-602`): validates `session_id` against `^[A-Za-z0-9_-]{1,80}$` (`:86`) before interpolating it into a loopback URL; maps to `running | connected | failed | not_found`; a finished session drives the account row (`connected`→active; `_EXPIRED_SESSION_CODES:81-83` → expired; any other failure → error).
- **Sync** (`sync:606-648`): `IntakeService.pull_outcomes(..., connector_id, since=now-since_days)`; `409 solercia_connect_needs_login` **only** when the run fetched nothing and every outcome code is in `LOGIN_REQUIRED_CODES`; every other failure is reported inside `data.errors` with `200` so partial progress stays visible (`_summarize:650-694`, statuses `completed|partial|error|skipped`).
- **Error vocabulary** (`_map_failure:128-161`): `solercia_connect_not_configured` (422), `solercia_connect_unavailable` (503), `solercia_connect_unauthorized` (502), `solercia_connect_protocol_error` (502). Connect's raw message is only forwarded on `configuration_error` and on typed session failures.

### 1.3 DTO surface — `backend/app/modules/connectors/schemas.py:172-307`

`SolerciaConnectTarget = Literal["outlook","teams","onedrive"]` (`:180`) · `SolerciaConnectState` = 7 values (`:182-190`) · `SolerciaConnectSessionState` = 4 values (`:192`) · register payload normalizes the account to `strip().lower()` (`:202-207`) · `since_days` is `ge=1, le=90`, default `7` (`:277-280`).

### 1.4 HTTP client — `backend/app/integrations/adapters/solercia_connect/client.py`

Envelope pinned to `solercia.connect/v1` (`:48`), API key sent as `X-Solercia-Connect-Key` (`:49`, only on authenticated calls). Anti-SSRF: `base_url` must be an exact member of `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST` and the rejected value is never echoed into the message (`:123-131`). Two families: `health`/`run` return the envelope and treat every non-envelope answer as failure (`:139-145`); `test_connection`/`connect_browser`/`session` return `ConnectResponse` (status code + body) because Connect's 404/409/422 **are** the information (`:147-200`). `401/403` → `SolerciaConnectAuthError`, `503` → `SolerciaConnectNotConfiguredError`, transport error → `SolerciaConnectUnavailableError` (`:220-233`).

### 1.5 Read adapter — `backend/app/integrations/adapters/solercia_connect/adapter.py`

- `PROVIDER = "solercia_connect"` (`:53`); declares `capabilities = {mail, calendar, meeting_notes}` (`:376`), `credential_kind=api_token`.
- Known targets (`_TARGETS:57`): `outlook, teams, onedrive, gmail, google_calendar`.
- **Target→capability map** (`_TARGET_CAPABILITIES:68-74`): `outlook={mail,calendar}`, `teams={meeting_notes}`, `gmail={mail}`, `google_calendar={calendar}`, **`onedrive=∅`**. A capability the target does not serve returns `[]` locally instead of asking Connect (which answers `422` and aborts the run) — this was fix `9cc7528`.
- **Mail folders** (`:76-82`, `SolerciaConnectMailPort:286-314`): `outlook` reads `mail.inbox.list` **and** `mail.sent.list`, merges, de-duplicates by `external_id` (first folder wins) and returns the newest `limit`; every other target reads sent items only.
- **Identity gate** (`_read_records:250-257`): the envelope's `account` must case-fold-equal the requested one or the read raises `SolerciaConnectAccountMismatchError` and yields zero records (ADR §4.1-4.3).
- `LOGIN_REQUIRED_CODES` (`:86-94`) is exported so the facade classifies "log in again" identically.
- `encode_access_context` (`:113-133`) still exists for the port path; the live path is the decrypted credential blob (`_flag:97-110` tolerates the `"true"/"false"` strings that `ApiTokenCredentials.as_mapping` produces).

### 1.6 Intake — `backend/app/modules/intake/service.py`

- `pull(..., connector_id=None, since=None)` (`:259-280`) and `pull_outcomes` (`:282-304`): connector-scoped ingestion, one `IntakeRun` per (connector, account); a foreign/unknown id simply reads nothing.
- `IntakeRunOutcome` (`:155-168`) keeps `error_code`, `error_detail` and `anchor_conflicts` behind a `status=error` run (no migration for a reason column).
- `_external_origin` (`:124-139`) anchors converted items via `TaskService.create_task(..., external_origin=(source, external_key))` only when `source ∈ KNOWN_TASK_SOURCES` (delivered by archived change 43).

### 1.7 Runtime configuration and ops

`backend/app/config.py:234-247`: allowlist `["http://127.0.0.1:8765","http://host.docker.internal:8765"]`, timeout `60.0s`, `SOLERCIA_CONNECT_BASE_URL` default `http://host.docker.internal:8765`, `SOLERCIA_CONNECT_API_KEY: SecretStr | None`, `SOLERCIA_CONNECT_DEFAULT_TARGET="outlook"`.
`docker-compose.yml:52-55`: both variables injected from the shell/root `.env` (gitignored), plus `extra_hosts: host.docker.internal:host-gateway`.
`gestion.sh:229-236`: `status` probes `http://127.0.0.1:8765/v1/health` and reports `interactive_login`, stating Connect runs on the host, never in this compose.

### 1.8 Frontend

- `frontend/src/entities/connector/connector.model.ts`: full type mirror (`:97-193`), `solerciaConnectSettingsOf` reader (`:199-222`), **`PROVIDER_CATALOG` reduced to a single creatable option** (`:236-243`), and a separate presentation map so legacy `jira`/`google` rows still render (`:251-261`).
- `connectors.service.ts:108-158`: the five facade calls, `session_id` URL-encoded.
- `widgets/solercia-connect-card/solercia-connect-card.component.ts`: card lifecycle — refresh on init plus a 60 s clock (`:505-513`); `refreshStatus` is suppressed while a login session runs, because the Chromium profile has a single owner (`:541-558`); `startLogin` (`:581-596`) with `409` handling for busy (offers "follow that session" as a sticky toast action) and interactive-disabled (`:598-622`); tracking = 1 s countdown + `timer(0, 2000)` + `exhaustMap` poll, hard stop at expiry (`:56-58`, `:624-658`); terminal states raise a toast and re-read status (`:660-698`); "cancel" only stops polling — the browser Connect opened stays open (`:700-712`); sync window chips 1/7/30 days (`:60-64`).
- `pages/connections/connections.component.ts`: renders the dedicated card for `provider === 'solercia_connect'` (`:149-151`), drawer pre-filled with the probable values and the existing registration (`:892-902`), submit keeps the drawer open on error so typed data is never lost (`:929-990`).
- `shared/lib/toast/{toast.store.ts,toast-host.component.ts,index.ts}`: app-owned transient feedback (there is no runtime alert service in `@solercia/ui`).

### 1.9 Connect side (sibling repo, branch `feat/http-interactive-login`)

- Gate: `config.py:196` `http_interactive_login` + `config.py:199-211` `http_interactive_allowed = switch AND api_key configured AND browser_fallback_enabled` (bind host is already forced to loopback).
- `service.py:34-37`: `/v1/connections/test`, `/v1/run`, `/v1/connections/connect` and `GET /v1/connections/sessions/` all require the API key. `:328` publishes `interactive_login` in `/v1/health`.
- `service.py:407-422` (`/v1/connections/test`), `:424-496` (`/v1/connections/connect`, `202`, rejects `allow_browser_fallback=false` with `422`), `:498+` (`GET /v1/connections/sessions/{id}`).
- `interactive_sessions.py`: process-local registry, **one headed browser at a time** (`:91-104`), results retained in memory for 1 hour (`:14`), worker exceptions become an `unknown_error` envelope so a session can never stay `running` forever (`:121-139`). Nothing is written to disk.
- Docs already amended: `docs/ARCHITECTURE.md:3-6,26-35` describes the opt-in explicitly.

### 1.10 Tests

`backend/tests/test_connectors_solercia_connect.py`, `backend/tests/test_adapter_solercia_connect.py`, `backend/tests/test_intake_external_origin.py`. Reported suite state at the end of the implementation session: 1568 backend tests passing; `eslint`/`tsc`/`build` clean. The frontend has **no unit-test runner** (`package.json` declares only `ng/start/build/lint/watch`; `tsconfig.app.json` compiles only what `src/main.ts` reaches).

---

## 2. Specification gap analysis

### 2.1 What the live specs say today

- `openspec/specs/connectors/spec.md` — generic connector CRUD, OAuth dance, `credential_kind`, direct `api_token` registration, encryption at rest, account listing/disconnect. **Zero mentions of `solercia_connect` anywhere under `openspec/specs/`** (verified by search). The adapter was built outside SDD and has never had a spec home; the repo's taxonomy would put it next to `adapter-microsoft365`, `google-adapter`, `glpi-adapter`.
- `openspec/specs/intake-items/spec.md:13,57-59` — only the org-wide `POST /api/v1/intake/pull`. Connector-scoped pull, the `since` window and the outcome/error classification are unspecified.

### 2.2 Live contradiction the delta MUST resolve

`openspec/specs/connectors/spec.md:64-77` — "Varias cuentas del mismo proveedor por usuario … la unicidad DEBE evaluarse por `external_account_id` dentro del conector". The facade contradicts it for this provider: `_retire_other_accounts` soft-deletes every account other than the registered one (`solercia_connect_service.py:296-307`). The delta must **scope** the one-account rule to the `solercia_connect` connector without weakening the general requirement.

### 2.3 47 → 49: satisfied / dropped / open

| 47 element | Status in the as-built route | Evidence |
|---|---|---|
| Single Command provider backed by Connect, Connect owns the session | **Satisfied** | facade + adapter, `PROVIDER_CATALOG` single option |
| Idempotent reuse of the org connector (no `500` on duplicate) | **Satisfied**, simpler (reuse by provider, settings replaced) | `:266-294` |
| Durable status + visible route on the card | **Satisfied** | `status`, `SolerciaConnectStatusRead`, card |
| Bounded Connect HTTP contract to create/poll an opaque interactive session | **Satisfied, narrowed** — create + poll, **no cancel** | `service.py:424-498` |
| Command container → `host.docker.internal:8765` | **Satisfied** | `config.py:234-247`, `docker-compose.yml:52-55` |
| Stacked, accessible, auto-dismissing toasts | **Satisfied** (app-owned `ToastStore`, not the 47 `AlertStore` naming) | `shared/lib/toast/` |
| Command never handles provider secrets | **Satisfied** | only the runtime key is stored, encrypted |
| Official-first routing with an eligible typed outcome revealing fallback | **Dropped**: over HTTP there is no terminal for a device code, so `connect_browser` always sends `allow_browser_fallback=true` | `client.py:161-172` |
| One-use 256-bit fallback capability, Fernet-encrypted in **Redis**, hash+consume in Connect | **Dropped** | no Redis key, no capability field anywhere |
| Hardened **SQLite** session store (`O_NOFOLLOW`, `BEGIN IMMEDIATE`, tombstones, 24 h/30 d retention) | **Dropped**: in-memory registry, 1 h retention | `interactive_sessions.py:14,55-119` |
| `ConnectionLifecycleEvent` append-only audit table + 365-day purge job | **Dropped**: no migration, no table | |
| Migration `0026` (`canonical_account`, `target`, `connection_route`, `connection_state`, `lifecycle_version`) | **Dropped**: state lives in `connectors.settings` + `ConnectedAccount.status` | `_config_of:742-760` |
| `MicrosoftIntegrationRouter` + retirement of legacy direct OAuth | **Dropped/not started**: `microsoft365` and `google` connectors still exist in the database | |
| `cancel` operation, `lifecycle_version` CAS, idempotency keys | **Dropped**: cancel is client-side only (stops polling) | card `:700-712` |
| Amend the **platform ADR** | **Open** — see risk R1 | |

### 2.4 Open behaviour (as-built limitations, to be recorded, not fixed here)

1. One account and one target per organization; a second mailbox (`cccalderon@catastrobogota.gov.co`) has no home today.
2. Inbox/sent provenance is lost: `MailMessage` (`backend/app/integrations/dtos.py:12-21`) has no folder field, so `raw_payload` cannot say where a message came from.
3. `SolerciaConnectTarget` accepts `onedrive`, which serves **zero** capabilities (`adapter.py:68-74`) → a registration that can never read anything and still reports `connected`. The facade Literal also omits `gmail`/`google_calendar`, which the adapter does serve.
4. `GET .../status` and `GET .../sessions/{id}` are member-reachable **and** mutate `ConnectedAccount.status` + commit (`:402`, `:595-601`) — reads with side effects, on an account that may belong to another member (`list_accounts` is called without `only_user_id`, cf. `repository.py:277-289`).
5. `register()` is not atomic: `ConnectorRepository.create/save` (`repository.py:73-84`) and `soft_delete_account` (`:338-357`) commit on their own, so a mid-register failure can leave a connector row without credentials (status then answers `misconfigured`). The service docstring claims "repositories flush, this service commits" — that claim is only true for `mark_status`.
6. Intake produces `IntakeItem` rows in `pending`; there is no `IntakeRule`, no triage page and no rules UI, so `items_converted` is structurally `0` today.
7. No frontend test runner: card lifecycle is covered only by `tsc`/`build` plus manual verification.

---

## 3. Affected areas (for spec and closure work)

**Spec deltas (documentation only — no runtime file is touched by this change):**

- `openspec/changes/49-…/specs/connectors/spec.md` — MODIFIED "Varias cuentas del mismo proveedor por usuario" (scope the one-account rule) + ADDED facade requirements (registration, RBAC split, settings storage, encrypted runtime key, status state machine, session poll, connector-scoped sync).
- `openspec/changes/49-…/specs/solercia-connect-connection-lifecycle/spec.md` — NEW, as-built and narrow: envelope `solercia.connect/v1`, API-key header, base-URL allowlist, Connect's opt-in gate, `test`/`connect`/`sessions/{id}`, single in-flight session, 1 h in-memory retention, no cancel, no capability grant.
- `openspec/changes/49-…/specs/solercia-connect-adapter/spec.md` — NEW (recommended): targets, target→capability map, inbox+sent merge/de-duplication, observed-identity gate, `LOGIN_REQUIRED_CODES`.
- `openspec/changes/49-…/specs/intake-items/spec.md` — MODIFIED: connector-scoped pull with `since`, outcome classification, `anchor_conflicts`.

**Closure artifacts:**

- `openspec/changes/38-oauth-ms-google/` and `openspec/changes/47-solercia-connect-operativo/` — move to `openspec/changes/archive/YYYY-MM-DD-<name>/` with an explicit `closure: superseded` marker and **no** delta merge.
- `openspec/changes/39-conector-capacidades/state.yaml:3-4` — `depends_on: [47-…]` → `[49-…]`; its `dependency_gating` lines that name 38 also need rewording (orchestrator-only edit).
- `openspec/specs/README.md` — traceability table (already stale: it stops at change 12) plus a new "closed without delta merge" section.

**Read-only evidence (not modified):** the eleven runtime files listed in §1.

---

## 4. Approaches

### 4.1 Scope of change 49

| # | Approach | Pros | Cons | Effort |
|---|---|---|---|---|
| A | **Pure retro-specification**: specs describe the as-built exactly; §2.4 items recorded as explicit limitations/deferred | Verify is honest and cheap (the code and its 1568 tests already exist); zero regression risk; unblocks 39 fastest | Freezes known warts (`onedrive`, side-effecting GETs) into the living spec until a later change | Low |
| B | Retro-spec **+ bounded corrections** (narrow the target Literal, add folder provenance to `MailMessage`, make the status write explicit) | One pass, spec and code agree on a better contract | `MailMessage` is shared with `microsoft365`/`google` adapters → blast radius beyond this change; verify mixes "describe" and "change"; review budget pressure | Medium |
| C | Split: 49 = retro-spec + closure; 50 = corrections | Cleanest separation of "write down the truth" from "change the truth" | Two SDD cycles; the warts stay documented as normative for a while | Low + Medium |

### 4.2 Closure of the 38 and 47 folders

| # | Approach | Pros | Cons | Effort |
|---|---|---|---|---|
| C1 | Move both folders to `changes/archive/` with `closure: superseded`, `superseded_by: 49`, `spec_merge: none` | Keeps the audit trail; empties the active list; makes the "do not merge" decision explicit and greppable | The archive currently means "completed"; the semantics must be stated in `specs/README.md` or a future reader may assume the deltas landed | Low |
| C2 | Leave both in place, add `superseded_by: 49` and freeze the phases | Zero movement, zero ambiguity about "completed" | Active-changes list keeps two dead entries; a future `sdd-archive` on 47 could still merge its deltas by accident | Low |
| C3 | Delete the folders | Simplest listing | Destroys the audit trail; forbidden by the archive convention | — |

---

## 5. Recommendation

1. **Scope: Approach A (pure retro-specification)**, with §2.4 written into the proposal as declared limitations. Mixing corrections in would make `sdd-verify` ambiguous and would drag `microsoft365`/`google` into the blast radius through the shared `MailMessage` DTO. Register the corrections as a candidate follow-up change.
2. **Relationships: `supersedes: [47-solercia-connect-operativo, 38-oauth-ms-google]`, `amends: [39-conector-capacidades]`, `depends_on: []`.** 47 already declared `supersedes: [38]` (`47/proposal.md:9-12`), so 49 inherits that supersession rather than leaving 38 orphaned behind a dead parent.
3. **Closure: Approach C1, executed as an explicit artifact work unit inside 49's `tasks.md`** — precedent: change 43 carried the artifact re-anchoring of change 40 as Fase 1 (`43/state.yaml` D8). The unit must state, per closed change: destination path, the added `closure`/`superseded_by`/`spec_merge: none` keys, and a verification command (a search for `supersedes` that returns only 49).
4. **Capabilities: four deltas** — `connectors` (MODIFIED+ADDED), `intake-items` (MODIFIED), `solercia-connect-connection-lifecycle` (NEW, reusing 47's capability name because 47's version was never merged, with the delta stating that the as-built contract is deliberately narrower), and `solercia-connect-adapter` (NEW, matching the repo's `*-adapter` taxonomy). A smaller surface may fold the adapter into the lifecycle capability — never into `connectors`, which is provider-agnostic by design.
5. **Re-anchor 39 in the same pass** (`39/state.yaml:3-4` + its `dependency_gating` lines): this is the follow-up 47 itself promised and the only reason 39 is blocked by a failed design gate.

---

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **Live ADR contradiction.** `solercia-connect/docs/decisions/2026-08-23-solercia-platform-decisions.md:98-100,110-113` still states "El adaptador HTTP nunca inicia ni espera un flujo interactivo" and "el servicio FastAPI en loopback es un adaptador no interactivo", which the shipped opt-in contradicts. The two repo copies of that ADR have also **drifted**: Command's copy does not contain those clauses at all | High | 49 must include the ADR amendment as an explicit work unit (Connect's `docs/ARCHITECTURE.md` was already amended; the decision record was not) and decide whether the copies are re-synchronized or formally forked |
| R2 | **Accidental merge of 47's deltas.** `47/specs/connectors/spec.md:5-35` contains MODIFIED blocks that would overwrite live requirements with unimplemented behaviour (migration `0026`, `canonical_account`, lifecycle events) if anyone ever runs `sdd-archive` on 47 | High | C1 closure with `spec_merge: none` recorded in `47/state.yaml`, plus a note in `openspec/specs/README.md` |
| R3 | **Retro-spec drift.** Both branches are unmerged and the owner decides PR/merge; specs written against `feat/*` could describe code that changes before landing | Medium | Pin the delta to the exact commits (Command `1112731`, Connect `9b67f63`) and make "specs match the merged code" a verify criterion |
| R4 | **Non-atomic registration** (§2.4.5) becomes normative if written down uncritically | Medium | Spec the observable contract (a failed registration leaves the connector `misconfigured`; re-registering is idempotent) and register the transaction-ownership fix as a follow-up change |
| R5 | **Capability-name collision** if 47 is archived later with the same `solercia-connect-connection-lifecycle` name | Medium | R2's mitigation covers it; state name ownership explicitly in 49's proposal |
| R6 | **Archive semantics**: archiving two never-implemented changes weakens "archive = completed" | Low | Explicit `closure` key + README section |
| R7 | **Frontend requirements are unverifiable by test** (no runner) | Low | Scope frontend scenarios to what `tsc`/`build` and manual acceptance prove, as change 43 did (`43/state.yaml` D-H) |

---

## 7. Open questions for the proposer (decide, do not interview the user)

1. Four capability deltas or three (fold the adapter into the lifecycle capability)?
2. Does 49 amend the ADR in **both** repos, or only Connect's copy with a note that Command's copy is a stale fork?
3. Are the §2.4 limitations normative "known limitation" requirements or only proposal-level deferrals?
4. Does the `intake-items` delta stay in 49, or move to the change that builds the triage/rules UI?

---

## 8. Persistence review (per `agents/rules/solercia-persistence.md`)

- **Provider ports/adapters:** `SolerciaConnectMailPort`, `SolerciaConnectCalendarPort`, `SolerciaConnectMeetingNotesPort`, `SolerciaConnectHandshake` — provider ports, not CRUD repositories. Compliant.
- **Semantic repository methods used:** `ConnectorRepository.get_by_provider`, `ConnectedAccountRepository.list_accounts(connector_id, organization_id, *, only_user_id)`, `mark_status(organization_id, …)`, `soft_delete_account`, `get_credentials`. All tenant-scoped; no unsafe `get(id)` at the service boundary (`_require_connector:717-727` enforces org + provider, `404` for the wrong kind).
- **Transaction ownership:** partially compliant. `mark_status` flushes and the facade commits (`:402`, `:601`, `:640`, `:807`), but `ConnectorRepository.create/save` and `soft_delete_account` commit inside the repository (`repository.py:73-84,338-357`) — a **pre-existing** deviation this change neither introduces nor fixes.
- **Tenant scoping:** every facade read/write is keyed by `organization_id`; the Connect runtime address is validated against a server allowlist, never taken from the client.
- **Tests required by the delta:** none new for behaviour (three existing test files cover it); verification is artifact-level (delta ↔ code correspondence) plus the existing backend suite.
- **Migration stage:** none. Change 49 adds no Alembic revision — deliberately, since 47's migration `0026` is among the dropped elements.

---

## 9. Ready for proposal

**Yes.** The as-built behaviour is mapped with `path:line` evidence, the 47 inheritance is classified (satisfied / dropped / open), the closure mechanics for 38/47 have a repository precedent, and the four open questions are proposer-level decisions.

---

*Engram mirror: topic `sdd/49-conexion-solercia-connect-directa/explore` (observation 4533).*
