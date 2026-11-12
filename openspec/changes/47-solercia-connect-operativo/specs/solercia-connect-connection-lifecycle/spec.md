# Solercia Connect Connection Lifecycle Specification

## Purpose

Versioned, tenant-safe Command↔host Connect lifecycle for Outlook-first connections.

## Requirements

### Requirement: Versioned official-first contract and preflight
Connect MUST add lifecycle routes under its existing `/v1` service and preserve the `solercia.connect/v1` envelope fields `schema,ok,operation,status,provider,account,route,data,receipt,error`. Every lifecycle route MUST require `X-Solercia-Connect-Key`; absent or invalid keys return `401 api_authentication_required`. Requests MUST reject extra fields.

- Preflight MUST be `POST /v1/connection-preflight` with `solercia.connect/connection-preflight-request/v1 {type,account}` and return `solercia.connect/connection-preflight/v1 {ready,official_available,browser_available,missing_configuration,reason_code}`: `200 ready`, `422 invalid_input|contract_version_unsupported`, or `503 configuration_invalid|not_ready`.
- Create MUST be `POST /v1/connection-sessions` with `solercia.connect/connection-session-request/v1 {type,account,binding_ref,idempotency_key,expected_lifecycle_version,ttl_seconds?,attempt,parent_session_id?,fallback_capability?}`: `fallback_capability` is forbidden for `attempt=official`, required for `attempt=browser`, and server-to-server only; responses are `202` new, `200` identical retry, `409 idempotency_conflict|session_already_active|fallback_disabled`, `410 semantic_replay_rejected`, `429 session_capacity_exceeded`, or `503 lifecycle_disabled|session_store_busy`.
- Status MUST be `GET /v1/connection-sessions/{session_id}` with no body: `200`, `404 session_not_found`, `410 session_retired`, or `503 session_store_busy`.
- Cancel MUST be `POST /v1/connection-sessions/{session_id}/cancel` with `solercia.connect/connection-session-cancel-request/v1 {idempotency_key,expected_lifecycle_version}`: `200`, `404 session_not_found`, `409 session_terminal|session_version_conflict`, `410 session_retired`, or `503 session_store_busy`.

Successful lifecycle data MUST use `solercia.connect/connection-session/v1 {session_id,event_id,state,route,reason_code,terminal,fallback_available,fallback_capability?,expires_at,poll_after_ms,observed_account?,lifecycle_version,updated_at}`. `fallback_capability` MAY appear only on eligible official terminal status over the API-key channel and only until expiry/consumption so a lost transport response is retryable; Command MUST strip it from its facade. States MUST be `queued|authorizing|action_required|browser_opened|connected|failed|expired|cancelled`; the last four are terminal. Provider outcomes MUST remain typed session data, not transport errors. An error MUST expose only `code,message,retryable,missing_configuration[],remediation[],cause_category`; failure `data` MUST be only `solercia.connect/lifecycle-error/v1 {event_id,session_id?}`. Unexpected upstream failure is redacted `502 provider_unavailable`.

#### Scenario: Offline or misconfigured preflight
- GIVEN Connect is unreachable, or endpoint/API key is absent or invalid
- WHEN preflight runs
- THEN it returns typed `offline` or `misconfigured` and does not start a session

#### Scenario: Version mismatch
- GIVEN Command and Connect advertise incompatible contract versions
- WHEN any lifecycle operation is called
- THEN a typed version-mismatch error is returned without mutation

#### Scenario: Official completion
- GIVEN valid preflight and authorized Microsoft binding
- WHEN official start then status polling completes
- THEN status is `connected`, route is `official`, and the binding is durable

### Requirement: Secret boundary
Passwords, MFA, cookies, provider tokens, browser state, API keys, and fallback capabilities MUST never enter Angular forms/DTOs/responses or logs. Provider secrets stay only in Connect's Microsoft page/runtime; Command may retain only the encrypted server-side fallback grant described below.

#### Scenario: Secret-free contract and logs
- GIVEN official or fallback operation traffic
- WHEN requests, responses, schemas, database records, and logs are inspected
- THEN no password, MFA, provider token, cookie, browser-state, API-key, or fallback-capability value appears outside the API-key-protected Command↔Connect transport and the two approved encrypted server stores

### Requirement: Bounded interactive lifecycle
Fallback requires a server-derived allowlisted reason and explicit per-attempt authorization. Opaque sessions MUST support start/status/cancel with a configurable `600s` default and `900s` maximum TTL, `1000ms` poll interval, `5s` per-poll HTTP timeout, four-session global executor capacity, and exact `(type, canonical_account)` single-flight concurrency across routes. Connect launches headed Playwright on the host.

On an eligible official terminal transition, Connect MUST generate 256 random bits and store its SHA-256 digest plus Fernet ciphertext under required `SOLERCIA_CONNECT_FALLBACK_CAPABILITY_KEY: SecretValue`, bound to `binding_ref,type,canonical_account,parent_session_id,expires_at=now+900s,consumed_at=NULL`. Eligible authenticated status MAY decrypt/return it until consumption so transport retry is idempotent. Browser admission MUST hash the presented capability and, inside the same `BEGIN IMMEDIATE`, constant-time compare every bound field, reject expiry/replay, set `consumed_at`, clear ciphertext, and insert the child session. Plaintext MUST never enter logs, audit, fixtures, or tombstones.

The private SQLite store MUST use `${XDG_STATE_HOME:-~/.local/state}/solercia-connect/connection-sessions.sqlite3`. It MUST open every component from filesystem root with retained `O_DIRECTORY|O_NOFOLLOW` descriptors and require directory, owner root/euid, no symlink, and no group/world write; missing state subdirectories MAY be created only below a verified euid-owned descriptor with mode `0700`. It MUST open the DB through the parent descriptor with `O_NOFOLLOW|O_CLOEXEC`; new files additionally use `O_CREAT|O_EXCL` and mode `0600`. Pre-schema and post-open `fstat` MUST match device/inode and require regular file, owner=euid, mode `0600`, and link-count one. SQLite MUST use the retained descriptor with `journal_mode=DELETE`; unsupported secure-descriptor access, mismatch, corruption, or race MUST return `503 session_store_unsafe`. The runtime MUST NOT chmod, replace, quarantine, repair, or use an insecure fallback.

Transactional `PRAGMA user_version` migrations MUST finish before readiness. `sessions` MUST have TEXT PK `session_id`; required TEXT `type,canonical_account,binding_ref,intent_fingerprint,state,event_id`; nullable TEXT `route,reason_code,fallback_capability_hash,fallback_capability_ciphertext,observed_account,parent_session_id`; required INTEGER `terminal DEFAULT 0,lifecycle_version,expires_at,created_at,updated_at`; and nullable INTEGER `terminal_at,fallback_capability_expires_at,fallback_capability_consumed_at`. `idempotency_keys` MUST have TEXT PK `key_hash`, required TEXT `fingerprint,operation,session_id`, nullable TEXT `safe_terminal_snapshot`, and required INTEGER `created_at,expires_at`. It MUST create `UNIQUE(type,canonical_account) WHERE state IN ('queued','authorizing','action_required','browser_opened')`, a unique key-hash index, and indexes for session/idempotency expiry, `session_id`, and fingerprint.

Admission MUST use `BEGIN IMMEDIATE` to resolve idempotency, active tuple, global count `<4`, and both inserts atomically. SQLite lock waiting MUST use `busy_timeout=250ms` and at most three retries delayed `25/50/100ms`, then `503 session_store_busy`. Transitions and cancel MUST compare-and-swap on `lifecycle_version`; a zero-row update reloads the winner or returns `409 session_version_conflict`.

Full terminal rows MUST remain 24 hours; 30-day idempotency tombstones MUST retain only a safe terminal snapshot. Same-key/fingerprint replay MUST return that snapshot after row purge. Direct status during days 1–30 MUST return `410 session_retired` with `session_id,state,terminal_at`; after tombstone expiry it MUST return `404 session_not_found`. Cleanup runs every 15 minutes; compaction runs only with zero active sessions and more than 20% free pages. Corruption MUST leave bytes untouched and keep the service unready until explicit operator recovery.

#### Scenario: Authorized single fallback
- GIVEN an allowlisted official failure from the server
- WHEN the user explicitly authorizes fallback once
- THEN exactly one headed browser session starts

#### Scenario: Replay and concurrent start
- GIVEN an authorized session is active, terminal, or its fallback authorization is consumed
- WHEN transport retries with the same idempotency key and fingerprint, or a new semantic start is attempted
- THEN the transport retry returns the same session, while active tuple conflict returns `409` and consumed/terminal semantic replay returns `410`; no second session starts

#### Scenario: Expiry, cancellation, terminal poll
- GIVEN a session expires or is cancelled
- WHEN status is polled or cancel is replayed
- THEN status returns canonical terminal `expired` or `cancelled`; identical-key cancel returns the same `cancelled` result, new-key terminal cancel returns `409 session_terminal`, and the session cannot restart

### Requirement: Permissions, tenant isolation, compatibility, rollback
Lifecycle operations MUST enforce tenant and caller authorization, redact secrets, and support a rollback flag disabling fallback while preserving official bindings.

Connect `AGENTS.md`, `docs/ARCHITECTURE.md`, `SECURITY.md`, and the platform decision record MUST state that general `/v1/run` remains non-interactive while only API-key-protected lifecycle routes may enqueue bounded local authorization. Those amendments MUST make official-first routing, explicit per-attempt Microsoft fallback, provider-page-only password/MFA, secure SessionStore controls, atomic admission, cancellation, and retention normative, explicitly replacing any claim that every FastAPI service operation is non-interactive.

#### Scenario: Unauthorized or cross-tenant operation
- GIVEN a caller lacks permission or references another tenant's binding
- WHEN lifecycle start/status/cancel is called
- THEN a typed authorization/not-found response is returned with no disclosure

#### Scenario: Rollback preserves official
- GIVEN rollback fallback is enabled after an official connection exists
- WHEN an official failure occurs
- THEN fallback is not offered and the official binding remains intact
