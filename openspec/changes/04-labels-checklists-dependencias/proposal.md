# Proposal: Labels, checklists y dependencias tarea-tarea

## Intent

Las tareas hoy solo tienen clave legible, subtareas, estimación y riesgo. Faltan tres piezas previstas en CLAUDE.md que los usuarios de Planner/Jira esperan: **etiquetas** para clasificar y filtrar, **checklists** para desglosar el "cómo" sin crear subtareas formales, y **dependencias tarea-tarea** para modelar bloqueos. Además, el motor de alertas no detecta tareas bloqueadas por demasiado tiempo (estrategia `blocked_task` pendiente). Cerrar esta brecha completa el modelo de tarea del MVP y alimenta la vista ejecutiva de riesgos.

## Scope

### In Scope (backend únicamente)
- **Labels**: `Label` (scope de proyecto: name, color) + `TaskLabel` (M:N) + CRUD de etiquetas + filtro de tareas por etiqueta.
- **Checklists**: `TaskChecklist` (1:N por tarea) + `ChecklistItem` (1:N: is_done, order) + endpoints CRUD + progreso agregado en el detalle de tarea (como el de subtareas).
- **Dependencias**: relación M:N tarea↔tarea con tipos `blocks` / `is_blocked_by`, prevención de ciclos, endpoints link/unlink/list y estado "bloqueada" expuesto en el detalle.
- **Alerta**: estrategia `blocked_task` (bloqueada más de X días vía `threshold_params`) registrada en el registry + `AlertRule` seed por defecto.

### Out of Scope
- Cualquier cambio en `frontend/` (congelado — constraint frontend-frozen).
- Etiquetas a nivel organización/globales; automatización de estado por dependencia (transición automática de "bloqueada").
- Canales email/WebSocket de la nueva alerta (solo in-app, como el resto).

## Capabilities

### New Capabilities
- `labels`: etiquetas por proyecto y su vínculo M:N con tareas más el filtro.
- `checklists`: checklists e ítems por tarea con rollup de progreso.
- `task-dependencies`: enlaces tarea↔tarea con tipos, prevención de ciclos y exposición de bloqueo.

### Modified Capabilities
- `tasks`: el detalle DEBE reportar progreso de checklists y estado de bloqueo; la lista DEBE soportar filtro por etiqueta.
- `alert-engine`: DEBE registrar la estrategia `blocked_task` y sembrar su regla por defecto.

## Approach

Módulos nuevos siguiendo router → service → repository con mixins existentes (Pk, Timestamp, SoftDelete, Tenant vía join a Project). La dependencia tarea-tarea vive en un módulo/tabla propios (`task_links` / `task_dependencies`) para NO colisionar con el módulo `dependencies` existente (áreas organizacionales). Ciclos: se valida en el service con recorrido del grafo antes de crear el enlace. La alerta reutiliza el `AlertStrategy` ABC + registry; el seed añade la 5.ª regla.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/labels/` (nuevo) | New | Label + TaskLabel + CRUD + filtro |
| `backend/app/modules/checklists/` (nuevo) | New | TaskChecklist + ChecklistItem |
| `backend/app/modules/task_links/` (nuevo) | New | TaskDependency (evita colisión con `dependencies/`) |
| `backend/app/modules/tasks/` | Modified | Detalle: progreso checklist + bloqueo; filtro por label |
| `backend/app/alerts/strategies/` + `db_init.py` | Modified | Estrategia y regla seed `blocked_task` |
| `backend/alembic/` | Modified | Migración de las tablas nuevas |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Colisión de nombres con el módulo `dependencies` (áreas) | High | Módulo/tabla distintos (`task_links`/`task_dependencies`); clase `TaskDependency`, nunca `Dependency` |
| Ciclos en el grafo de dependencias | Med | Validación de ciclos en el service antes de persistir; test rojo del ciclo primero |
| Regla seed duplicada al re-sembrar | Med | Seed idempotente por `rule_type` (patrón de las 4 existentes) |

## Rollback Plan

Todo es aditivo. Rollback = `alembic downgrade` de la migración (drop de tablas nuevas), quitar el registro de la estrategia `blocked_task` del registry y la regla seed. Sin cambios destructivos sobre datos existentes.

## Dependencies

- `depends_on: 02-contrato-api` — hereda el contrato de paginación (filtro/listas de labels) y auditoría created_by/updated_by. Conceptualmente independiente de 03-boards.

## Success Criteria

- [ ] CRUD de labels y filtro de tareas por etiqueta operativo, con tests TDD.
- [ ] Checklists con progreso agregado visible en `GET /tasks/{id}`.
- [ ] Dependencias link/unlink/list con prevención de ciclos verificada por test.
- [ ] Estrategia `blocked_task` registrada, regla seed creada y evaluación produce notificación in-app deduplicada.
- [ ] Cero impacto en el módulo `dependencies` (áreas) existente.
