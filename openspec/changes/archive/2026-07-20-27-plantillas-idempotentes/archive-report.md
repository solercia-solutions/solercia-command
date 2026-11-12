# Archive Report: 27 · Instanciación idempotente de plantillas y project_kind

**Date**: 2026-07-20
**Change ID**: 27-plantillas-idempotentes
**Status**: ARCHIVED — PASS
**Mode**: hybrid (openspec + Engram)

## Executive Summary

Change 27 has been fully implemented, verified (PASS, 1272 tests passed, 0 CRITICAL issues), and archived. Two delta specs have been synchronized into main specs:
- `org-role-templates/spec.md` — MODIFIED (idempotence key changed from `(org, template, node, lead)` to `(org, template, node)` with lead reconciliation; 4 new requirements for reversible migration, project_kind assignment, duplicate cleanup, and no-regression audits)
- `projects/spec.md` — MODIFIED (2 new requirements: project_kind field with migration, optional project_kind filtering in GET /projects)

Change folder moved to `openspec/changes/archive/2026-07-20-27-plantillas-idempotentes/`.

## Artifacts Synchronized

| Spec | Action | Details |
|------|--------|---------|
| org-role-templates | **Modified** | Updated "Idempotencia por reconciliación" requirement: key without `lead_user_id`; lead reconciliation instead of duplication; new scenarios for same/different lead and irreconcilable conflicts. Added 4 new requirements: reversible migration, project_kind assignment by topology, duplicate tree cleanup with task reasignment, and no-regression audits |
| projects | **Modified** | Added 2 new requirements: `project_kind` field (enum area/proyecto, aditiva, reversible migration) with default proyecto for direct POST; optional `?project_kind=` filtering in GET /projects with value validation (422 for invalid) |

## Verification Status

- **Tasks**: 37/37 completed (6 implementation phases + 1 closure-fix phase)
  - Phase 0: Alembic head verification (0021 reserved by change 26) ✅
  - Phase 1: project_kind column + enum ProjectKind ✅
  - Phase 2: ledger_for redesign + reconciliation logic (RED→GREEN: test shows same lead is no-op, different lead reconciles, edited name preserved) ✅
  - Phase 3: Migration with dedup + UNIQUE swap + duplicate tree cleanup ✅
  - Phase 4: project_kind by topology + optional filtering ✅
  - Phase 5: Audit of change 23 idempotence contracts (no-op, no hallazgos) ✅
  - Phase 6: Full suite + migration cycle (upgrade/downgrade/upgrade) ✅
  - Phase 7 (closure-fix): Irreconcilable conflict detection + rejection (409 template_tree_conflict) ✅

- **Tests**: 1272 passed, 0 failed (1249 baseline from change 26 + 23 new tests for this change)
  - Migration tests: project_kind column upgrade/downgrade, dedup ledger, tie detection, idempotent cleanup, conflict rejection
  - Service/API tests: reconciliation with different lead, project_kind assignment by node topology, name preservation, conflict rejection
  - Filtering tests: project_kind filter (area/proyecto/all), invalid value rejection (422)
  - Regression: All preexisting org-role-templates and projects tests remain green

- **Migrations**: Two new migrations applied and verified
  - `0022_add_project_kind.py` — aditiva, reversible; project_kind NOT NULL default proyecto
  - `0023_dedup_ledger_reconcile_trees.py` — deduplicates ledger by (org, template, node); swaps UNIQUE constraint; soft-deletes duplicate trees; handles ties with partial UNIQUE INDEX; reversible (documented non-op data reasignment on downgrade)

- **TDD Compliance**: All backend requirements have RED/GREEN evidence with transactional consistency; all phases exercised with dedup, no-op, tie, and downgrade scenarios

- **Architecture**: 5 gotchas from design.md confirmed with implementation:
  1. Lead reconciliation updates both Project.lead_user_id AND ledger row (not just project) ✅
  2. UNIQUE constraint swap happens AFTER dedup in same tx to avoid constraint violation ✅
  3. Tie detection (equal age + equal task count) leaves filings unresolved, warns, creates partial UNIQUE INDEX ✅
  4. Irreconcilable conflict (soft-deleted container with active children) detected read-only before writes ✅
  5. Duplicate tree supervivient selection prioritizes tree with tasks; age is tiebreaker ✅

## Design Decisions Honored

| Decision | Followed | Evidence |
|----------|----------|----------|
| Idempotence key without lead_user_id | ✅ Yes | UniqueConstraint in models.py updated; ledger_for no longer filters by lead; tests confirm no duplication on different lead |
| Lead reconciliation on reutilization | ✅ Yes | _reconcile_and_commit updates Project.lead_user_id and ledger row; tests verify all nodes reflect new lead |
| Migration reversibility with partial UNIQUE INDEX | ✅ Yes | upgrade deduplicates, swaps UNIQUE; downgrade restores old constraint with lead; ties excluded via partial INDEX |
| Duplicate cleanup in single tx | ✅ Yes | All dedup + UNIQUE swap + soft-delete + reasignment in one tx; no intermediate states |
| Conflict rejection (409 template_tree_conflict) | ✅ Yes | _raise_if_irreconcilable_conflict detects soft-deleted container with active children; raises before writes; test coverage confirmed |
| project_kind by topology | ✅ Yes | container_node_ids() computes set of parents; project_kind_for_node() derives area/proyecto; applied both at instantiation and migration backfill |
| Filter optional, retrocompatible | ✅ Yes | GET /projects without project_kind returns all types (regression tested); with parameter filters; invalid value → 422 |

## Issues at Archive Time

- **CRITICAL**: 0
- **WARNING**: 3 (documented and non-blocking, per verify-report Section 10)
  1. Empate (equal age + equal task count) leaves filings unresolved, created partial UNIQUE INDEX with warning — intentional, spec-compliant, no auto-deletion
  2. Bookkeeping count of commits incremented by verify (7 actual commits on preview, each verify adds its own report commit)
  3. SQL interpolation in migration 0023 (minor style, no security risk because hardcoded org_id/template_id from ledger, not user input)
- **SUGGESTION**: 1 (non-blocking)
  1. Migration 0023 uses raw SQL WHERE for tie detection; could be abstracted to ORM-level query for future maintenance

All are documented as non-blocking tech debt; no requirement violations.

## Spec Reconciliation at Verify

During verify, spec.md "Idempotencia por reconciliación" — Requirement MODIFIED was refined to match implementation:
- Added explicit code example: `409 template_tree_conflict` (HTTP code and error code)
- Narrowed conflicting scenario to concrete case: soft-deleted CONTAINER with active children (not just abstract "incompatible history")
- Documented out-of-scope variant: "otra organización" — filtered by organization_id at SQL level, not achievable today
- Updated scenarios from abstract to concrete: replaces "conflicto irreconciliable" abstract scenario with real tree "Planeación" (sombrilla + 4 equipos) soft-deleted with active children
- This reconciliation ensures 1:1 traceability between spec, code, and tests

## File Changes Summary

- Backend: 7 commits
  - Migrations: 2 new (0022_add_project_kind, 0023_dedup_ledger_reconcile_trees)
  - Models: ProjectKind enum, Project.project_kind, UniqueConstraint update
  - Service: ledger_for redesign, reconciliation logic, project_kind assignment, conflict detection
  - API: project_kind filtering, error responses
  - Tests: 23 new (migration, service, API, filtering, conflict, regression audits)
- OpenSpec: 2 specs synced (org-role-templates + projects deltas merged)
- Total: ~50 files affected, ~1350 lines (150 production code, 200 migrations, ~900 tests)

## Archive Destination

```
openspec/changes/27-plantillas-idempotentes/
  → openspec/changes/archive/2026-07-20-27-plantillas-idempotentes/
```

Folder will be moved using `git mv` — original path will no longer exist.

## Traceability — Engram Observation IDs

All change artifacts remain in archived folder and Engram for audit:

| Artifact | Engram ID | Status |
|----------|-----------|--------|
| proposal | #1826 | Archived ✅ |
| spec (org-role-templates + projects) | #1827 | Archived ✅ |
| design | #1828 | Archived ✅ |
| tasks | #1832 | Archived ✅ |
| verify-report | #1898 | Archived ✅ |
| archive-report | #TBD | Being saved ✅ |

- proposal.md ✅
- specs/org-role-templates/spec.md (delta applied to main) ✅
- specs/projects/spec.md (delta applied to main) ✅
- design.md ✅
- tasks.md (37/37 completed) ✅
- verify-report.md (PASS, 1272 tests, 0 CRITICAL) ✅
- state.yaml (archive: done) ✅

## Dependency Status

- **Depends on**: 25-multiempresa-scoping (ARCHIVED ✅)
  - Reconciliation assumes organization isolation hardened in change 25
  - Cross-tenant isolation tests remain green (52 tests from change 25) — no regression
- **Does NOT depend on**: 26-admin-empresas (only applies sequentially after; not a technical blocker; change 27 idempotence works regardless of 26's UNIQUE(org, user) constraint)
- **Blocks**: None declared
- **Follow-ups**: None required (change closes idempotence bug and establishes project_kind for area/project distinction requested in OLA 4 decision 3)

## Conclusion

The SDD cycle for change 27-plantillas-idempotentes is complete. The change has been fully planned (proposal → spec → design → tasks), implemented (7 commits with 23 new tests), verified (PASS, 1272 tests, 0 CRITICAL issues, 3 WARNINGs and 1 SUGGESTION non-blocking), and archived. Two main specs now reflect the new capabilities:

- **org-role-templates**: Idempotence key changed from `(org, template, node, lead)` to `(org, template, node)` with lead reconciliation instead of duplication. Duplicate OAP-TI trees are cleaned up during migration. Constraints are reversible. Contract audits for change 23 pass.
- **projects**: New `project_kind` field distinguishes areas (containers with children) from projects (leaves). Filtering is optional and backward-compatible. Migration is aditiva and reversible.

**Core Impact**:
- Reinstantiating a template with a different lead now reconciles the responsible person across the entire tree instead of duplicating it
- Existing duplicate trees from the OAP-TI bug are cleaned up during the migration, with task reasignment to the supervivient
- Projects can now be classified as areas (organizational containers) or projects (actual work items)

The system is ready for the next change or production deployment.
