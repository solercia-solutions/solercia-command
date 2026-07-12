# Design: 10 · Búsqueda global + filtros avanzados

## Technical Approach

Módulo nuevo `search/` (`router → service → repository`) que resuelve una búsqueda multi-entidad sobre **tasks**, **projects** y **comments** con `ILIKE '%q%'` acelerado por `pg_trgm` + GIN `gin_trgm_ops`, ordenada por relevancia con `similarity()`. El repository de búsqueda concentra TODO el SQL (el router jamás toca SQLAlchemy); scope de tenant obligatorio por rama. Los **filtros avanzados** NO viven en `search/`: extienden el constructor de query existente de `TaskRepository.list_for_project` (mismo patrón incremental `if x is not None: stmt = stmt.where(...)`) y adoptan la paginación de 02. Migración Alembic **0008** (encadena a `0007`) habilita la extensión + índices GIN. TDD estricto. Corrige un dato del proposal: la columna de texto del comentario es **`task_comments.body`**, no `content`.

## Architecture Decisions

### Decisión 1: módulo `search/` dedicado vs. métodos en módulos existentes

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Módulo `search/` (router+service+repository) que importa los 3 modelos | Es consumidor hoja (nadie importa `search`) → sin ciclos; cohesiona la consulta transversal | **Elegida** |
| Un método `search()` por módulo + orquestador | Dispersa la unión multi-entidad, duplica scope de tenant, ranking inconsistente | Rechazada |

Los filtros de tareas SÍ pertenecen a `tasks/` (no a `search`): son la lista de tareas, no una búsqueda transversal.

### Decisión 2: mecanismo de índices y paridad con `alembic check` (crítica)

El test existente `test_alembic_check_reports_no_diff_after_upgrade` exige **cero diff** entre el schema migrado y `Base.metadata`. Además el fixture `engine` de tests construye el schema con `Base.metadata.create_all`, **no** con migraciones.

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Declarar los índices GIN en `__table_args__` de los modelos **y** `CREATE EXTENSION` en la migración 0008 **y** en el fixture `engine` de `conftest.py` | Única fuente de verdad; `create_all` y `alembic upgrade` producen el mismo schema → `alembic check` verde; `similarity()` disponible en tests | **Elegida** |
| Crear índices sólo por `op.execute` en la migración + `include_object` en `env.py` para excluirlos | Determinista, pero rompe la disciplina de paridad modelo/migración que el proyecto ya valida y deja un punto ciego permanente | Rechazada (fallback si `alembic check` reporta falso positivo de opclass GIN) |

Consecuencia obligatoria: `conftest.py::engine` debe ejecutar `CREATE EXTENSION IF NOT EXISTS pg_trgm` **antes** de `create_all` (sin ella, `create_all` de un índice `gin_trgm_ops` falla y `similarity()` no existe en `solercia_test`).

### Decisión 3: orden por `similarity()` y lista plana (resuelve preguntas abiertas del proposal)

- **Orden**: `similarity()` DESC por entidad, con `WHERE` por `ILIKE '%q%'` (subcadena, acelerada por GIN). Para tasks: `GREATEST(similarity(title,q), similarity(description,q))`. Tiebreak determinista `rank DESC, entity_type ASC, created_at DESC, id ASC`. Se descarta ILIKE puro (sin relevancia → mala UX de caja de búsqueda). Es testeable porque la Decisión 2 garantiza `pg_trgm` en `solercia_test`.
- **Forma**: **lista plana** vía `UNION ALL` de las ramas habilitadas (cada rama: `entity_type, id, snippet, project_id, project_name, task_key, task_id, rank` — `task_id` es NULL salvo en la rama `comment`, donde la spec lo exige como contexto), un solo `total`, paginación offset estándar. Se descarta la respuesta agrupada `{tasks,projects,comments}` porque rompe el contrato de un único `{data, meta:{page,size,total}}` de 02; la agrupación es presentacional (frontend congelado la resuelve). `types=` filtra qué ramas participan.

### Decisión 4: scope multi-tenant por rama + exclusión de soft-deleted (riesgo HIGH)

| Entidad | Scope | Activo |
|---------|-------|--------|
| projects | `Project.organization_id == org` | `Project.is_active` |
| comments | `TaskComment.organization_id == org` (TenantMixin) | `TaskComment.is_active` + join Task/Project activos para contexto |
| tasks | join `Project`, `Project.organization_id == org` (Task NO lleva `organization_id`) | `Task.is_active` + `Project.is_active` |

Cada rama se filtra de forma independiente; test de aislamiento por CADA tipo de entidad.

### Decisión 5: composición de filtros avanzados + validación 422

Extender `TaskRepository.list_for_project` con kwargs opcionales `priority`, `label_ids: Sequence[UUID]` (multi), `due_from`, `due_to`, `q`; se componen con el patrón incremental ya presente. `label_id` pasa a repetible (`?label_id=a&label_id=b`, retrocompatible) con semántica **OR** (`TaskLabel.label_id.in_(...)` + `.distinct()`). `priority` tipado como enum `Priority` → 422 automático. `q` = ILIKE title/description (filtro, NO re-rankea la lista de tareas). Cross-field `due_from > due_to` → `AppException` 422 en el service. `sort` inválido ya da 422 vía `paginate`.

## Data Flow

    GET /api/v1/search?q=&types=&page=&size=
      → SearchService.search(org, q, types, pagination)
        → SearchRepository.search(): UNION ALL ramas scoped → count + ORDER BY rank → limit/offset
      → {data:[{entity_type,id,title,snippet,project_id,project_name,task_key,task_id}], message, meta}

    NOTA de paginación (corrección de gate): /search NO hereda el opt-in del pipeline de 02.
    La spec exige meta incondicional {page, size, total}. El endpoint SIEMPRE pagina:
    defaults page=1, size=20 (máx 100) aplicados en el router aunque el cliente no envíe
    parámetros; el meta se construye siempre con page/size/total (no se usa el flag
    `PaginationParams.requested` para omitirlos). El opt-in de 02 sigue intacto en los
    endpoints existentes — esta excepción es exclusiva del endpoint nuevo.

    GET /projects/{id}/tasks?status=&priority=&label_id=&assignee_id=&sprint_id=&due_from=&due_to=&q=&page=&size=
      → TaskService.list_tasks (valida due_from<=due_to) → TaskRepository.list_for_project (where incremental) → paginate

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/search/{router,service,repository,schemas}.py` | Create | Búsqueda multi-entidad; router sin SQL |
| `app/modules/tasks/repository.py` | Modify | Kwargs `priority/label_ids/due_from/due_to/q`; `.distinct()` |
| `app/modules/tasks/{router,service,schemas}.py` | Modify | Query params filtros; validación `due_from<=due_to` |
| `app/modules/tasks/models.py` · `projects/models.py` · `comments/models.py` | Modify | `__table_args__` con `Index(..., postgresql_using="gin", postgresql_ops={...})` |
| `app/main.py` | Modify | Registrar `search.router` |
| `alembic/versions/0008_add_search_trgm_indexes.py` | Create | `CREATE EXTENSION` + 5 índices GIN; downgrade inverso |
| `tests/conftest.py` | Modify | `CREATE EXTENSION IF NOT EXISTS pg_trgm` antes de `create_all` |

Índices GIN (`gin_trgm_ops`): `tasks.title`, `tasks.description`, `projects.name`, `projects.description`, `task_comments.body`. `projects.code` y `tasks.task_number` ya tienen btree (clave `SDM-7` = exact/prefix, sin trigram).

## Interfaces / Contracts

```python
# search/repository.py — el router jamás llama esto directo
async def search(self, organization_id: uuid.UUID, q: str,
                 types: set[str], pagination: PaginationParams
                 ) -> tuple[Sequence[SearchRow], int]: ...

# search/schemas.py
class SearchResult(BaseModel):
    entity_type: str          # "task" | "project" | "comment"
    id: uuid.UUID
    title: str                # task.title | project.name | task del comentario
    snippet: str              # primeros ~160 chars del campo textual coincidente
    project_id: uuid.UUID | None
    project_name: str | None
    task_key: str | None      # "SDM-7" para tasks
    task_id: uuid.UUID | None # solo en resultados "comment": la tarea del comentario (exigido por la spec)

# Seguridad: el patrón ILIKE se pasa SIEMPRE como parámetro ligado
# (Task.title.ilike(bindparam)); escapar %, _ y \ en q antes de envolver.
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | escape de comodines LIKE en `q`; validación `due_from<=due_to`; parseo de `types` | pytest sin BD |
| Integration (search) | happy por cada entidad (task/project/comment, con snippet y `task_id` en comment); **aislamiento de tenant por CADA tipo**; soft-deleted excluido; `types=` subconjunto; `types` inválido → 422; `q` < 2 chars (tras trim) → 422; orden por `similarity`; `meta` incondicional page/size/total sin params | httpx AsyncClient + fixtures 01 |
| Integration (filtros) | combinación `status+priority+label_id(multi)+assignee+sprint+due range+q`; 422 `due_from>due_to`; paginación | httpx AsyncClient |
| Migration | `alembic upgrade head` crea `pg_trgm` + 5 índices GIN; `downgrade` los revierte + extensión; `alembic check` sin diff | BD desechable `solercia_test_migrations` (patrón existente) |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocess, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. Nota de seguridad (fuera del boundary del skill): ILIKE por parámetro ligado (anti-inyección) + escape de comodines LIKE.

## Migration / Rollout

Migración aditiva 0008 (`down_revision = "0007"`). `upgrade()`: `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")` → 5 `op.create_index(..., postgresql_using="gin", postgresql_ops={col:"gin_trgm_ops"})`. `downgrade()`: drop de los 5 índices y luego `op.execute("DROP EXTENSION IF EXISTS pg_trgm")` (orden inverso; seguro porque en la historia lineal de Alembic ningún objeto posterior depende de la extensión al bajar 0008). Alternativa considerada — dejar la extensión huérfana — descartada por el contrato de rollback simétrico del proposal; `IF EXISTS` evita fallo si ya no está.

## Open Questions

- [x] Orden (similarity vs ILIKE puro): RESUELTO — `similarity()` DESC (Decisión 3).
- [x] Agrupación vs lista plana: RESUELTO — lista plana `UNION ALL` (Decisión 3).
- [x] Downgrade dropea la extensión: RESUELTO — sí, tras los índices (Migration).
- [ ] Riesgo residual: si `alembic check` marca falso positivo de opclass GIN, aplicar el fallback `include_object` en `env.py` (Decisión 2).

## Forecast de tamaño (para sdd-tasks)

Estimado ~480 líneas (search ~290, filtros tasks ~100, migración ~70, modelos/conftest ~20). **400-line budget risk: Medium-High.** `Decision needed before apply: Yes` — considerar 2 slices: (A) migración 0008 + índices/modelos + endpoint `/search`; (B) filtros avanzados de tareas. Comparten la extensión pero A es autónomo y desplegable; B depende sólo de 02/04.
