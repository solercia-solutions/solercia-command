# Archive Report: 18 · Adaptador Jira (importador de issues, doble vía)

**Date Archived**: 2026-07-19
**Change ID**: 18-adapter-jira
**Status**: Complete ✅

## Executive Summary

Change 18-adapter-jira (Jira Cloud read-only adapter with dual import paths: REST API + CSV/Excel file) has been successfully archived. All 33 tasks completed, verify verdict PASS (12/12 requirements, 23/23 scenarios), apply and verify phases finalized. Specification deltas merged into main specs (jira-import as new spec, connectors delta with ADDED requirement for api_token provisioning). Artifact store mode: **hybrid** — filesystem artifacts moved to `openspec/changes/archive/2026-07-19-18-adapter-jira/`; Engram observations recorded with full traceability.

## Specs Merged

### New Spec: jira-import
- **Location**: `openspec/specs/jira-import/spec.md` (created)
- **Source**: `openspec/changes/18-adapter-jira/specs/jira-import/spec.md`
- **Action**: Full spec copied as-is (jira-import domain was NEW capability, no predecessor)
- **Content**: 11 requirements + 19 scenarios covering Jira Cloud read-only import (API REST v3 + CSV/Excel file)
- **Details**: Two convergent paths → single `NormalizedJiraIssue` normalization pipeline; homologation with fallback + reporting; read-only boundary (no Task/Sprint/Label persistence)

### Modified Spec: connectors (delta merge)
- **Location**: `openspec/specs/connectors/spec.md` (updated)
- **Source**: `openspec/changes/18-adapter-jira/specs/connectors/spec.md`
- **Action**: ADDED requirement merged into existing spec
- **Requirement Added**: "Provisión de credenciales por API token para conectores sin flujo OAuth" (1 requirement, 4 scenarios)
- **Details**: 
  - Admin provisions `email` + `api_token` via direct endpoint (no OAuth browser flow)
  - Token encrypted Fernet, never exposed in responses/logs
  - Credential kind `api_token` owned exclusively by change 17; change 18 consumes only
  - Member access: 403; foreign org connector: 404
  - Resend same token updates without duplication
- **Merge note**: Delta spec consumed `credential_kind` enum contract from 17-adapter-glpi (not redefined). Minimal delta, reusable by other adapters (GLPI also uses api_token for Basic auth).

## Archive Contents

| Artifact | Status | Path | Notes |
|----------|--------|------|-------|
| proposal.md | ✅ | `openspec/changes/archive/2026-07-19-18-adapter-jira/proposal.md` | Full SDD proposal, archived for audit trail |
| design.md | ✅ | `openspec/changes/archive/2026-07-19-18-adapter-jira/design.md` | Design decisions, threat matrix, architecture |
| tasks.md | ✅ | `openspec/changes/archive/2026-07-19-18-adapter-jira/tasks.md` | 33 tasks, all [x] complete; 11 lotes + pre-flight verification |
| verify-report.md | ✅ | `openspec/changes/archive/2026-07-19-18-adapter-jira/verify-report.md` | PASS verdict; 949 passed (86 jira/connectors isolated); 0 CRITICAL, 0 WARNING blocker |
| state.yaml | ✅ | `openspec/changes/archive/2026-07-19-18-adapter-jira/state.yaml` | All phases marked done; last_updated_by: sdd-archive |

## Artifacts in Engram (Traceability)

| Artifact | Observation ID | Type | Topic Key |
|----------|----------------|------|-----------|
| Proposal | 1641 | architecture | sdd/18-adapter-jira/proposal |
| Spec | 1649 | architecture | sdd/18-adapter-jira/spec |
| Design | 1653 | architecture | sdd/18-adapter-jira/design |
| Tasks | 1662 | architecture | sdd/18-adapter-jira/tasks |
| Verify Report | 1726 | architecture | sdd/18-adapter-jira/verify-report |
| **Archive Report** | *pending* | architecture | sdd/18-adapter-jira/archive-report |

## Task Completion Gate — PASSED ✅

All 33 tasks marked [x] complete:
- Lote 0: 3 tasks (pre-flight: migration chain order, credential_kind + settings columns present, 17-adapter-glpi archived)
- Lote 1: 4 tasks (fixtures: JSON API paginated + 429, fields.json, CSV/XLSX with BOM + repeated columns, malformed + bomb)
- Lote 2: 2 tasks (DTOs frozen, mappings with defaults + overrides)
- Lote 3: 1 task (normalizer: convergence API ↔ file)
- Lote 4: 1 task (file parser: BOM, repeated headers, bomb guard 50K rows / 500K cells)
- Lote 5: 1 task (client: pagination nextPageToken, 429+backoff, 401 no secret leak, anti-SSRF)
- Lote 6: 1 task (adapter registry: get_adapter("jira") + port exclusion)
- Lote 7: 1 task (connectors delta: admin token provision, validation via /myself, no duplication)
- Lote 8: 1 task (jira_import router + service: API + file, RBAC, read-only boundary)
- Lote 9: 1 task (promote httpx + openpyxl to requirements.txt)
- Lote 10: 1 task (C4 diagram update: jira node + jira_import module)

**No unchecked implementation tasks. Archive validates all completeness gates.**

## Verification Gate — PASSED ✅

- **Verdict**: PASS (HEAD: 01ac1d1, 11 apply commits + 1 fix 4R)
- **Coverage**: 12/12 requirements, 23/23 scenarios COMPLIANT
- **Build**: mypy ✅ clean (252 files), ruff ✅ clean (All checks passed!)
- **Tests**: 949 passed / 13 failed (legacy preexisting, same baseline as 17-adapter-glpi); 86/86 jira/connectors isolated
- **Alembic**: head unique 0017; no 0018_* migration (change 18 adds no schema delta)
- **Critical findings**: 0
- **Warning blockers**: 0 (2 SUGGESTIONs: pytest-cov not installed, 13 legacy test failures are tech debt)

## Spec Compliance

### jira-import domain (11 req / 19 scenarios) — ALL COMPLIANT ✅
1. Adapter registration (no core edits) ✅
2. API pagination (nextPageToken until isLast) ✅
3. Rate limit 429 (Retry-After + backoff, no page loss) ✅
4. Custom fields configurable (resolve by name + override) ✅
5. File import parity with API ✅
6. Malformed file error handling ✅
7. Homologation type/status/priority (fallback + report) ✅
8. Assignee/labels raw ✅
9. Invalid credential error (no token leak) ✅
10. REST surface (perms + multi-tenant) ✅
11. Read-only boundary (no Task/Sprint/Label/staging persistence) ✅

### connectors delta (1 req / 4 scenarios) — ALL COMPLIANT ✅
1. API token provisioning (admin role, org-scoped, no dupe on resend) ✅
   - Scenario: admin provision (account created, token hidden) ✅
   - Scenario: member 403 ✅
   - Scenario: foreign org 404 ✅
   - Scenario: resend same token updates without duplication ✅

## Architecture Decisions Honored

| Decision | Ratified? | Proof |
|----------|-----------|-------|
| `credential_kind` exclusive to 17, consumed only by 18 | ✅ | Pre-flight 0.1/0.2/0.3 verified both columns; jira_import does not redefine |
| Apply order: 17 → 18 strict, with head verification | ✅ | Lote 0 pre-flight executed; 17-adapter-glpi archived before Lote 1 start |
| Single normalizer for both API + file paths | ✅ | Same `normalizer._build_issue` called; convergence test passes |
| `settings.jira.*` namespace, not generic `connectors.settings` override | ✅ | mappings.py reads status_map/type_map/priority_map from settings.jira; client reads base_url/field overrides |
| Anti-SSRF by suffix (*.atlassian.net), not closed allowlist | ✅ | JiraClient.__init__ validates before any request; test `test_rejects_host_outside_atlassian_net_before_any_request` passes |
| No migration of own: change 18 adds zero schema delta | ✅ | alembic heads → unique 0017; no 0018_*.py in versions/; test_migrations_baseline passes |
| C4 diagram updated with correct tildes | ✅ | Fix 01ac1d1 corrected "paginacion"→"paginación", "unico"→"único" in diagram |

## Risk Assessment

| Risk | Likelihood | Mitigation Implemented | Status |
|------|------------|----------------------|--------|
| Custom field ID variance by instance | High | Resolve by name via /field; override via settings.jira | ✅ Mitigated |
| Homologation ambiguity (custom workflows) | High | Fallback safe (task/todo/medium) + report unmapped | ✅ Mitigated |
| Rate limits on large orgs | Med | 429+Retry-After backoff; incremental import by updated | ✅ Mitigated |
| API token long-lived secret | Med | Fernet encryption; never in response/logs | ✅ Mitigated |
| Bomb XLSX decompression | Med | openpyxl read_only + row/cell count limit (50K / 500K) | ✅ Mitigated |
| Multi-tenant isolation | High | RBAC require_role; connector scoped by org_id; 404 on foreign | ✅ Mitigated |
| Secret leak in exception/logs | High | test_no_secret_leaks_in_the_exception_text_or_logs passes | ✅ Mitigated |

**All documented risks addressed.**

## Delivery Status

- **Artifact Store**: hybrid (filesystem + Engram)
  - Filesystem: `openspec/changes/archive/2026-07-19-18-adapter-jira/` (full)
  - Engram: 5 observations + 1 archive-report (topic_key for future retrieval)
- **Main Specs Updated**:
  - New: `openspec/specs/jira-import/spec.md` (full, replaces delta)
  - Modified: `openspec/specs/connectors/spec.md` (delta merged, no duplication)
- **OLA_2.md**: Row 18 updated — apply ☑, verify ☑, archive ☑
- **Git History**: Ready for orchestrator commit (11 apply + 1 fix = 12 commits on feat/consume-solercia-ui)

## Rollback Boundary (if needed, pre-archive)

1. Revert 12 commits from feat/consume-solercia-ui
2. Delete `openspec/specs/jira-import/` directory
3. Revert connectors delta from `openspec/specs/connectors/spec.md`
4. Archive remains as audit trail; no data loss (import never persisted)

## SDD Cycle Complete

This change has completed all phases:
- ✅ Proposal (scope, approach, dependencies)
- ✅ Spec (11 req jira-import + 1 req connectors delta, 23 scenarios)
- ✅ Design (tech approach, DTOs, threat matrix, TDD strategy)
- ✅ Tasks (33 tasks, 11 lotes, pre-flight verification)
- ✅ Apply (11 commits, 942 tests passing, TDD strict)
- ✅ Verify (1 fix 4R with 7 new tests, PASS verdict)
- ✅ **Archive** (specs merged, filesystem archived, Engram persisted)

Ready for the next change.

---

## Engram Observation IDs (Audit Trail)

Save this report to Engram with topic_key `sdd/18-adapter-jira/archive-report` for future retrieval.

Artifact lineage:
- sdd/18-adapter-jira/proposal → 1641
- sdd/18-adapter-jira/spec → 1649
- sdd/18-adapter-jira/design → 1653
- sdd/18-adapter-jira/tasks → 1662
- sdd/18-adapter-jira/verify-report → 1726
- sdd/18-adapter-jira/archive-report → *this document*
