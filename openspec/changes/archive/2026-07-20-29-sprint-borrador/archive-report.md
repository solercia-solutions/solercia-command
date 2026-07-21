# Archive Report: 29 · Sprint borrador (creación con solo nombre + autonombre)

**Change**: 29-sprint-borrador  
**Archived**: 2026-07-20  
**Mode**: hybrid (filesystem + Engram)  
**Artifact Store**: Complete — proposal, specs, design, tasks, verify-report

## Status Summary

| Phase | Result |
|-------|--------|
| proposal | ✅ Complete |
| spec | ✅ Complete |
| design | ✅ Complete |
| tasks | ✅ Complete (46/46 tasks) |
| apply | ✅ Complete (6 commits, 1332 tests passing) |
| verify | ✅ PASS WITH WARNINGS (no CRITICAL issues) |
| archive | ✅ Complete — spec merged, report written, state updated |

## Specification Merge

### Source: Delta Spec

`openspec/changes/29-sprint-borrador/specs/sprints/spec.md` (ADDED requirements)

### Target: Main Spec

`openspec/specs/sprints/spec.md`

### Merge Action

**Type**: APPEND — all 6 ADDED requirements (R5–R10) appended to main spec's Requirements section.

**Requirements Added**:
- R5: Creación en borrador sin fechas (POST /projects/{id}/sprints con name opcional, nace `draft`)
- R6: Autonombre sugerido (GET /projects/{id}/sprints/suggested-name, sin persistencia)
- R7: Inicio de sprint exige fechas (POST /sprints/{id}/start con validación 422 español)
- R8: Permisos y aislamiento de tenant (mismo modelo que rest del módulo)
- R9: UI del flujo de sprint borrador (crear liviano, badge "Borrador", Añadir fechas, Iniciar condicionado)
- R10: No regresión sobre sprints existentes (suite completa en verde)

**Sections Updated**:
- Propósito: incorpora flexibilidad de fechas y autonombre
- Alcance: 6 endpoints (3 nuevos + 3 existentes reutilizados)
- Modelo Sprint: status amplía a `draft | active | closed`; fecha temporal en borrador nullable
- Limitaciones: nota que cambio 29 no introduce unicidad de nombres
- Referencias: lista los 4 archivos de test nuevos y link a artefactos de cambio 29

**Conflicts**: None — delta only contains ADDED, no MODIFIED/REMOVED, pure append.

## Artifact Contents Verified

### Proposal (`proposal.md`)

✅ Present and complete

| Field | Status |
|-------|--------|
| Intent | Defined — flujo Jira: crear sprint vacío, llenar desde backlog, luego fechar e iniciar |
| Scope | In/Out clearly marked — draft + autonombre + POST /start in scope; drag&drop/validación metodología out scope |
| Capabilities | Modified: `sprints` (no nuevas) |
| Approach | Described — autonombre función pura, `status` String libre, no migración |
| Affected Areas | 5 modules listed |
| Risks | 4 riesgos documentados con mitigación |
| Rollback Plan | Code-only, no data changes, simple revert |
| Success Criteria | 5 criteria listed, all verified as passing by apply/verify |

### Spec — Delta (`specs/sprints/spec.md`)

✅ Present, merged into main spec

| Component | Status |
|-----------|--------|
| ADDED Requirements | 6 requirements (R5–R10) with scenarios — all merged |
| Alcance | 3 endpoints nuevos, 3 reutilizados — spec documents full contract |
| Model changes | status enum → `draft | active | closed`; fecha nullable en draft — documented |

### Design (`design.md`)

✅ Present and complete

| Section | Status |
|---------|--------|
| Technical Approach | Aditivo, sin migración, función pura — described |
| Architecture Decisions | 5 decisions (D1–D5) with tradeoffs, reconciliations documented |
| Data Flow | Diagrams POST /projects/{id}/sprints and POST /sprints/{id}/start pipelines |
| File Changes | 13 files listed (8 modified, 4 test files created, 1 i18n) |
| Interfaces | Contracts for next_sprint_name, SprintCreate, SprintNextName, endpoints |
| Testing Strategy | Unit (pure function), integration (full flows), regression (existing suite) |
| Migration | None required — status freeform string in DB, whitelist in service |
| Open Questions | None — all resolved by orchestrator review |

### Tasks (`tasks.md`)

✅ Present, all 46 tasks complete

| Unit | Phases | Status |
|------|--------|--------|
| U1 | 1.1–1.4 (Función pura next_sprint_name, tabla de verdad 6 casos) | ✅ Complete |
| U2 | 2.1–2.10 (Creación draft + autonombre + estado derivado de fechas) | ✅ Complete |
| U3 | 3.1–3.11 (POST /sprints/{id}/start + guarda en PATCH directo) | ✅ Complete |
| U4 | 4.1–4.7 (GET /projects/{id}/sprints/suggested-name) | ✅ Complete |
| U5 | 5.1–5.8 (Frontend: crear liviano, Añadir fechas, Iniciar condicionado) | ✅ Complete |
| U6 | 6.1–6.6 (Suite completa + regresión + commit final) | ✅ Complete |

**Checkbox status**: 46/46 implementation tasks checked (`[x]`), no stale unchecked tasks.

**Commits**: 6 (feat naming, feat draft creation, feat start+guarda, feat suggested-name, feat frontend, fix suite closure).

### Verify Report (`verify-report.md`)

✅ Present, verdict PASS WITH WARNINGS

| Criterion | Result |
|-----------|--------|
| Completeness | 46/46 tasks checked, 6 commits, no schema migration (verified) |
| Build/Tests | ✅ 1332 passed (30 new + 1302 baseline), 0 failed, exit 0 |
| Frontend build | ✅ `npm run build` exit 0 |
| Spec Compliance | 5/6 requirements COMPLIANT (1 PARTIAL = UI, see below) |
| TDD Evidence | 4 test files, 30 tests, RED→GREEN cycle documented |
| Assertion Quality | ✅ All 30 assertions verify real behavior, no tautologies |
| Design Coherence | ✅ 5/5 architecture decisions followed (D1–D5) |
| Issues Found | CRITICAL: 0; WARNING: 3 noted (UI coverage, code reuse, meta-test); SUGGESTION: 1 |

**Verdict**: PASS WITH WARNINGS — no blockers, warnings are pre-existing infrastructure limits or documentation notes.

## Change Closure

### Capability Changed

- `sprints`: **MODIFIED** (expanded from 4 endpoints to 6, status from `active | closed` to `draft | active | closed`, autonombre logic added)

### Constraints Verified

- ✅ `tdd-cannot-start-without-dates` — guarda implementada en `/start` y en `PATCH status=active`
- ✅ `tdd-autoname-consecutive-non-conventional` — 9 test cases en `test_sprint_naming.py` cubriendo tabla de verdad
- ✅ `strategy-driven-sprints-enabled-no-if-methodology` — `_require_sprints_enabled` único punto de lectura, no `if methodology ==` nuevo
- ✅ `no-schema-migration-status-is-freeform-string` — no Alembic changes, status sigue siendo String(20)
- ✅ `additive-only-backwards-compatible` — sprints con `start_date && end_date` siguen naciendo `active` (retro-compatible)
- ✅ `ui-copy-es-co-formal-tuteo` — i18n newstrings added, no voseo

### Dependencies Resolved

- `depends_on: []` (técnico) — cambio 29 no bloquea ni es bloqueado por otros cambios en la fase 4.2

### Boundary Assertions Verified

All 6 boundary assertions from `state.yaml` verified as implemented:
1. ✅ Sprint creatable solo con nombre → nace `draft`
2. ✅ `draft` es value nuevo de String(20), sin migración
3. ✅ Autonombre correcto (tabla de verdad)
4. ✅ Autonombre es sugerencia editable, sin unicidad
5. ✅ Transición draft→active vía POST /start con validación de fechas
6. ✅ "Añadir fechas" reutiliza PATCH, draft solo en sprints_enabled

## Persistence and Traceability

### Artifact IDs (for hybrid mode audit trail)

All artifacts from this change have been persisted. Observation IDs recorded for post-archive traceability:

- Proposal: available in `openspec/changes/29-sprint-borrador/proposal.md`
- Spec delta: available in `openspec/changes/29-sprint-borrador/specs/sprints/spec.md`
- Spec main (merged): updated at `openspec/specs/sprints/spec.md`
- Design: available in `openspec/changes/29-sprint-borrador/design.md`
- Tasks: available in `openspec/changes/29-sprint-borrador/tasks.md`
- Verify report: available in `openspec/changes/29-sprint-borrador/verify-report.md`
- Archive report: this document (`openspec/changes/29-sprint-borrador/archive-report.md`)

### Files Changed During Archive

- **`openspec/specs/sprints/spec.md`** — merged delta spec (R5–R10 added, scopes updated, references augmented)
- **`openspec/changes/29-sprint-borrador/state.yaml`** — updated: `archive: done`, `last_updated: 2026-07-20`
- **`openspec/changes/29-sprint-borrador/archive-report.md`** — this report

### Rollback Boundary

The change is code-only, no data-bearing migrations:
- Revert the 6 commits restores prior behavior
- Main spec can be reverted if future changes supersede these requirements
- Sprints created as `draft` between apply and potential revert continue to work (no DB schema change)

## Sign-Off

**Archived by**: sdd-archive executor  
**Date**: 2026-07-20  
**Verification gate**: ✅ PASS WITH WARNINGS (no CRITICAL blockers)  
**Task completion**: ✅ 46/46  
**Spec merge**: ✅ Main spec updated (R5–R10 appended)  
**SDD cycle**: ✅ COMPLETE — change ready for integration

---

**Next**: Change is archived and closed. Pending git operations (folder move to `archive/`, final commit) belong to orchestrator.
