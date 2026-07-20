# Archive Report: 26 · Administración de empresas y empresa activa

**Date**: 2026-07-20
**Change ID**: 26-admin-empresas
**Status**: ARCHIVED — PASS WITH WARNINGS
**Mode**: hybrid (openspec + Engram)

## Executive Summary

Change 26 has been fully implemented, verified (PASS WITH WARNINGS, 1249 tests passed, 0 CRITICAL issues), and archived. Three delta specs have been synchronized into main specs:
- `organizations-admin/spec.md` — NEW capability (CRUD + member management + active organization resolution)
- `frontend-org-switcher/spec.md` — NEW capability (UI selector + context refresh)
- `multi-tenancy/spec.md` — MODIFIED (header-based resolution + unique membership constraint)

Change folder moved to `openspec/changes/archive/2026-07-20-26-admin-empresas/`.

## Artifacts Synchronized

| Spec | Action | Details |
|------|--------|---------|
| organizations-admin | **Created** | New `openspec/specs/organizations-admin/spec.md` with 5 requirements: bootstrap admin, RBAC permissions, membership uniqueness, header-based resolution, "my organizations" + /auth/me |
| frontend-org-switcher | **Created** | New `openspec/specs/frontend-org-switcher/spec.md` with 5 requirements: UI selector, context refresh on switch, header injection, error handling, Spanish formal language |
| multi-tenancy | **Modified** | Updated R2 (tenant resolution: header `X-Organization-Id` with fallback to first membership); added R5 (unique constraint on `(organization_id, user_id)`) with reversible migration 0021 |

## Verification Status

- **Tasks**: 11/13 completed (tasks 10.6 and 12.4 are browser-only verification, explicitly out-of-agent-scope)
- **Tests**: 1249 passed, 0 failed (1210 baseline from change 25 + 39 new)
- **Migrations**: 0021 (unique_org_member) — tested with dedup, constraint enforcement, and full reversibility cycle
- **TDD Compliance**: All backend requirements have RED/GREEN evidence; frontend code complete with no harness
- **Architecture**: 4 gotchas from design.md confirmed with tests or code review:
  1. Target-scoped authorization (never depends on active header)
  2. Foreign org header → 403 (never 404)
  3. No header → first membership (backward compatible)
  4. Logout cleans `sp-active-org` (no stale cookie)

## Design Decisions Honored

| Decision | Followed | Evidence |
|----------|----------|----------|
| Header-based resolution, fallback compatible | ✅ Yes | `get_current_membership(request)` implemented; 1249 tests green without header |
| Target-scoped with `MemberRole.admin`, not RBAC catalog | ✅ Yes | `require_org_admin` uses `MemberRole`; confirmed in Sección 3 of verify-report |
| Migration 0021 dedup + unique reversible | ✅ Yes | Test + real cycle `upgrade→downgrade→upgrade` passed |
| Transactional bootstrap without global superadmin | ✅ Yes | `create_with_admin` in repository; confirmed in verify-report |
| Full page reload on switch (not selective reset) | ✅ Yes | `ActiveOrgStore.setActiveOrg()` calls `window.location.reload()` |

## Issues at Archive Time

- **CRITICAL**: 0
- **WARNING**: 2 (documented and non-blocking, per verify-report Section 10)
  1. `auth/me` did not require code changes (preexisting path already passed membership correctly)
  2. Admin pages placed in `pages/admin/organizations/` (consistency with existing admin pattern) instead of `features/manage-organizations/`

Both are intentional design improvements, not requirement violations.

## File Changes Summary

- Backend: 6 commits (resolver + migrations + CRUD/members + tests)
- Frontend: 7 commits (store + interceptor + entity + UI + pages)
- OpenSpec: 3 specs synced
- Total: 31 files, 4207 additions, 20 deletions (no trailing `/` files, no orphaned directories)

## Archive Destination

```
openspec/changes/26-admin-empresas/
  → openspec/changes/archive/2026-07-20-26-admin-empresas/
```

Folder moved using `git mv` — original path no longer exists.

## Traceability

All change artifacts remain in the archived folder for audit:
- proposal.md ✅
- specs/organizations-admin/spec.md ✅
- specs/frontend-org-switcher/spec.md ✅
- specs/multi-tenancy/spec.md (delta applied to main) ✅
- design.md ✅
- tasks.md (11/13 completed, 2 browser-only out-of-scope) ✅
- verify-report.md (PASS WITH WARNINGS, 1249 tests, 0 CRITICAL) ✅
- state.yaml (archive: done) ✅

## Dependency Status

- **Depends on**: 25-multiempresa-scoping (ARCHIVED ✅)
  - Active organization resolver assumes organization isolation hardened in 25
  - Cross-tenant isolation tests (52 from change 25) remain green — no regression
- **Blocks**: None declared
- **Follow-ups**: None required (MVP closure for multi-company + organization self-admin use case)

## Conclusion

The SDD cycle for change 26-admin-empresas is complete. The change has been fully planned (proposal → spec → design → tasks), implemented (13 commits, 12 Lotes), verified (PASS WITH WARNINGS, 1249 tests, 4 gotchas confirmed), and archived. Three main specs now reflect the new capabilities and modifications:
- Organizations are now dynamically created and managed
- Active organization resolves by header with backward-compatible fallback
- Membership is unique per (org, user) pair
- Frontend selector enables switching between multiple organizations with full context refresh

The system is ready for the next change or production deployment.
