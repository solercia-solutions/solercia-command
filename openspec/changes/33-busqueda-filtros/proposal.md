# Proposal: 33 · Búsqueda y filtros compartidos en backlog y cronograma (Gantt)

## Intent

El backlog agrupado (30) y el cronograma Gantt (`sprint-gantt.component.ts`) consumen el mismo `Task[]` del workspace (`allTasks()`), pero no ofrecen forma de encontrar ni acotar tareas: no hay búsqueda por clave (`SDM-7`) ni texto, ni filtros por asignado, épica, tipo o fechas. Con sprints colapsables (30) y subtareas indentadas (32), ubicar una tarea concreta o ver "solo lo de una persona" es tedioso. Este cambio (OLA 4, fase 4.2) añade una barra de filtros **compartida** entre backlog y Gantt: búsqueda con expansión+resaltado de secciones colapsadas, fila de avatares multi-selección, y filtros por épica/tipo/rango de fechas combinables (AND).

## Scope

### In Scope
- **Feature compartida `filter-tasks`** (frontend): fuente única de estado de filtros + predicado/anotación consumida por el backlog (30) y el Gantt.
- **Búsqueda** por `task_key` y texto parcial (título): resalta coincidencias y **auto-expande** secciones colapsadas con match (no oculta el resto).
- **Fila de avatares** para filtrar por asignado, multi-selección con overflow "+N".
- **Filtros** por épica (vía `parent_task_id`→épica), tipo de tarea y rango de fechas; combinación **AND** entre todos.
- **Regla del 32** en el filtro por asignado: la subtarea asignada SIEMPRE aparece; el padre ajeno se muestra atenuado como contexto (resuelto en cliente sobre el set completo cargado).
- Chip/acción **Limpiar filtros**; estado vacío ("sin coincidencias").

### Out of Scope
- JQL / lenguaje de consulta (visión futura).
- Etiquetas en filtros (fuera de alcance de la OLA).
- Filtrado server-side / paginación del listado (frontera documentada).
- Drag & drop (31), estimación normalizada (34).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None — cambio de composición frontend; sin delta de API ni de spec backend. La regla autoritativa "nada se oculta por jerarquía" ya quedó blindada con TDD en el 32.

## Approach

**Filtrado client-side sobre `allTasks()` ya cargado (preferido sobre server-side para el MVP).** El workspace ya carga el set completo del proyecto (y el 32 suma las subtareas), así que todo padre está en memoria: los filtros se aplican al instante sin refetch y la regla de contexto del 32 se replica en cliente con fiabilidad. La búsqueda exige comportamiento de árbol (mantener estructura, expandir secciones con match, resaltar) que es intrínsecamente de cliente. La feature `filter-tasks` expone un signal de estado + un predicado/anotación reutilizado por backlog y Gantt (misma barra, mismos resultados). Cero delta de API → sin migración, sin TDD backend, rollback = revertir commit. **Frontera**: si el volumen por proyecto supera una carga sin paginar, se promueve a server-side (el endpoint ya soporta `assignee_id`/`task_type`/rango/`q`; el 32 expone el contrato de contexto; faltaría `assignee_id` repetible + filtro por épica). Alternativa a confirmar en design: filtro por asignado server-side reusando el contrato del 32.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `frontend/src/features/filter-tasks/**` | New | Estado de filtros + predicado/anotación compartidos |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modified | Barra de filtros; auto-expandir/resaltar secciones; contexto por asignado |
| `frontend/src/widgets/sprint-gantt/sprint-gantt.component.ts` | Modified | Consume el mismo predicado de filtros |
| `frontend/src/assets/i18n/es-CO.json` | Modified | Textos (tuteo) |
| `backend/**` | None | Sin delta de API para el MVP |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Set cargado sin paginar limita la escala | Media | Frontera documentada; migración server-side viable (endpoint + contrato 32) |
| Replicar la regla del 32 en cliente diverge del backend | Media | El 32 mantiene la regla autoritativa con TDD; el cliente la espeja sobre el set completo; design confirma server vs client |
| Búsqueda que oculta contexto en vez de resaltar | Baja | Contrato: buscar resalta + expande, no elimina los no-match |
| "Filtrar por épica" sin `epic_id` | Baja | Se resuelve por `parent_task_id`→épica en memoria (subtarea→historia→épica) |

## Rollback Plan

Solo frontend, sin migración ni API: revertir el commit restaura el backlog (30) y el Gantt sin barra de filtros. Ningún dato se toca.

## Dependencies

- `depends_on: [30-backlog-sprints-agrupados, 32-jerarquia-subtareas]` — la barra vive sobre las secciones colapsables del 30 y consume las subtareas/contexto del 32. Ordena su apply tras cerrar ambos.

## Success Criteria

- [ ] Barra de filtros única y compartida entre backlog y Gantt.
- [ ] La búsqueda por clave/texto resalta y auto-expande las secciones colapsadas con match.
- [ ] Los avatares multi-selección con overflow "+N" filtran por asignado.
- [ ] Los filtros por épica, tipo y rango de fechas combinan en AND; chip Limpiar operativo.
- [ ] El filtro por asignado respeta la regla del 32 (subtarea visible; padre atenuado como contexto).
- [ ] Sin delta de API (o server-side confirmado en design); sin regresión en 30/32.

## Proposal question round

Supuestos a validar: (1) el filtrado es **client-side** sobre `allTasks()` ya cargado para el MVP; (2) la regla del 32 (contexto por asignado) se **replica en cliente** sobre el set completo, en lugar de llamar al endpoint server-side del 32 (alternativa a confirmar en design); (3) la **búsqueda resalta y expande** sin ocultar el resto (sin narrowing duro); (4) el filtro por **épica** se deriva de `parent_task_id`→épica (no hay `epic_id`); (5) **etiquetas y JQL** quedan fuera. Segunda ronda si prefieres el filtro por asignado server-side (reusando el 32) desde ya, o narrowing duro en la búsqueda.
