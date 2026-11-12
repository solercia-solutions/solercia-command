# Archive Report: 17-adapter-glpi

**Change**: 17-adapter-glpi  
**Archived**: 2026-07-19  
**Artifact Store Mode**: hybrid  
**Veredicto**: PASS → ARCHIVED

## Executive Summary

El cambio **17-adapter-glpi** (Adaptador GLPI + homologación de usuarios) completó exitosamente todas las fases del ciclo SDD: proposal → spec → design → tasks → apply (9 commits) → fix 4R (1 commit) → verify (PASS) → **archive**. 

Dos nuevas capacidades (`glpi-adapter`, `user-homologation`) + dos deltas en el núcleo (`integration-ports`, `connectors`). 19 requisitos, 40 escenarios COMPLIANT. 872/872 tests al core + 13 fallas preexistentes (cero regresión). Ciclo SDD CIERRE: archivos fusionados en openspec/specs, cambio movido a archivo, todas las fases done.

---

## Artifacts Reconciliation

### Specification Deltas Merged into Main Specs

| Domain | Type | Action | Details |
|--------|------|--------|---------|
| `openspec/specs/integration-ports/spec.md` | Modified | Merged | ADDED: "Identidad de personas asignadas" (2 esc., new req) + MODIFIED: "Protocolo de adaptador uniforme" (ampliado para `credential_kind`/`api_token`, 3 esc. totales). Preserva 4 req. originales de 14. |
| `openspec/specs/connectors/spec.md` | Modified | Merged | ADDED: `credential_kind` (2 esc., new req) + registro directo `api_token` (2 esc., new req) + MODIFIED: `authorize` (ahora rechaza `api_token` con error controlado, 3 esc.). Preserva 6 req. originales de 14. |
| `openspec/specs/glpi-adapter/spec.md` | New | Created | Nueva capability: adaptador GLPI con 7 req. (11 escenarios totales). Registro import-time, auth `api_token`, session cache Redis, reinicio 401, extracción de tickets con asignados, frontera read-only, manejo de errores, aislamiento multi-tenant. |
| `openspec/specs/user-homologation/spec.md` | New | Created | Nueva capability: homologación con 7 req. (17 escenarios totales). Documento de identidad, cascada email→documento→nombre, mapeos persistentes, cola consolidada por persona, resolución manual, sincronización on-demand, aislamiento multi-tenant. |

**Merge Summary**: 4 spec deltas → 2 main specs updated + 2 new specs created = 4 total specs synced into `openspec/specs/`.

---

## Archived Artifacts

**Location**: `openspec/changes/archive/2026-07-19-17-adapter-glpi/`

| Artifact | Status | Observation IDs |
|----------|--------|-----------------|
| proposal.md | Archived | 1640 (Engram) |
| design.md | Archived | 1655 (Engram) |
| tasks.md (58/58 tasks complete) | Archived | 1667 (Engram) |
| specs/integration-ports/spec.md (delta) | Archived | —  (delta specs not persisted separately; merged into main specs) |
| specs/connectors/spec.md (delta) | Archived | — |
| specs/glpi-adapter/spec.md (new) | Archived | — |
| specs/user-homologation/spec.md (new) | Archived | — |
| verify-report.md (PASS verdict) | Archived | 1716 (Engram) |
| state.yaml (all phases done) | Archived | — |

**Folder Move**: `openspec/changes/17-adapter-glpi/` → `openspec/changes/archive/2026-07-19-17-adapter-glpi/` ✅

---

## Phase Closure

### Proposal → Spec → Design → Tasks

- **Proposal (DONE)**: Intent ratified, scope clear, capabilities declared (glpi-adapter new, user-homologation new, integration-ports MODIFIED, connectors MODIFIED), risks mitigated, success criteria defined.
- **Spec (DONE)**: 4 domain specs generated. Deltas documented (integration-ports +2 req., connectors +3 req.). New specs ratified: glpi-adapter (7 req.), user-homologation (7 req.). Total: 19 req., 40 scenarios.
- **Design (DONE)**: Architectural decisions documented (adapter separation vs. homologation module, `credential_kind` protocol vs. optional methods, `difflib` vs. `pg_trgm`, number document global unicidad, queue header+detail consolidation). 8-lote TDD chain planned with HIGH workload risk (Lotes 2 y 8 > 400 lines each), excepted via `delivery_strategy: exception-ok`.
- **Tasks (DONE)**: 8 sequential lotes (commits), 58 tasks total, all [x] marked. RED→GREEN→VERIFY per lote, final suite 872/13 (preexisting faults, no regression).

### Apply (9 commits) + Fix 4R (1 commit)

**Apply Commits (Lotes 1-8)**:
1. Delta 14 integration-ports/connectors (CredentialKind, OAuthHandshake, ApiTokenHandshake, ExternalPerson, Ticket.assignees)
2. Migración única + modelos ORM + er-model.md (numero_documento, credential_kind, settings, 3 GLPI tables)
3. Conectores api_token: registro directo + authorize rechazado
4. Cliente GLPI base: initSession/killSession, paginación Range, allowlist SSRF
5. Cache session_token Redis + reinicio ante 401
6. Adaptador completo: mapper + adapter + errors + import-time registration
7. Cascada de homologación: email→documento→nombre
8. Cola + mapeos + REST + wiring final + VERIFY

**Fix 4R (1 commit: 245cdc1)**:
- CRITICAL #1: Cruce de tenant en `resolve_unmatched_entry` → added `is_org_member()` check antes de crear link
- CRITICAL #2: Ticket envenenado bloqueando sync completo → try/except por ticket con logger.warning y continue
- +6 WARNINGs no-bloqueantes: retry/backoff, Redis→503, máquina de estados 409, GlpiConfigError→422
- +10 tests RED→GREEN nuevos

**Resultado**: HEAD 245cdc1, 872/872 tests passed (core scope), 13 legacy preexistent failures unchanged = 0 regression verified.

### Verify (DONE)

**Verdict**: PASS  
**Requirements**: 19/19 COMPLIANT  
**Scenarios**: 40/40 COMPLIANT  
**Tests**: 872 passed (10 nuevos del fix) + 13 preexistent unchanged  
**Build**: ruff clean, mypy clean  
**Migration**: 0017_add_glpi_homologation.py, round-trip verified, `alembic check` without diff  
**Docs**: er-model.md y c4-architecture.md updated y verified against real code  

Blockers: 0  
Critical issues: 0 (2 CRITICAL de 4R fueron corregidos en apply)  
Review gate result: allow ✅

---

## Spec Fusion Details

### Integration-Ports (14 base → 17 delta merged)

**ADDED**:
- "Identidad de personas asignadas en el puerto de tickets" (2 scenarios): `Ticket.assignees` poblado por adaptador, nunca null

**MODIFIED**:
- "Protocolo de adaptador uniforme" → extendido para `credential_kind (oauth|api_token)`, handshakes separados `OAuthHandshake`/`ApiTokenHandshake`, núcleo rechaza OAuth sobre `api_token` (1 scenario nuevo)

**Preserved**: Puertos read-only, registro extensible, fake adapter, frontera solo-lectura (4 reqs de 14)

### Connectors (14 base → 17 delta merged)

**ADDED**:
- "Tipo de credencial del conector" (2 scenarios): `credential_kind` field, default oauth, immutable
- "Registro directo de credenciales api_token sin flujo OAuth" (2 scenarios): POST endpoint, credentials encrypted, gateado admin/manager

**MODIFIED**:
- "Inicio del flujo OAuth (authorize)" → agregó scenario nuevo: authorize sobre `api_token` responde error controlado

**Preserved**: Modelo multi-tenant, CRUD permisos, varias cuentas, callback, tokens cifrados, etc. (6 reqs de 14)

### GLPI-Adapter (NEW spec, 7 requirements, 11 scenarios)

1. Registro import-time sin tocar núcleo (1 esc.)
2. Auth `api_token` con session_token cached en Redis TTL (2 esc.)
3. Reinicio de sesión ante expiración (2 esc.)
4. Extracción tickets con asignados (2 esc.)
5. Frontera read-only (1 esc.)
6. GLPI inaccesible o credenciales inválidas (2 esc.)
7. Aislamiento multi-tenant (1 esc.)

### User-Homologation (NEW spec, 7 requirements, 17 scenarios)

1. Documento de identidad (2 esc.)
2. Cascada email→documento→nombre (4 esc.)
3. Mapeos confirmados persistentes (3 esc.)
4. Cola consolidada por persona (2 esc.)
5. Resolución manual (3 esc.)
6. Sync on-demand (2 esc.)
7. Aislamiento multi-tenant (1 esc.)

---

## Deviations Documented in As-Built

All deviations are recorded in apply-progress and verify-report:

1. **OAuthHandshake extraction**: Spec delta MODIFIED required refactoring existing IntegrationAdapter protocol; existing contract test updated, no silent regressions, 3 adapters (fake, microsoft365, google) harmonized with new protocol.

2. **JSON blob encryption vs. field mapping**: `register_api_token_credentials` encrypts raw as complete JSON blob in `access_token_enc` instead of field-by-field GLPI-specific mapping → decision to keep connectors/service.py 100% provider-agnostic, same pattern as 14's nucleus; adapter layer (GLPI) decodes on reauth.

3. **Specification delta schema**: Integration-ports delta (specs/integration-ports/spec.md in changes/) contains ADDED + MODIFIED sections; stored in archive as historical record (not a new spec, but a delta document referenced by proposal.md).

4. **No two-session persistence test**: All 5 write flows (`run_sync`, `resolve`, `ignore`, `revoke_link`, `register_api_token_credentials`) call explicit `commit()` (verified by line-by-line inspection), but test suite uses shared SAVEPOINT fixture instead of two independent AsyncSession instances — same structural gap as pre-fix 20-sso-keycloak; WARNING (non-blocking), recommended future test pattern before 18/19 depend on glpi_user_links.

---

## Source of Truth Updated

The following specs in `openspec/specs/` now include the merged changes and are the source of truth for future work:

- `openspec/specs/integration-ports/spec.md` — 6 requirements (4 from 14 + 2 new from 17)
- `openspec/specs/connectors/spec.md` — 9 requirements (6 from 14 + 3 new from 17)
- `openspec/specs/glpi-adapter/spec.md` — 7 requirements (NEW)
- `openspec/specs/user-homologation/spec.md` — 7 requirements (NEW)

**Total in source of truth**: 29 requirements (19 new/modified by change 17 + 10 preserved from base 14).

---

## SDD Cycle Closure

✅ **Proposal**: Intent clear, scope bounded, capabilities declared, risks identified  
✅ **Spec**: 4 domain specs, 19 req., 40 scenarios, deltas documented, new specs ratified  
✅ **Design**: Architecture decisions, 8-lote TDD chain, testing strategy, threat matrix, rejected alternatives  
✅ **Tasks**: 58 tasks (all [x]), RED→GREEN→VERIFY per lote, 872 tests passed (core), 0 regression  
✅ **Apply**: 9 commits + 1 fix, 2 CRITICAL fixed with evidence RED→GREEN, 10 tests new  
✅ **Verify**: PASS verdict, 19/19 req. COMPLIANT, 40/40 scenarios COMPLIANT, 0 blockers, migration verified, docs updated  
✅ **Archive**: All artifacts moved to `openspec/changes/archive/2026-07-19-17-adapter-glpi/`, specs merged into main, state.yaml set to archive: done  

**Next Change**: Ready for 18-adapter-dynamics (or 19-adapter-jira), which depend on `connectors.credential_kind`/`connectors.settings` and `integration-ports` deltas introduced by this change.

---

## Engram Observation IDs (Traceability)

| Artifact | Observation ID | Created |
|----------|---|---|
| Proposal | 1640 | 2026-07-18 19:15:02 |
| Spec | 1652 | 2026-07-18 19:22:43 |
| Design | 1655 | 2026-07-18 19:24:00 |
| Tasks | 1667 | 2026-07-18 19:40:04 |
| Verify-Report | 1716 | 2026-07-19 04:21:13 |
| Archive-Report | TBD (this artifact) | 2026-07-19 |

---

**Archiver**: sdd-archive (phase executor)  
**Archive Date**: 2026-07-19  
**Commit Hash** (latest in-code): 245cdc1  
**Status**: COMPLETE — Ready for next ola
