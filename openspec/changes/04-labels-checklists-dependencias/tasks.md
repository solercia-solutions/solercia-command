# Tasks: Labels, checklists, dependencias tarea-tarea y alerta blocked_task

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas | ~1700-1900 (5 módulos nuevos + migraciones + tests TDD) |
| Riesgo 400 líneas | High |
| Commits encadenados | Sí |
| División sugerida | Batch A → B → C → D → E → Final |
| Estrategia de entrega | commits locales directos a main (sin PR) |
| Estrategia de cadena | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Work Units (commit-sized batches)

| Batch | Objetivo | Commit | Riesgo |
|---|---|---|---|
| A | Labels (modelo+migración+CRUD+link/unlink+filtro) | 1 | Medio |
| B | Checklists (modelos+migración+CRUD+toggle+progreso) | 2 | Medio |
| C | task_links (TaskDependency+migración+ciclos+is_blocked) | 3 | Alto — dividir en C1/C2 si supera ~450 líneas |
| D | Alerta blocked_task (estrategia+registry+seed) | 4 | Bajo |
| E | Integración detalle de tarea + docs | 5 | Bajo |
| Final | Suite + lint + tipos | 6 | — |

Migraciones: 3 revisiones Alembic encadenadas (A, B, C), no una sola combinada — requerido por el modelo de commit atómico por batch. A encadena al head de 02 (`add_audit_fields`); B encadena a A; C encadena a B.

Bloqueo: apply NO puede iniciar hasta que `02-contrato-api` esté aplicado (`AuditMixin`, `pagination_params`/`paginate`/`SORTABLE_FIELDS`, cadena Alembic).

## Batch A — Labels
R1 nombre único por proyecto · R2 asignar/desasignar · R3 filtro `label_id` · R4 borrado sin afectar tareas

- [x] T01 RED: nombre duplicado activo en mismo proyecto → 422 (R1)
- [x] T02 GREEN: `modules/labels/models.py` `Label` (Pk+Timestamp+Soft+Audit+Tenant) + migración (down=head 02) + repo/service/router CRUD; montar `labels_router` en `main.py`
- [x] T03 RED+GREEN: `TaskLabel` (Pk+Timestamp) link/unlink; 422 si etiqueta y tarea son de proyectos distintos (R2)
- [x] T04 RED+GREEN: filtro `label_id` en `list_for_project` + query param del router (R3)
- [x] T05 RED+GREEN: soft-delete de `Label` desvincula (soft-delete) sus `TaskLabel`; tareas intactas (R4)

## Batch B — Checklists
R5 CRUD checklist · R6 CRUD/toggle/reorder ítems · R7 progreso agregado

- [ ] T06 RED+GREEN: `TaskChecklist` (Pk+Timestamp+Soft+Audit+Tenant) + migración (down=A) + CRUD repo/service/router; montar `checklists_router` (R5)
- [ ] T07 RED+GREEN: `ChecklistItem` CRUD + reorder por `order` (R6)
- [ ] T08 RED+GREEN: endpoint toggle `is_done` (R6)
- [ ] T09 RED+GREEN: `get_checklist_progress` (done/total por checklist + agregado, espejo de `get_subtask_counts`) (R7)

## Batch C — task_links (TaskDependency)
R8 enlazar mismo proyecto · R9 prevención de ciclos · R10 desenlazar/listar · R11 estado de bloqueo en detalle

- [ ] T10 GREEN: `TaskDependency` (Pk+Timestamp+Soft+Tenant) + migración (down=B); `UniqueConstraint(blocker_task_id, blocked_task_id)`
- [ ] T11 RED+GREEN: link exige mismo proyecto; rechaza auto-lazo y proyectos distintos → 422 (R8)
- [ ] T12 RED primero: ciclo directo A→B→A → 422 con código de ciclo (R9)
- [ ] T13 GREEN: DFS de ciclos en el service — una query de aristas activas (`is_active=true`) del proyecto, adyacencia, DFS desde `blocked` (R9)
- [ ] T14 RED+GREEN: ciclo transitivo A→B→C→A → 422 (R9)
- [ ] T15 RED+GREEN: `type=is_blocked_by` invierte antes de persistir (`related_task_id`→blocker; tarea del path→blocked); `type=blocks` no invierte
- [ ] T16 RED+GREEN: unlink = soft delete (nunca físico); listado bidireccional `blocks`/`is_blocked_by` (R10)
- [ ] T17 RED+GREEN: `get_incomplete_blockers` (aristas activas, `blocker.completed_at IS NULL`) → `is_blocked`+`blockers[]` en `TaskRead`; se limpia al completar el bloqueador (R11)
- [ ] T18 GREEN: router link/unlink/list con `pagination_params`+`paginate`+`SORTABLE_FIELDS` propio (contrato de 02); montar `task_links_router`

## Batch D — Alerta blocked_task
R12 estrategia en registry · R13 deduplicación · R14 seed idempotente

- [ ] T19 RED+GREEN: `BlockedTaskStrategy.evaluate` notifica al `assignee` de la tarea bloqueada tras `threshold_params.blocked_days` (default 3) (R12)
- [ ] T20 RED+GREEN: sin notificación si el bloqueo es reciente (< `blocked_days`) (R12)
- [ ] T21 RED+GREEN: `dedup_key=f"blocked_task:{blocked_task_id}"` evita duplicados en corridas repetidas (R13)
- [ ] T22 GREEN: registrar `blocked_task` en `alerts/registry.py`; `db_init.py` — 5.ª regla en `_DEFAULT_ALERT_RULES`, idempotente por `rule_type` (R14)

## Batch E — Integración detalle de tarea + docs

- [ ] T23 RED+GREEN: `TaskRead` += `labels[]` + `checklist_progress`; `get_task`/`get_task_by_key` agregan las 3 consultas acotadas (labels, progreso, bloqueadores) sin N+1
- [ ] T24 Integración: `GET /tasks/{id}` expone `labels[]`+`checklist_progress`+`is_blocked`+`blockers[]` simultáneamente (test único); actualizar `docs/API.md` con los endpoints nuevos si el contrato de docs lo exige

## Final

- [ ] T25 Suite completa verde: `cd backend && pytest tests/ -v`; `ruff check .`; `mypy .`
