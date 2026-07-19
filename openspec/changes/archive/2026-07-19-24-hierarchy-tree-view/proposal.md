# Proposal: 24 · Vista de árbol jerárquico de proyectos

## Intent

No existe una vista que muestre la jerarquía completa de proyectos de arriba hacia abajo. `GET /projects` (lista plana) y el workspace `/projects/:id` no revelan la estructura padre-hijo ni el avance roll-up del cambio 21 (18/20). Un jefe necesita ver en una pantalla limpia las sombrillas → subproyectos con su avance consolidado y navegar al proyecto. Este cambio agrega esa vista de solo lectura consumiendo los endpoints del 21.

## Scope

### In Scope
- Página y ruta lazy `hierarchy` (evita la colisión con `projects/:id`), enlazada desde la lista de proyectos.
- Widget recursivo `project-tree`: nodo = proyecto/subproyecto con avance done/total (18/20), expandir/colapsar y "ir al proyecto" (routerLink a `/projects/:id`).
- Consumo de `GET /projects/{id}/tree` y `/progress` (21) y `parent_project_id` de `GET /projects`.
- Estados de carga, vacío y error; responsive y accesible (roles tree/treeitem, teclado).
- Composición con primitivos @solercia/ui; gap de componente de árbol documentado (criterio del 13).

### Out of Scope
- Reparentar (`PATCH /projects/{id}/parent`): mutación con permisos admin/manager; se difiere.
- Listar tareas individuales por nodo (viven en el workspace); el árbol muestra el conteo agregado.
- Endpoint de bosque/agregación en backend (no existe en 21): se compone en cliente.
- Harness de pruebas de frontend.

## Capabilities

### New Capabilities
- `frontend-hierarchy-view`: vista de solo lectura del árbol de proyectos con avance roll-up.

### Modified Capabilities
- None

## Approach

FSD: `pages/hierarchy/` (ruta + carga + estados), `widgets/project-tree/` (componente recursivo), extensión de `entities/project/` (`tree()`/`progress()`, modelos, `parent_project_id`). El bosque se compone en cliente: `GET /projects` → raíces por `parent_project_id`; por cada raíz una llamada `/progress` (devuelve done/total de todo su subárbol) más el anidado. Nodo = SolCard + SolBadge/SolProgressBar + SolIconButton (chevron). @solercia/ui 0.3.0 no exporta SolTree y SolTimeline es Gantt por fechas (inservible aquí): se arma un árbol propio y `sol-tree` queda como pendiente de librería.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `frontend/src/pages/hierarchy/` | New | Página + ruta lazy |
| `frontend/src/widgets/project-tree/` | New | Componente recursivo del árbol |
| `frontend/src/entities/project/` | Modified | `tree()`/`progress()`, modelos, `parent_project_id` |
| `frontend/src/app/app.routes.ts` | Modified | Ruta `hierarchy` + enlace |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Superficie REST del 21 (`/tree`, `/progress`, `parent_project_id` en la lista) pendiente de apply | Alta | Gating de orquestador: el apply del 24 no arranca hasta que el 21 complete apply + verify + archive |
| Sin endpoint de bosque → N+1 por raíz | Media | 1 `/progress` por raíz cubre su subárbol; batch futuro |
| Sin harness de pruebas | Alta | build + eslint + checklist manual |
| Árboles de 5 niveles (responsive/a11y) | Media | indentación + ARIA + teclado |

## Rollback Plan

Revertir los commits de ruta/página/widget/entidad; sin migración ni backend. La app vuelve a la lista de proyectos.

## Dependencies

- 21-project-hierarchy: proposal/spec/design/tasks done y apply EN CURSO — hasta ahora solo aterrizaron la migración 0014 + la columna `parent_project_id` + los CTEs del repository; el router/schemas/service de `/tree` y `/progress` aún NO existen. El apply del 24 queda BLOQUEADO por orquestación hasta que el 21 complete apply + verify + archive (decisión de secuenciamiento; el 24 NO incorpora backend).
- 13-ui-component-audit (patrón de consumo y criterio de gaps de librería).

## Success Criteria

- [x] Bosque completo top-down con done/total por nivel (18/20).
- [x] Expandir/colapsar e "ir al proyecto" funcionan.
- [x] Carga/vacío/error visibles.
- [x] Responsive + accesible (teclado, ARIA tree).
- [x] Usa @solercia/ui; gap de árbol documentado.
- [x] `ng build` y `eslint` en verde.

Verificado por lectura de código + `npm run build`/`npm run lint`/`tsc --noEmit` en verde (apply del 24, tasks.md 5.4). Pendiente una pasada de QA manual interactiva con navegador real: esta sesión de apply no tuvo herramienta de navegador disponible (ver tasks.md 3.4/4.4/5.4).

## Proposal question round

Supuestos a validar con el usuario: (1) primer corte solo lectura, reparentar diferido; (2) el árbol para en nodos de proyecto con conteo agregado, sin listar tareas; (3) bosque compuesto en cliente, sin endpoint nuevo de backend.
