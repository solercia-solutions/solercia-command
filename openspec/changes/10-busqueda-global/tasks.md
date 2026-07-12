# Tasks: 10 · Búsqueda global + filtros avanzados

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~480–600 (search ~290 prod + suite propia; filtros tasks ~100 prod + suite propia; migración ~70; modelos/conftest ~20) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | No (sin PR de GitHub; ver nota) |
| Split sugerido | Lote A (migración 0008 + pg_trgm + índices GIN) → Lote B (módulo `search/` completo) → Lote C (filtros avanzados de tareas) |
| Estrategia de entrega | commits directos a `main` por lotes, sin PR, convencionales en español, sin atribución de IA |
| Estrategia de encadenado | size-exception — aceptada por el usuario, entrega por lotes |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Nota: `Chained PRs recommended: No` refiere a la ausencia de cadena de Pull Requests en GitHub (no aplica en este flujo de commits directos). El volumen SÍ se fragmenta en 3 lotes secuenciales (A→C), cada uno dejando la suite completa en verde con `ruff`/`mypy` limpios — `size:exception` cubre el exceso de líneas por lote, no la ausencia de fragmentación.

**Serialización obligatoria**: este `sdd-apply` corre DESPUÉS de `11-blindaje-baseline`. La migración 0008 es la siguiente en la cadena Alembic al momento de aplicar (hoy `down_revision="0007"`; verificar el head real antes de crear el archivo — 11 no agrega migraciones nuevas). No tocar `backend/` hasta que ese apply concurrente termine.

**Dependencia dura**: Lote B (`search/`) requiere Lote A aplicado — sus tests de integración usan `similarity()`, que solo existe tras `CREATE EXTENSION pg_trgm` (fixture `engine` de `conftest.py`, Decisión 2 del design). Lote C es independiente de A y B (extiende `TaskRepository.list_for_project` sin `pg_trgm`); puede aplicarse en cualquier orden relativo a ellos.

**Convención de rojo**: cada tarea RED corre primero con la prueba fallando de verdad (módulo/kwarg/migración aún inexistente → error de colección o `AssertionError`); se confirma el fallo antes de escribir el código de producción.

### Suggested Work Units

| Unit | Objetivo | Commit | Test enfocado | Arnés de ejecución | Frontera de rollback |
|------|----------|--------|----------------|---------------------|------------------------|
| A | Migración 0008 (`pg_trgm` + 5 índices GIN) + modelos + `conftest.py` | 1 — `feat(search): ...` | `pytest backend/tests/test_migrations_baseline.py -v` | BD desechable `solercia_test_migrations` vía `alembic upgrade/downgrade` (patrón existente) | revertir el commit elimina `0008_*.py`, los `__table_args__` de los 3 modelos y la línea `CREATE EXTENSION` de `conftest.py`; `alembic downgrade` deja el schema como `0007` |
| B | Módulo `search/` completo (`router→service→repository→schemas`) + registro en `app/main.py` | 2 — `feat(search): ...` | `pytest backend/tests/test_search.py -v` | ASGI in-process (`client`/`session`, fixtures 01 + `two_orgs` de 11) | revertir el commit elimina `app/modules/search/` y su registro en `main.py`; no toca `tasks`/`projects`/`comments` |
| C | Filtros avanzados en `GET /projects/{id}/tasks` | 3 — `feat(tasks): ...` | `pytest backend/tests/test_task_filters.py -v` | ASGI in-process | revertir el commit deja `list_for_project`/`schemas`/`router` de `tasks` en su firma previa (`label_id` único, sin `priority/due_from/due_to/q`) |

## Lote A — Migración 0008 + `pg_trgm` + índices GIN (Commit 1)

- [x] T01 RED `backend/tests/test_migrations_baseline.py`: agregar `test_migration_0008_upgrade_creates_gin_indexes` (consulta `pg_indexes`/`pg_am` — los 5 índices existen con `amname='gin'` sobre `tasks.title`, `tasks.description`, `projects.name`, `projects.description`, `task_comments.body`) y `test_migration_0008_downgrade_removes_indexes_and_extension` (tras `alembic downgrade -1` no quedan los 5 índices ni la extensión `pg_trgm`). Ambos fallan en rojo (migración 0008 aún no existe).
- [x] T02 [Foundation] `backend/tests/conftest.py::engine`: ejecutar `CREATE EXTENSION IF NOT EXISTS pg_trgm` antes de `Base.metadata.create_all` (Decisión 2 del design — sin esto, `create_all` falla al crear un índice `gin_trgm_ops` y `similarity()` no existe en `solercia_test`).
- [x] T03 GREEN `backend/app/modules/tasks/models.py` · `projects/models.py` · `comments/models.py`: agregar `__table_args__` con `Index(..., postgresql_using="gin", postgresql_ops={col: "gin_trgm_ops"})` en `tasks.title`, `tasks.description`, `projects.name`, `projects.description`, `task_comments.body`.
- [x] T04 GREEN `backend/alembic/versions/0008_add_search_trgm_indexes.py`: `down_revision` = head real al aplicar (hoy `0007`); `upgrade()` crea la extensión (`op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")`) + los 5 índices GIN; `downgrade()` los revierte en orden inverso (índices → `DROP EXTENSION IF EXISTS`).
- [x] T05 VERIFY `pytest backend/tests/test_migrations_baseline.py -v` en verde (incl. `test_alembic_check_reports_no_diff_after_upgrade` sin diff); `pytest backend/tests/ -v` completo sin regresiones por el cambio de `conftest.py`; `ruff check .`, `mypy app`. Commit `feat(search): migración 0008 pg_trgm + índices GIN`.

## Lote B — Módulo `search/` completo (Commit 2)

- [x] T06 RED `backend/tests/test_search.py` (unit, sin BD): escape de comodines LIKE (`%`, `_`, `\`) en `q` antes de envolver en `ILIKE`; parseo de `types` (csv → set, default los tres, vacío inválido). Rojo (módulo `search` no existe).
- [x] T07 GREEN `backend/app/modules/search/schemas.py`: `SearchResult` (`entity_type`, `id`, `title`, `snippet`, `project_id`, `project_name`, `task_key`, `task_id`) + util de escape LIKE y parseo de `types`.
- [x] T08 RED `backend/tests/test_search.py` (integración): happy por cada entidad (task/project/comment, con `snippet` y `task_id` solo en `comment`); `types=` filtra ramas; orden por `similarity()` DESC con tiebreak determinista; `meta` incondicional `{page,size,total}` incluso sin `page`/`size` en la query. Rojo (repository/service/router aún no existen).
- [x] T09 GREEN `backend/app/modules/search/repository.py`: `search()` — `UNION ALL` de las 3 ramas habilitadas, `ILIKE` con bind param + `similarity()` para orden, tiebreak `rank DESC, entity_type ASC, created_at DESC, id ASC`, `count()` + `limit/offset`.
- [x] T10 GREEN `backend/app/modules/search/service.py`: valida `q` (trim, longitud < 2 → 422), valida `types` (fuera de catálogo → 422), arma `PaginationParams` SIEMPRE (page=1/size=20 default, tope 100 — excepción explícita al opt-in de 02, exclusiva de este endpoint).
- [x] T11 GREEN `backend/app/modules/search/router.py`: `GET /search` con envelope `{data,message,meta}`; registrar `search.router` en `app/main.py`.
- [x] T12 VERIFY parcial `pytest backend/tests/test_search.py -k "not aislamiento and not soft_delete" -v` en verde (happy + validaciones + orden + meta).
- [x] T13 RED `backend/tests/test_search.py`: aislamiento de tenant por CADA tipo de entidad (task/project/comment) con fixture `two_orgs` (de 11-blindaje-baseline); borrado suave excluido en las 3 ramas (tarea, proyecto, comentario); cualquier rol (`member` incl.) puede buscar sin restricción adicional.
- [x] T14 GREEN Confirmar/ajustar scope por rama en `search/repository.py`: `tasks` vía join a `Project.organization_id` (Task no lleva `organization_id`); `projects`/`comments` por `organization_id` directo (`TenantMixin`); excluir `is_active=false` en las 3 ramas (+ Task/Project activos para el contexto de `comment`).
- [x] T15 VERIFY `pytest backend/tests/test_search.py -v` completo en verde; `pytest backend/tests/ -v` sin regresiones; `ruff check .`, `mypy app`. Commit `feat(search): endpoint GET /search multi-entidad`.

## Lote C — Filtros avanzados de tareas (Commit 3)

- [ ] T16 RED `backend/tests/test_task_filters.py`: combinación simultánea `status+priority+assignee_id+label_id+due_from+due_to`; `label_id` repetible con semántica OR (unión sin duplicados); `q` sobre `title`/`description`; rango `due_from`/`due_to`; 422 por `priority` fuera de catálogo; 422 por `due_from>due_to`; `meta{page,size,total}` con paginación estándar de 02. Rojo (los kwargs aún no existen en el repository).
- [ ] T17 GREEN `backend/app/modules/tasks/repository.py::list_for_project`: kwargs opcionales `priority`, `label_ids: Sequence[UUID]` (OR vía `TaskLabel.label_id.in_(...)` + `.distinct()`), `due_from`, `due_to`, `q` (`ILIKE` sobre `title`/`description`); patrón incremental `if x is not None: stmt = stmt.where(...)` ya presente.
- [ ] T18 GREEN `backend/app/modules/tasks/schemas.py` (o módulo de query params): `priority: Priority | None`, `label_id: list[UUID] | None` (repetible, retrocompatible con un solo valor), `due_from`/`due_to: date | None`, `q: str | None`.
- [ ] T19 GREEN `backend/app/modules/tasks/service.py`: valida `due_from<=due_to` (cross-field) → `AppException` 422 antes de delegar al repository; `priority` como enum ya da 422 automático vía Pydantic.
- [ ] T20 GREEN `backend/app/modules/tasks/router.py`: exponer los nuevos query params en `GET /projects/{id}/tasks` (`label_id` pasa a `Query(default=None)` repetible), manteniendo la paginación estándar existente.
- [ ] T21 VERIFY `pytest backend/tests/test_task_filters.py -v` en verde; `pytest backend/tests/ -v` completo sin regresiones (`test_tasks_pagination.py`, `test_boards*.py`, `test_labels.py`); `ruff check .`, `mypy app`. Commit `feat(tasks): filtros avanzados combinables + paginación estándar`.

## Trazabilidad de requisitos

`global-search`: R1 Contrato del endpoint (T07,T08,T09,T11,T12) · R2 Longitud mínima de `q` (T10,T12) · R3 Validación de `types` (T10,T12) · R4 Scope estricto por organización (T13,T14,T15) · R5 Exclusión de borrado suave (T13,T14,T15) · R6 Permisos sin restricción de rol (T13,T15). `tasks` (delta): R7 Filtros combinables + `label_id` multi + `q` + rango de fechas (T16,T17,T18,T20,T21) · R8 Validación 422 de filtros inválidos (T16,T19,T21). Infraestructura compartida (`pg_trgm`+GIN, sin requisito propio pero condición de R1/R4): T01–T05.
