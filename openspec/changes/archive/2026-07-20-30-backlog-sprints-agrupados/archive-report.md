# Archive Report: 30 · Backlog con sprints agrupados (secciones colapsables estilo Jira)

**Change**: 30-backlog-sprints-agrupados  
**Archived**: 2026-07-20  
**Mode**: hybrid (filesystem + Engram)  
**Artifact Store**: Complete — proposal, specs, design, tasks, verify-report

## Status Summary

| Phase | Result |
|-------|--------|
| proposal | ✅ Complete |
| spec | ✅ Complete |
| design | ✅ Complete |
| tasks | ✅ Complete (29/29 tasks) |
| apply | ✅ Complete (4 commits, 1337 tests passing) |
| verify | ✅ PASS WITH WARNINGS (0 CRITICAL, 2 WARNING, 1 SUGGESTION) |
| archive | ✅ Complete — spec merged, report written, state updated |

## Specification Merge

### Source: Delta Spec

`openspec/changes/30-backlog-sprints-agrupados/specs/sprints/spec.md` (ADDED requirements)

### Target: Main Spec

`openspec/specs/sprints/spec.md`

### Merge Action

**Type**: APPEND — all 6 ADDED requirements (R11–R16, plus R17 for regression guard) appended to main spec's Requirements section, replacing previous "Cambio 29" conclusion with a new "Cambio 30" section.

**Requirements Added**:
- R11: Agregados por sprint y por Backlog en la lista (`story_count`, `estimation_hours_sum`, `meta.backlog` en GET /projects/{id}/sprints)
- R12: Permisos de la lectura de agregados (mismo modelo que rest del módulo, aislamiento tenant)
- R13: Orden, visibilidad y estados vacíos del Backlog agrupado (active → draft asc → Backlog; closed oculto; vacíos claros)
- R14: Cabecera de sección y acción contextual (nombre, badge, fechas, conteo, suma, botón por estado)
- R15: Persistencia del colapso por proyecto y sección (localStorage, default expandido)
- R16: Ids estables por sección — seam drag & drop 31 (sprint.id / 'backlog')
- R17: No regresión del listado y acciones existentes (suite backend en verde, SprintRead intacto)

**Sections Updated**:
- Línea de origen: agregada mención de delta merge 30
- Propósito: incorpora pestaña Backlog reorganizada con secciones colapsables
- Alcance: GET /projects/{id}/sprints enriquecido con agregados
- Limitaciones: nota sobre test runner frontend ausente (pre-existing, aceptado en cambios 28-29) y showClosedSprints en memoria
- Referencias: nuevos 3 archivos de test y fuentes frontend

**Conflicts**: None — delta only contains ADDED, no MODIFIED/REMOVED, pure append.

## Artifact Contents Verified

### Proposal (`proposal.md`)

✅ Present and complete

| Field | Status |
|-------|--------|
| Intent | Defined — reorganizar Backlog en secciones colapsables por sprint (agregados + UI) |
| Scope | In/Out clearly marked — agregados backend + UI colapsable in scope; drag&drop (31), estimation_display (34), búsqueda (33), crear/editar sprint (29) out scope |
| Capabilities | Modified: `sprints` (lectura enriquecida con agregados; no nuevas) |
| Approach | Described — agregados en backend (única fuente de verdad), cuerpo reutiliza allTasks() en cliente, localStorage para colapso, reutiliza seams de 29 |
| Affected Areas | 5 modules listed (backend sprints/*.py, frontend workspace/*, project-workspace.component.ts, i18n) |
| Risks | 4 riesgos documentados: divergencia conteo, ruptura burndown/close, suma sin formato, desincronización colapso |
| Rollback Plan | Code-only, sin migración, revert simple |
| Success Criteria | 6 criteria listed, todas verificadas por apply/verify |

### Spec — Delta (`specs/sprints/spec.md`)

✅ Present, merged into main spec

| Component | Status |
|-----------|--------|
| ADDED Requirements | 7 requirements (R11–R17) con scenarios — all merged |
| Alcance | GET /projects/{id}/sprints enriquecido (único endpoint modificado, sin nuevos endpoints) |
| Modelo | Campos aditivos a SprintListItem; BacklogAggregate en meta; SprintRead intacto |

### Design (`design.md`)

✅ Present and complete

| Section | Status |
|---------|--------|
| Technical Approach | Única consulta agrupada (no N+1), agregados aditivos, UI composición con signals, localStorage |
| Architecture Decisions | 7 decisions (D1–D7) with rationale y alternativas: GROUP BY sprint_id, SprintListItem aditivo, collapsible as composition, order/visibility, contextual action (29 reuse), localStorage, drag&drop seams |
| Data Flow | Diagrama GET /projects/{id}/sprints → cabecera (servidor) + cuerpo (allTasks() agrupado local) |
| File Changes | 9 files (4 backend + 3 frontend + i18n) |
| Interfaces | Contracts SprintListItem, BacklogAggregate, lista envelope {data, meta} |
| Testing Strategy | Integration (HTTP + Postgres), regresión (suite + SprintRead guard), frontend (signals localStorage mock — no runner disponible) |
| Migration | None — solo código |
| Open Questions | None bloqueante |

### Tasks (`tasks.md`)

✅ Present, all 29 tasks complete

| Phase | Fases | Status |
|-------|-------|--------|
| Fase 1 | 1.1–1.10 (Backend agregados: repository + schemas + service + router + tests + suite verde) | ✅ Complete (10/10 tasks) |
| Fase 2 | 2.1–2.9 (Frontend secciones colapsables: tipos + signals + localStorage + colapso + build) | ✅ Complete (9/9 tasks) |
| Fase 3 | 3.1–3.5 (Estados vacíos + i18n es-CO + build) | ✅ Complete (5/5 tasks) |
| Fase 4 | 4.1–4.5 (Suite completa + no regresión + commits finales) | ✅ Complete (5/5 tasks) |

**Checkbox status**: 29/29 implementation tasks checked (`[x]`), no stale unchecked tasks.

**Commits**: 4 (feat backend agregados, feat frontend secciones, feat vacíos+i18n, fix suite pagination).

### Verify Report (`verify-report.md`)

✅ Present, verdict PASS WITH WARNINGS

| Criterion | Result |
|-----------|--------|
| Completeness | 29/29 tasks checked, 4 commits, no schema migration |
| Build/Tests | ✅ 1337 passed (5 new en test_sprint_backlog_aggregates.py + 2 modified en test_catalog_pagination.py + 1302 baseline), 0 failed, exit 0 |
| Frontend build | ✅ `npm run build` exit 0, ESLint clean |
| Spec Compliance | 4/9 scenarios COMPLIANT (backend + tests); 5/9 PARTIAL (frontend UI, no test runner — pre-existing) |
| TDD Evidence | 5 backend tests (aggregate_by_sprint, backlog with/without, tenant isolation, call count, guard SprintRead) all RED→GREEN; frontend 4 tasks (UI source-only, build verified) |
| Assertion Quality | ✅ All assertions verify real behavior, empty cases triangulated against non-empty, spy test proves single query |
| Design Coherence | ✅ 7/7 architecture decisions followed (D1–D7) |
| Issues Found | CRITICAL: 0; WARNING: 2 noted (FE test coverage gap, actual diff 705 lines vs forecast ~480); SUGGESTION: 1 (showClosedSprints memory-only, documented accepted) |

**Verdict**: PASS WITH WARNINGS — no CRITICAL blockers. Warnings are pre-existing constraint (FE test runner) and documented accepted risk (size exception).

### Warnings & Suggestions Detail

**WARNING 1: Frontend test coverage gap**
- 5/9 spec scenarios (order/visibility/empty-states, header action, localStorage persist, stable ids) verified by source inspection + green `ng build`/`eslint`, not behavioral runtime tests
- Root cause: `frontend/package.json` has no `test` script at all (pre-existing, project-wide, same as changes 28, 29)
- Mitigation: explicitly documented in tasks.md as "npm run build" as runtime harness for U2/U3
- Accepted: yes, not a blocker

**WARNING 2: Actual diff exceeds forecast**
- Forecast: ~480–520 authored lines; actual: 705 insertions / 30 deletions (735 total)
- Reason: reestructuración plantilla project-workspace.component.ts más completa que previsto
- Mitigación: `size-exception` pre-accepted at tasks phase (`Decision needed before apply: No`)
- Accepted: yes, explicitly resolved in tasks.md

**SUGGESTION 1: `showClosedSprints` state memory-only**
- `showClosedSprints = signal(false)` resets to hidden on every tab reload (not persisted to localStorage like `collapsedSections`)
- Explicitly documented in tasks.md as accepted risk (non-blocking, outside scope of 30)
- Accepted: yes, can be revisited if user requests

## Change Closure

### Capability Changed

- `sprints`: **MODIFIED** (GET list enriquecida con agregados por sprint + backlog; UI pestaña Backlog reorganizada con secciones colapsables; no nuevas capabilities)

### Constraints Verified

- ✅ `backend-aggregates-preferred-over-client` — agregados en servidor, cuerpo reutiliza allTasks() sin recomputar
- ✅ `additive-only-sprintread-untouched` — SprintListItem extends SprintRead sin tocar la clase base; burndown/close/start (29) intactos
- ✅ `reuse-loaded-tasks-for-section-bodies-no-extra-fetch` — tasksBySprint computed agrupa allTasks() una sola vez
- ✅ `collapse-state-persisted-client-localstorage` — collapsedSections persiste en localStorage por project+section
- ✅ `stable-section-ids-seam-for-drag-drop-31` — sectionId() función pura retorna sprint.id o 'backlog'
- ✅ `read-only-plus-existing-actions-iniciar-completar` — UI usa canStartSprint/startSprint/openCloseSprint de 29, sin nuevos endpoints
- ✅ `hours-sum-simple-estimation-display-frontier-34` — suma en horas directa, no enriquecida (llega con 34)
- ✅ `ui-copy-es-co-formal-tuteo` — i18n strings en es-CO formal, cero voseo

### Dependencies Resolved

- `depends_on: [29-sprint-borrador]` — requiere estado `draft`, POST /sprints/{id}/start, sprintBadgeClass con rama draft, mapa estado→acción. 29 archivado 2026-07-20.

### Boundary Assertions Verified

All 8 boundary assertions from `state.yaml` verified as implemented:
1. ✅ Pestaña Backlog reorganizada: sprints colapsables + Backlog fijo
2. ✅ Cabecera sección: nombre, fechas/sin fechas, badge, conteo, suma, acción contextual
3. ✅ Acción: draft sin fechas → "Añadir fechas"; draft con fechas → "Iniciar"; active → "Completar"
4. ✅ Agregados calculados backend (conteo/suma), aditivos, SprintRead intacto
5. ✅ Cuerpo reutiliza allTasks() agrupado, sin fetch extra
6. ✅ Estado colapso persistido localStorage, clave proyecto+sección, default expandido
7. ✅ Ids estables sprint-{uuid} / 'backlog' para drag&drop 31
8. ✅ Suite verde 1337/1337, no regresión

## Persist and Traceability

### Artifact IDs (for hybrid mode audit trail)

All artifacts from this change are persisted at filesystem and Engram. Paths recorded for audit trail:

- Proposal: `openspec/changes/30-backlog-sprints-agrupados/proposal.md`
- Spec delta: `openspec/changes/30-backlog-sprints-agrupados/specs/sprints/spec.md`
- Spec main (merged): updated at `openspec/specs/sprints/spec.md`
- Design: `openspec/changes/30-backlog-sprints-agrupados/design.md`
- Tasks: `openspec/changes/30-backlog-sprints-agrupados/tasks.md`
- Verify report: `openspec/changes/30-backlog-sprints-agrupados/verify-report.md`
- Archive report: this document, persisted to Engram as `sdd/30-backlog-sprints-agrupados/archive-report`

### Files Changed During Archive

- **`openspec/specs/sprints/spec.md`** — merged delta spec (R11–R17 added, scopes updated, propósito y alcance ampliados, referencias actualizadas)
- **`openspec/changes/30-backlog-sprints-agrupados/state.yaml`** — updated: `archive: done`, `last_updated: 2026-07-20`
- **`openspec/changes/30-backlog-sprints-agrupados/archive-report.md`** — this report

### Rollback Boundary

The change is code-only, no data-bearing migrations:
- Revert the 4 commits restores prior flat Backlog UI and single-sprint-list endpoint
- Main spec can be reverted if future changes supersede these requirements
- No DB schema changes; sprints with aggregates between apply and potential revert continue to work

## Issues & Mitigation Summary

### Fact-Based Decisions

From spec/design verification:
1. **Aggregation strategy** — Single `GROUP BY sprint_id` query vs N queries or client-side aggregation. Chosen: single query (deterministic, server-sourced).
2. **Frontend test coverage** — No Karma/Jasmine runner in repo; UI verified by source inspection + green build. Explicitly documented as pre-existing accepted constraint (same in changes 28, 29).
3. **Size exception** — 705 lines vs ~480–520 forecast. Accepted at tasks phase with explicit `size-exception` flag (`Decision needed before apply: No`).
4. **Closed sprints visibility** — Hidden by default behind "Ver sprints cerrados" toggle. Accepted design (simplifies initial load).
5. **localStorage toggle state** — `showClosedSprints` in memory only, not persisted. Explicitly marked as accepted non-blocking risk in tasks.md Risks section.

## Sign-Off

**Archived by**: sdd-archive executor  
**Date**: 2026-07-20  
**Verification gate**: ✅ PASS WITH WARNINGS (0 CRITICAL, 2 WARNING, 1 SUGGESTION — all pre-accepted or pre-existing)  
**Task completion**: ✅ 29/29  
**Spec merge**: ✅ Main spec updated (R11–R17 appended + origin/alcance/propósito updated)  
**SDD cycle**: ✅ COMPLETE — change ready for integration

---

**Next**: Change is archived and closed. Pending git operations (folder move to `archive/`, final commit) belong to orchestrator.
