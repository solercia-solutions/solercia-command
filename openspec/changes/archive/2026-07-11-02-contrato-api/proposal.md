# Propuesta: Contrato de API — paginación, auditoría y refresco de documentación

## Intent

El contrato transversal del backend incumple lo que el propio CLAUDE.md define. Hoy: (1) **toda** lista devuelve cada fila con `meta.total = len()` — sin `?page&size&sort&order` — lo que no escala y satura clientes; (2) **no** existen `created_by` / `updated_by`, pese a ser patrón obligatorio de auditoría — no hay rastro de quién crea o modifica; (3) `docs/API.md` está desactualizado (omite comments, attachments, notifications, alert-rules, tasks/by-key, subtasks, velocity y sprint close) y afirma en falso que `meta.page` existe. El cambio alinea el contrato real con el contrato prometido.

## Scope

### In Scope
- **Paginación estándar** (`?page&size&sort&order` + `meta: {page, size, total}`) en las listas de: tasks, notifications, users, roles, menus, dependencies, projects, sprints, comments, attachments, alert-rules.
- **Auditoría automática** `created_by` / `updated_by` en modelos de dominio, poblada desde el usuario autenticado (dependency de FastAPI) + migración Alembic.
- **Refresco de `docs/API.md`** para reflejar la superficie real tras aterrizar (1) y (2).

### Out of Scope
- Cualquier cambio en `frontend/` (congelado, constraint `frontend-frozen`).
- Nuevos endpoints o features; solo se documenta lo existente.
- Paginación por cursor/keyset (solo offset-based en este ciclo).
- Backfill histórico de `created_by`/`updated_by` (filas previas quedan en null).
- Permisos granulares por endpoint y unificación de roles (deuda aparte).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `api-conventions`: agrega el requisito del contrato de paginación (`?page&size&sort&order` + `meta {page,size,total}`) y el de auditoría `created_by`/`updated_by`.
- `tasks`, `notifications`, `sprints`, `projects`, `comments-mentions`, `attachments`, `rbac-catalog` (roles/menus), `users-admin`, `alert-engine` (alert-rules): sus endpoints de lista incorporan el escenario de paginación opt-in.

## Approach

- **Paginación**: extender el helper de envelope/paginación en `backend/app/shared/`; dependency reutilizable de params (`page/size/sort/order`) con defaults; `LIMIT/OFFSET` + `COUNT` en repository; `meta` pasa de `{total}` a `{page, size, total}` (aditivo, conserva `total`). Whitelist de campos ordenables para evitar inyección.
- **Auditoría**: columnas `created_by`/`updated_by` (nullable) vía `base_model`; dependency inyecta el id del usuario autenticado; el service las setea en create/update. Migración Alembic aditiva (sin backfill).
- **Docs**: reescribir `docs/API.md` desde la superficie real de routers.
- **Compat backend/frontend**: sin params de paginación, la lista mantiene el comportamiento actual (devolver todo) para no romper al Angular existente. La forma exacta del default (o paginación opt-in) se decide en design; aquí se marca el tradeoff.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `backend/app/shared/` | Modified | Helper de paginación, params dependency, `base_model` auditoría |
| `backend/app/modules/*/repository.py` | Modified | `LIMIT/OFFSET` + `COUNT` en listas |
| `backend/alembic/versions/` | New | Migración de `created_by`/`updated_by` |
| `docs/API.md` | Modified | Superficie real de la API |

## Risks

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Romper al frontend Angular que consume sin params | Media | Default: sin params → devolver todo (opt-in). Decidir en design |
| Cambio de forma de `meta` (`{total}`→`{page,size,total}`) | Baja | Aditivo, se conserva `total` |
| Inyección vía `sort`/`order` | Media | Whitelist de campos ordenables por endpoint |
| Migración de auditoría sobre datos existentes | Baja | Columnas nullable, sin backfill |
| Apply arranca antes de aterrizar Alembic | Media | Bloqueado por dependencia con `01-fundacion-tdd` |

## Rollback Plan

Revertir la migración Alembic (drop `created_by`/`updated_by`); revertir el helper de paginación (`meta` vuelve a `{total}`, sin params); `git revert` del `docs/API.md`. Cada pieza es independiente y reversible.

## Dependencies

- **`01-fundacion-tdd`** (bloqueante): adopción de Alembic, fixtures de test y BD `solercia_test`. El **apply de este cambio NO puede iniciar** hasta que `01` esté aplicado (la migración de auditoría y el TDD estricto dependen de esa base).

## Success Criteria

- [ ] Las listas aceptan `?page&size&sort&order` y devuelven `meta {page, size, total}`.
- [ ] Sin params, los consumidores actuales siguen funcionando (comportamiento por defecto).
- [ ] `created_by`/`updated_by` se pueblan en create/update desde el usuario autenticado; migración Alembic presente.
- [ ] `docs/API.md` refleja la superficie real y elimina la afirmación falsa de `meta.page`.
- [ ] Tests TDD cubren: paginación (happy path), default sin params, y poblado de auditoría.
