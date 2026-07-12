# Design: Contrato de API — paginación opt-in, auditoría created_by/updated_by y refresco de docs

## Technical Approach

Se extiende el contrato transversal sin romper al Angular congelado. Tres piezas independientes y reversibles: (1) un módulo compartido de paginación (`backend/app/shared/pagination.py`) consumido por routers/repositories; (2) un `AuditMixin` en `base_model.py` poblado explícitamente en la capa de servicio desde el actor autenticado; (3) refresco de `docs/API.md` desde la superficie real de los 13 routers. Se respeta el patrón `router → service → repository` y el estilo explícito del repo (sin magia oculta). Depende de `01-fundacion-tdd` (baseline Alembic + BD `solercia_test`); el apply no arranca hasta que 01 aterrice.

## Architecture Decisions

### Decisión: Paginación opt-in (compatibilidad hacia atrás)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Opt-in: sin params → lista completa + `meta{total}`; con `page/size` → slice + `meta{page,size,total}` | Preserva el shape exacto actual para el frontend congelado; meta variable | **Elegida** |
| Paginar por defecto (`size=20` siempre) | Rompe al Angular que pide sin params y espera la lista completa | Rechazada |
| Siempre `meta{page,size,total}` | Cambia el shape para llamadores sin params (riesgo si leen meta) | Rechazada |

**Rationale**: el frontend consume las 11 listas sin params y lee `data`. Opt-in es puramente aditivo en el camino sin params (`meta{total}` intacto) y solo introduce `page/size` cuando el cliente los envía.

### Decisión: Mecánica reutilizable + whitelist de orden

**Choice**: `pagination_params(page, size, sort, order)` como dependency FastAPI (defaults: `size=20`, tope `100`, `order` ∈ `{asc,desc}`). Helper async `paginate(stmt, params, sortable) → (rows, total)` que aplica `ORDER BY` (mapeando `sort` a la `Column` real), `LIMIT/OFFSET` y un `COUNT(*)` sobre el `stmt` filtrado. Cada módulo expone una constante `SORTABLE_FIELDS: dict[str, InstrumentedAttribute]` con su orden por defecto; `sort` fuera del dict → `422`.
**Alternatives considered**: whitelist en el schema Pydantic (aleja el mapeo de la `Column`); interpolar `sort` en texto SQL (inyección).
**Rationale**: mapear el string a un atributo ORM es intrínsecamente seguro; la constante vive junto al modelo/repositorio, que es donde se conocen los campos ordenables. El helper centraliza `LIMIT/OFFSET/COUNT`.
**Exclusión explícita — `assignee_name` no ordenable**: `TaskRead.assignee_name` es un campo computado en Python después de la consulta (`backend/app/modules/tasks/service.py:466-479`); no existe `InstrumentedAttribute` en el statement que lo respalde. Queda EXCLUIDO de `SORTABLE_FIELDS` de tasks en este cambio: ordenarlo exigiría un join nuevo con `users`, fuera del alcance del MVP. `?sort=assignee_name` responde `422` como cualquier campo fuera de la whitelist.

### Decisión: Auditoría por asignación explícita en servicio (no event listeners)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Asignación explícita: dependency `get_actor_id → UUID\|None`, el service estampa `created_by`/`updated_by` en create/update | Cambio de firma mecánico en servicios; explícito, testeable (TDD), tolera `None` de jobs | **Elegida** |
| `before_flush` + `ContextVar` | DRY pero magia oculta; frágil entre `await`; el scheduler corre fuera de request → siempre `None` | Rechazada |

**Rationale**: el alert evaluator (`app/alerts/evaluator.py`) crea filas sin usuario autenticado; la asignación explícita deja `None` sin esfuerzo y es verificable con TDD estricto, alineada con el estilo del repo. El router ya resuelve `membership.user_id`, que se pasa como `actor_id`.

### Decisión: Alcance de auditoría, migración y exposición

**Choice**: `AuditMixin` (dos columnas UUID nullable, FK → `users.id` `ondelete=SET NULL`) se aplica a los **11 modelos que ya llevan `SoftDeleteMixin`** (tasks, projects, sprints, comments, attachments, roles, menus, dependencies, alert_rules, users, organizations). `Notification` (sin SoftDelete, generada por el sistema) queda **excluida**. Una única migración Alembic aditiva (columnas nullable, sin backfill, `down_revision` = head del baseline de 01). Los `Read` schemas exponen `created_by`/`updated_by` como opcionales (aditivo; el frontend ignora campos extra).
**Rationale**: "modelo con SoftDelete" es el criterio mecánico y verificable que delimita el conjunto y acota la migración.

## Correcciones de gate (2026-07-11)

Hallazgos confirmados por el gate adversarial sobre este diseño. Cada corrección es VINCULANTE para la fase de tasks; ninguna tarea puede contradecirlas.

1. **[CRITICAL] `meta.tree` de menus se preserva.** `GET /admin/menus` devuelve hoy `meta: {total, tree}` (`backend/app/modules/menus/router.py:39`). El helper genérico de paginación (`build_list_meta` / `paginate`) DEBE fusionar sus claves dentro de `meta` sin eliminar claves existentes — contrato: solo añade/actualiza `page`, `size`, `total`; nunca remueve otras claves. El router de menus conserva `meta.tree` y DEBE quedar cubierto por un escenario/test explícito que verifique que `meta.tree` sobrevive con y sin parámetros de paginación.
2. **[CRITICAL] Auditoría en UPDATE masivo.** `close_sprint` usa `update(Task).where(...).values(sprint_id=...)` (`backend/app/modules/sprints/repository.py:161-169`), que NO pasa por la asignación de auditoría en el service. Todo método de repositorio con UPDATE masivo que mute filas auditadas DEBE recibir el `actor_id` enhebrado hasta el `.values(..., updated_by=actor_id)`. Hoy aplica al move de `close_sprint`; es regla general para cualquier operación bulk futura. Escenario/test obligatorio: cerrar un sprint estampa `updated_by` en las tareas movidas.
3. **[CRITICAL] `assignee_name` fuera de la whitelist de sort.** Campo computado en Python post-query (`backend/app/modules/tasks/service.py:466-479`), sin columna ORM en el statement; queda excluido de `SORTABLE_FIELDS` de tasks en este cambio (sin join nuevo en MVP). Detalle y razón en la decisión de whitelist.
4. **[WARNING] Criterio de modelos auditados.** El criterio es "los 11 modelos con `SoftDeleteMixin`" (AlertRule, Attachment, TaskComment, Dependency, Menu, Organization, Project, Role, Sprint, Task, User), NO "tenant-scoped": `Menu` es un catálogo GLOBAL sin tenant y SÍ se audita. La spec `specs/audit-fields.md` queda alineada a este criterio para eliminar la ambigüedad 10 vs. 11 en tasks/apply.
5. **[WARNING] Writes del seed sin auditoría — aceptado.** `db_init.py` hace `session.add(...)` directo en cada arranque (roles, menús, organización, admin, proyectos demo) sin pasar por services; esas filas quedan con `created_by`/`updated_by` en `NULL` de forma permanente. Es comportamiento ACEPTADO: la auditoría nullable tolera filas de sistema. No se modifica el seed en este cambio.
6. **[WARNING] Cobertura del artefacto de migración.** Los tests de integración validan el esquema vía `create_all` (modelos), no contra el archivo de migración real; la única guardia del artefacto de migración es `test_migrations_baseline.py` (`alembic check`) del cambio 01. Esa dependencia/brecha queda declarada explícitamente en Testing Strategy.

## Data Flow

    ?page&size&sort&order → pagination_params → router → service → repository.paginate(stmt, params, SORTABLE_FIELDS)
                                                                         │  ORDER BY(col) + LIMIT/OFFSET + COUNT
    router {data, meta} ◀── (rows, total) ◀──────────────────────────────┘

    JWT → get_actor_id ─┐                         (sin JWT: alert scheduler)
                        └→ router(actor_id) → service.stamp(created_by/updated_by) → repository   → actor_id = None

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/shared/pagination.py` | Create | `pagination_params` dependency, `paginate()` helper, `build_list_meta()` |
| `backend/app/shared/base_model.py` | Modify | `AuditMixin` (created_by/updated_by nullable FK) |
| `backend/app/dependencies.py` | Modify | `get_actor_id → UUID\|None` |
| `backend/app/modules/*/models.py` (11) | Modify | Mezclar `AuditMixin` en modelos con SoftDelete |
| `backend/app/modules/*/{repository,service,router,schemas}.py` | Modify | `paginate` + `SORTABLE_FIELDS` en listas; estampar audit; exponer campos |
| `backend/alembic/versions/xxxx_add_audit_fields.py` | Create | Migración única, nullable, sin backfill |
| `docs/API.md` | Modify | Regenerar tabla desde los 13 routers; eliminar `meta.page` falso |

## Interfaces / Contracts

```python
# meta sin params (intacto):            {"total": N}
# meta con page/size:                   {"page": 1, "size": 20, "total": N}
def pagination_params(page: int | None = None, size: int = 20,
                      sort: str | None = None, order: str = "desc") -> PaginationParams: ...
async def paginate(stmt, params, sortable: dict[str, InstrumentedAttribute]) -> tuple[Sequence, int]: ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | validación de params, `sort` fuera de whitelist → 422, shape de meta | pytest, sin BD |
| Integration | sin params = lista completa + `meta{total}`; con `page/size` = slice + `meta{page,size,total}`; `order` asc/desc; create estampa `created_by`; update estampa `updated_by`; fila de alert scheduler tolera `actor_id=None` | httpx AsyncClient + fixtures de 01 |
| Integration (gate) | `GET /admin/menus` conserva `meta.tree` con y sin parámetros de paginación; cerrar sprint estampa `updated_by` en las tareas movidas por el UPDATE masivo | httpx AsyncClient + fixtures de 01 |

Notas de alcance:

- **Filas de sistema del seed**: las filas creadas por `db_init.py` quedan con `created_by`/`updated_by` en `NULL` de forma permanente; comportamiento aceptado (la auditoría nullable tolera filas de sistema), no se prueba en contrario ni se modifica el seed.
- **Artefacto de migración**: los tests de integración validan contra `create_all` (modelos), no contra el archivo de migración real; la única guardia del artefacto es `test_migrations_baseline.py` (`alembic check`) del cambio 01. Este cambio depende de esa guardia y declara la brecha explícitamente.

## Migration / Rollout

Una revisión Alembic encadenada al baseline de 01 (`down_revision` = head de 01), columnas nullable sin backfill. Rollback: `downgrade` elimina las dos columnas; el helper de paginación y `docs/API.md` se revierten por commit.

## Open Questions

- [ ] La diferencia de shape de `meta` entre camino sin params (`{total}`) y paginado (`{page,size,total}`) se acepta como el contrato opt-in; confirmar en spec.
- [ ] Churn mecánico en 13 módulos: alto riesgo del presupuesto de 400 líneas; `sdd-tasks` debe recomendar PRs encadenados por grupo de módulos.
