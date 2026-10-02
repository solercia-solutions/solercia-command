# Proposal: 47 · Operational Solercia Connect connection

## Decision

Present Microsoft 365 as one Command provider backed by Solercia Connect. Command owns product configuration and scheduling; Connect owns execution, authentication, tokens, cookies, and browser state.

## Relationships

- `supersedes: [38-oauth-ms-google]`
- `amends: [39-conector-capacidades]`
- `conflicts: []`
- Follow-up: replace change 39's dependency on 38 with 47; only the orchestrator edits `state.yaml`.

## Intent

Users need a real Outlook connection from `/connections`. Duplicate creation becomes HTTP 500, Connect lacks a lifecycle path, and failures appear as a generic inline error.

## Scope

### Slice 1

- Idempotently reuse the organization’s Microsoft 365 connector.
- Persist target-aware bindings, keeping Outlook distinct from future Teams/OneDrive bindings for the same account.
- Show durable status and route (`official` or `browser_fallback`) on the card.
- Try official first; only an eligible typed outcome reveals an explicit per-attempt browser fallback.
- Amend the platform ADR and add a bounded Connect HTTP contract to create/poll/cancel an opaque interactive session. Connect launches headed Playwright; Command never requests, stores, returns, or logs passwords, MFA, provider tokens, cookies, or browser state.
- Support Command container → `host.docker.internal:8765` → host-run Connect.
- Replace inline transient errors with adapted boki-front stacked, accessible, auto-dismissing toasts; durable state remains on the card.

### Deferred / Non-goals

- Cadence and functions (`obtain_emails`, `obtain_transcripts`) become a dependent change after target bindings are proven.
- OneDrive/TAREAS ingestion, provider writes, background sync, and non-Microsoft browser fallback.

## Capabilities

### New Capabilities

- `solercia-connect-connection-lifecycle`: versioned official-first and bounded interactive-session contract across both products.

### Modified Capabilities

- `connectors`: Microsoft 365 identity, target-aware state, idempotency, route visibility, fallback, and toast feedback.

## Approach

Command persists tenant-scoped lifecycle through semantic repositories; the use case owns transactions. Its Connect adapter consumes versioned DTOs and typed reasons. Connect owns session state and exposes no secret material. Slice 1 proves Outlook only.

## Cross-repository Impact

| Area | Change |
|---|---|
| Command connector backend and Connect adapter | Bindings, lifecycle, idempotency, client |
| Command connections page and Compose | Card, toasts, host endpoint |
| Connect `src/solercia_connect/` | Session API and browser ownership |
| Platform ADR | Amendment |

## Risks, Rollout, Rollback

Use opaque IDs, allowlisted reasons, bounded TTLs, redacted logs, capability preflight, and PostgreSQL migration tests. Roll out official-only behind a flag, then enable local fallback. Roll back by disabling fallback and reverting clients; preserve bindings and official routing.

## Success Measures

- Duplicate Microsoft 365 creation never returns an internal error.
- Outlook status and route survive refresh.
- Eligible failure offers exactly one explicit fallback attempt.
- Password/MFA entry occurs only in the Connect-owned Microsoft page.
- Transient outcomes auto-dismiss without erasing card state.
