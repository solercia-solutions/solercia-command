# Proposal: 32 · Jerarquía de subtareas en el backlog (padre → subtareas indentadas)

## Intent

Hoy el listado del backlog es **plano y solo de nivel superior**: `GET /projects/{id}/tasks` fija `top_level_only = (parent_task_id is None)` (`tasks/service.py:111`), así que **ninguna subtarea aparece** en la vista de backlog salvo que se pida hija por hija (`?parent_task_id={id}`, patrón N por padre de `loadEpicChildren`). Como consecuencia, **filtrar por asignado oculta las subtareas**: `?assignee_id=X` mantiene `top_level_only=True`, y una subtarea asignada a X jamás se devuelve si su padre no matchea. Este cambio (OLA 4, fase 4.2) muestra las subtareas indentadas bajo su padre dentro de las secciones del cambio 30 y garantiza la **regla de producto innegociable**: una subtarea asignada a un usuario SIEMPRE aparece al filtrar por ese usuario, aunque el padre esté asignado a otro (el padre se muestra atenuado como contexto). Nada se oculta por posición jerárquica.

## Scope

### In Scope
- **Backend**: modo de listado que incluye subtareas (`include_subtasks`/jerárquico) levantando `top_level_only`, para que el cliente arme la indentación sin N consultas por padre.
- **Backend (regla innegociable)**: con `assignee_id` presente, la lista devuelve las subtareas asignadas + los **padres de contexto** de las subtareas cuyo padre no matchea, marcados con campo aditivo `is_context=true` (default `false`, `TaskRead` intacto para consumidores previos).
- **Frontend**: subtareas indentadas bajo su padre dentro de cada sección (30) — clave (`task_key`), estado, estimación y avatar (círculo de inicial, reutiliza `taskCardInitial`); padre atenuado cuando llega solo como contexto.
- **TDD**: filtro por asignado devuelve subtareas de padres ajenos; padre presente como contexto (no cuenta como match); scoping multi-tenant.

### Out of Scope
- Colapso/chevron por padre para plegar subtareas (mínimo: subtareas siempre visibles indentadas; el expandir/colapsar por búsqueda es del 33).
- Fila de avatares para filtrar por asignado en la UI (cambio 33) — aquí se blinda el **contrato backend** que esa fila consumirá.
- Drag & drop de subtareas (31) y `estimation_display` enriquecido (34): aquí suma/estimación tal cual.
- Sub-subtareas: la anidación sigue en un solo nivel (`subtask_nesting_not_allowed`, sin cambios).
- Agregados de sección del 30 (conteo de historias / horas): permanecen intactos; el contexto no infla conteos.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `tasks`: el listado `GET /projects/{id}/tasks` expone subtareas en modo jerárquico; el filtro `assignee_id` deja de excluir subtareas y añade padres de contexto (`is_context`); `TaskRead` gana el campo aditivo `is_context`.

## Approach

**Composición de jerarquía en cliente (preferida sobre orden jerárquico en backend).** El repo ya compone hijos por `parent_task_id` (`loadEpicChildren`) y el 30 agrupa `allTasks()` por `sprint_id` en cliente; se mantiene ese patrón. El backend NO serializa un árbol: solo **suministra** las subtareas en el mismo listado (flag `include_subtasks` que levanta `top_level_only`) en el orden ya existente (`order asc, created_at asc`), y el cliente indenta agrupando por `parent_task_id`. Evita N+1 por padre y desacopla la vista de la serialización. **Padres de contexto resueltos en backend (preferido sobre cliente).** Bajo filtro por asignado, un padre ajeno puede estar filtrado fuera (o en otra página): el cliente no puede resolverlo con fiabilidad. Por eso el backend, cuando hay `assignee_id`, hace una segunda pasada que trae los padres de las subtareas matcheadas cuyo padre no matchea, con `is_context=true`; si el padre ya matchea el filtro, se devuelve normal (`is_context=false`) sin duplicar. `is_context` es aditivo (default `false`), espeja el patrón de campos aditivos del 30.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/tasks/{repository,service,router,schemas}.py` | Modified | Modo `include_subtasks`; padres de contexto con `assignee_id`; `is_context` aditivo |
| `backend/tests/**` | New | Subtarea de padre ajeno aparece; padre como contexto; sin doble conteo; scoping |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modified | Indentación de subtareas en secciones (30); padre atenuado como contexto |
| `frontend/src/entities/workspace/{workspace.model,workspace.service}.ts` | Modified | `is_context`, `include_subtasks`; agrupación por `parent_task_id` |
| `frontend/src/assets/i18n/es-CO.json` | Modified | Textos (tuteo) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Padres de contexto descuadran el total de paginación | Media | Contexto suplementario, NO cuenta en el `total` de matches; se define en design + test de conteo |
| Padre aparece dos veces (match real + contexto) | Media | Dedup: si el padre matchea el filtro, `is_context=false` y no se reinyecta como contexto |
| N+1 al traer subtareas por padre | Baja | Un solo listado con `include_subtasks`; el cliente agrupa por `parent_task_id` (sin fetch por padre) |
| Romper el listado plano por defecto | Baja | `include_subtasks` opt-in; `top_level_only` sigue por defecto; `is_context` aditivo default `false` |
| Regla limitada al filtro por asignado (no otros filtros) | Baja | Se documenta la frontera; patrón extensible a estado/etiqueta después |

## Rollback Plan

Solo código, sin migración ni datos tocados: revertir el commit restaura el listado plano top-level y el filtro por asignado previo. `is_context` es aditivo y lo ignoran los consumidores actuales; ningún cliente escribe con estos campos.

## Dependencies

- `depends_on: [30-backlog-sprints-agrupados]` — la indentación vive DENTRO de las secciones de sprint/backlog del 30. Ordena su apply tras cerrar el 30. Comparte seam con 31 (orden/DnD por `task.order`) y 33 (fila de avatares que consumirá este contrato de filtro por asignado).

## Success Criteria

- [ ] Las subtareas se muestran indentadas bajo su padre dentro de las secciones (30) con clave, estado, estimación y avatar (inicial).
- [ ] `GET /projects/{id}/tasks?assignee_id=X` devuelve subtareas asignadas a X aunque el padre sea de otro usuario.
- [ ] El padre ajeno vuelve como contexto (`is_context=true`), atenuado, sin contarse como match real ni duplicarse.
- [ ] El listado por defecto sigue plano top-level (sin regresión); `is_context` aditivo default `false`.
- [ ] Suite backend en verde (TDD del filtro por asignado, contexto y scoping multi-tenant).

## Proposal question round

Supuestos a validar: (1) el colapso/chevron por padre queda **fuera del 32** — las subtareas se muestran siempre indentadas y el expandir/colapsar por búsqueda lo asume el 33; (2) el padre atenuado de contexto es **no interactivo** salvo abrir su detalle en lectura; (3) la regla innegociable aplica ahora al **filtro por asignado**, con el patrón "nada se oculta por jerarquía" extensible a otros filtros (estado, etiqueta) en un cambio posterior; (4) el padre que llega solo como **contexto NO cuenta** en los agregados de sección del 30 ni como match real; (5) las subtareas **no inflan** el conteo de historias del 30 (que cuenta historias top-level). Se puede correr una segunda ronda si prefieres incluir el colapso por padre en el 32 o extender la regla de contexto a todos los filtros desde ya.
