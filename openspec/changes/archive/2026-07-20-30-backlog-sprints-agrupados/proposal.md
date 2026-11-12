# Proposal: 30 · Backlog con sprints agrupados (secciones colapsables estilo Jira)

## Intent

Hoy el workspace separa dos vistas: **Backlog** (lista plana de tareas sin sprint, `project-workspace.component.ts` → `backlogTasks()`) y **Sprints** (pestaña aparte con formulario + tarjetas). No existe la vista tipo Jira donde los sprints aparecen como secciones colapsables encima del backlog, cada una con sus agregados y su acción contextual. Este cambio (OLA 4, fase 4.2) reorganiza la pestaña Backlog: sprints como secciones colapsables arriba (nombre, fechas, conteo de historias, suma de estimaciones, acción según estado) y, debajo, la sección Backlog con las tareas sin sprint.

## Scope

### In Scope
- **Backend**: enriquecer la lectura de sprints con agregados por sprint (conteo de historias/tareas + suma de horas estimadas) calculados en servidor, más agregados del Backlog (tareas sin sprint). Reutiliza el precedente `func.count`/`func.sum` del repositorio.
- **Frontend**: pestaña Backlog reorganizada — secciones de sprint colapsables arriba + sección Backlog abajo. Cabecera: nombre, fechas, badge de estado (reutiliza 29), conteo, suma de horas y acción contextual (Iniciar para `draft`/`planned` con fechas vía `/start` de 29; Completar para `active` vía `/close` existente).
- Estado de colapso **persistido en cliente** (localStorage por proyecto + sección).
- Estados vacíos claros: sin sprints (solo Backlog), backlog vacío, sprint sin historias.
- **Ids estables por sección** (`sprint.id` + `'backlog'`) como seam para el drag & drop del cambio 31.

### Out of Scope
- Drag & drop backlog↔sprint (cambio 31) — solo se dejan los seams (ids, zonas de drop futuras).
- `estimation_display` enriquecido (cambio 34): aquí, suma simple en horas.
- Búsqueda y filtros en backlog (cambio 33).
- Crear/editar sprint (permanece en la pestaña Sprints / 29); aquí solo lectura + acciones existentes.
- Unicidad de nombres y controles de metodología (42).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `sprints`: la lectura de sprints expone agregados por sprint (`story_count`, `estimation_hours_sum`) y agregados del backlog, para alimentar la vista agrupada sin componer N llamadas.

## Approach

**Agregados en backend (preferido sobre cliente).** El front ya carga todas las tareas y podría agrupar en memoria, pero esos conteos dependerían del subconjunto cargado/filtrado (el listado de tareas admite filtros/paginación y el cambio 33 añade búsqueda). Calcularlos en servidor da una única fuente de verdad, independiente del filtro de UI. Se agregan campos **aditivos** a un item de lista de sprints (o `?with=aggregates`), sin tocar el payload de `burndown`/`close` (`SprintRead` intacto). El **cuerpo** de cada sección reutiliza las tareas ya cargadas (`allTasks()` agrupadas por `sprint_id`), sin llamadas extra. Como `@solercia/ui` 0.3.0 no expone acordeón, la sección colapsable es composición local con signals (espeja el toggle de burndown), candidata a subir a la librería; badge y mapa estado→acción se centralizan reutilizando 29.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/sprints/{repository,service,schemas,router}.py` | Modified | Agregados por sprint + backlog en la lectura |
| `backend/tests/**` | New | Contrato de conteo/suma; backlog sin sprint |
| `frontend/.../project-workspace.component.ts` | Modified | Pestaña Backlog agrupada + secciones colapsables |
| `frontend/src/entities/workspace/{workspace.model,workspace.service}.ts` | Modified | Campos de agregados; tipos de sección |
| `frontend/src/assets/i18n/es-CO.json` | Modified | Textos (tuteo) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Doble fuente de conteo (backend vs `allTasks()`) diverge | Media | Cabecera = agregado backend; cuerpo = agrupación local, sin recomputar el conteo en cliente |
| Agregar campos a la lista rompe `burndown`/`close` | Baja | Item de lista propio; `SprintRead` no se toca |
| Suma de horas confusa sin formateo (llega en 34) | Baja | Suma simple en horas + frontera documentada |
| Colapso local desincronizado entre pestañas | Baja | Clave por proyecto+sección; default expandido |

## Rollback Plan

Solo código, sin migración ni datos tocados: revertir el commit restaura el Backlog plano y la pestaña Sprints previos. Los agregados son de solo lectura; ningún cliente depende de ellos para escribir.

## Dependencies

- `depends_on: [29-sprint-borrador]` — requiere el estado `draft`, `POST /sprints/{id}/start` y los seams de badge/acción contextual. El apply se ordena tras cerrar el ciclo de 29.

## Success Criteria

- [ ] La pestaña Backlog muestra los sprints como secciones colapsables arriba y el Backlog abajo.
- [ ] Cada cabecera muestra nombre, fechas, conteo de historias y suma de horas (agregados del servidor).
- [ ] La acción contextual coincide con el estado (Iniciar draft/planned con fechas; Completar active).
- [ ] Estado de colapso persiste por proyecto/sección entre recargas.
- [ ] Estados vacíos claros; ids de sección estables (seam 31).
- [ ] Suite backend en verde (TDD del contrato de agregados).

## Proposal question round

Supuestos a validar: (1) los agregados se calculan en **backend** como campos aditivos de un item de lista de sprints (no un endpoint nuevo dedicado), dejando `SprintRead`/`burndown`/`close` intactos; (2) el **cuerpo** de cada sección reutiliza `allTasks()` ya cargado en cliente (sin fetch extra), mientras la cabecera usa el conteo autoritativo del servidor; (3) el estado de colapso se persiste en **localStorage** por proyecto+sección (default: expandido); (4) la vista agrupada reemplaza el contenido de la pestaña **Backlog** existente (no crea una pestaña nueva); (5) la suma se muestra en **horas simples** ahora y el cambio 34 podrá enriquecer el display después. Se puede correr una segunda ronda si el usuario prefiere un endpoint `backlog-overview` dedicado o persistir el colapso en servidor.
