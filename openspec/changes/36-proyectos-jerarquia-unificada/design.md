# Design: 36 · Proyectos con jerarquía unificada (árbol como vista principal)

## Technical Approach

Cambio solo-frontend (más una limpieza idempotente del seed de menú). Se funde el árbol
del 24 en la página existente `pages/projects/projects.component.ts`, que ya es dueña de
la carga de datos, el formulario de creación, el drawer de edición, los textos `projects.*`
y las affordances por permiso. La página pasa a ser un **shell tree-first**: un
`sol-view-toggle` (primitivo existente) alterna **árbol** (por defecto,
`sol-project-tree` del 24) y **solo hojas** (la grilla actual, filtrada por
`?project_kind=proyecto`). La composición de bosque de `hierarchy.component` (con su
timeout/`catchError` por raíz, R7 del 24) se extrae a un helper puro reutilizable;
`HierarchyComponent` se elimina y `/hierarchy` redirige a `/projects`. El nodo gana edición
inline y distinción por `project_kind`. Sin migración; 36 se aplica tras 27
(apply+verify+archive). Contratos backend intactos: `PATCH /projects/{id}` (guard
admin/manager → 403) y `GET /projects?project_kind=` (27).

## Architecture Decisions

### Decisión 1: shell tree-first en la página de Proyectos; grilla como rama del toggle

| Opción | Tradeoff | Decisión |
|---|---|---|
| **`ProjectsComponent` hospeda `sol-project-tree` (árbol=default); grilla = rama `@if` del toggle; composición de bosque → helper puro `project-forest.ts`** | Un solo dueño de datos/permisos/i18n; reutiliza el widget del 24 verbatim; el helper aísla la lógica R7 sin harness | **Elegida** |
| Promover `HierarchyComponent` a `/projects` y plegar grilla+form allí | Reescribe lo que ya funciona (form, drawer, errores de dominio) | Rechazada |
| Mantener dos páginas y solo mover el menú | Contradice "una sola pantalla"; deja `/hierarchy` vivo | Rechazada |

Navegación (boundary): el **chevron** siempre expande/colapsa; **clic en el nombre** de un
nodo `proyecto` navega a `/projects/:id`, de un nodo `area` alterna expandir/colapsar
(mismo criterio para Enter). Se retira el ícono `link` redundante.

### Decisión 2: edición inline con `TreeEditState` (un nodo a la vez, pesimista)

| Opción | Tradeoff | Decisión |
|---|---|---|
| **Servicio `TreeEditState` provisto en el contenedor (hermano de `TreeFocusState`): `editingId`/`editingField`/`savingId`/`errorById`; PATCH pesimista; la página parchea su señal de bosque en sitio** | Invariante de un solo editor; sin `@Output` burbujeando por la recursión; conserva el estado de expansión (sin recargar) | **Elegida** |
| Optimista con rollback | Más código de reversión ante 409/422; innecesario a esta escala | Rechazada |
| `@Output` (renamed) bubbling nodo→página | Frágil con el nodo auto-referente | Rechazada |

Gesto: hover→lápiz o doble clic en el nombre → `sol-input` inline (Enter guarda `{name}`,
Esc cancela). Descripción: acción "Editar descripción" abre una **fila inline expandida**
con `sol-textarea` bajo el nodo (Guardar/Cancelar), no un drawer ni popover (sin primitivo
de popover; mínimo usable). El diff/patch reutiliza la lógica de `onEditSubmit`. **Error**:
`@solercia/ui` no exporta toast → se muestra **inline** bajo el nodo (patrón `editError`
actual), mapeando `code` de dominio (403 `forbidden`, 409 `project_code_taken`,
422 `methodology_not_editable`) por i18n; `sol-toast` queda como gap documentado (aporte a la lib).

### Decisión 3: `project_kind` con fallback topológico (gating del 27)

`Project` gana `project_kind?: 'area'|'proyecto'`; `TreeNodeVM` gana `project_kind` y
`description`. `kindOf(p) = p.project_kind ?? (children.length ? 'area' : 'proyecto')` —
misma regla topológica del 27, así el árbol distingue aunque el kind llegue ausente. Badge
por kind junto al de metodología (label "Área"/"Proyecto"; ícono de `ICON_REGISTRY`
existente, gap documentado si ninguno calza — criterio del 24). "Solo hojas": primario
`?project_kind=proyecto`; fallback client-side por hoja si el payload omite el kind
(27 D5: parámetro ausente = colección completa).

### Decisión 4: permisos en UI desde el store de auth

`AuthService` ya expone `isAdmin`; se añade `canManageProjects = computed(ADMIN|MANAGER)`
reusando `_user().roles`. La página pasa `[editable]="canManageProjects()"` al árbol; el
nodo oculta lápiz/edición si es `false`. El backend sigue forzando 403 (defensa en profundidad).

### Decisión 5: consolidación idempotente del seed de menú (único delta backend)

`_ensure_menus` solo INSERTA. Se (a) quita `("Jerarquía",…,"/hierarchy",…)` de `_MENU_SEED`
y "Jerarquía" de los grants MANAGER/MEMBER en `_ROLE_MENU_SEED`; (b) se añade
`_prune_removed_menus(session)` que borra `RoleMenu` (FK) y luego el `Menu` cuyo `path ∈
_REMOVED_MENU_PATHS = {"/hierarchy"}`, llamado en `seed_default` tras `_ensure_role_menus`;
no-op si ausente. Orgs ya sembradas quedan con una sola entrada "Proyectos" al reiniciar.

## Data Flow

    GET /projects (+ ?project_kind en "solo hojas")
        │  buildForest(projects, progressByRoot)   (helper puro; timeout+catchError por raíz, R7)
        ▼
    ProjectsComponent  ──[toggle]──►  árbol: sol-project-tree ─► sol-project-tree-node (recursivo)
        │  forest: signal<TreeNodeVM[]>              nombre (input inline) · desc (textarea) · badge kind
        │  canManageProjects → [editable]           chevron toggle · clic nombre→/:id | toggle
        └─ TreeEditState.save(id, patch) ─► PATCH /projects/{id} ─► parche in-place del bosque

## File Changes

| File | Action | Description |
|---|---|---|
| `pages/projects/projects.component.ts` | Modify | Shell tree-first: `sol-view-toggle`, señal de bosque, hospeda `sol-project-tree`; grilla = rama "solo hojas" |
| `pages/hierarchy/hierarchy.component.ts` | Delete | Composición migrada al helper; ruta redirige |
| `entities/project/project-forest.ts` | Create | `buildForest(projects, progressByRoot)` puro (R7 preservado) |
| `widgets/project-tree/project-tree-node.component.ts` | Modify | Edición inline (name/desc), badge por kind, clic-nombre por kind |
| `widgets/project-tree/tree-edit-state.ts` | Create | Señales de edición/guardado/error (un nodo) |
| `widgets/project-tree/project-tree.component.ts` | Modify | Provee `TreeEditState`; input `editable`; parcheo del bosque |
| `entities/project/project.model.ts` | Modify | `project_kind` en `Project`; `TreeNodeVM`+kind/description; labels/íconos de kind |
| `entities/project/projects.service.ts` | Modify | `list(params?: { project_kind })` |
| `features/auth/auth.service.ts` | Modify | `canManageProjects` (ADMIN\|MANAGER) |
| `app/app.routes.ts` | Modify | `/hierarchy` → `redirectTo: 'projects'` |
| `assets/i18n/es-CO.json` | Modify | Claves toggle, kind, edición inline |
| `backend/app/db_init.py` | Modify | Quitar Jerarquía de seed+grants; `_prune_removed_menus` |
| `backend/tests/test_menu_seed_projects.py` | Create | Contrato: una entrada `/projects`, cero `/hierarchy`; prune borra menú+grants |

## Interfaces / Contracts

```ts
export type ProjectKind = 'area' | 'proyecto';
// Project: + project_kind?: ProjectKind ; TreeNodeVM: + project_kind, description
list(params?: { project_kind?: ProjectKind }): Observable<ProjectListResponse>;
class TreeEditState {                    // provisto en el contenedor del árbol
  editingId; editingField: 'name'|'description'|null; savingId;
  errorById: Signal<Map<string,string>>;
  begin(id, field); cancel(); save(id, patch: { name?: string; description?: string|null });
}
```
```python
_REMOVED_MENU_PATHS = {"/hierarchy"}
async def _prune_removed_menus(session) -> None  # borra RoleMenu y luego Menu; no-op si ausente
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Build/Lint | Plantillas y estilo (sin harness front, criterio 13/24) | `ng build`, `eslint .` |
| Backend unit | `_MENU_SEED`: una entrada `/projects`, ninguna `/hierarchy`; grants sin "Jerarquía"; `/hierarchy ∈ _REMOVED_MENU_PATHS` | patrón `test_menu_seed_appearance.py` |
| Backend integr. | `_prune_removed_menus` borra el `Menu` `/hierarchy` sembrado y sus `RoleMenu`; idempotente (no-op al repetir) | siembra menú + grant, corre prune |
| Manual | tree-first; clic nombre por kind; edición inline name/desc (Enter/Esc, pesimista, error 403/422/409 inline); badge kind + fallback; toggle "solo hojas"; `/hierarchy`→`/projects`; carga/vacío/error | checklist del spec |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. El redirect y el `routerLink ['/projects', id]`
(id UUID del backend) son configuración/navegación estática de Angular.

## Migration / Rollout

Sin migración de datos. El prune del seed corre en cada arranque (idempotente). 36 se aplica
tras el apply+verify+archive del 27 (fallback topológico si `project_kind` llega ausente).
Rollback: revertir commits de página/widget/entidad/rutas/auth y del seed; restaurar la ruta
`/hierarchy` + `HierarchyComponent` + las filas "Jerarquía".

## Open Questions

- [ ] Glifo del badge de kind: reutilizar un ícono de `ICON_REGISTRY`; documentar gap si ninguno calza (como el 24).
- [ ] Sin primitivo `sol-toast`: error inline (decidido); registrar `sol-toast` como aporte pendiente a la lib.

## Forecast de tamaño (para sdd-tasks)

Estimado ~400–460 líneas (nodo inline ~90, `tree-edit-state` ~40, página toggle+bosque ~120,
modelo ~30, helper ~40, seed+prune+test ~80, i18n ~30, auth/service/rutas ~20).
`400-line budget risk: Medium`. `Decision needed before apply: No`. `Chained PRs recommended: No`
(corte opcional: slice backend-seed vs slice frontend si cruza el presupuesto).
