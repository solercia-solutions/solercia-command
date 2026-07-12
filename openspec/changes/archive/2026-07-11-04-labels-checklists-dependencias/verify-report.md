# Verify Report: 04-labels-checklists-dependencias

**Fecha**: 2026-07-12
**Modo**: Strict TDD (test runner: `cd backend && pytest tests/ -v`, backend/.venv)
**Artifact store**: hybrid (openspec + Engram)

## Veredicto final: PASS

0 CRITICAL, 0 WARNING, 2 SUGGESTION.

## Rebuild y entorno

- `docker compose up -d --build backend` — imagen reconstruida, entrypoint aplicó migraciones `0003 → 0004 (add_labels) → 0005 (add_checklists) → 0006 (add_task_dependencies)` sin errores.
- `alembic current` sobre `solercia_test` (host `localhost:5432`, tras `DROP/CREATE` previo del apply — no repetido porque ya estaba en `0006 (head)`): sin drift.
- Suite completa ejecutada dos veces (antes y después de los spot-checks HTTP en vivo) con `TEST_DATABASE_URL`, `API_BASE_URL=http://localhost:8000/api/v1` y `TEST_AUTH_TOKEN` (JWT fresco vía `POST /auth/login` con `admin@solercia.com`): **230 passed, 0 failed** ambas veces.
- `ruff check .` — clean (132 archivos). `mypy app` — clean, 0 issues.

## 1. Trazabilidad requisito → implementación → test

### Labels (R1-R4)

| Requisito | Escenario | Test | Evidencia en vivo |
|---|---|---|---|
| R1 nombre único por proyecto | Creación exitosa | `test_create_label_success` | POST `/projects/{id}/labels` → 201 |
| R1 | Nombre duplicado activo | `test_create_label_duplicate_name_in_same_project_is_422` | Repetir creación con mismo `name` → 422 confirmado en vivo |
| R1 | Mismo nombre en proyectos distintos | `test_create_label_same_name_in_different_projects_both_succeed` | — |
| R2 asignar/desasignar | Asignar mismo proyecto | `test_assign_label_to_task_of_same_project` | POST `/tasks/{id}/labels` → detalle muestra `labels[]` |
| R2 | Asignar de otro proyecto | `test_assign_label_from_other_project_is_422` | — |
| R2 | Desasignar | `test_unassign_label_removes_it_from_task` | — |
| R3 filtro `label_id` | Filtrado por etiqueta | `test_filter_tasks_by_label_id_returns_only_tagged_tasks` | `GET /projects/{id}/tasks?label_id=` en vivo devolvió únicamente la tarea etiquetada (1/1) |
| R4 borrado sin afectar tareas | Borrado con tareas vinculadas | `test_delete_label_unlinks_from_tasks_without_deleting_them` | — |

### Checklists (R5-R7, referidas como R1-R3 en el contexto de dominio)

| Requisito | Escenario | Test | Evidencia en vivo |
|---|---|---|---|
| CRUD de checklists | Creación | `test_create_checklist_returns_201_and_appears_in_listing` (+ update/delete) | POST `/tasks/{id}/checklists` → 201 |
| CRUD/toggle/reorder ítems | Alternar `is_done` | `test_toggle_item_flips_is_done` | `PATCH /checklist-items/{id}/toggle` en vivo: `is_done` false→true |
| | Reordenar | `test_reorder_items_updates_display_order` | — |
| Progreso agregado | Progreso por checklist | `test_checklist_listing_reports_done_over_total` | Detalle en vivo tras el toggle: `checklist_progress = 0.5` (1/2) |
| | Agregado con varios checklists | `test_get_checklist_progress_aggregates_across_checklists` | — |

### Task-dependencies (4 requisitos de la spec)

| Requisito | Escenario | Test | Evidencia en vivo |
|---|---|---|---|
| Enlazar mismo proyecto | Enlace válido | `test_link_two_tasks_same_project_succeeds` | POST `/tasks/{A}/dependencies` (`is_blocked_by` B) → 201 |
| | Proyectos distintos | `test_link_tasks_of_different_projects_is_422` | — |
| Prevención de ciclos | Directo A→B→A | `test_direct_cycle_via_api_is_422_with_cycle_code` | Enlace inverso B is_blocked_by A → 422 `dependency_cycle` confirmado en vivo |
| | Transitivo A→B→C→A | `test_transitive_cycle_via_api_is_422` | Cadena A←B←C construida en vivo; enlace C is_blocked_by A → 422 `dependency_cycle` confirmado |
| Desenlazar/listar | Bidireccional | `test_list_dependencies_is_bidirectional` | — |
| | Desenlazar | `test_unlink_removes_edge_from_both_listings`, `test_unlink_is_soft_delete_row_still_exists_in_db` | DELETE en vivo → 204, fila `is_active=false` verificada por SQL directo |
| Estado de bloqueo en detalle | Tarea bloqueada | `test_task_detail_reports_blocked_state` | `GET /tasks/{A}` en vivo: `is_blocked=true`, `blockers=[B]` |
| | Resuelto al completar | `test_task_detail_unblocks_when_blocker_completes` | — |

### Alert-blocked-task (3 ADDED Requirements)

| Requisito | Escenario | Test | Evidencia en vivo |
|---|---|---|---|
| Estrategia registrada | Notificación por bloqueo prolongado | `test_evaluate_notifies_assignee_after_blocked_days` | Arista backdateada a 5 días vía SQL; `POST /alerts/evaluate` → `{"created": 1}`; fila confirmada en `notifications` (`rule_type=blocked_task`, `dedup_key=blocked_task:{id}`) |
| | Sin notificación por bloqueo reciente | `test_evaluate_skips_recently_blocked_task` | — |
| Deduplicación | Corridas repetidas sin duplicar | `test_repeated_evaluation_does_not_duplicate_notification` | Segunda llamada a `/alerts/evaluate` en vivo → `{"created": 0}`, conteo en BD sigue en 1 |
| Seed idempotente | Seed inicial / re-seed sin duplicar | `test_seed_creates_five_rules_including_blocked_task`, `test_reseed_does_not_duplicate_rules` | `docker compose restart backend` (re-ejecuta `seed_default()`) → `alert_rules` sigue con exactamente 1 fila por `rule_type` (5 reglas, incluida `blocked_task`) |

**Cobertura de escenarios obligatorios (del artefacto de spec)**: los 6 escenarios listados como obligatorios (ciclo directo, ciclo transitivo, filtro por etiqueta, progreso 2/5, dedup de blocked_task, nombre único) tienen test cubridor en verde Y evidencia HTTP en vivo adicional donde el contexto lo pedía explícitamente.

## 2. Correcciones de gate (BINDING) — verificación física

| Corrección | Verificación | Resultado |
|---|---|---|
| #1 SoftDelete en `TaskDependency`, unlink=`is_active=False` | `app/modules/task_links/models.py:23` hereda `SoftDeleteMixin`; `service.py::unlink` hace `dependency.is_active = False; dependency.deleted_at = ...`; jamás un `db.delete()` físico (grep confirmó cero usos de `db.delete`/`session.delete` en `task_links/`) | ✅ Cumple |
| #2 Dirección canónica invertida para `is_blocked_by` | `service.py::link` — con `type == "is_blocked_by"`: `blocker_id, blocked_id = related.id, task.id`; con `type == "blocks"` no invierte | ✅ Cumple, confirmado además en vivo (`test_type_is_blocked_by_inverts_before_persisting`) |
| Filtro `is_active` en DFS y en `get_incomplete_blockers` | `repository.py::list_active_edges_for_project` y `get_incomplete_blockers` ambos filtran `TaskDependency.is_active.is_(True)` | ✅ Cumple |
| #3 Criterio de desbloqueo `completed_at IS NOT NULL` (no "cancelado", trazado como deuda) | `get_incomplete_blockers` filtra `Task.completed_at.is_(None)`; docstring documenta la deuda explícitamente | ✅ Cumple, deuda trazada (no omisión silenciosa) |
| #4 `TenantMixin` directo en las 4 entidades nuevas + audit | `Label`, `TaskChecklist`, `ChecklistItem`: heredan `TenantMixin` + `AuditMixin`; `TaskDependency`: hereda `TenantMixin` (sin `AuditMixin`, documentado explícitamente en el docstring del modelo — consistente con design.md "Decisión: Modelo de datos") | ✅ Cumple |
| #5 Paginación (`pagination_params`+`paginate()`+`SORTABLE_FIELDS`) en labels y task_links | `labels/router.py` y `task_links/router.py` importan `pagination_params`/`build_list_meta`; `labels/repository.py` y `task_links/repository.py` definen `SORTABLE_FIELDS` y llaman `paginate()` cuando `pagination.requested` | ✅ Cumple. Checklists NO usa paginación (correcto — la corrección #5 solo menciona labels y task_links) |
| #6 Nomenclatura spec↔design | Confirmado por lectura cruzada; sin discrepancia funcional | ✅ Cumple |

## 3. Reconciliaciones documentadas por apply — evaluación

| Desviación reportada | Verificación independiente | Veredicto |
|---|---|---|
| Migraciones encadenan al head real (0003), no al nominal "02" | `alembic history` muestra la cadena real `0003→0004→0005→0006`; sin diff tras `alembic upgrade head` | Aceptable, razonado (03-boards ya existía cuando este apply comenzó) |
| `TaskLabel`: hard delete físico al soft-deletar `Label` | `labels/repository.py::unlink_all_for_label` usa `delete(TaskLabel).where(...)` (SQL físico); `TaskLabel` no tiene `SoftDeleteMixin` en `models.py` | Aceptable — consistente con el precedente `UserRole`/`RoleMenu` citado en design.md; resultado funcional idéntico al exigido por la spec (tareas intactas) |
| `ChecklistItem.text`, no `.content` | `checklists/models.py:55` usa `text: Mapped[str]`; coincide literalmente con `specs/checklists.md` | Aceptable — spec gana sobre inconsistencia de nomenclatura en design.md |
| `BlockedTaskStrategy` acepta `blocked_days` y `days` como alias | `alerts/strategies/blocked_task.py:34-36`: `threshold_params.get("blocked_days", threshold_params.get("days", 3))` | Aceptable — no rompe ninguna de las dos fuentes de verdad |
| Reactivación de aristas soft-deleted en `link()` | Verificado EN VIVO: unlink (204, `is_active=false`) → relink del mismo par → misma fila (`id` idéntico) reactivada, `UniqueConstraint` no violada | Aceptable y verificado — necesario estructuralmente, sin escenario Gherkin explícito pero comportamiento correcto |
| `docs/API.md` actualizado | Confirmadas 3 secciones nuevas: "Etiquetas (labels)" L1132, "Checklists" L1208, "Dependencias entre tareas" L1286 | Aceptable |

## 4. Idempotencia del seed (verificación adicional solicitada)

- Estado inicial: 5 filas en `alert_rules` (una por `rule_type`, incluida `blocked_task`).
- `docker compose restart backend` → entrypoint re-ejecuta `seed_default()` → `_ensure_alert_rules` vuelve a iterar `_DEFAULT_ALERT_RULES`.
- Estado final: sigue en 5 filas, una por `rule_type`. **Sin duplicados confirmado.**

## 5. Alcance — sin scope creep

- `git show --stat` de los 7 commits (`307b9bd`, `de5740a`, `30afb8c`, `4a124d8`, `3ea6c9f`, `c6af48f`, `1cde015`) — cero archivos bajo `frontend/`.
- Constraint `frontend-frozen` de `state.yaml` respetada.

## 6. TDD Compliance (Strict TDD)

| Check | Resultado | Detalle |
|---|---|---|
| TDD Evidence reportado | ⚠️ Parcial | `apply-progress` (Engram #1316) documenta el ciclo RED→GREEN de forma narrativa por batch, no como tabla formal por tarea; `tasks.md` sí anota RED/GREEN por tarea individual (T01-T24) |
| Todas las tareas tienen test | ✅ | 5 módulos de test nuevos, uno por batch funcional |
| RED confirmado (archivos existen) | ✅ | `test_labels.py`, `test_checklists.py`, `test_task_links.py`, `test_task_detail_enrichment.py`, `test_blocked_task_alert.py` — verificados en el filesystem |
| GREEN confirmado (tests pasan) | ✅ | 230/230 passed en ejecución real, dos corridas independientes |
| Triangulación | ✅ | Ciclos: 4 casos unitarios (`TestDetectsCycleUnit` — sin aristas, directo, transitivo, aristas no relacionadas) + 2 de integración (directo/transitivo vía API) |
| Conteo de tests nuevos vs. reportado | ✅ Coincide | Reportado: 9+10+17+3+7+5=51. Verificado en filesystem: labels=9, checklists=10, task_links=20 (17+3), task_detail_enrichment=5, blocked_task_alert=7 → 51 |

**TDD Compliance**: 5/6 checks en verde. El único hueco es de FORMATO del artefacto (tabla dedicada ausente en `apply-progress`), no de sustancia — la evidencia RED/GREEN por tarea SÍ existe en `tasks.md` y fue corroborada con ejecución real.

### Auditoría de calidad de aserciones

Escaneados los 5 archivos de test nuevos (`test_labels.py`, `test_checklists.py`, `test_task_links.py`, `test_task_detail_enrichment.py`, `test_blocked_task_alert.py`):

- Cero tautologías (`assert True`, `assert 1 == 1`).
- Cero "ghost loops" — los `for` encontrados son de *setup* (crear N tareas/ítems), no de aserción sobre colecciones potencialmente vacías; las aserciones sobre listas/sets comparan contra un valor esperado fijo y no vacío.
- 128 aserciones en total sobre 51 tests nuevos (~2.5 aserciones/test) — sin señal de mock-heavy (son tests de integración vía `httpx.AsyncClient`, no mocks).

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real.

## 7. Completitud de tareas

- 25/25 tareas marcadas `[x]` en `tasks.md`, verificadas contra el estado real del código (no solo el checkbox): cada tarea tiene código de producción correspondiente + test verde.
- `state.yaml`: `apply: done`, `next_recommended: sdd-verify` — coherente.

## Issues

### CRITICAL
Ninguno.

### WARNING
Ninguno.

### SUGGESTION

1. **Formalizar la tabla "TDD Cycle Evidence" en `apply-progress`** para futuros batches (05+): el formato narrativo actual es suficiente para verificar sustancia (se cruzó con `tasks.md` y ejecución real), pero una tabla explícita por tarea agilizaría auditorías futuras sin depender de una lectura cruzada de dos artefactos.
2. **Estado `cancelled` pendiente** (deuda ya trazada en design.md #3): cuando exista un estado terminal de cancelación en el dominio (p. ej. vía metodología `custom`), el criterio de desbloqueo de `get_incomplete_blockers` y `BlockedTaskStrategy` debe extenderse más allá de `completed_at IS NOT NULL`. No bloquea este cambio — ya está documentado como deuda explícita, no omisión silenciosa.

## Recomendación

**Listo para `sdd-archive`.** Cero hallazgos CRITICAL o WARNING; las dos SUGGESTION son de mejora de proceso/deuda ya trazada, no defectos funcionales.
