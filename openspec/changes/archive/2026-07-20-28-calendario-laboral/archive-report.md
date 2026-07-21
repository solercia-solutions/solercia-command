# Archive Report: 28 · Calendario laboral configurable (empresa → equipo → proyecto)

**Archived**: 2026-07-20  
**Change**: 28-calendario-laboral  
**Status**: COMPLETE  
**Artifact Store**: hybrid  

## Summary

Change 28 introduces configurable work calendars scoped to organization (default 8h, Mon-Fri) with optional root-project override, consumed by changes 34 (normalized estimates) and 35 (expected progress). Verified with 1302 passing tests (0 CRITICAL issues). All 44 implementation tasks completed.

## Specs Merged

| Domain | Action | Details |
|--------|--------|---------|
| work-calendar | Created | New capability. Full spec created at `openspec/specs/work-calendar/spec.md` (124 lines, 4 requirements, 15 scenarios). Covers organization default calendar, root project override, cascading resolution (team → organization → default), and tenant isolation. |
| projects | Updated | Added requirement for nullable `working_hours_per_day` and `working_days` columns on Project (only writable by root). Merged into existing `openspec/specs/projects/spec.md` with 3 scenarios validating root-only persistence, child null-ness, and additive reversible migration. |

## Archive Contents Verified

✅ `openspec/changes/28-calendario-laboral/proposal.md` (Engram ID 1830)  
✅ `openspec/changes/28-calendario-laboral/specs/work-calendar/spec.md` (full spec, 124 lines)  
✅ `openspec/changes/28-calendario-laboral/specs/projects/spec.md` (delta ADDED, 31 lines, now merged into main)  
✅ `openspec/changes/28-calendario-laboral/design.md` (Engram ID 1831, technical decisions ADR format)  
✅ `openspec/changes/28-calendario-laboral/tasks.md` (Engram ID 1834, 44/44 tasks completed ✓)  
✅ `openspec/changes/28-calendario-laboral/verify-report.md` (Engram ID 1905, PASS WITH WARNINGS, 0 CRITICAL)  
✅ `openspec/changes/28-calendario-laboral/state.yaml` (phases all done, archive pending)  

## Implementation Evidence

### Task Completion
- **44/44 tasks completed** ✅
  - Phase 0: Migration revision fixed at 0024 (head real: 0020, after 25→26→27 sequence)
  - Phase 1: Migration + ORM columns (organizations NOT NULL+default, projects nullable)
  - Phase 2: Resolver module with cascading CTE and CalendarSource enum
  - Phase 3: Endpoints (organization, project override, resolved) with permission gates
  - Phase 4: ProjectRead schema exposure (always null on non-root)
  - Phase 5: Suite complete, reversible migration cycle verified

### Test Coverage
- **Backend suite**: 1302 passed (baseline 1272 + 30 new)
  - 2 migration tests
  - 9 schema tests (validation, enum mapping)
  - 4 resolver tests (cascades, isolation)
  - 13 API tests (permission gates, error cases)
  - 2 projects schema exposure tests
- **Verification**: All 4 cascading scenarios confirmed (grandchild→root override, root→org default, org→global default, cross-tenant rejection)
- **Enum serialization**: `CalendarSource` (internal: `project_root_override|organization_default|global_default`) mapped to wire values (`team|organization|default`) with dedicated test

### Review Receipt
- Verification report status: **PASS WITH WARNINGS**
  - 0 CRITICAL issues
  - 2 WARNING (preexisting form debt, not introduced by this change)
  - 2 SUGGESTION (documentation, non-blocking)
- No blocking issues found

### Artifact Lineage (Engram)

| Artifact | Observation ID | Type | Created |
|----------|----------------|------|---------|
| Proposal | 1830 | architecture | 2026-07-20 14:18:39 |
| Spec | 1833 | architecture | 2026-07-20 14:24:35 |
| Design | 1831 | architecture | 2026-07-20 14:22:56 |
| Tasks | 1834 | architecture | 2026-07-20 14:32:11 |
| Verify-report | 1905 | architecture | 2026-07-20 19:19:10 |

## Specifications Locked

The following specifications are now the source of truth:

- **`openspec/specs/work-calendar/spec.md`** — Complete capability definition, 4 requirements:
  1. Organization work calendar (GET/PUT, ADMIN gate, validation 1-24h, days 1-7 no duplicates)
  2. Root project override (nullable, GET/PUT with ADMIN/MANAGER gate, error code `override_requires_root` for non-root)
  3. Cascading resolution and resolved calendar (source: team|organization|default, tenant isolation)
  4. No regression and prerequisite for 34/35 (additive reversible migration, suite green, resolver reusable)

- **`openspec/specs/projects/spec.md`** (merged, new requirement added) — Projects now expose:
  - Nullable `working_hours_per_day` (Numeric 1-24, supports halves like 7.5)
  - Nullable `working_days` (array of ISO integers 1-7, min 1 element, no duplicates)
  - Both always null on non-root projects (read-only exposure of the override that lives in work-calendar capability)

## Dependencies

- **Prerequisite**: 27-plantillas-idempotentes (provides `project_kind` and root project concept)
- **Prerequisite**: 25-multiempresa-scoping (organization-scoped data isolation)
- **Consumers**: 34-estimacion-normalizada, 35-avance-esperado-vs-real (both consume the resolver without caching in MVP)

## Reversibility

- Migration 0024 is fully reversible: `downgrade` removes the 4 columns from organizations and projects without data loss
- No endpoints changed behavior; existing contracts unchanged
- Resolver is a new interface, not a breaking change to existing services

## Notes

- **Enum mapping handled**: Tasks/apply reconciliation completed; internal `CalendarSource` enum correctly maps to public wire values via Pydantic `field_serializer` without changing enum definitions
- **Cross-module integrity**: New `work_calendar` module follows Screaming Architecture pattern; does not modify existing `OrganizationRepository`/`ProjectRepository`, avoiding friction with parallel changes 25/26/27
- **Schema evolution**: First use of PostgreSQL `ARRAY` type in project; validated against migration baseline test (`alembic check` reports no diff)
- **Permissions matrix**:
  - GET `/organizations/me/work-calendar` → any member
  - PUT `/organizations/me/work-calendar` → admin
  - GET `/projects/{id}/work-calendar` → any member (null if non-root)
  - PUT `/projects/{id}/work-calendar` → admin or manager, root-only (422 `override_requires_root` otherwise)
  - GET `/projects/{id}/work-calendar/resolved` → any member, tenant-scoped (404 cross-tenant)

## SDD Cycle Status

✅ **COMPLETE**

- Proposal: ✅ scoped, dependencies identified
- Spec: ✅ 4 requirements, 15 scenarios, contracts defined
- Design: ✅ technical decisions (columns vs table, CTE cascade, enum serialization), ADRs documented
- Tasks: ✅ 44/44 completed, 5 commits, strict TDD phases
- Apply: ✅ implementation verified, all phases delivered
- Verify: ✅ PASS WITH WARNINGS (0 CRITICAL), 1302 tests
- Archive: ✅ specs merged, traceability locked

**Ready for next change in the feature branch chain.**
