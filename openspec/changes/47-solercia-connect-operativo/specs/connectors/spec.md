# Delta for connectors

## MODIFIED Requirements

### Requirement: CRUD de conectores con permisos por rol

Create/update/delete MUST require admin or manager; reads MUST be tenant-scoped. `create_connector` MUST canonicalize provider with `strip().casefold()` before lookup/write, then `SELECT ... FOR UPDATE` by `(organization_id, canonical_provider)` including inactive rows. No match MUST insert with `201`. Compatibility MUST mean equal `credential_kind`, canonical sorted/deduplicated scopes, and JCS-normalized non-secret settings. An equivalent active Microsoft 365 connector MUST return the same ID with `200` and `meta.reused=true`. A compatible soft-deleted match MUST set `is_active=true`, `deleted_at=NULL`, `status=active` on the same ID and return `200` with `meta.reactivated=true`. A tenant-local incompatible match MUST return `409 connector_configuration_conflict`, never `500`. Every lookup and retry MUST keep the tenant predicate; foreign rows and database constraint details MUST NOT be disclosed. Only expected `uq_connectors_organization_provider` races use the idempotent reread; other integrity failures MUST remain redacted internal errors.

(Previously: duplicate behavior was undefined.)

#### Scenario: Equivalent duplicate is idempotent
- GIVEN an active equivalent Microsoft 365 connector, or two equivalent creates racing in one organization
- WHEN an authorized user repeats creation, or the losing insert flush raises `IntegrityError`
- THEN the existing connector ID is returned with `200` and `meta.reused=true`; the losing transaction rolls back and tenant-scoped re-reads in a new transaction

#### Scenario: Incompatible duplicate is typed
- GIVEN an existing connector with incompatible configuration
- WHEN creation is requested
- THEN the API returns generic `409 connector_configuration_conflict`, never `500` or database details

#### Scenario: Soft-deleted match and foreign match
- GIVEN a compatible soft-deleted connector, or a matching connector in another tenant
- WHEN creation is requested
- THEN the former reactivates the same ID with `meta.reactivated=true`, while the latter is excluded and not disclosed

### Requirement: Varias cuentas del mismo proveedor por usuario

Accounts MUST be target-aware; uniqueness is by connector, external identity, and target, not user/provider alone.

Migration `0026` MUST add `canonical_account VARCHAR(255)`, `target VARCHAR(50)`, `connection_route VARCHAR(20) NULL`, `connection_state VARCHAR(20)`, `reason_code VARCHAR(64) NULL`, and `lifecycle_version BIGINT`. Before DDL/DML, upgrade MUST compute `external_account_id.strip().casefold()` in Python, reject blank/overlength values, and abort with offending IDs if `(connector_id,canonical_account,'legacy')` collides. It then adds required columns nullable with temporary `target='legacy'` and retained server defaults `connection_state='disconnected'`, `lifecycle_version=0`; backfills every row as `target='legacy'`, `connection_route='legacy_oauth'` only for Microsoft 365 rows with credentials, and `connection_state='connected'` only when credentials exist. It MUST drop `uq_connected_accounts_connector_external`, create `uq_connected_accounts_connector_account_target` on `(connector_id,canonical_account,target)` and `ix_connected_accounts_connector_target_state` on `(connector_id,target,connection_state)`, make required columns NOT NULL, and remove the temporary `target` default. API/Connect mapping is exactly `type=outlook` ↔ `target=outlook_mail`; new inputs use `strip().casefold()`. Downgrade MUST reject when any target is not `legacy`, any lifecycle version is nonzero, lifecycle events exist, or projection onto `(connector_id,external_account_id)` collides; only then may it restore the old constraint and drop the new index/columns/table.

#### Scenario: Same account, distinct targets
- GIVEN an account bound to Outlook mail
- WHEN the same account is bound to another target
- THEN a distinct binding is persisted without collision

## ADDED Requirements

### Requirement: Durable connection state and route
`/connections` MUST present Microsoft 365 with account, durable state, start/reconnect, and method `Official` or `Solercia Connect — supervised browser`. Angular MUST call only these JWT-authenticated Command endpoints and MUST never receive the Connect API key:

- `POST /api/v1/connectors/{connector_id}/connection/preflight` with `{account,target}`;
- `POST /api/v1/connectors/{connector_id}/connection-sessions` with `Idempotency-Key` and `{account,target,attempt,parent_session_id?}`;
- `GET /api/v1/connectors/{connector_id}/connection-sessions/{session_id}`;
- `POST /api/v1/connectors/{connector_id}/connection-sessions/{session_id}/cancel` with `Idempotency-Key` and `{expected_lifecycle_version}`.

Preflight MUST require authenticated membership and a tenant-scoped connector. Start/status/cancel MUST permit a member only for their own binding and admin/manager for any binding in the organization; foreign tenant MUST be `404`, same-tenant non-owner MUST be `403`. Request DTOs MUST reject extra fields. `ConnectionPreflightRead` and `ConnectionLifecycleRead` MUST expose only binding/session/state/route/reason/expiry/poll/version/event fields.

Command MUST inject `X-Solercia-Connect-Key` from server settings and allowlist translations: Connect `401→503 connect_service_misconfigured`; version `422→503 connect_contract_mismatch`; validation `422→422 connection_request_invalid`; safe lifecycle `404/409/410/429` preserve status/code; `502/503→503 connect_unavailable`. Raw Connect messages MUST be discarded.

Fallback capability MUST be server-only. Eligible official terminal status MAY return a one-use 256-bit opaque capability over the API-key channel until expiry/consumption. Command MUST Fernet-encrypt it in Redis at `connect:fallback:{organization_id}:{connector_id}:{canonical_account}:{parent_session_id}` with at most 900-second TTL and metadata binding the same tuple; Angular receives only `fallback_available=true`. Exact flow is Angular preflight → Command/Connect preflight → official start/poll → eligible typed failure → explicit user click → browser start with `{attempt=browser,parent_session_id}` → Command decrypts and forwards the capability → Connect hashes, tuple-checks, consumes atomically, and creates a new child session. Missing, expired, mismatched, or replayed capability returns safe `409 fallback_disabled` or `410 semantic_replay_rejected` without starting a browser.

`MicrosoftIntegrationRouter` MUST resolve `provider=microsoft365,target=outlook_mail` to Solercia Connect lifecycle/read ports and `target=legacy` to the historical adapter only while `MICROSOFT_DIRECT_OAUTH_LEGACY_READ_ENABLED`. Migration MUST backfill legacy, promote verified Connect bindings, retire legacy `ConnectionCredentials` transactionally, then disable direct authorize/callback and deregister/remove the historical adapter only after zero active legacy rows and the OAuth-state TTL has drained. Before credential retirement rollback MAY reactivate legacy; afterward reconnect through Connect is required.

SQLAlchemy `ConnectionLifecycleEvent` MUST map append-only `connection_lifecycle_events`: UUID PK `id`; required `organization_id` FK/CASCADE; required snapshot UUID `binding_id` without FK so evidence survives; nullable `actor_id` FK/SET NULL; `actor_kind VARCHAR(16),event_type VARCHAR(40),lifecycle_version BIGINT`; nullable `route VARCHAR(32),reason_code VARCHAR(64),session_ref_hash CHAR(64)`; and `occurred_at TIMESTAMPTZ`. CHECKs MUST allow only user/system actor consistency and the approved event allowlist. It MUST index `(organization_id,occurred_at DESC)`, `(binding_id,occurred_at DESC)`, and `occurred_at`, plus unique `(organization_id,binding_id,lifecycle_version,event_type)`. Its semantic repository MUST only flush; TxA/TxB MUST append in the same use-case transaction as binding changes. A non-HTTP daily maintenance job MUST purge batches of 1,000 older than 365 days using a CTE with `FOR UPDATE SKIP LOCKED`.

#### Scenario: Official completion persists
- GIVEN Angular starts Microsoft 365 through the authorized Command facade and official status completes
- WHEN the card is refreshed
- THEN it shows account, durable `connected`, method `Official`, and a lifecycle audit event without exposing the Connect API key or provider secrets

### Requirement: Official-first fallback and safe UX
Only an allowlisted server-derived official outcome MAY expose one explicit fallback attempt; clients MUST NOT self-assert eligibility. The method label MUST become `Solercia Connect — supervised browser` only after that explicit attempt starts. Password and MFA MUST appear only on Microsoft's Connect-owned page. A transient lifecycle error MUST provide a secret-free `event_id`, safe `message`, typed `code`, `retryable=true`, `cause_category`, and `remediation[]`. Because installed `@solercia/ui` exposes alert theme/icon primitives but no runtime alert service, Command MUST use app-owned `AlertStore`, `AlertService`, and `AlertCenterComponent`, mounted once in `app.component.ts`, styled with `@solercia/ui`. It MUST stack errors, deduplicate only `(binding_id,event_id)`, auto-dismiss after eight seconds with cancel-safe timers, expose live-region/keyboard dismissal, respect reduced motion, and never write lifecycle errors to the persistent notification panel.

#### Scenario: Ineligible client assertion
- GIVEN the client claims fallback eligibility without an allowlisted server reason
- WHEN fallback is requested
- THEN Connect rejects it and no browser session starts

#### Scenario: Toast accessibility
- GIVEN transient lifecycle outcomes
- WHEN multiple outcomes arrive
- THEN they stack, auto-dismiss, preserve durable card state, support keyboard/screen readers, and respect reduced motion
