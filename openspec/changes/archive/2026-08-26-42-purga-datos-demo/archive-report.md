# Archive Report: 42-purga-datos-demo

**Date**: 2026-08-26  
**Change**: 42 · Purga de datos demo y bootstrap de la jerarquía SDMUJER  
**Store mode**: openspec  
**Status**: Complete  

## Executive Summary

Change `42-purga-datos-demo` has been successfully implemented, verified, and archived. All 72 tasks are complete. Verification passed with warnings (no CRITICAL blockers after remediation in commit `e33000f`). Five capability specs have been merged into the source of truth, and the change folder has been moved to archive. Ready for next cycle.

## Task Completion

- **Total tasks**: 72
- **Completed**: 72 (100%)
- **Pending**: 0

All tasks marked `[x]` including Phase 7 remediation (commits `e082769`, `fc97125`, `e33000f`).

## Verification Status

**Verdict**: `pass_with_warnings` (per `verify-report.md`, evidence revision `sha256:f9b3663b6c9e20adee98a6bdd2c8b0d568615245ff7234b742d0491f5056a638`)

- **Blockers**: 0
- **Critical findings**: 0 (2 CRITICAL resolved via remediation in commit `e33000f`)
- **Requirements**: 15/15 ✅
- **Scenarios**: 35/35 ✅
- **Tests**: 1415 passed, 3 failed (preexisting, unrelated to this change, clock-dependent in `test_adapter_microsoft365.py`)
- **Build**: ✅ mypy clean in scope (`app/maintenance`, `scripts`)

### Warnings Carried Forward to Archive

1. **Narrow assertion scope** (WARNING #1): Test `test_restart_con_flag_apagado_no_revive_miembros_tras_purga` verifies idempotence but only checks `organization_members` non-duplication, not the full seed universe. Non-blocking, preexisting coverage gap documented for trazability.

2. **Format debt** (WARNING #2): 7 of 17 files in scope differ from `ruff format --check` (preexisting, explicit decision to not reformat in this change).

3. **Preexisting external lint/type debt** (WARNING #3): 1 ruff error in `test_cross_tenant_isolation.py` and 6 mypy errors in 4 files outside scope of this change.

4. **Deselected tests** (WARNING #4): 3 tests in `test_adapter_microsoft365.py` excluded from YAML envelope command due to clock-dependency, included in full suite evidence without regressions.

## Specs Merged

### Summary Table

| Capability | Action | Reqs before | Reqs after | Scenarios before | Scenarios after | Notes |
|---|---|---|---|---|---|---|
| data-maintenance | **CREATED** | — | 9 | — | 19 | New capability, full spec at `openspec/specs/data-maintenance/spec.md` |
| api-conventions | **MODIFIED** | 6 | 6 | 6 | 9 | R4 (MODIFIED): seed split structural/demo; R5 (MODIFIED): no migration needed; R3b (ADDED): maintenance exception to R3; scenarios expanded from 6→9 |
| multi-tenancy | **MODIFIED** | 5 | 5 | 1 | 4 | R4 (MODIFIED): demo members conditional on `SEED_DEMO_DATA`; scenarios added for R4 (was 1→4, others remain same) |
| org-role-templates | **MODIFIED** | 7 | 8 | 16 | 18 | NEW requirement: purge preserves system catalog; 2 scenarios added |
| intake-classifier | **MODIFIED** | 7 | 8 | 10 | 12 | NEW requirement: bootstrap pre-configures default project; 2 scenarios added |

### Merged Specs Detail

#### data-maintenance (CREATED)

- **Path**: `openspec/specs/data-maintenance/spec.md` ← copied mechanically from `openspec/changes/42-purga-datos-demo/specs/data-maintenance/spec.md`
- **Requirements**: 9 total
  1. Compuerta SEED_DEMO_DATA
  2. Purga idempotente con dry-run por defecto
  3. Orden de borrado hoja-raíz y huérfanos sin FK
  4. Protección del catálogo y de conectores reales
  5. Fallo cerrado si una connected_account pertenece a un usuario a borrar
  6. Respaldo obligatorio y verificado antes de cualquier borrado
  7. Bootstrap idempotente de SDMUJER
  8. Invariantes post-ejecución con código de salida no cero
  9. Contrato de ejecución en el host
- **Scenarios**: 19 (all COMPLIANT in verify-report.md)

#### api-conventions (MODIFIED)

**Requirements replaced/added**:

- **R4 (MODIFIED)**: Was: "`seed_default` DEBE ser idempotente: arranques repetidos no duplican datos"  
  Now: Expanded to distinguish structural seed (unconditional) from demo seed (conditional on `SEED_DEMO_DATA`). Scenarios expanded from 1 → 3.

- **R5 (MODIFIED)**: Was: "El esquema de base de datos DEBE originarse y evolucionar mediante revisiones de Alembic versionadas. El arranque asume que las migraciones ya se aplicaron y se limita a ejecutar `seed_default` sobre el esquema ya migrado. `seed_default` NO cambia de comportamiento (sigue siendo idempotente)."  
  Now: Clarified that `SEED_DEMO_DATA` is a Settings change, not schema, so no new Alembic migration required. Scenarios expanded from 2 → 3.

- **R3b (ADDED)**: "Alcance del borrado suave y excepción de mantenimiento para borrado físico"  
  New requirement clarifying that R3 (soft delete for domain operations) coexists with maintenance exception for physical delete via CLI, with constraints (dedicated usecase, backup required, dry-run default, never exposed via HTTP). Scenarios: 3.

#### multi-tenancy (MODIFIED)

**Requirements replaced**:

- **R4 (MODIFIED)**: Was: "El seed inicial DEBE ser idempotente y crear la organización 'Solercia' con sus miembros demo."  
  Now: Clarified: org + admin ALWAYS created unconditionally; demo members (`ana@`, `carlos@`, `diana@`) only created when `SEED_DEMO_DATA = true`. Scenarios expanded from 0 → 3.

#### org-role-templates (MODIFIED)

**Requirements added**:

- **NEW**: "La purga de datos demo preserva el catálogo de plantillas de sistema"  
  Purge operation MUST delete instantiated tree and `org_role_template_instantiations` in demo scope, but MUST preserve catalog (`org_role_templates` and `org_role_template_nodes` with `organization_id IS NULL`, `is_system=true`). Scenarios: 2.

#### intake-classifier (MODIFIED)

**Requirements added**:

- **NEW**: "Bootstrap operativo satisface el proyecto por defecto sin crear 'Tareas Outlook'"  
  When `IntakeSettings.default_project_id` already points to existing project (e.g., pre-configured by `data-maintenance` bootstrap to SEGURIDAD), do NOT create lazy "Tareas Outlook" project; reuse configured one. Scenarios: 2.

## Reference Traceability

| Artifact | Location | Status |
|---|---|---|
| Proposal | `openspec/changes/archive/2026-08-26-42-purga-datos-demo/proposal.md` | ✅ Archived |
| Specs | `openspec/changes/archive/2026-08-26-42-purga-datos-demo/specs/` | ✅ Archived + merged to `openspec/specs/` |
| Design | `openspec/changes/archive/2026-08-26-42-purga-datos-demo/design.md` | ✅ Archived |
| Tasks | `openspec/changes/archive/2026-08-26-42-purga-datos-demo/tasks.md` | ✅ Archived |
| Verify Report | `openspec/changes/archive/2026-08-26-42-purga-datos-demo/verify-report.md` | ✅ Archived |

## Final State Authority

### Per Verify-Report (Observation #3720)

- Evidence revision: `sha256:f9b3663b6c9e20adee98a6bdd2c8b0d568615245ff7234b742d0491f5056a638`
- Verdict: `pass_with_warnings` ✅
- 72/72 tasks complete per `tasks.md` (all marked `[x]`)
- 15/15 requirements compliant
- 35/35 scenarios with passing test evidence at runtime
- All remedial commits applied (e082769, fc97125, e33000f)

### Operational Execution (Phase 5)

- **Backup**: Pre-purge dump `solercia-command-pre-ola5-2026-08-27-execute.sql` (649,254 B, verified)
- **Dry-run**: exit 0, all 8 invariants I1–I8 PASS, zero demo rows remaining
- **Execute**: exit 0, 8/8 invariants PASS, data purged successfully
- **Post-restart**: `orgs=1, users=1, projects=3 (SDM/SEG/PAN), tasks=0, sprints=0, boards=3, templates=5, instantiations=0, connectors=3, attachments=0, notifications=0`
- **No demo revival**: After rebuild with `SEED_DEMO_DATA=false`, ana/carlos/diana remain absent; structural seed (org "Solercia", admin user, etc.) regenerated per R4.

## Closure

**Archive state**: `openspec/changes/archive/2026-08-26-42-purga-datos-demo/`  
**Archived at**: 2026-08-26 (UTC)  
**SDD cycle**: Complete  

The change has been fully planned (proposal), specified (specs + design), implemented (apply, 72/72 tasks), verified (pass_with_warnings, no CRITICAL), and archived (specs merged, folder moved, audit trail created). Ready for next SDD iteration.
