# Design: 21 · Jerarquía de proyectos

## Technical Approach

Se añade una self-FK `parent_project_id` (nullable, `ondelete=SET NULL`, indexada) a `Project`, mismo patrón aditivo que `code` (ADR 0003) y que `Task.parent_task_id`. La lógica de jerarquía vive en `projects/` (repository → service → router), sin tocar `dashboard/`. El **árbol** y el **roll-up** se resuelven con un **CTE recursivo de PostgreSQL** que acota el subárbol filtrando `organization_id` + `is_active` en cada nivel. La validación de ciclos/profundidad se hace en el service caminando ancestros (acotado por la profundidad máxima). Migración Alembic **0014** (encadena a `0013`, head vigente). TDD estricto. El "done" del roll-up se **reconcilia** con `DashboardService._build_projects_progress` (ver Decisión 1).

## Architecture Decisions

### Decisión 1: reconciliar "done" con el dashboard — CTE puro SQL vs precálculo por proyecto

Evidencia: el dashboard deriva "done" así — `_StatusBounds.is_done` (`dashboard/service.py:43`) compara `status == last`, donde `last = strategy.allowed_statuses()[-1]` (`_bounds_for`, `service.py:449`) y `strategy = resolve_board_strategy(project, db)` (`board_aware.py:66`). `allowed_statuses()` devuelve los `status_key` persistidos de las columnas del board (`board_aware.py:39-51`), ordenadas `column_order ASC, created_at ASC` (`boards/repository.py:88,124`). Es decir, **"done" por proyecto = el `status_key` de la última columna del board de ese proyecto**.

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **A. CTE puro SQL**: subárbol recursivo + CTE `last_status` = `DISTINCT ON (b.project_id) bc.status_key ORDER BY b.project_id, bc.column_order DESC, bc.created_at DESC`; join a `tasks` y conteo en una consulta | Roll-up en la BD, una sola consulta (meta del proposal), escala con índice. `create_project` siembra board a todo proyecto (`service.py:131`), luego "última columna" == `allowed_statuses()[-1]` en estado estable | **Elegida** |
| B. Precálculo Python: CTE devuelve ids del subárbol → `resolve_board_strategy` por proyecto (reusa dashboard literal) → agrega en Python | Semántica byte-idéntica incl. fallback a strategy base, pero N resoluciones (N+1) y pierde la consulta única | Rechazada |

Divergencia documentada (única): para un board legado **sin columnas**, el dashboard cae a la strategy base; el CTE no vería columna y no contaría "done". No ocurre en estado estable (todo proyecto nace sembrado). Test: el roll-up de un proyecto recién creado debe igualar su `percent_done` del dashboard.

### Decisión 2: denominador del roll-up — conteo, `cancelled` y subtareas

Roll-up = **conteo** de tareas (no puntos/horas), consistente con `_build_projects_progress` (`service.py:275`, `done = sum(1 ...)`). **`cancelled` fuera del denominador** (`WHERE status <> 'cancelled'`): refinamiento deliberado del roll-up; planner/kanban/scrum nunca emiten ese estado, así que para ellos el total coincide con el dashboard (que no filtra cancelled). **Subtareas se cuentan igual** que en el dashboard (itera toda tarea del proyecto, sin excluir `parent_task_id`). Filtros por nivel: `Task.is_active`, tenant heredado del subárbol de proyectos.

### Decisión 3: validación de ciclos/profundidad — caminar ancestros vs CTE

Al fijar `parent = P` sobre el hijo `C`: (1) rechazar auto-padre (`C == P`); (2) `P` debe existir, misma org, activo; (3) **subir por ancestros de `P`** siguiendo `parent_project_id` — si `C` aparece en `{P} ∪ ancestros(P)`, `P` está dentro del subárbol de `C` → ciclo → rechazo; (4) profundidad: `nueva_profundidad(C) = profundidad(P) + 1 + altura_subárbol(C)` no debe exceder `MAX_DEPTH`. La caminata de ancestros está acotada por `MAX_DEPTH` (barato, corta en ciclo). Se descarta CTE para validar (innecesario dado el límite). `altura_subárbol(C)` (solo reparent) se obtiene con un CTE recursivo pequeño; en create es 0. Límite `PROJECT_HIERARCHY_MAX_DEPTH = 5` en `config.py`, profundidad = nivel de anidación (raíz = 1).

## Data Flow

    POST /projects (con parent_project_id?)  ─┐
    PATCH /projects/{id}/parent  ────────────►│ ProjectService.validate_parent()
                                              │   ancestros(P) + altura(C) → ciclo/prof/tenant
                                              └─► repo.save
    GET /projects/{id}/tree      ──► repo.subtree_cte(org,is_active) ──► árbol anidado
    GET /projects/{id}/progress  ──► repo.rollup_cte + last_status ──► {self, rollup} por nodo

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/config.py` | Modify | `PROJECT_HIERARCHY_MAX_DEPTH: int = 5` |
| `app/modules/projects/models.py` | Modify | `parent_project_id` self-FK nullable `SET NULL`, `index=True` (`ix_projects_parent_project_id`) |
| `app/modules/projects/schemas.py` | Modify | `ProjectCreate.parent_project_id?`; nuevos `ProjectTreeNode`, `ReparentRequest`, `ProjectProgressNode` |
| `app/modules/projects/repository.py` | Modify | CTE: `fetch_subtree`, `rollup_progress`, `ancestor_ids`, `subtree_height` |
| `app/modules/projects/service.py` | Modify | `validate_parent` en `create_project` + `reparent`; armado de árbol/progreso |
| `app/modules/projects/router.py` | Modify | `GET /{id}/tree`, `GET /{id}/progress`, `PATCH /{id}/parent` |
| `alembic/versions/0014_add_project_parent_id.py` | Create | `down_revision="0013"`; ALTER add column + índice; downgrade completo |
| `docs/diagrams/er-model.md` (o `docs/DATA-MODEL.md`) | Modify (apply) | Actualizar ER: relación padre-hijo en `projects` |

## Interfaces / Contracts

```python
# schemas.py
class ProjectTreeNode(BaseModel):        # árbol anidado
    id: uuid.UUID; name: str; code: str | None
    methodology: Methodology; status: ProjectStatus
    children: list["ProjectTreeNode"]

class ReparentRequest(BaseModel):        # PATCH /{id}/parent
    parent_project_id: uuid.UUID | None  # null = desanclar (vuelve a raíz)

class ProjectProgressNode(BaseModel):    # GET /{id}/progress
    project_id: uuid.UUID; name: str
    self: dict          # {done, total, percent_done} — solo tareas propias
    rollup: dict        # {done, total, percent_done} — subárbol completo (18/20)
    children: list["ProjectProgressNode"]
```

Rutas: `PATCH /{id}/parent` requiere `require_role(MemberRole.admin, MemberRole.manager)` (mutación estructural, `dependencies.py:149`); `POST /projects` conserva su permiso actual (cualquier miembro) y valida `parent_project_id` si viene; `GET /{id}/tree` y `GET /{id}/progress` los lee cualquier miembro. Errores: `parent_not_found` (404, cross-tenant o inexistente), `project_cycle` (409), `max_depth_exceeded` (422), `self_parent` (422). Envelope `{data, meta}` de 02.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | ciclo (caminata ancestros), cálculo de profundidad, `self_parent` | pytest sin BD |
| Integration | árbol 3+ niveles anidado; reparent que cierra ciclo → 409; profundidad > 5 → 422; padre de otra org → 404 + tree/progress nunca cruzan org; roll-up 18/20 (metodologías mixtas planner+scrum, cada "done" según su última columna); roll-up con `cancelled` fuera del denominador; roll-up de proyecto recién creado == `percent_done` del dashboard | httpx AsyncClient + fixtures 01/02 |
| Migration | `alembic upgrade head` añade columna+índice; `downgrade` los revierte; `alembic check` sin diff (paridad modelo/migración, patrón 0008) | BD `solercia_test_migrations` |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocess, automatización VCS/PR, clasificación de ejecutables ni integración de procesos.

## Migration / Rollout

Aditiva `0014` (`down_revision="0013"`). `upgrade()`: `op.add_column("projects", sa.Column("parent_project_id", Uuid, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True))` + `op.create_index("ix_projects_parent_project_id", "projects", ["parent_project_id"])`. `downgrade()`: `drop_index` → `drop_column` (round trip completo). El modelo declara el mismo índice vía `index=True` para que `create_all` (conftest) y la migración produzcan schema idéntico. Rollback: revertir merge y ejecutar `downgrade`; los proyectos quedan planos (`parent_project_id=NULL`), ninguna tarea se altera.

## Open Questions

- [x] "done" dependiente de metodología en el CTE: RESUELTO — última columna por proyecto (Decisión 1).
- [x] `cancelled`/subtareas/ponderación: RESUELTO — conteo, cancelled fuera, subtareas incluidas (Decisión 2).
- [ ] Ruta del doc ER (`docs/diagrams/er-model.md` vs `docs/DATA-MODEL.md`): el apply usa la primera si existe; si no, actualiza `docs/DATA-MODEL.md`.

## Forecast de tamaño (para sdd-tasks)

Estimado ~330 líneas (modelo/migración ~50, repository CTE ~110, service ~90, schemas/router ~80). **400-line budget risk: Low.** `Decision needed before apply: No`. `Chained PRs recommended: No`. Slice único autónomo y desplegable.
