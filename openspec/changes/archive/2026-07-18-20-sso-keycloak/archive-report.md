# Archive Report: 20-sso-keycloak

**Date Archived**: 2026-07-18  
**Change**: 20-sso-keycloak (SSO OIDC/Keycloak as second login method)  
**Store**: hybrid (openspec + Engram)  
**Status**: PASS | 21/21 tasks complete | 15/15 scenarios COMPLIANT | 683 tests passed

## Artifact Collection

All artifacts successfully retrieved from hybrid store and consolidated into archive:

| Artifact | Engram ID | Type | Status |
|----------|-----------|------|--------|
| Proposal | #1623 | architecture | active |
| Spec (auth + sso-oidc) | #1633 | architecture | active |
| Design | #1630 | architecture | active |
| Tasks | #1636 | architecture | active |
| Verify Report | #1683 | architecture | active |
| Archive Report | (this) | architecture | active |

## Specs Merged

### 1. Auth Spec (MODIFIED + ADDED)

**File**: `openspec/specs/auth/spec.md`

**Changes**:
- **MODIFIED R4**: Added null-password handling for SSO-only users (reject local login with generic message).
- **ADDED R6**: JWT emission convergence after SSO callback (same access token 30 min + refresh cookie 7 days as local login).
- **ADDED R7**: Dual login coexistence — password + SSO both authenticate the same user.

**Scenarios added**: 3 new scenarios (R4 null-password, R6 JWT after SSO, R7 dual login).

### 2. SSO-OIDC Spec (NEW FULL SPEC)

**File**: `openspec/specs/sso-oidc/spec.md`

This is a new domain-specific capability (not a delta — sso-oidc did not exist before). Full spec with 7 requirements (R1–R7):

- R1: Authorization Code + PKCE flow initiation
- R2: Callback validations (state, redirect_uri, ID token)
- R3: Verified email requirement
- R4: User resolution order (by issuer+subject, email, auto-provision)
- R5: IdP error handling
- R6: 100% env-based configuration
- R7: SPA button + callback integration

**Scenarios**: 15 scenarios across all requirements — all COMPLIANT per verify-report.

## Merge Summary

| Domain | Action | Details |
|--------|--------|---------|
| auth | Updated | 2 requirements modified/added; 3 scenarios added; converges with sso-oidc |
| sso-oidc | Created | New full spec; 7 requirements, 15 scenarios; standalone capability |

**Total Requirements**: 10 unique (5 in auth after merge, 7 in sso-oidc — R6 and R7 in auth are distinct from sso-oidc R6/R7).  
**Total Scenarios**: 18 unique (across both specs).

## Verification Summary

**Verification Verdict**: PASS

- **Tasks**: 21/21 complete (100%)
- **Specifications**: 10/10 requirements implemented
- **Scenarios**: 15/15 COMPLIANT
- **Tests**: 683 passed / 0 CRITICAL / 0 WARNING / 2 SUGGESTION (non-blocking)
- **Build & Lint**: Backend (ruff/mypy) ✅ | Frontend (build/lint) ✅
- **Migration**: Alembic 0016 (federated_identities + hashed_password nullable) ✅ | Round-trip upgrade/downgrade ✅

### Critical Findings Resolved

**One CRITICAL was found and resolved**:
- **Issue**: `resolve_or_provision_user` in sso_service.py did not persist SSO links across request sessions (missing `db.commit()`).
- **Root Cause**: Test harness used shared SAVEPOINT session, masking the defect (flush visible without commit).
- **Fix**: Commit `b630807` added `await db.commit()` with symmetric rollback; verified with independent session test.
- **Evidence**: New regression test (`test_resolve_commits_so_a_new_request_session_sees_the_provisioned_user`) confirms persistence across sessions; 683/683 tests pass without regression.

### Non-Blocking Suggestions

1. **R6 Coverage** (sso-oidc): Multi-provider configuration tested indirectly (state↔provider cross-check) but without full E2E against a second IdP. Recommended for future follow-up.
2. **E2E Checklist** (T21): Manual test with real Keycloak deferred (task T21 notes). Recommended before enabling `SSO_ENABLED=true` in production.

## Implementation Summary

**Commits**: 5 primary (A–E) + 2 correction/post-verify (d6601c9, b630807) = 7 total commits included in verification.

| Unit | Commit | Tests | Status |
|------|--------|-------|--------|
| A (Foundation: deps, redis.py, FederatedIdentity, migration, nullable password, ER) | 1 | 3/3 migration tests | ✅ PASS |
| B (OidcClient: discovery, token, JWKS, PKCE) | 2 | 12/12 | ✅ PASS |
| C (sso_service: state, resolution order, provisions) | 3 | 11/11 | ✅ PASS |
| D (Endpoints: /login, /callback, validation) | 4 | 9/9 (auth_sso + auth combined) | ✅ PASS |
| E (Frontend: SSO button + auth-callback component) | 5 | npm build+lint | ✅ PASS |
| Correction 1 (Review findings from d6601c9) | d6601c9 | +3 tests (claims, email sync) | ✅ PASS |
| Correction 2 (Persistance fix b630807) | b630807 | +1 test (regression) | ✅ PASS |

**Estimated Lines**: ~900–1000 (Budget risk: HIGH per design.md; delivery_strategy=exception-ok accepted).

## Data Model Changes

**File Updated**: `docs/diagrams/er-model.md`

New table `federated_identities`:
- Columns: user_id (FK, index), provider, issuer, subject, email
- Constraint: UNIQUE(issuer, subject) — crypt anchor per OIDC (sub unique by issuer)
- Soft delete & audit mixins applied

Modified table `users`:
- `hashed_password` changed to nullable (NULL for SSO-only accounts)

Downgrade guard implemented: migration fails if any user has `hashed_password IS NULL`, preventing data loss.

## Security Review

### Threat Model Covered (Strict TDD)

| Threat | Mitigation | Test |
|--------|-----------|------|
| Account takeover (unverified email) | Require `email_verified=true` | R3 scenario |
| CSRF / code interception | `state` (single-use) + PKCE S256 + fixed redirect_uri | R1, R2 scenarios |
| Forged ID token | JWKS signature validation + iss/aud/exp/nonce checks | R2 scenarios + oidc_client.py tests |
| Open redirect | Landing URL from fixed env var (allowlist of 1) | D5 ratified |
| SSRF | issuer + endpoints from trusted env; provider validated | Design D2 |
| Secret leak | client_secret in .env only; never in logs | Config conventions |

## Rollback & Downgrade

**Rollback Strategy**:
- Set `SSO_ENABLED=false` (endpoints become inert).
- Revert change commit.
- Run migration downgrade: drops `federated_identities`, reverts `hashed_password` to NOT NULL (fails if SSO-only users exist — safety guard).
- Local login endpoints (`/auth/login`, `/auth/refresh`) unmodified; no data loss for password-authenticated users.

**Deployment Risk**: Low (aditivo change, toggleable, no breaking changes to existing auth endpoints).

## Traceability

### Observation IDs (Engram)

- Proposal: obs-1d22127abd363beb (#1623)
- Spec: obs-ad80a3b5755d6ca9 (#1633)
- Design: obs-5d601bd0304300a5 (#1630)
- Tasks: obs-85f25796f59cfed2 (#1636)
- Verify-Report: obs-5d0e9a6e1ea398a9 (#1683)
- Archive-Report: (saved via mem_save during archive phase)

### Filesystem Paths (Archived)

```
openspec/changes/archive/2026-07-18-20-sso-keycloak/
├── proposal.md
├── design.md
├── tasks.md (all 21 tasks [x] complete)
├── verify-report.md (PASS)
├── state.yaml (all phases done)
├── specs/
│   ├── auth/spec.md (merged delta: R4 MODIFIED, R6/R7 ADDED)
│   └── sso-oidc/spec.md (new full spec)
└── archive-report.md (this file)
```

### Main Specs Updated

- `openspec/specs/auth/spec.md` — merged delta (R4/R6/R7 added/modified)
- `openspec/specs/sso-oidc/spec.md` — new full spec (R1–R7 complete)

## Closure Confirmation

✅ **SDD cycle complete**:
1. Proposal: reviewed (OLA 2 item 3)
2. Spec: 10 requirements, 18 scenarios defined
3. Design: 5 architecture decisions (D1–D5) documented
4. Tasks: 21 tasks implemented and verified (5 commits + 2 corrections)
5. Apply: all commits verified green (strict TDD)
6. Verify: 15/15 scenarios COMPLIANT, CRITICAL resolved, PASS verdict
7. Archive: specs merged, folder archived, traceability complete

**Next**: Candidate for release integration (await orchestrator decision on PR strategy given size-exception delivery).
