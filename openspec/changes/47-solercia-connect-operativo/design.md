# Design: 47 · Operational Solercia Connect connection

## Technical approach

Angular calls only authenticated Command APIs. Command owns tenant/RBAC, durable binding/audit state, Connect API key, and encrypted fallback grants; Connect owns OAuth/provider secrets, supervised browser, and bounded sessions. `provider=microsoft365`, `target=outlook_mail`, Connect `type=outlook`, and execution `provider_id=microsoft.graph` remain distinct. Graph is primary; browser is explicit fallback.

## Architecture decisions

| Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|
| Browser boundary | Command→Connect lifecycle HTTP | Angular→Connect/CLI | Hides key and provider secrets. |
| Fallback authority | Connect-issued 256-bit capability; hash+ciphertext in Connect, Fernet ciphertext in Command Redis | Browser token in Angular | One use, tuple-bound, server-only, retryable transport. |
| Microsoft routing | Target-aware router | Replace global registry | Supports controlled legacy drain. |
| Transactions | Use-case/UoW commits | Repository commits | Atomic binding+audit writes. |
| Sessions | Secured SQLite | Memory/Redis | Durable local replay. |
| Audit | Append-only PostgreSQL table | Logs | Tenant-queryable 365-day evidence. |
| Toasts | App-owned alert store/service/center using `@solercia/ui` primitives | Persistent notifications | Transient, accessible stacking. |

## End-to-end flow

`/connections` → Command JWT/RBAC → Connect preflight → official childless start → poll. Eligible typed terminal failure makes Connect store a tuple-bound capability hash+ciphertext and return plaintext only over the API-key channel until expiry/consumption; Command encrypts it in Redis for ≤900s and returns only `fallback_available`. Explicit click sends `{attempt=browser,parent_session_id}` to Command; Command loads/decrypts the tuple-matched grant and starts a new Connect child session. Connect atomically consumes it before headed Playwright. Password/MFA remain on Microsoft’s page. Network never runs inside PostgreSQL transactions.

## Contracts and persistence

The two delta specs are normative for exact Connect `/v1` envelopes, Command facade/RBAC/DTO/error mapping, 600/900-second TTL, capacity four, single-flight, CAS, replay/cancel, 24-hour rows/30-day tombstones, capability fields, and redaction. Angular start DTO deliberately excludes `fallback_capability`.

Migration `0026` follows the connectors spec’s reversible recipe: exact columns/defaults, canonical legacy backfill, preflight collision abort, `outlook↔outlook_mail`, constraint/index replacement, audit table, and guarded downgrade. `ConnectionLifecycleEvent` writes in TxA/TxB with the binding; daily maintenance purges locked batches older than 365 days. SessionStore follows the lifecycle spec’s descriptor-relative `O_NOFOLLOW`, ownership/mode/link, pre/post-open identity, no-repair, atomic-admission, and corruption controls.

`backend/app/config.py` adds `SOLERCIA_CONNECT_LIFECYCLE_ENABLED=false`, `SOLERCIA_CONNECT_BROWSER_FALLBACK_ENABLED=false`, `MICROSOFT_DIRECT_OAUTH_LEGACY_READ_ENABLED=true`, `SOLERCIA_CONNECT_BASE_URL`, `SOLERCIA_CONNECT_LIFECYCLE_TIMEOUT_SECONDS=5`, and `SOLERCIA_CONNECT_API_KEY: SecretStr`; Connect adds `SOLERCIA_CONNECT_FALLBACK_CAPABILITY_KEY: SecretValue`, required only when fallback is enabled. `backend/app/db_init.py` registers routing/Connect and removes the `microsoft365` import only at phase D after zero legacy rows plus OAuth-state TTL drain. `docker-compose.yml` passes Command flags/key/base URL and adds `extra_hosts: host.docker.internal:host-gateway`; Connect remains a separately configured host process, never a Command container.

## Exact file map

| Repository | Files |
|---|---|
| Command | `backend/app/config.py`; `backend/app/db_init.py`; `docker-compose.yml`; `backend/app/modules/connectors/models.py`; `backend/app/modules/connectors/ports.py`; `backend/app/modules/connectors/repository.py`; `backend/app/modules/connectors/unit_of_work.py`; `backend/app/modules/connectors/service.py`; `backend/app/modules/connectors/router.py`; `backend/app/modules/connectors/schemas.py`; `backend/app/integrations/routing.py`; `backend/app/integrations/adapters/solercia_connect/client.py`; `backend/app/integrations/adapters/solercia_connect/adapter.py`; `backend/app/integrations/adapters/solercia_connect/errors.py`; `backend/app/integrations/adapters/solercia_connect/mapper.py`; historical `backend/app/integrations/adapters/microsoft365/adapter.py`; `backend/app/integrations/adapters/microsoft365/client.py`; `backend/app/integrations/adapters/microsoft365/errors.py`; `backend/app/integrations/adapters/microsoft365/mappers.py`; `backend/app/integrations/adapters/microsoft365/oauth.py`; `backend/app/integrations/adapters/microsoft365/ports.py`; `backend/app/maintenance/connection_lifecycle_events.py`; `backend/alembic/versions/0026_add_connector_lifecycle.py`; `backend/tests/test_connector_lifecycle.py`; `backend/tests/test_connector_migration.py`; `backend/tests/test_connector_audit.py`; `frontend/src/entities/connector/connector.model.ts`; `frontend/src/entities/connector/connectors.service.ts`; `frontend/src/pages/connections/connections.component.ts`; `frontend/src/pages/connections/connections.component.spec.ts`; `frontend/src/shared/lib/alerts/alert.model.ts`; `frontend/src/shared/lib/alerts/alert.store.ts`; `frontend/src/shared/lib/alerts/alert.store.spec.ts`; `frontend/src/shared/lib/alerts/alert.service.ts`; `frontend/src/shared/lib/alerts/alert.service.spec.ts`; `frontend/src/widgets/alert-center/alert-center.component.ts`; `frontend/src/widgets/alert-center/alert-center.component.spec.ts`; `frontend/src/app/app.component.ts`; `frontend/src/app/app.component.spec.ts`; `docs/decisions/2026-08-23-solercia-platform-decisions.md`. |
| Connect | `src/solercia_connect/config.py`; `src/solercia_connect/domain.py`; `src/solercia_connect/service.py`; `src/solercia_connect/sessions.py`; `src/solercia_connect/session_store.py`; `tests/test_connection_lifecycle_api.py`; `tests/test_session_store.py`; `tests/test_connection_lifecycle_security.py`; `AGENTS.md`; `docs/ARCHITECTURE.md`; `SECURITY.md`; `docs/decisions/2026-08-23-solercia-platform-decisions.md`. |

Connect documents preserve noninteractive `/v1/run` while defining the bounded API-key lifecycle exception, worker flow, official-first policy, secret/store controls, rollback, and consequences.

## Threat matrix

| Boundary | Decision/test |
|---|---|
| Documentation paths, Git selection, commit, push, PR | N/A: no executable/VCS automation. |
| Browser process | Typed allowlisted arguments, never shell; RED tests injection, duplicate capacity, timeout/cancel cleanup. |

## Testing strategy

Unit: canonicalization, DTO exclusion, RBAC/error translation, grant encryption/tuple match, redaction, alert dedupe/timer/live-region/keyboard/reduced-motion. Integration: real PostgreSQL upgrade/backfill/collision/constraint/downgrade, UoW audit atomicity and 365-day purge; SQLite concurrent admission, capacity, CAS, cancel/replay/tombstones, symlink/owner/mode/race/corruption. E2E: Angular→Command official completion and explicit fallback, stacked toasts, durable refresh, and absence of key/password/MFA/capability across DTOs, DB, logs, UI, forms, fixtures.

Independent validation remains required before tasks.
