# Archive Report: 48-puerto-llm

**Change**: 48-puerto-llm  
**Date Archived**: 2026-08-26  
**Archive Path**: `openspec/changes/archive/2026-08-26-48-puerto-llm/`  
**Artifact Store Mode**: hybrid (openspec + Engram)

## Final State Authority

This archive report describes the state of the change at close, per the SDD archive contract. Intermediate artifacts (verify-report, apply-progress) are snapshots that may differ from this record if work continued after they were persisted.

**Evidence hierarchy (highest-ranked first)**:
1. Native review authority — none (no review was started for this candidate)
2. Persisted tasks artifact — tasks.md ✅ 79/79 complete, all checkboxes marked
3. Verify report (Engram #3762) — pass_with_warnings, 12/12 requirements, 30/30 scenarios, 0 blockers, 0 critical findings
4. Final state facts from launch prompt — no additional overrides provided

## Execution Summary

### Specs Merged to openspec/specs

Two new capabilities were extracted from the delta specs and merged to main openspec:

| Capability | Source | Destination | Requirements | Scenarios | Status |
|---|---|---|---|---|---|
| llm-port | `openspec/changes/48-puerto-llm/specs/llm-port/spec.md` | `openspec/specs/llm-port/spec.md` | 8 | 21 | ✅ Created |
| assistant-health | `openspec/changes/48-puerto-llm/specs/assistant-health/spec.md` | `openspec/specs/assistant-health/spec.md` | 4 | 9 | ✅ Created |

**Merge validation**: Both specs are complete (no `## ADDED/MODIFIED/REMOVED` sections). Neither destination existed in openspec prior to archive. Byte-identity verified with `diff -r` after copy — both diffs returned empty (PASS).

### Task Completion Validation

**Gate Status**: ✅ PASS

Inspected `openspec/changes/archive/2026-08-26-48-puerto-llm/tasks.md` (79 tasks total). All implementation tasks are marked `[x]` complete:

- Fase 0 (Verificación previa): 8/8 ✅
- Fase 1 (Núcleo): 8/8 ✅
- Fase 2 (openai_compatible): 5/5 ✅
- Fase 3 (anthropic): 17/17 ✅
- Fase 4 (assistant): 18/18 ✅
- Fase 5 (Validación manual opcional contra Ollama): [MANUAL] (not counted as implementation task)
- Fase 6 (suite completa + cierre): 23/23 ✅

**Total implementation tasks**: 79 completed (0 pending, 0 unchecked stale tasks).

### Archive Move Verification

**Gate Status**: ✅ PASS

- Source: `openspec/changes/48-puerto-llm/`
- Destination: `openspec/changes/archive/2026-08-26-48-puerto-llm/`
- Method: `git mv` (tracked by git)
- Snapshot verification: Pre-move recursive snapshot created and compared post-move with `diff -r` excluding archive-report (additive-only). Result: **empty diff** (PASS — byte-identity confirmed).
- Source verification: `openspec/changes/48-puerto-llm/` no longer exists (confirmation passed).

## Spec Requirement & Scenario Counts

**llm-port** (8 requirements / 21 scenarios):
```
### Requirement: Contrato del puerto y DTOs congelados (2 scenarios)
### Requirement: Selección del adaptador activo por entorno (3 scenarios)
### Requirement: Adaptador fake sin red (2 scenarios)
### Requirement: Adaptador openai_compatible (3 scenarios)
### Requirement: Adaptador anthropic sobre el SDK oficial (5 scenarios)
### Requirement: Guarda de destino por allowlist (2 scenarios)
### Requirement: Protección de secretos y datos en logs y errores (2 scenarios)
### Requirement: Configuración LLM_* con valores por defecto seguros (2 scenarios)
```

**assistant-health** (4 requirements / 9 scenarios):
```
### Requirement: Endpoint protegido por RBAC de integración (3 scenarios)
### Requirement: Sobre de respuesta y campos de configuración (1 scenario)
### Requirement: Sonda opt-in sin gasto de tokens (4 scenarios)
### Requirement: Ningún secreto ni URL completa en la respuesta (1 scenario)
```

**Total**: 12 requirements / 30 scenarios (all matched with test coverage).

## Verification Evidence

**Verdict per Engram #3762**: `pass_with_warnings`

| Metric | Value | Status |
|---|---|---|
| Requirements covered | 12/12 | ✅ |
| Scenarios covered | 30/30 | ✅ |
| Blockers | 0 | ✅ |
| Critical findings | 0 | ✅ |
| Tasks complete | 79/79 | ✅ |

**Test execution (from verify-report)**:
- Test suite (focused 72 new tests): **72/72 passed**
- Full suite (with deselect of 3 preexisting flaky tests): **1487/1487 passed** ✅
- Build (mypy on change scope): **0 issues** ✅
- Statics (ruff check + ruff format --check): **All passing** ✅

**Preexisting test failures** (declared as deselect in verify-report):
- `tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window` (clock-dependent)
- `tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering` (clock-dependent)
- `tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto` (clock-dependent)

**Outstanding warnings** (not blockers):
1. One non-reproducible transient test failure in `test_connectors_oauth_redirect.py::test_callback_provider_error_with_destination_302s_back_with_error_code` (appeared in first full run, absent in immediate repeat; isolated run passes 14/14). No change files touch connectors code. Root cause: preexisting flakiness unrelated to this change.
2. Preexisting technical debt: 6 mypy errors in full repo (not in change scope), 309 ruff format violations (not touched by this change).

## Artifacts Persisted

### OpenSpec filesystem
- ✅ `/openspec/specs/llm-port/spec.md` (8 req / 21 sc)
- ✅ `/openspec/specs/assistant-health/spec.md` (4 req / 9 sc)
- ✅ `/openspec/changes/archive/2026-08-26-48-puerto-llm/` (complete directory with all source artifacts)

### Engram observations (topic_key references)
| Artifact | Engram ID | Topic Key |
|---|---|---|
| Proposal | #3712 | `sdd/48-puerto-llm/proposal` |
| Spec delta | #3713 | `sdd/48-puerto-llm/spec` |
| Design | #3715 | `sdd/48-puerto-llm/design` |
| Tasks | #3718 | `sdd/48-puerto-llm/tasks` |
| Verify Report | #3762 | `sdd/48-puerto-llm/verify-report` |
| **Archive Report** | (saved by sdd-archive) | `sdd/48-puerto-llm/archive-report` |

## Final State by Component

### Capabilities delivered

**New capabilities** (2 total):
- `llm-port`: LLM port abstraction with 3 adapters (fake, openai_compatible, anthropic), error taxonomy, mandatory local validation, deterministic retries, allowlist guard, secret redaction.
- `assistant-health`: Health check endpoint with RBAC (admin/manager), configuration reporting, opt-in probe without token cost.

**Modified capabilities**: None (this change adds entirely new domains).

**Removed capabilities**: None.

### Implementation

- **Backend package**: `backend/app/ai/` (new)
  - `ports.py` — LlmPort protocol, DTOs (frozen dataclasses)
  - `errors.py` — Taxonomy (8 exception types with stable codes)
  - `registry.py` — Provider resolution at call time
  - `adapters/{fake,openai_compatible,anthropic}.py` — 3 implementations
  - `prompts/__init__.py` — PROMPT_VERSION
- **Integration module**: `backend/app/modules/assistant/` (new)
  - `router.py` — `GET /api/v1/assistant/health` endpoint
  - `service.py` — Health logic, probe, secret protection
  - Tests via `test_assistant_health_endpoint.py`
- **Configuration**: `backend/app/config.py` (added `LLM_*` block at end)
- **Environment files**: `env.example`, `docker-compose.yml` (mirrors of config)
- **Test files** (new, 72 tests):
  - `test_ai_port_contract.py`
  - `test_ai_registry.py`
  - `test_ai_adapter_openai_compatible.py`
  - `test_ai_adapter_anthropic.py`
  - `test_assistant_health_endpoint.py`
- **Migrations**: None (design explicitly excludes persistence)

### Design decisions finalized

| Decision | Rationale | Verified |
|---|---|---|
| D1: `output_schema: type[BaseModel] \| None` | Pydantic v2 type for schema transport; parsed instance only if validation passes | ✅ Enum 'FinishReason' and truncation handling verified per design #3715 |
| D2: `max_tokens` optional in DTO, integer on wire | Adapter resolves `None` to `settings.LLM_MAX_TOKENS`; allows flexible call sites | ✅ Both adapters tested with override and default resolution |
| D3: Single active adapter per process by `LLM_PROVIDER` | Centralizes provider choice; avoids multi-provider registry complexity | ✅ Registry.get_llm_port reads setting at call time (not import constant) |
| D4: Mandatory local validation, parsed only if valid | Guarantees output shape independent of model/version compliance | ✅ Schema mismatch → llm_schema_mismatch 502; parsed never unvalidated |
| D5: Lazy import of anthropic package | Dependency optional in runtime; isolated to one adapter file | ✅ Verified: anthropic not in sys.modules when LLM_PROVIDER ≠ "anthropic" |
| D6: Allowlist validated in constructor | Prevents URLs from reaching transport; enforced before any request | ✅ AssertionError in tests when URL outside list (handler never called) |
| D7: Deterministic retries, never model-decided | Backoff acotado in openai_compatible; delegated to SDK in anthropic | ✅ 429 respects Retry-After up to LLM_MAX_BACKOFF_SECONDS |

### Security and isolation

- ✅ No LLM_API_KEY or full LLM_BASE_URL in logs or responses
- ✅ Request body (sensitive) never logged; response limited to 200 chars
- ✅ base_url_host reported as netloc only (no path, no auth)
- ✅ Probe never generates text; openai_compatible: GET /models; anthropic: configuration only
- ✅ RBAC: admin/manager only; member/viewer get 403
- ✅ No new migrations; no SQLAlchemy models

### Known issues and debt

| Issue | Category | Severity | Status |
|---|---|---|---|
| `test_connectors_oauth_redirect.py` non-reproducible flake | Preexisting | Low | Documented in WARNING #1; outside change scope |
| `test_adapter_microsoft365.py` clock-dependent 3 failures | Preexisting | Low | Deselected in verify; suggested for follow-up investigation |
| Full repo mypy: 6 errors | Preexisting | Low | Outside change scope; documented as external debt |
| Full repo ruff format: 309 files | Preexisting | Low | Outside change scope; automated remedy not blocked |

## Rollback Plan

Change is fully reversible:
1. Revert openspec filesystem: `git reset --hard <pre-archive-commit>`
2. Remove `backend/app/ai/`, `backend/app/modules/assistant/` (new code only)
3. Revert `backend/app/config.py`, `env.example`, `docker-compose.yml` to remove `LLM_*` block
4. Revert `backend/requirements.txt` (only anthropic added; openai_compatible uses existing httpx)
5. Run `pytest tests/ -q` — suite returns to baseline 1411/3 (preexisting failures)

No data migration needed; no schema changes persisted.

## Traceability

This archive report, combined with the linked Engram observations, forms the complete audit trail for this SDD cycle. Future readers can access:
- **Proposal intent & scope**: Engram #3712
- **Spec details & requirements**: Engram #3713
- **Design decisions & tradeoffs**: Engram #3715
- **Task breakdown & work units**: Engram #3718
- **Verification evidence & test results**: Engram #3762
- **Archive checklist & final state**: This document

The change is closed. The cycle is complete. Future work on LLM integration (change 49: classifier, 50: triage UI, 51: closing) builds on this stable port.
