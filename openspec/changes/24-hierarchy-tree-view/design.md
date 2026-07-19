# Design: 24 · Vista de árbol jerárquico de proyectos

## Technical Approach

Vista de solo lectura, solo frontend, que compone en cliente el bosque de proyectos con avance roll-up del 21. FSD estándar (patrón real de `pages/projects/projects.component.ts`): standalone + `OnPush` + signals, textos por `I18nService` (`@shared/i18n`), primitivos desde `@shared/ui` (re-export puro de `@solercia/ui`, `shared/ui/index.ts:4`), ruta lazy con `authGuard`. Tres piezas: `pages/hierarchy/` (host de datos y estados), `widgets/project-tree/` (contenedor `role="tree"` + nodo recursivo), extensión de `entities/project/` (`tree()`/`progress()`, tipos, `parent_project_id`). Contratos consumidos del 21: `GET /projects/{id}/progress` (nodo anidado `self`/`rollup`), `GET /projects/{id}/tree` (nodo anidado con `methodology`/`status`), y `parent_project_id` en `GET /projects`. **Estado real del 21**: proposal/spec/design/tasks done y apply EN CURSO — hasta ahora solo aterrizaron la migración 0014 + la columna `parent_project_id` + los CTEs del repository; el router/schemas/service de `/tree` y `/progress` aún NO existen. Por eso el **apply del 24 queda BLOQUEADO por orquestación** hasta que el 21 complete apply + verify + archive (decisión de secuenciamiento; el 24 NO se re-alcanza para incluir backend).

## Architecture Decisions

### Decisión 1: composición del bosque — lista plana + `/progress` por raíz

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **A. Estructura desde `GET /projects` agrupando por `parent_project_id`; 1 `/progress` por raíz para los números** | La lista ya viene filtrada por tenant + `is_active` (backend) y trae `methodology`/`status`; agrupar padre-hijo NO reimplementa el CTE del 21. `N+1` acotado (mitigación ratificada del proposal). `/progress` es anidado → cubre todo el subárbol de la raíz | **Elegida** |
| B. `GET /{id}/tree` + `/progress` por raíz (forkJoin), zip por id | Estructura autoritativa del backend, pero `2N+1` llamadas y `/tree` duplica lo que la lista ya expone | Rechazada (se conserva `tree()` como fallback) |

`tree()` queda en el service como fallback si la lista omitiera `parent_project_id`/`methodology`. Raíces = proyectos con `parent_project_id == null`. **Huérfano** (hijo cuyo `parent_project_id` no está en el conjunto, p.ej. padre soft-deleted) → se promueve a raíz. Números: aplanar cada `/progress` anidado a `Map<projectId, {done,total}>` y enlazar por id.

### Decisión 2: componente recursivo vs render aplanado

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Nodo recursivo auto-referente (`project-tree-node` se renderiza a sí mismo para los hijos)** | ARIA nativo: `treeitem` con `group` anidado calza con el DOM; expand/collapse = signal local por nodo; profundidad acotada a 5 (`MAX_DEPTH` del 21) → sin virtualización | **Elegida** |
| Lista aplanada con `aria-level`/`aria-setsize` | Mejor para miles de nodos (virtual scroll), pero ARIA manual y propiedad de grupos colapsados más frágil; innecesario a esta escala | Rechazada |

### Decisión 3: barra de avance — primitivo existe

Verificado: `SolProgressBarComponent` (`solercia-ui.d.ts:806`, modo `continuous`, `role="progressbar"` con `aria-valuenow/max`) SÍ se exporta. Se usa `value=rollup.done`, `max=rollup.total`, `variant` por umbral; **no se requiere barra CSS manual**. La fracción `18/20` va como texto contiguo. `total===0` → sin barra, texto "sin tareas". Fallo de `/progress` de una raíz → subárbol sin números ("—"), no rompe el resto (estado parcial).

## Data Flow

    GET /projects ─► raíces (parent_project_id==null) + estructura anidada (methodology/status)
         │                                   │
         └─ forkJoin: por raíz GET /{id}/progress ─► Map<id,{done,total}>
                                             │
                    project-tree (role=tree) ─► project-tree-node (recursivo)
                        SolCard · SolBadge · SolProgressBar · SolIcon(chevron) · routerLink

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `entities/project/project.model.ts` | Modify | `parent_project_id` en `Project`; tipos `ProjectTreeNode`, `ProjectProgressNode`, envoltorios y view-model del bosque |
| `entities/project/projects.service.ts` | Modify | `tree(id)`, `progress(id)` (thin HTTP, patrón de `list()`) |
| `pages/hierarchy/hierarchy.component.ts` | Create | Host: carga, forkJoin por raíz, estados carga/vacío/error/parcial |
| `widgets/project-tree/project-tree.component.ts` | Create | Contenedor `role="tree"` + roving tabindex/flechas |
| `widgets/project-tree/project-tree-node.component.ts` | Create | Nodo recursivo `treeitem`/`group`, `aria-expanded` |
| `app/app.routes.ts` | Modify | Ruta lazy `hierarchy` con `authGuard` |
| `app/app.component.ts` | Modify | Enlace `hierarchy` en `fallbackLinks` (nav de solo texto) |
| `assets/i18n/es-CO.json` | Modify | Claves `hierarchy.*` (título, estados, ARIA) |

## Interfaces / Contracts

```ts
export interface ProjectProgressNode {
  project_id: string; name: string;
  self: { done: number; total: number; percent_done: number };
  rollup: { done: number; total: number; percent_done: number };
  children: ProjectProgressNode[];
}
export interface TreeNodeVM {                 // view-model compuesto en cliente
  id: string; name: string; methodology: Methodology; status: string;
  rollup?: { done: number; total: number }; children: TreeNodeVM[];
}
// service: tree(id): Observable<{data: ProjectTreeNode}>; progress(id): Observable<{data: ProjectProgressNode}>
```

Gap de librería (criterio del 13): `@solercia/ui` 0.3.0 no exporta `sol-tree` → se arma árbol propio; se registra `sol-tree` como pendiente de aporte. Chevrons `chevron-right`/`chevron-down` SÍ existen en `ICON_REGISTRY` (no hay gap de ícono). La nav es de solo texto (como los `fallbackLinks` actuales) → sin ícono; un glifo de jerarquía (`sitemap`) está ausente del registro, pendiente menor documentado.

## Testing Strategy

Sin harness de frontend (confirmado por design del 13). Verificación:

| Capa | Qué | Cómo |
|------|-----|------|
| Build | Plantillas sin error | `ng build` |
| Lint | Estilo + plantillas | `eslint .` |
| Manual | Bosque top-down 18/20 por nivel; expandir/colapsar; "ir al proyecto"; carga/vacío/error/parcial; responsive; teclado (flechas, Enter) + ARIA `tree/treeitem/group`, `aria-expanded` | Checklist por escenario del spec |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. Ruta lazy = configuración estática.

## Migration / Rollout

Sin migración ni backend. Rollback: revertir commits de ruta/página/widget/entidad; la app vuelve a la lista de proyectos.

## Open Questions

- [ ] Toda la superficie REST del 21 (`/tree`, `/progress`, y `parent_project_id` en `GET /projects`) está pendiente del apply del 21 — hoy solo existen la migración 0014, la columna y los CTEs del repository. El apply del 24 se ejecuta contra la superficie ya aterrizada tras el apply + verify + archive del 21 (gating de orquestador) y verifica que `GET /projects` emita `parent_project_id`; si no lo emite, activa el fallback `tree()` por raíz (Decisión 1).

## Forecast de tamaño (para sdd-tasks)

Estimado ~380–420 líneas (nodo recursivo ~130, contenedor ~80, página ~120, entidad ~40, i18n ~25, ruta/nav ~10). `400-line budget risk: Medium`. `Decision needed before apply: No`. `Chained PRs recommended: No` (feature cohesiva; corte opcional data-layer → widget si cruza el presupuesto).
