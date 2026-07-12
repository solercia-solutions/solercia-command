# Tasks: Contrato de API — paginación opt-in, auditoría created_by/updated_by, docs/API.md

Depende de `01-fundacion-tdd` aplicado (fixtures NullPool+SAVEPOINT+ASGI+factories, baseline Alembic). No iniciar apply antes.

## Requirement Legend (traceability)

| Ref | Fuente |
|-----|--------|
| R1 | api-pagination.md — Envelope de lista con paginación estándar (opt-in, compat sin params) |
| R2 | api-pagination.md — Validación de límites de page y size (422) |
| R3 | api-pagination.md — Whitelist de campos ordenables por endpoint (422 fuera de whitelist) |
| R4 | audit-fields.md — Auditoría automática created_by/updated_by |
| R5 | audit-fields.md — Exposición de auditoría en respuestas |
| G1 | design.md gate #1 — `meta.tree` de menus se preserva (fusión aditiva) |
| G2 | design.md gate #2 — auditoría en UPDATE masivo (`close_sprint`) |
| G3 | design.md gate #3 — `assignee_name` excluido de SORTABLE_FIELDS |
| G4 | design.md gate #4 — criterio de 11 modelos SoftDeleteMixin (incluye Menu global) |
| G5 | design.md gate #5 — filas del seed sin auditoría, aceptado |
| G6 | design.md gate #6 — artefacto de migración solo guardado por `alembic check` de 01 |

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-750 (13 módulos tocados: 11 listas + AuditMixin + migración + docs) |
| 400-line budget risk | High |
| Chained PRs recommended | No (esta sesión no usa PRs) |
| Suggested split | 6 commits secuenciales (A, B1, B2, B3, C, D) |
| Delivery strategy | Local commits directos a `main`, sin PR, un commit convencional por batch |
| Chain strategy | stacked-to-main (análogo por commits: cada batch se integra a `main` en orden) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units (commit batches)

| Batch | Commit (conventional) | Contenido | Depende de |
|-------|------------------------|-----------|------------|
| A | `feat(pagination): add shared pagination module + query-params dependency` | `pagination.py` + tests helper-level | 01 aplicado |
| B1 | `feat(pagination): wire tasks and notifications list endpoints` | tasks + notifications | A |
| B2 | `feat(pagination): wire admin catalogs (users, roles, menus)` | users, roles, menus (+ `meta.tree`) | A |
| B3 | `feat(pagination): wire remaining list endpoints` | dependencies, projects, sprints, comments, attachments, alert-rules | A |
| C | `feat(audit): add AuditMixin, migration, service stamping and bulk-update threading` | AuditMixin + `get_actor_id` + migración + stamping + `close_sprint` | B1-B3 (schemas Read compartidos) |
| D | `docs(api): refresh docs/API.md to match pagination and audit contract` | docs/API.md | A-C |

## Batch A — Módulo compartido de paginación

- [x] T01 RED — `backend/tests/test_pagination.py`: `pagination_params` — defaults (`size=20`), `page<1`→422, `size>100`→422, `order` fuera de `{asc,desc}`→422. (R2)
- [x] T02 GREEN — Crear `backend/app/shared/pagination.py`: dependency `pagination_params(page, size=20, sort=None, order="desc")`. (R2)
- [x] T03 RED — `test_pagination.py`: `paginate(stmt, params, sortable)` — aplica `ORDER BY` mapeado por `SORTABLE_FIELDS`, `LIMIT/OFFSET`, `COUNT(*)`; `sort` fuera del dict → 422. (R1, R3)
- [x] T04 GREEN — Implementar `paginate()` en `pagination.py` (tipar `SORTABLE_FIELDS: dict[str, InstrumentedAttribute]`). (R1, R3)
- [x] T05 RED — `test_pagination.py`: `build_list_meta()` — sin params devuelve exactamente `{total}`; con params devuelve `{page,size,total}`; fusiona sobre un `meta` existente sin eliminar claves ajenas (ej. `tree` simulado). (R1, G1)
- [x] T06 GREEN — Implementar `build_list_meta()` en `pagination.py` — solo añade/actualiza `page`/`size`/`total`, nunca remueve otras claves. (R1, G1)

## Batch B1 — tasks + notifications

- [x] T07 RED — `backend/tests/test_tasks_pagination.py`: `GET /projects/{id}/tasks` sin params = lista completa + `meta{total}` (byte-compat); `?page=2&size=10` = slice correcto; `?sort=assignee_name`→422; `?sort=created_at&order=desc`→200 ordenado. (R1, R2, R3, G3)
- [x] T08 GREEN — Wire `pagination_params`/`paginate` en `tasks/router.py` + `tasks/repository.py`; `SORTABLE_FIELDS` sin `assignee_name`. (R1, R2, R3, G3)
- [x] T09 RED — `backend/tests/test_notifications_pagination.py`: `GET /notifications` — mismos 4 escenarios (compat, slice, sort inválido 422, sort/order válidos). (R1, R2, R3)
- [x] T10 GREEN — Wire pagination en `notifications/router.py` + `notifications/repository.py`. (R1, R2, R3)

## Batch B2 — catálogos admin (users, roles, menus)

- [x] T11 RED — `backend/tests/test_users_roles_pagination.py`: `GET /admin/users` y `GET /admin/roles` — compat, slice, sort inválido 422, sort/order válido. (R1, R2, R3)
- [x] T12 GREEN — Wire pagination en `users/{router,repository}.py` y `roles/{router,repository}.py`. (R1, R2, R3)
- [x] T13 RED — `backend/tests/test_menus_pagination.py`: `GET /admin/menus` — compat + slice; assert explícito `meta.tree` presente e inalterado CON y SIN parámetros de paginación. (R1, G1)
- [x] T14 GREEN — Wire pagination en `menus/router.py` + `menus/repository.py` usando `build_list_meta()` sobre el dict `{total, tree}` existente sin perder `tree`. (R1, R3, G1)

## Batch B3 — dependencies, projects, sprints, comments, attachments, alert-rules

- [x] T15 RED — `backend/tests/test_catalog_pagination.py`: `GET /admin/dependencies`, `GET /projects`, `GET /projects/{id}/sprints` — compat, slice, sort inválido 422, sort/order válido. (R1, R2, R3)
- [x] T16 GREEN — Wire pagination en dependencies, projects, sprints (`router.py`+`repository.py`). (R1, R2, R3)
- [x] T17 RED — `backend/tests/test_nested_pagination.py`: `GET /tasks/{id}/comments`, `GET /tasks/{id}/attachments`, `GET /alert-rules` — mismos 4 escenarios. (R1, R2, R3)
- [x] T18 GREEN — Wire pagination en comments, attachments, alert_rules (`router.py`+`repository.py`). (R1, R2, R3)

## Batch C — AuditMixin, migración, stamping y UPDATE masivo

- [x] T19 RED — `backend/tests/test_audit_mixin.py`: `AuditMixin` declara `created_by`/`updated_by` UUID nullable, FK→`users.id` `ON DELETE SET NULL`. (R4)
- [x] T20 GREEN — Añadir `AuditMixin` en `backend/app/shared/base_model.py`. (R4)
- [x] T21 GREEN — Mezclar `AuditMixin` en los 11 modelos con `SoftDeleteMixin` (`alert_rules`, `attachments`, `comments`, `dependencies`, `menus`, `organizations`, `projects`, `roles`, `sprints`, `tasks`, `users` — `models.py`). (R4, G4)
- [x] T22 RED — `backend/tests/test_actor_id_dependency.py`: `get_actor_id` devuelve `UUID` con JWT válido, `None` sin contexto autenticado. (R4)
- [x] T23 GREEN — Añadir `get_actor_id` en `backend/app/dependencies.py`. (R4)
- [x] T24 RED — `backend/tests/test_audit_stamping.py`: `POST` en tasks estampa `created_by=updated_by=actor.id`; `PATCH` estampa `updated_by` y conserva `created_by` original. (R4)
- [x] T25 GREEN — Enhebrar `actor_id` router→service→repository en create/update de tasks, projects, sprints, comments, attachments, roles, menus, dependencies, alert_rules, users (10 módulos; `organizations` excluido — solo seed, sin service). (R4, G5)
- [x] T26 RED — Extender `backend/tests/test_sprint_close.py`: `close_sprint` (UPDATE masivo) estampa `updated_by=actor_id` en cada tarea movida. (G2)
- [x] T27 GREEN — Enhebrar `actor_id` en `sprints/repository.py::close_sprint` — `.values(sprint_id=..., updated_by=actor_id)`. (G2)
- [x] T28 RED — `backend/tests/test_audit_exposure.py`: detalle y lista de los 11 modelos exponen `created_by`/`updated_by`; `null` en filas preexistentes/seed. (R5, G5)
- [x] T29 GREEN — Añadir `created_by`/`updated_by` opcionales a los `Read` schemas de los 11 módulos. (R5)
- [x] T30 — Crear migración Alembic `backend/alembic/versions/xxxx_add_audit_fields.py`: columnas nullable aditivas en las 11 tablas, `down_revision`=head de 01, `downgrade` reversible sin pérdida de datos. (R4)
- [x] T31 — Verificar que `test_migrations_baseline.py` (`alembic check`, de 01) cubre la nueva revisión; declarar explícitamente que no hay test local contra el artefacto de migración más allá de esa guardia. (G6)

## Batch D — Documentación

- [x] T32 — Regenerar `docs/API.md` desde la superficie real de los 13 routers: documentar `page/size/sort/order` en los 11 endpoints paginables y el shape real de `meta` (con y sin params); eliminar cualquier `meta.page` documentado que no exista en código.

## Cierre

- [ ] T33 — Suite completa + lint: `cd backend && pytest tests/ -v`, `ruff check .`, `mypy .` — todo en verde antes de handoff a `sdd-verify`.
