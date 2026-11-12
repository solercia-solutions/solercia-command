# Proposal: 36 · Proyectos con jerarquía unificada (árbol como vista principal)

## Intent

Proyectos tiene hoy DOS vistas desconectadas: la grilla plana (`/projects`, `pages/projects`) que no revela la estructura padre-hijo, y el árbol de SOLO LECTURA (`/hierarchy`, `widgets/project-tree`, cambio 24) que muestra la jerarquía con roll-up pero no permite editar ni distingue área de proyecto. El jefe no tiene una sola pantalla para ver la organización, entrar a las tareas de un proyecto y renombrar en contexto. La OLA 4 (fase 4.3, decisión 2) resuelve unificar: el árbol pasa a ser la vista principal, con edición inline y distinción por `project_kind` (área vs proyecto, del cambio 27).

## Scope

### In Scope
- Promover el árbol del 24 (`project-tree` + composición de bosque de `hierarchy.component`) a vista PRINCIPAL de Proyectos en `/projects`.
- Clic en nodo proyecto → workspace de tareas (`/projects/:id`); nodo área → expandir/colapsar.
- Edición inline de nombre/descripción en el nodo → `PATCH /projects/{id}` (ya existe, guard admin/manager); control oculto para roles sin permiso.
- Distinción visual por `project_kind`: ícono/insignia área vs proyecto (junto al badge de metodología).
- Toggle "solo hojas": grilla secundaria vía `GET /projects?project_kind=proyecto` (filtro del 27).
- Consolidar navegación: `/hierarchy` redirige a `/projects`; una sola entrada de menú.
- Estados de carga, vacío y error (reúsa los del 24 y la grilla).

### Out of Scope
- Reparentar por drag&drop (el `PATCH /projects/{id}/parent` existe; su UI se difiere).
- Delta backend de permisos del rename (ya exige admin/manager → 403).
- Cambiar la reconciliación del 27 (matchea por ledger, nunca por nombre; el rename no la rompe).

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `frontend-hierarchy-view`: de árbol de solo lectura a vista principal editable de Proyectos (edición inline, distinción por `project_kind`, navegación nodo→workspace, toggle "solo hojas").

## Approach

Reutilizar `widgets/project-tree` y la composición de bosque de `hierarchy.component` como núcleo de `/projects`. Extender `Project`/`TreeNodeVM` (frontend) con `project_kind` y `description` (el backend ya los expone tras el 27). El nodo gana: edición inline (pencil → input de nombre + textarea de descripción) que llama `PATCH /projects/{id}` y refresca; ícono por kind; clic en proyecto navega al workspace. La grilla queda como render alterno ("solo hojas") por `?project_kind=proyecto`. Sin código backend nuevo; 36 depende de que el 27 aplique.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `frontend/src/pages/projects/*` | Modified | Vista principal tree-first + toggle "solo hojas" |
| `frontend/src/widgets/project-tree/*` | Modified | Edición inline, ícono por kind, clic→workspace |
| `frontend/src/entities/project/project.model.ts` | Modified | `project_kind`, `description` en `Project`/`TreeNodeVM` |
| `frontend/src/pages/hierarchy/*`, `app/app.routes.ts` | Modified/Removed | `/hierarchy` redirige a `/projects` |
| `backend/app/db_init.py` | Modified | Consolidar menú (una entrada de Proyectos) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| 27 sin aplicar → `GET /projects` sin `project_kind` | Alta | Gating: apply del 36 tras apply+verify del 27; fallback visual "proyecto" |
| Edición inline sin harness front | Alta | build + eslint + checklist manual; PATCH ya cubierto por tests backend |
| Menú "Jerarquía" ya sembrado en orgs existentes | Media | redirect inocuo `/hierarchy`→`/projects` + limpieza idempotente del menú |
| Rename rompe trazabilidad del template | Baja | 27 matchea por ledger (template_id+node_id), no por nombre — verificado |

## Rollback Plan

Revertir los commits de página/widget/entidad/rutas y del seed de menú; restaurar `/hierarchy` como vista independiente. Sin migración: rollback puramente de código frontend + seed.

## Dependencies

- `27-plantillas-idempotentes`: `project_kind` en `GET /projects` + filtro `?project_kind=`.
- `24-hierarchy-tree-view` (archivado): widget `project-tree` y composición de bosque reutilizados.

## Success Criteria

- [ ] `/projects` muestra el árbol como vista principal; clic en proyecto abre sus tareas.
- [ ] Nombre/descripción editables inline en el nodo (admin/manager); el miembro no ve el control.
- [ ] Distinción visual área vs proyecto por `project_kind`.
- [ ] Toggle "solo hojas" lista los proyectos hoja.
- [ ] `/hierarchy` consolidado; `ng build`/`eslint` en verde; el rename no rompe la reconciliación del 27.

## Proposal question round

Supuestos a validar: (1) unificar en `/projects` (árbol-first) y redirigir `/hierarchy`, en vez de repuntar el menú a `/hierarchy`; (2) edición inline REAL en el nodo (pencil → campos en sitio) para nombre+descripción, no un drawer aparte; (3) clic en nodo proyecto navega al workspace, nodo área expande/colapsa; (4) "solo hojas" = grilla secundaria por `?project_kind=proyecto`; (5) cero delta backend (PATCH y filtro ya existen; permiso admin/manager ya aplicado). Segunda ronda disponible para revisar el gesto de edición (inline vs drawer) o el clic en áreas.
