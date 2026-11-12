# Tasks: 36 · Proyectos con jerarquía unificada (árbol como vista principal)

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas | ~480–560 (seed+prune+tests backend ~150; forest+model+service ~130; `projects.component.ts` ~140; borrado `hierarchy.component.ts` ~205; tree-node/tree/edit-state ~190; rutas/i18n/auth/nav-fallback ~60) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | PR único; commits escalonados por fase (1→5); merge local a `preview` |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Objetivo | Commit (mismo PR) | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| U1 | Fase 1 — seed backend: consolida "Proyectos", depura "Jerarquía" (prune idempotente) | 1 | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_menu_seed_projects.py backend/tests/test_menu_seed.py` | Pytest contra Postgres de test | Revert commit; sin migración, solo filas de catálogo |
| U2 | Fase 2 — shell tree-first: `/projects` hospeda `sol-project-tree`, chevron/clic-nombre, redirect `/hierarchy`, borra `HierarchyComponent` | 2 | `cd frontend && npm run build` | Manual: navegar `/projects`, expandir/colapsar, clic en nombre | Revert commit; `/hierarchy` vuelve a existir |
| U3 | Fase 3 — edición inline (`TreeEditState`, permisos) | 3 | `cd frontend && npm run build && npm run lint` | Manual: admin edita name/desc, member sin lápiz, error 403 inline | Revert commit; árbol queda solo-lectura |
| U4 | Fase 4 — `project_kind` (badge+`kindOf`) + toggle "solo hojas" | 4 | `cd frontend && npm run build` | Manual: badges mixtos, fallback sin kind, toggle grilla | Revert commit; badges/toggle desaparecen, árbol intacto |
| U5 | Fase 5 — verde total + commit final si aplica | 5 (condicional) | `cd backend && pytest -q` + `cd frontend && npm run build && npm run lint` | N/A — regresión | Revert commit aislado |

## Fase 1 — Seed backend (STRICT TDD, `backend/app/db_init.py`)

- [ ] 1.1 [RED] `backend/tests/test_menu_seed_projects.py`: `_MENU_SEED` tiene una sola entrada `/projects`, ninguna `/hierarchy`; `_ROLE_MENU_SEED["MANAGER"/"MEMBER"]` sin "Jerarquía"; `"/hierarchy" in _REMOVED_MENU_PATHS`. Falla hoy.
- [ ] 1.2 [RED] Mismo archivo: test de integración — siembra menú+grants con "Jerarquía" preexistente, corre `_prune_removed_menus(session)`, afirma que `Menu`/`RoleMenu` de `/hierarchy` desaparecen y "Proyectos" queda intacto; correr el prune dos veces no falla ni duplica. Falla hoy (`_prune_removed_menus` no existe).
- [ ] 1.3 [GREEN] Quitar `("Jerarquía", "list-tree", "/hierarchy", None, 1)` de `_MENU_SEED`; quitar `"Jerarquía"` de `_ROLE_MENU_SEED["MANAGER"]`/`["MEMBER"]`.
- [ ] 1.4 [GREEN] Añadir `_REMOVED_MENU_PATHS = {"/hierarchy"}` e implementar `_prune_removed_menus(session)`: borra `RoleMenu` por `menu_id`, luego `Menu` por `path`; no-op si no hay filas.
- [ ] 1.5 [GREEN] Llamar `await _prune_removed_menus(session)` en `seed_default()` justo tras `_ensure_role_menus`.
- [ ] 1.6 Actualizar `backend/tests/test_menu_seed.py` (contrato del 24 sobre "Jerarquía", ahora obsoleto): reemplazar sus aserciones por la consolidación en "Proyectos" — hallazgo propio, no listado en `design.md`, imprescindible para no romper la suite.
- [ ] 1.7 Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_menu_seed_projects.py backend/tests/test_menu_seed.py backend/tests/test_menu_seed_connections.py backend/tests/test_menu_seed_appearance.py`

Commit 1: `fix(menu): consolida Proyectos y depura Jerarquia de forma idempotente`

## Fase 2 — Shell tree-first en `/projects`

- [ ] 2.1 Crear `frontend/src/entities/project/project-forest.ts`: `buildForest(projects, rollupById, errorByRoot)` puro, portando el agrupamiento/`toNode` de `hierarchy.component.ts:107-201` (R7 preservado: timeout+catchError quedan en el llamador).
- [ ] 2.2 `entities/project/project.model.ts`: añadir `description: string | null` a `TreeNodeVM`.
- [ ] 2.3 `pages/projects/projects.component.ts`: portar la orquestación HTTP de `hierarchy.component.ts` (forkJoin/timeout/catchError por raíz) a un método `loadTree()`; hospedar `<sol-project-tree [nodes]="forest()">` como vista por defecto (sin toggle todavía, Fase 4 lo agrega).
- [ ] 2.4 `widgets/project-tree/project-tree-node.component.ts`: el clic en el NOMBRE navega a `/projects/{id}` sin importar `project_kind`; el chevron sigue expandiendo/colapsando; quitar el ícono `link` redundante; Enter replica el clic en nombre (ya no expande si tiene hijos — ArrowRight/Left conservan expandir/colapsar por teclado).
- [ ] 2.5 Borrar `pages/hierarchy/hierarchy.component.ts`.
- [ ] 2.6 `app/app.routes.ts`: reemplazar la ruta `hierarchy` por `{ path: 'hierarchy', pathMatch: 'full', redirectTo: 'projects' }`.
- [ ] 2.7 `app/app.component.ts`: quitar la entrada `hierarchy` del fallback estático de `sidebarItems`; `pages/teams/teams.component.ts`: repuntar el botón "Ver en la jerarquía" a `/projects` — hallazgo propio, no listado en `design.md`.
- [ ] 2.8 `assets/i18n/es-CO.json`: quitar `hierarchy.title/subtitle/loading/empty.*/errors.*` (huérfanos) y `nav.links.hierarchy`; conservar `hierarchy.node.*`/`hierarchy.tree.ariaLabel` (aún usados por el widget).
- [ ] 2.9 Verify: `cd frontend && npm run build && npm run lint`; manual: `/projects` muestra el árbol, clic en nombre navega, `/hierarchy` redirige.

Commit 2: `feat(projects): unifica /projects como arbol principal y retira /hierarchy`

## Fase 3 — Edición inline

- [ ] 3.1 Crear `widgets/project-tree/tree-edit-state.ts`: `TreeEditState` con `editingId`, `editingField`, `savingId`, `errorById`, `patchedById`; `begin(id,field)`, `cancel()`, `save(id,patch)` → `ProjectsService.update()` pesimista, mapeo de error (403/404, mismo patrón que `domainErrorMessage` de `projects.component.ts`).
- [ ] 3.2 `project-tree.component.ts`: `providers:[TreeFocusState, TreeEditState]`; input `editable`.
- [ ] 3.3 `project-tree-node.component.ts`: lápiz hover/doble clic activa edición de nombre (`sol-input`, Enter guarda, Esc cancela); acción "Editar descripción" abre fila inline con `sol-textarea` + Guardar/Cancelar; oculto si `!editable()`; error inline bajo el nodo (patrón `editError`).
- [ ] 3.4 `features/auth/auth.service.ts`: `canManageProjects = computed(...ADMIN|MANAGER)`.
- [ ] 3.5 `projects.component.ts`: `[editable]="canManageProjects()"` al árbol.
- [ ] 3.6 `assets/i18n/es-CO.json`: claves de edición inline (aria de lápiz/guardar/cancelar).
- [ ] 3.7 Verify: `npm run build && npm run lint`; manual: admin edita, member sin lápiz, error 403 inline, Enter/Esc.

Commit 3: `feat(projects): edicion inline de nombre y descripcion en el arbol`

## Fase 4 — `project_kind` y toggle "solo hojas"

- [ ] 4.1 `project.model.ts`: `ProjectKind`, `project_kind?` en `Project`+`TreeNodeVM`, `KIND_LABELS`, `KIND_ICON` (`area:'layers'`, `proyecto:'briefcase'`), `kindOf(kind, hasChildren)`.
- [ ] 4.2 `project-forest.ts`: setear `project_kind: kindOf(...)` por nodo.
- [ ] 4.3 `project-tree-node.component.ts`: badge de kind junto al de metodología.
- [ ] 4.4 `projects.service.ts::list(params?: {project_kind})`.
- [ ] 4.5 `projects.component.ts`: `sol-view-toggle` árbol/solo-hojas; "solo hojas" llama `list({project_kind:'proyecto'})` con fallback cliente si el kind llega ausente.
- [ ] 4.6 `assets/i18n/es-CO.json`: claves del toggle y del badge de kind.
- [ ] 4.7 Verify: `npm run build`; manual: badges mixtos, fallback sin kind, toggle "solo hojas".

Commit 4: `feat(projects): distingue project_kind y agrega el toggle solo hojas`

## Fase 5 — Verde total

- [ ] 5.1 `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` completo.
- [ ] 5.2 `cd frontend && npm run build && npm run lint`.
- [ ] 5.3 Checklist manual completo del spec (carga/vacío/error, permisos, reconciliación del 27 no se rompe con el rename).
- [ ] 5.4 Merge local a `preview` (sin PR nuevo); commits convencionales en español ya creados por fase.

## Trazabilidad de requisitos

- Vista principal árbol + redirect + menú único · 2.1-2.9
- Navegación por kind (clic-nombre/chevron/Enter) · 2.4
- Edición inline (permiso, Enter/Esc, error, trazabilidad del 27) · 3.1-3.7
- Distinción visual de kind + fallback topológico · 4.1-4.3
- Toggle "solo hojas" · 4.4-4.5
- Consolidación idempotente del menú · 1.1-1.7
