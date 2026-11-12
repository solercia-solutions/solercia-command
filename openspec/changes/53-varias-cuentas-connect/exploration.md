# Exploration: several Microsoft accounts through one Solercia Connect connector

Change: `53-varias-cuentas-connect` · Depends on `49-conexion-solercia-connect-directa` (retro-spec of the implemented connection). Branch under study: `feat/conexion-solercia-connect`.

Goal driving this: the owner has two institutional mailboxes (SDMujer today, Catastro next), wants Outlook first and Teams/OneDrive later **per account**. Today the second registration destroys the first.

---

## Current State

### The read path is already per-account

This is the decisive finding. Three of the four layers already work with N accounts:

- `ConnectedAccount` is unique per `(connector_id, external_account_id)` (`backend/app/modules/connectors/models.py:80-86`), never per `(user_id, provider)`.
- `openspec/specs/connectors/spec.md` §"Varias cuentas del mismo proveedor por usuario" (L64-75) already RATIFIES the N-accounts-per-connector model: a second external account MUST create a second `ConnectedAccount` row.
- `IntakeService.pull_outcomes` (`backend/app/modules/intake/service.py:293-304`) already iterates `connectors × list_accounts(connector.id, org)`, and `_pull_account` isolates one account's failure from the others, producing one `IntakeRun` per account.
- `SolerciaConnectAdapter` reads `account` and `target` from the **per-account encrypted credential blob** (`_decode_access_context`, `backend/app/integrations/adapters/solercia_connect/adapter.py:136-154`), NOT from `connectors.settings`. Each account therefore already carries its own target and its own identity check (`SolerciaConnectAccountMismatchError`).

### What actually forces a single account

Only the facade `backend/app/modules/connectors/solercia_connect_service.py`:

| Mechanism | Location | Effect |
|---|---|---|
| `_retire_other_accounts` | `solercia_connect_service.py:296-307` | Soft-deletes every account whose `external_account_id` differs from the one just registered, and `soft_delete_account` **hard-deletes** its `ConnectionCredentials` |
| Single settings object | `_ConnectorConfig` / `_config_of` (`:100-113`, `:742-760`) | `connectors.settings["solercia_connect"] = {account, target, allow_browser_fallback}` — one account, one target, replaced wholesale on re-register |
| `_primary_account` | `:762-772` | Collapses N accounts to the one named by settings, falling back to `accounts[0]` |
| Connector-keyed routes | `router.py:425-525` | `status`, `connect`, `sessions/{sid}`, `sync` take only `connector_id`; no account selector |

### The `uq_connectors_organization_provider` invariant

`UNIQUE(organization_id, provider)` exists in `models.py:44-48` and migration `0015_add_connectors.py:78`. Its only production consumer is `ConnectorRepository.get_by_provider`, called from exactly one place: `SolerciaConnectService._create_or_reuse_connector`. It is also asserted in `backend/tests/test_connectors_migration.py:168` and relied on by `test_connectors_oauth_redirect.py:323`. Coupling is therefore narrow but the invariant is documented and spec-backed.

### Correction to a stated premise (verified in the Connect repo)

The Chromium profile is **not** single-owner per runtime. `microsoft_browser_profile_path` (`solercia-connect/src/solercia_connect/browser_profile.py:27-31`) returns `<root>/sha256(normalize_account(account))[:16]` — **one isolated profile per account**. Two accounts can stay logged in simultaneously and reads do not contend for one profile.

What IS single-owner is the **interactive login registry**: `InteractiveSessionRegistry.start` (`interactive_sessions.py:83-95`) returns `None` while any session is unfinished, which the service maps to `409 interactive_session_busy` (`service.py:461-483`). So the constraint is *one supervised login at a time per runtime*, across accounts — it restricts logins, not reads.

---

## Affected Areas

| Path | Why it is affected |
|---|---|
| `backend/app/modules/connectors/solercia_connect_service.py` | Owns every single-account assumption: `_retire_other_accounts`, `_ConnectorConfig`, `_config_of`, `_primary_account`, `_require_configured`, the `needs_login` rule in `sync` |
| `backend/app/modules/connectors/schemas.py:195-307` | `SolerciaConnectRegister/SettingsRead/StatusRead/SyncRead` are all single-account shaped; `SyncRead` docstring states "normally exactly one — one account per connector" |
| `backend/app/modules/connectors/router.py:398-525` | Five routes keyed by `connector_id` only |
| `backend/app/modules/connectors/models.py` + a new Alembic migration | Where per-account non-secret settings would live (option A1) |
| `backend/app/modules/connectors/repository.py` | `list_accounts`, `get_account`, `soft_delete_account` already tenant-scoped and reusable as-is |
| `backend/app/modules/intake/service.py:347-417` | `item_account_id` is `None` for `api_token` connectors → items from two mailboxes are indistinguishable |
| `backend/app/modules/intake/models.py:44-47` | Idempotency is `UNIQUE(organization_id, connector_id, external_id)` — not account-scoped |
| `backend/app/modules/intake/classifier.py:42-59` | Rule criteria support `connector_id` but no account field → no per-mailbox routing under one connector |
| `frontend/src/pages/connections/connections.component.ts` | One card per connector; `openCreate()` pre-fills from the existing connector, so "add account" and "re-register" are the same gesture |
| `frontend/src/widgets/solercia-connect-card/solercia-connect-card.component.ts` | Reads a single `settings()`; calls status/login/sync with `connector.id`; its trash button deletes the **connector**, not the account |
| `frontend/src/entities/connector/connector.model.ts:122-134,199-222` | `SolerciaConnectSettings` and `solerciaConnectSettingsOf` are single-valued |
| `frontend/src/entities/connector/connectors.service.ts:102-160` | Five methods keyed by `connectorId` |
| `frontend/src/assets/i18n/es-CO.json` | New copy under `connectors.solerciaConnect.*` |
| `backend/tests/test_connectors_solercia_connect.py` | 33 tests keyed to connector-scoped routes; `test_register_with_another_account_retires_the_previous_one` (L281) asserts the behaviour being removed |

### What breaks concretely with two accounts today

1. **Registration destroys the previous mailbox.** Registering Catastro soft-deletes the SDMujer account and purges its credentials; settings are overwritten. SDMujer becomes unreachable and needs a full re-registration plus a new supervised login.
2. **No place for a second `{target, allow_browser_fallback}`.** `_config_of` returns one config, so "Outlook for SDMujer, Teams for Catastro" cannot be expressed.
3. **Status/connect/session act on the wrong account silently.** `_primary_account` resolves whatever settings name; the other account can never be checked or re-authenticated.
4. **`sync` mis-reports mixed outcomes.** It already fans out over every account of the connector, but the 409 rule is `all(outcome.error_code in LOGIN_REQUIRED_CODES)` (`solercia_connect_service.py:629-633`): one healthy + one expired account suppresses the 409, and `_primary_account` would mark the WRONG account `expired` if it did fire.
5. **Intake cannot attribute an item to a mailbox.** `connected_account_id` is set only for `oauth` connectors; `solercia_connect` is `api_token`, so every item stores `None`. Combined with connector-scoped idempotency, a message Connect reports with the same `id` in both mailboxes is silently counted as `duplicated` and attributed to neither.
6. **The UI has no concept of an account.** One card per connector, one account field, and the destructive action deletes the whole connector.

---

## Approaches

### A. One connector per organization, N `ConnectedAccount`s, endpoints keyed by account

Remove `_retire_other_accounts`; move `{target(s), allow_browser_fallback}` from the connector onto the account; key `status`/`connect`/`sessions`/`sync` by `connected_account_id`. `DELETE /connected-accounts/{id}` already exists and already purges credentials, so "remove one account" comes for free.

Where per-account settings live — three sub-options:

- **A1 (recommended): new nullable `settings` JSONB column on `connected_accounts`.** Mirrors `Connector.settings` exactly (non-secret provider config), additive, readable by the UI without decrypting. Costs one Alembic migration.
- **A2: keep them inside the encrypted credential blob.** No migration, but they are non-secret, the UI would need a decrypt on every read, and changing a target would force a re-registration. Rejected.
- **A3: keyed map `connectors.settings["solercia_connect"]["accounts"][<canonical account>]`.** No migration, but re-introduces the settings/account drift that `_primary_account` already papers over, with the account address as a JSON key in two places.

- Pros: matches the ratified main spec; preserves the `uq_connectors_organization_provider` invariant and every test that asserts it; the adapter, the intake fan-out, the per-account failure isolation and the account-isolated Connect profiles all keep working unchanged; per-account identity verification stays inside the credential blob where it already is.
- Cons: touches the five facade routes and their schemas; needs a migration (A1) plus a backfill from the current connector-level settings; the frontend card must be re-keyed from connector to account; the intake attribution gap (finding 5) must be decided explicitly rather than inherited.
- Effort: **Medium**.

### B. One connector per account (relax `uq_connectors_organization_provider`)

- Pros: `connector_id` alone identifies the account, so every existing endpoint, the existing intake rule criterion `connector_id`, `IntakeItem` idempotency, item attribution and the frontend "one card per connector" all keep working with almost no code change.
- Cons: contradicts `openspec/specs/connectors/spec.md`, which explicitly says a second account is a second `ConnectedAccount`, not a second connector; breaks `test_connectors_migration.py:168` and the assumption in `test_connectors_oauth_redirect.py:323`; `get_by_provider` (single-row semantics) must change or go; `Connector` acquires a second, duplicate notion of identity next to `ConnectedAccount`; the constraint is shared with every other provider, so relaxing it silently permits duplicate `microsoft365`/`google`/`glpi` connectors that nothing else expects.
- Effort: **Medium-High**, with a spec contradiction that must be resolved before any code.

### C. Minimal: make `settings.account` a list, resolve per request body

- Pros: no migration, smallest diff.
- Cons: leaves the settings↔account drift in place, gives the UI no stable per-account identity, and does not solve targets-per-account or intake attribution. Postpones the same work.
- Effort: **Low**, but it is not a model — it is a patch.

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| A — N accounts, per-account settings + endpoints | Matches ratified spec; adapter/intake/Connect already per-account; keeps org-provider invariant | Facade + schemas + router + migration + frontend re-key | Medium |
| B — one connector per account | Almost no code change downstream; free attribution and rule routing | Contradicts main spec; breaks shared constraint and two tests; duplicate identity concept | Medium-High |
| C — account list in settings | Smallest diff | No per-account identity, no per-account targets, no attribution | Low (defers the problem) |

---

## Recommendation

**Approach A with sub-option A1** (new `connected_accounts.settings` JSONB).

Rationale: the system is already three-quarters there. The credential blob, the adapter, the intake fan-out, the per-account `IntakeRun` isolation and Connect's account-isolated browser profiles are ALL per-account today. The only single-account artefacts are `_retire_other_accounts` and one settings object in the facade. Approach A deletes an artificial constraint instead of relaxing a real, documented invariant that other modules share, and it is the model `openspec/specs/connectors/spec.md` already ratifies.

Suggested migration path from the current single-account settings:

1. Add nullable `connected_accounts.settings` JSONB (additive, no default rewrite).
2. Backfill: for each existing `solercia_connect` connector, copy `connectors.settings["solercia_connect"]` into the surviving account's row, keyed by canonical `external_account_id`.
3. Keep `_config_of` as a read-time fallback for one release so an un-backfilled account still resolves.
4. Stop writing the connector-level object; drop `_retire_other_accounts`.
5. Rollback: the column stays, the facade reverts to reading `connectors.settings`. No data is destroyed by the forward migration, which is why the backfill must be a copy, never a move.

---

## UI Implications (ux-psicologia applied)

**What the person comes to do here:** connect a mailbox and keep it working — for each of their accounts.

1. **One card per ACCOUNT inside the Connect section, not per connector.** Card shows account address, target, route, last check, state badge, and its own actions (Sincronizar / Iniciar sesión / Verificar). *Reconocer > recordar:* both mailboxes visible side by side, never behind a selector.
2. **"Agregar cuenta" must not pre-fill the other account's address.** Today `openCreate()` pre-fills from the existing connector, which reads as "edit". Smart defaults still apply to `target=outlook` and `allow_browser_fallback=true` (both probable), but the address field starts empty for a NEW account and pre-filled only when editing a specific one.
3. **Busy state must be shared across cards.** Only one supervised login runs per runtime. While account A's login is `running`, account B's "Iniciar sesión" must be disabled **with a tooltip naming the reason and the account holding the session** — never a disabled button without the reason. This needs a page-level signal or store; today each card only knows its own session.
4. **The "seguir esa sesión" action on a `409 interactive_session_busy` currently attaches the wrong card.** `onStartError` tracks `meta.session_id` from whichever card was clicked; with two accounts that session belongs to the OTHER account. The session's account must be checked before attaching.
5. **The destructive action changes meaning.** Today the trash on the card deletes the whole connector (`DELETE /connectors/{id}`). Per-account cards must delete the ACCOUNT (`DELETE /connected-accounts/{id}`, which already purges credentials); deleting the connector becomes a separate, rarer action placed away from the frequent ones (Fitts).
6. **Sync per account,** each with its own `since_days` chips. If a "sincronizar todo" is added it must show per-account results — an aggregate that hides one failing mailbox is exactly the "no hay datos" vs "falló la consulta" confusion.
7. **Five states, per card and for the list:** loading (skeleton, already present), legitimate empty (no accounts yet → "Conecta tu primera cuenta" with the primary action), account-list load error (distinct from empty), per-card error showing the backend `detail` (already honoured), success toast (already present).
8. **Copy** goes in `frontend/src/assets/i18n/es-CO.json` under `connectors.solerciaConnect.*`, Colombian formal Spanish with tuteo, never voseo.

---

## Risks

1. **Irreversible loss from past retirements.** `soft_delete_account` hard-deletes `ConnectionCredentials`. Any account already retired by `_retire_other_accounts` cannot be revived by flipping `is_active` — it needs a fresh registration and a new supervised login. Inspect the target database before designing the backfill.
2. **Login contention, not profile contention.** One headed Chromium login at a time per runtime. The UI must serialize logins across cards and explain the wait; reads and `/status` for a second account are safe at the profile level but still contend for the runtime, so the conservative rule (block status polls while any login runs) should be stated explicitly rather than assumed.
3. **Intake attribution and dedup is the largest open gap.** Items land with `connected_account_id=None` for `api_token` connectors and idempotency is `(org, connector, external_id)`. Two mailboxes under one connector can collide, and per-account triage or rules are impossible without a new field and a new classifier criterion. This is a decision, not an implementation detail.
4. **Tenant scoping of the new account-keyed routes.** Every route must resolve through `ConnectedAccountRepository.get_account(organization_id, account_id)` (already tenant-scoped) and return 404 for a foreign organization or a non-`solercia_connect` connector, matching the existing "wrong kind == not found" convention.
5. **Ownership and visibility.** For `api_token` registration the account's `user_id` is the REGISTRANT (`ConnectorService.register_api_token_credentials`), and `list_accounts(only_user_id=...)` scopes plain members to their own accounts. Two accounts registered by two different admins would be invisible to each other's owner under member visibility rules.
6. **Per-account identity verification depends on the blob.** The adapter refuses a response whose observed `account` differs from the requested one, but only because `account` travels inside the per-account credential blob. Any design that moves per-account config OUT of the blob must re-establish that guarantee.
7. **Reactivation semantics.** `upsert_account` reactivates a soft-deleted row for the same `external_account_id`, but its credentials were purged. Confirm the flow leaves a reactivated account in `needs_login`, never `active`.
8. **Test surface.** 33 tests in `test_connectors_solercia_connect.py` are keyed to connector-scoped routes; `test_register_with_another_account_retires_the_previous_one` asserts the exact behaviour being removed and must be inverted. TDD is mandatory in this project (`openspec/config.yaml` `rules.apply.tdd: true`).

---

## Open Questions for the Proposer

1. Per-account settings storage: new `connected_accounts.settings` JSONB (A1, recommended) or a keyed map under `connectors.settings` (A3, no migration)?
2. Endpoint shape: flat `/connected-accounts/{id}/solercia-connect/*` (matches the existing `DELETE /connected-accounts/{id}` precedent) or nested `/connectors/{cid}/solercia-connect/accounts/{aid}/*` (keeps connector scoping explicit in the path)?
3. Does `sync` stay connector-wide (fan out to every account) with an added per-account variant, or become per-account only? The current connector-wide `needs_login` rule mis-reports mixed outcomes either way and must be redefined.
4. Should `IntakeItem.connected_account_id` be populated for account-scoped `api_token` connectors, should idempotency become `(org, connector, account, external_id)`, and should the classifier gain an account criterion so SDMujer and Catastro route to different projects?
5. One target per account or several (`targets: ["outlook", "teams"]`)? The adapter maps capabilities for a single `target` today (`_TARGET_CAPABILITIES`, `_MAIL_FOLDERS_BY_TARGET`) and the blob carries one value.
6. RBAC: is the Connect section admin/manager-only, or should a member see the card for their own account?
7. Compatibility window: keep reading `connectors.settings["solercia_connect"]` as a fallback for one release, or migrate and drop within this change?

---

## Ready for Proposal

**Yes**, with question 4 (intake attribution and dedup) flagged as the one that materially changes scope: it can either be included in this change or split into a follow-up, but it must be decided before `sdd-spec`. Questions 1, 2, 5 and 6 are ordinary design decisions the proposer can carry; question 3 depends on 4.

---

*Engram mirror: topic `sdd/53-varias-cuentas-connect/explore` (observation 4530). This file was materialized by the orchestrator from that observation to restore hybrid parity.*
