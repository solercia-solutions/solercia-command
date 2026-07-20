# Proposal: 31 · Backlog drag & drop (arrastrar historias entre backlog y sprints)

## Intent

En la vista agrupada del cambio 30 (sprints como secciones colapsables + Backlog),
mover una historia entre backlog y un sprint hoy exige abrir el modal de la tarea y
cambiar `sprint_id` en un desplegable (`project-workspace.component.ts` → `updateTask({sprint_id})`,
líneas 1339/1354). No hay arrastre fluido. Este cambio (OLA 4, fase 4.2) habilita
**arrastrar historias/tareas backlog ↔ sprint y entre sprints no iniciados**, con la
zona de drop visible durante el arrastre, reutilizando los ids de sección estables
(`sprint-<uuid>` / `backlog`) que el cambio 30 dejó como seams.

## Scope

### In Scope
- **Drag & drop con Angular CDK** (`DragDropModule`): `@angular/cdk ^22` ya está instalado pero **no hay DnD en el proyecto** (el board mueve por botones de estado, no por arrastre). Se introduce CDK: cada sección es un `cdkDropList` conectado; las tarjetas, `cdkDrag`.
- **Reglas de destino** (interpretación fiel a OLA_4, ver más abajo): backlog ↔ cualquier sprint visible (draft y active); sprint ↔ sprint solo si **ambos** están sin iniciar (`draft`); nunca hacia/desde sprints `closed`.
- **Zona de drop visible**: resaltar destinos válidos y atenuar/deshabilitar inválidos durante el arrastre.
- **Actualización optimista con rollback** ante error de red/servidor.
- **Persistencia vía endpoint existente**: `PATCH /tasks/{id}` con `{ sprint_id, order }` (ya acepta ambos). Sin endpoint nuevo por defecto.
- **Accesibilidad**: menú contextual "Mover a…" por tarjeta como ruta de teclado equivalente (reutiliza el mismo PATCH); el drag por teclado de CDK como complemento.

### Out of Scope
- DnD de columnas del board kanban (permanece por botones + `PATCH /tasks/{id}/column`).
- Búsqueda/filtros (33), jerarquía de subtareas y su arrastre (32), `estimation_display` (34).
- Mover tareas entre proyectos.
- Avisos de cambio de scope al soltar en sprint iniciado (cambio 42).
- Enforcement server-side de las reglas de destino como requisito duro (se plantea como endurecimiento opcional).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None por defecto: reutiliza `PATCH /tasks/{id}` (`sprint_id` + `order`); las reglas de destino se aplican en la UI. **Decisión de diseño abierta**: si design adopta un guard de movimiento server-side o un endpoint de reordenamiento por lotes, `tasks` pasa a Modified y sdd-spec añade su delta (con TDD).

## Approach

**Interpretación de "backlog ↔ sprint y entre sprints no iniciados".** OLA_4 dice literal
"entre sprints no iniciados". Se interpreta: **backlog ↔ sprint** = soltar entre el
Backlog y cualquier sprint **visible en la vista de 30** (active + draft; los closed
están ocultos), como en Jira; **entre sprints** = solo si ambos son `draft`. Tradeoff:
permitir soltar backlog→active agrega historias a un sprint en curso (scope change) que
el cambio 42 avisará después; la alternativa estricta (solo draft como destino) es más
segura pero rompe el flujo Jira de "arrastrar al sprint activo". Se elige la primera y
se documenta la frontera con 42.

**Persistencia.** `PATCH /tasks/{id}` ya acepta `sprint_id` (`_verify_sprint`) y `order`
en la misma llamada → un solo write por drop. La estrategia de reindexado de `order`
(entero por ítem con normalización vs. un `reorder` por lotes) se decide en design; si
exige delta backend, ese delta lleva TDD (regla de movimiento + orden).

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `frontend/.../project-workspace/project-workspace.component.ts` | Modified | `cdkDropList` conectados por sección + `cdkDrag`; handler de drop; reglas de destino; optimista+rollback; menú "Mover a…" |
| `frontend/src/entities/workspace/workspace.service.ts` | Modified | Reutiliza/ajusta el PATCH de tarea con `{sprint_id, order}` |
| `frontend/src/assets/i18n/es-CO.json` | Modified | Textos (tuteo): "Mover a…", estados de arrastre, errores |
| `frontend/.../*.spec.ts` | New | Reglas de destino, optimista/rollback, agrupación |
| `backend/app/modules/tasks/**` | Modified (condicional) | Solo si design añade guard de movimiento o `reorder` por lotes (con TDD) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Reindexado de `order` entero colisiona con muchos movimientos | Media | Design elige normalización o `reorder` por lotes; MVP con listas pequeñas |
| Reglas de destino solo en UI → request crafteada mueve a sprint inválido | Baja | Riesgo igual al de hoy (el PATCH ya lo permite); endurecimiento server-side opcional flagueado |
| CDK nuevo en el proyecto (sin precedente) sube superficie | Baja | Primitiva de librería estándar y accesible; aislada a la vista de 30 |
| Soltar en sprint activo confunde (scope change silencioso) | Media | Feedback visual claro; aviso formal llega en 42 |

## Rollback Plan

Solo código (default sin migración): revertir el commit restaura la vista de 30 sin
arrastre; mover sprint/backlog sigue disponible por el modal de tarea. Si design añadió
un delta backend, su migración/endpoint es aditivo y reversible por commit.

## Dependencies

- `depends_on: [30-backlog-sprints-agrupados]` — requiere la vista de secciones y los
  ids estables `sprint-<uuid>` / `backlog` como origen/destino del DnD. El apply se
  ordena tras cerrar el ciclo de 30.

## Success Criteria

- [ ] Arrastrar una historia backlog → sprint (draft o active) la reubica y persiste.
- [ ] Arrastrar entre dos sprints `draft` funciona; hacia/desde `closed` está bloqueado.
- [ ] La zona de drop resalta destinos válidos y atenúa inválidos durante el arrastre.
- [ ] Fallo de servidor revierte la posición optimista (rollback).
- [ ] Ruta de teclado "Mover a…" equivalente disponible por tarjeta.
- [ ] Suite frontend en verde (reglas de destino + optimista/rollback); backend en verde si hubo delta.

## Proposal question round

Supuestos a validar con el usuario: (1) usar **Angular CDK** DnD (no hay DnD previo que
reutilizar; el board usa botones de estado); (2) reglas de destino: **backlog ↔ sprints
visibles (draft y active)** y **sprint↔sprint solo entre draft**, nunca closed —
¿o se prefiere la variante estricta "solo draft como destino"?; (3) persistir con el
**`PATCH /tasks/{id}` existente** (`sprint_id`+`order`), decidiendo el reindexado de
`order` en design (¿aceptas un mínimo `reorder` por lotes si el entero colisiona?);
(4) reglas enforçadas **en UI** por defecto, con endurecimiento server-side como opción;
(5) fallback de teclado por **menú "Mover a…"**. Se puede correr una segunda ronda si
el usuario quiere el guard server-side desde ya o bloquear el drop en sprints activos.
