# Tasks: 21 · Jerarquía de proyectos

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1.100–1.300 (producción ~460: config 2, modelo 10, migración 0014 ~50, schemas ~40, repository CTE ~150, service ~140, router ~70; docs ER ~30; **pruebas TDD ~750**: migración ~70, repository ~150, validación ~120, endpoints ~350, `test_projects.py` ~60) |
| Divergencia con design.md | El forecast de `design.md` (~330 líneas) solo contaba código de producción. Este forecast de `sdd-tasks` suma las pruebas TDD estrictas (28 escenarios de spec + pruebas unitarias de ciclos/profundidad/CTE + prueba de migración), que dominan el diff total. |
| 400-line budget risk | **High** (incluso repartido en 3 lotes: Lote A ≈430, Lote B ≈780 superan individualmente el presupuesto de 400 líneas por la densidad de escenarios TDD) |
| Chained PRs recommended | Yes (adaptado: sin PRs nuevos — commits secuenciales sobre `feat/consume-solercia-ui`) |
| Estrategia de entrega | Commits convencionales directos a la rama actual, un commit por lote; `size:exception` ya aceptada por el orquestador (`delivery_strategy: exception-ok`) |
| Estrategia de encadenado | stacked-to-main (adaptada a commits directos, sin abrir PRs) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota**: `exception-ok` ya cubre el excedente sobre 400 líneas a nivel de la entrega completa; el reparto en 3 lotes (A/B/C) es igualmente obligatorio por `work-unit-commits` para mantener cada commit revisable y con rollback independiente, aunque el Lote B por sí solo también exceda 400 líneas (endpoints + su batería de pruebas de integración). Si el apply quiere una granularidad más fina, el Lote B puede subdividirse en B1 (schemas + service, sin endpoints) y B2 (router + pruebas de integración) sin cambiar el orden de dependencias.

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| A | Migración 0014 + `parent_project_id` en el modelo + CTE de jerarquía en el repositorio (`ancestor_ids`, `subtree_height`, `fetch_subtree`, `rollup_progress`) | 1 — `feat(projects): migracion 0014, self-FK parent_project_id y CTE de jerarquia` | `cd backend && pytest tests/test_project_hierarchy_migration.py tests/test_project_hierarchy_repository.py -v` | `alembic upgrade head` / `alembic downgrade -1` contra BD desechable (patrón `test_boards_backfill_migration.py`) | Revert commit + `alembic downgrade -1` (elimina columna e índice, ningún proyecto pierde datos) |
| B | Validación de jerarquía + reparentado en el service + endpoints `PATCH .../parent`, `GET .../tree`, `GET .../progress` + `parent_project_id` en create/list/detail | 2 — `feat(projects): validacion de jerarquia, reparentado y endpoints de arbol/avance` | `cd backend && pytest tests/test_project_hierarchy_validation.py tests/test_project_hierarchy_endpoints.py tests/test_projects.py -v` | `httpx.AsyncClient` contra el router montado (patrón `test_notification_deliveries_endpoint.py`) sembrando un árbol de 3 niveles | Revert commit (sin migración propia); rutas/campos nuevos sin dependientes fuera de `projects/` |
| C | Actualizar `docs/diagrams/er-model.md` (ER vivo) + pulido de docstrings + verificación final de suite completa | 3 — `docs(projects): actualiza ER model con jerarquia de proyectos` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` | `alembic upgrade head` contra `solercia_test` + `GET /projects/{id}/tree` y `GET /projects/{id}/progress` reales sobre el árbol sembrado (reproduce 18/20) | Revert commit; solo toca documentación y docstrings, sin código ejecutable |

## Fase 1 — Migración, modelo y repositorio CTE (Lote A / Commit 1)

- [x] 1.1 [Pre-requisito] Verificar el head real de Alembic: `cd backend && alembic heads`. Este cambio está SERIALIZADO con los apply de 14 y 20 — si el head vigente ya NO es `0013` (otro cambio tomó ese slot), fijar `down_revision` de 1.4 al head real antes de crear el archivo. **Confirmado: head vigente = `0013`, sin cambios.**
- [x] 1.2 [Foundation] `app/config.py`: agregar `PROJECT_HIERARCHY_MAX_DEPTH: int = 5`. [R3]
- [x] 1.3 [Foundation] `app/modules/projects/models.py`: agregar `parent_project_id: Mapped[uuid.UUID | None]`, self-FK `ForeignKey("projects.id", ondelete="SET NULL")`, `index=True` (genera `ix_projects_parent_project_id`, patrón `code`/`Task.parent_task_id`). [R1]
- [x] 1.4 [Foundation] `backend/alembic/versions/0014_add_project_parent_id.py`: `down_revision` = head confirmado en 1.1; `upgrade()` = `op.add_column` (FK nullable `SET NULL`) + `op.create_index("ix_projects_parent_project_id", ...)`; `downgrade()` = `drop_index` → `drop_column` (round trip completo, patrón docstring de `0008`). [R1]
- [x] 1.5 RED `backend/tests/test_project_hierarchy_migration.py` (patrón `test_boards_backfill_migration.py`, BD desechable + raw SQL): upgrade al head anterior, INSERT raw de un proyecto sin `parent_project_id`; upgrade a `0014` → columna e índice existen (`information_schema.columns` / `pg_indexes`), la fila sobrevive; `downgrade()` → columna e índice desaparecen, cero filas perdidas. [R1]
- [x] 1.6 VERIFY confirmar T1.5 en ROJO (columna inexistente) antes de aplicar 1.3/1.4; luego `cd backend && alembic upgrade head && pytest tests/test_project_hierarchy_migration.py -v` en verde; `alembic check` sin diff (paridad modelo/migración vía `index=True`). **Nota de ejecución**: RED confirmado por `alembic.util.exc.CommandError: Can't locate revision identified by '0014'` (el test referencia la revisión antes de crearla); el "upgrade head" real se verificó contra una BD desechable (patrón `test_migrations_baseline.py`, NO contra `solercia_test`, que se construye via `create_all` sin tracking de `alembic_version` — ver Issues Found del reporte de apply) — `alembic check` sin diff confirmado ahí.
- [x] 1.7 [Foundation] `app/modules/projects/repository.py`: `ancestor_ids(organization_id, project_id) -> list[uuid.UUID]` — caminata de ancestros por `parent_project_id`, acotada por `PROJECT_HIERARCHY_MAX_DEPTH` (corta barato en ciclo). [R1,R2,R3]
- [x] 1.8 [Foundation] `app/modules/projects/repository.py`: `subtree_height(organization_id, project_id) -> int` — CTE recursivo pequeño (altura del subárbol; 0 en create sin hijos). [R3]
- [x] 1.9 [Foundation] `app/modules/projects/repository.py`: `fetch_subtree(organization_id, project_id) -> Sequence[Project]` — CTE recursivo (base: nodo solicitado; recursivo: `parent_project_id = anterior.id`), filtra `organization_id` + `is_active` en cada nivel. [R5]
- [x] 1.10 [Foundation] `app/modules/projects/repository.py`: `rollup_progress(organization_id, project_id) -> Sequence[...]` — CTE `subtree` (igual a 1.9) + CTE `last_status` (`DISTINCT ON (b.project_id) bc.status_key` sobre `boards`/`board_columns`, `ORDER BY b.project_id, bc.column_order DESC, bc.created_at DESC`) + join a `tasks` (`status <> 'cancelled'`), agregando `done`/`total` por proyecto del subárbol. [R6]
- [x] 1.11 RED `backend/tests/test_project_hierarchy_repository.py` (unit sin BD para ancestros/altura; integración con BD para CTE): ciclo detectado vía `ancestor_ids` (auto-padre y transitivo); `subtree_height` en árbol de 3 niveles; `fetch_subtree` respeta `organization_id`+`is_active`; `rollup_progress` reproduce 18/20 (metodologías mixtas planner+scrum) y excluye `cancelled` del denominador. [R1,R2,R3,R5,R6] **Nota de terminología**: como en el resto del repo no existe un patrón de mocking sin BD, los 10 tests usan la fixture `session` (SAVEPOINT sobre Postgres real, `@skip_no_db`) igual que el resto de la suite — "unit sin BD" se interpreta como "sin capa HTTP", no como ausencia literal de conexión.
- [x] 1.12 VERIFY confirmar T1.11 en ROJO antes de GREEN de T1.7–T1.10; `cd backend && pytest tests/test_project_hierarchy_repository.py tests/test_project_hierarchy_migration.py -v` en verde; `ruff check .` / `mypy app` limpios. **RED confirmado**: 10/10 fallaron con `AttributeError: 'ProjectRepository' object has no attribute '...'` antes de implementar 1.7-1.10. GREEN: 12/12 (repository + migration) en verde; `ruff check` y `mypy app/modules/projects/` limpios.

## Fase 2 — Service, validaciones y endpoints (Lote B / Commit 2)

- [ ] 2.1 [Foundation] `app/modules/projects/schemas.py`: `ProjectCreate.parent_project_id: uuid.UUID | None = None`; `ProjectRead.parent_project_id: uuid.UUID | None = None`. [R10,R11]
- [ ] 2.2 [Foundation] `app/modules/projects/schemas.py`: `ProjectTreeNode` (id/name/code/methodology/status/`children` anidados), `ReparentRequest` (`parent_project_id: uuid.UUID | None`, `null` desvincula), `ProjectProgressNode` (`self`/`rollup`: `{done,total,percent_done}` + `children`). [R5,R6,R9]
- [ ] 2.3 RED `backend/tests/test_project_hierarchy_validation.py`: `ProjectService.validate_parent` — auto-padre rechazado (`self_parent`, 422); padre de otra organización rechazado (`parent_not_found`, 404); padre inactivo rechazado (`parent_not_found`, 404); ciclo directo y transitivo rechazados (`project_cycle`, 409); profundidad 5 aceptada, profundidad 6 rechazada (`max_depth_exceeded`, 422). [R1,R2,R3,R9]
- [ ] 2.4 VERIFY confirmar T2.3 en ROJO (método inexistente) antes de GREEN.
- [ ] 2.5 GREEN `app/modules/projects/service.py`: `validate_parent(organization_id, parent_id, child_id=None)` — orquesta `self_parent` → padre existe/activo/mismo tenant (`parent_not_found`) → `ancestor_ids` (ciclo → `project_cycle`) → `subtree_height(child_id)` + profundidad del padre (solo en reparent) → `max_depth_exceeded`; cada rechazo usa `AppException` con `code` propio (inline, sin factory nueva — patrón ya usado en el módulo). [R1,R2,R3,R9]
- [ ] 2.6 GREEN `app/modules/projects/service.py`: `create_project` invoca `validate_parent` cuando `data.parent_project_id` viene, ANTES de `self.repo.db.add(project)` (todo-o-nada: si falla, ningún proyecto queda persistido). [R10]
- [ ] 2.7 GREEN `app/modules/projects/service.py`: `reparent(organization_id, project_id, parent_project_id) -> Project` — valida con `child_id=project_id`, aplica `project.parent_project_id = parent_project_id`, `repo.save`. [R4]
- [ ] 2.8 GREEN `app/modules/projects/service.py`: `get_tree(organization_id, project_id) -> ProjectTreeNode` — arma el árbol anidado desde `repo.fetch_subtree`; `project_not_found` (404) si la raíz no existe/no pertenece a la organización. [R5]
- [ ] 2.9 GREEN `app/modules/projects/service.py`: `get_progress(organization_id, project_id) -> ProjectProgressNode` — arma `self`/`rollup` por nodo desde `repo.rollup_progress`, sumando `done`/`total` de todo el subárbol en el nodo raíz solicitado; `project_not_found` (404) si no existe/no pertenece a la organización. [R6]
- [ ] 2.10 GREEN `app/modules/projects/router.py`: `PATCH /{project_id}/parent`, `Depends(require_role(MemberRole.admin, MemberRole.manager))`, envelope `{data, message}`. [R4,R7,R9]
- [ ] 2.11 GREEN `app/modules/projects/router.py`: `GET /{project_id}/tree` y `GET /{project_id}/progress`, `Depends(get_current_membership)` (cualquier rol), envelope `{data}`. [R5,R6,R7,R9]
- [ ] 2.12 RED `backend/tests/test_project_hierarchy_endpoints.py` (httpx `AsyncClient` + fixtures `tenant`/`user`/`two_orgs`/`make_member`, patrón `test_notification_deliveries_endpoint.py`): árbol de 3 niveles reproduce la jerarquía; tenant B → 404 en `tree`/`progress`; roll-up 18/20 (planner+scrum mixtos); `cancelled` fuera del denominador; roll-up de proyecto recién creado == `percent_done` del dashboard; reparent válido, a `null` (desvincula), ciclo rechazado (jerarquía intacta); `member` → 403 en `PATCH`, `manager` → 200; `POST /projects` con `parent_project_id` válido / inválido (todo-o-nada) / omitido; `GET /projects` y `GET /projects/{id}` exponen `parent_project_id`. [R1,R2,R3,R4,R5,R6,R7,R9,R10,R11]
- [ ] 2.13 VERIFY confirmar T2.12 en ROJO (rutas/campos inexistentes) antes de este commit; `cd backend && pytest tests/test_project_hierarchy_validation.py tests/test_project_hierarchy_endpoints.py tests/test_projects.py -v` en verde; `ruff check .` / `mypy app` limpios.

## Fase 3 — Docs ER y verificación final (Lote C / Commit 3)

- [x] 3.1 [Docs] `docs/diagrams/er-model.md`: agregar `parent_project_id` a la tabla `projects` (columna + FK auto-referenciada `SET NULL`), agregar la arista `projects --> projects` (self-relación) en el diagrama mermaid del dominio CORE, actualizar "Fecha de línea base" y la migración más reciente citada a `0014`. Debe ir en el mismo commit que toca el modelo si el apply prefiere fusionarlo con el Lote A; aquí queda en Lote C por la nota obligatoria del proposal de mantenerlo como cierre documental verificable. **Completado anticipadamente en el commit del Lote A por instrucción explícita del orquestador** (el ER model debía ir en el mismo commit que la migración 0014, no en el commit C). [Nota obligatoria del proposal]
- [ ] 3.2 [Polish] Revisar docstrings Swagger de los 3 endpoints nuevos (`router.py`): documentar el contrato de errores (`parent_not_found`/`project_cycle`/`max_depth_exceeded`/`self_parent`) igual que el resto del módulo.
- [ ] 3.3 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa en verde, sin regresión; `ruff check .` / `mypy app` limpios; `alembic check` sin diff.
- [ ] 3.4 VERIFY runtime harness: `alembic upgrade head` contra `solercia_test` + llamadas reales `GET /projects/{id}/tree` y `GET /projects/{id}/progress` sobre un árbol de 3 niveles sembrado a mano, confirmando el ejemplo de negocio 18/20.

## Trazabilidad de requisitos

R1 Relación padre-hijo y restricciones estructurales · 1.3,1.7,1.11,2.3,2.5,2.6,2.12
R2 Prevención de ciclos · 1.7,1.11,2.3,2.5,2.12
R3 Profundidad máxima configurable · 1.2,1.8,1.11,2.3,2.5,2.12
R4 Reparentado de un proyecto existente · 2.7,2.10,2.12
R5 Árbol jerárquico · 1.9,2.2,2.8,2.11,2.12
R6 Avance consolidado por conteo (roll-up) · 1.10,2.2,2.9,2.11,2.12
R7 Permisos sobre la jerarquía · 2.10,2.11,2.12
R8 Invariante de borrado suave de un padre con hijos activos · **sin tarea de implementación en este cambio** — no existe endpoint de soft-delete de `Project` en la API hoy (`test_projects.py`: "NO hay PATCH ni DELETE de proyectos vía API"); el requisito queda trazado en `specs/project-hierarchy/spec.md` como invariante forward-looking para cuando ese mecanismo exista, tal como fija el propio spec.
R9 Contrato de envelope y errores · 2.2,2.3,2.5,2.10,2.11,2.12
R10 Creación de proyecto con padre opcional · 2.1,2.6,2.12
R11 Exposición de `parent_project_id` en las respuestas · 2.1,2.12
