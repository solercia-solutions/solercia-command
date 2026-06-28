# ADR 0006 — Workspace del frontend guiado por `methodology_info`

- **Estado:** Aceptado
- **Fecha:** 2026-06-27
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (secciones 6 y 10), `docs/API.md` (Proyectos,
  Tareas, Sprints), `docs/adr/0002-configurable-methodology-strategy.md`,
  `docs/adr/0005-work-items-status-as-column.md`

---

## Contexto

El workspace de un proyecto (tablero, backlog, sprints, formulario de tarea) debe
**comportarse distinto según la metodología**: scrum muestra sprints y backlog y estima en
puntos; kanban es flujo continuo sin sprints y estima en horas; planner es una lista simple
sin estimación; custom parte en blanco.

La tentación es replicar en el frontend la misma trampa que el ADR 0002 evitó en el backend:
condicionales por metodología regados por componentes.

```typescript
// Anti-patrón: el frontend decide por metodología con if/switch dispersos.
if (project.methodology === 'scrum') {
  showSprintsTab = true;
  columns = ['To Do', 'In Progress', 'In Review', 'Done'];
  estimationField = 'points';
} else if (project.methodology === 'kanban') {
  showSprintsTab = false;
  columns = ['Backlog', 'Doing', 'Done'];
  estimationField = 'hours';
} // ... y este switch se repite en pestañas, columnas y formulario
```

Ese enfoque acopla la UI a los nombres de las metodologías, repite el mismo `switch` en
varios componentes y obliga a tocar el frontend cada vez que se agrega o ajusta una
metodología en el backend.

## Decisión

El frontend **no ramifica por metodología**. Cada respuesta de proyecto incluye
`methodology_info` —que el backend deriva de la Strategy— y la UI se **construye a partir de
ese objeto**:

```json
{
  "methodology": "scrum",
  "default_columns": ["To Do", "In Progress", "In Review", "Done"],
  "allowed_statuses": ["To Do", "In Progress", "In Review", "Done"],
  "sprints_enabled": true,
  "estimation_mode": "points",
  "has_backlog": true
}
```

Reglas de derivación:

1. **Pestañas:** «Tablero» siempre; «Backlog» solo si `has_backlog`; «Sprints» solo si
   `sprints_enabled`.
2. **Columnas del tablero:** una columna por cada valor de `allowed_statuses`, en orden. Cada
   tarjeta vive en la columna igual a su `status`.
3. **Campos de estimación** del formulario de tarea, según `estimation_mode`:
   `none` → ninguno; `points` → `estimation_points`; `hours` → `estimation_hours`;
   `both` → ambos.
4. **Asignación:** el selector de persona se alimenta de `GET /projects/{id}/members`.

```typescript
// The workspace derives its shape from methodology_info — no per-methodology switch.
const tabs = [
  { id: 'board', label: 'Tablero' },
  info.has_backlog ? { id: 'backlog', label: 'Backlog' } : null,
  info.sprints_enabled ? { id: 'sprints', label: 'Sprints' } : null,
].filter(Boolean);

const columns = info.allowed_statuses; // one board column per status, in order

const estimationFields = {
  none: [],
  points: ['estimation_points'],
  hours: ['estimation_hours'],
  both: ['estimation_points', 'estimation_hours'],
}[info.estimation_mode];
```

### Drag-and-drop con Angular CDK

El tablero usa `@angular/cdk/drag-drop`. Al soltar una tarjeta en otra columna, el componente
contenedor emite `PATCH /tasks/{id}` con el `status` (rótulo) de la columna destino y
persiste la posición con `order`. **No** se mantiene un estado de tablero local que haya que
sincronizar: la columna **es** el estado de la tarea (ver ADR 0005).

```typescript
onTaskDropped(event: CdkDragDrop<Task[]>, targetStatus: string): void {
  const task = event.item.data as Task;
  // The destination column label IS the new task status.
  this.tasksApi.patch(task.id, { status: targetStatus, order: event.currentIndex })
    .subscribe();
}
```

### Patrón container / presentational

Se conserva la convención del frontend (ADR 0004, sección 6 de la arquitectura): las
`pages/*` (smart) orquestan los datos y las llamadas a la API; los componentes de tablero,
columna y tarjeta son **presentacionales** y reciben todo por `@Input` / `@Output`. Antes de
crear un componente nuevo se verifica si ya existe en `shared/ui`.

## Consecuencias

### Positivas

- **Abierto/cerrado de punta a punta:** una metodología nueva se define en su Strategy del
  backend y el workspace la soporta **sin cambios**, porque solo lee `methodology_info`.
- **Sin lógica de metodología duplicada** entre frontend y backend: la fuente de verdad es la
  Strategy; el frontend la consume serializada.
- **UI coherente con el contrato:** el tablero, las pestañas y la estimación no pueden
  «desalinearse» de la metodología, porque se derivan del mismo objeto que valida el backend.
- **Drag-and-drop simple:** mover una tarjeta es un `PATCH` de `status`; no hay estado de
  columnas que reconciliar.

### Negativas / costos

- **Dependencia del contrato `methodology_info`:** si el backend cambia la forma de ese
  objeto, el frontend debe acompañarlo. Se mitiga documentándolo en `docs/API.md` y tratándolo
  como contrato estable.
- **Metodología `custom`:** al llegar con `allowed_statuses` vacío, el tablero no tiene
  columnas. El frontend debe mostrar un estado vacío claro («Este proyecto aún no tiene
  columnas definidas») hasta que la parametrización de `custom` exista; ese flujo de edición
  queda fuera del alcance de esta fase.
- **Render dinámico:** construir pestañas y columnas a partir de datos exige cuidado de
  accesibilidad y de claves estables en las listas (`@for` con `track`), frente a una
  plantilla estática.

## Alternativas descartadas

- **Condicionales por metodología en el frontend (`switch` por componente):** rechazada por
  duplicar la lógica que ya vive en la Strategy y por acoplar la UI a los nombres de las
  metodologías (ver Contexto).
- **Un componente de workspace por metodología (`ScrumBoard`, `KanbanBoard`, …):** rechazada
  por multiplicar código casi idéntico y obligar a crear un componente nuevo por cada
  metodología, justo lo contrario del objetivo abierto/cerrado.
- **Mantener un estado de columnas en el cliente y sincronizarlo con el backend:** rechazada
  por innecesaria; al ser el `status` la columna, el `PATCH` de la tarea es la única
  escritura requerida.
