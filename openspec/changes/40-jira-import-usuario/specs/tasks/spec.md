# Delta for tasks

> Base: `openspec/specs/tasks/spec.md`. El ancla de procedencia externa
> (`source` + `external_key`) en `Task` ya NO la agrega este delta: la
> entrega `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md`
> (requisito «Ancla de procedencia externa (source + external_key)», D8). Este
> delta la **consume** y agrega solo la reconciliación idempotente por
> procedencia externa que ejecuta el importador Jira al reimportar; no
> modifica ningún requisito existente de clave legible, estados o filtros.

## ADDED Requirements

### Requirement: Reconciliación idempotente por procedencia externa

Al recibir una tarea con el mismo (`source`, `external_key`) que una ya existente dentro de la misma organización, el sistema DEBE actualizar sus campos base (título, estado mapeado, estimación, sprint) en la fila ya anclada en lugar de crear una nueva. Un conflicto ambiguo (mismo ancla con datos incompatibles entre sí) DEBE rechazarse con un mensaje claro en lugar de sobrescribir silenciosamente.

#### Scenario: Reimportar actualiza en vez de duplicar
- Dado una tarea ya anclada a `source="jira"`, `external_key="PROJ-123"` con título "Versión antigua"
- Cuando se reimporta el mismo issue con título "Versión antigua (editado)"
- Entonces la tarea existente actualiza su título y no se crea una segunda tarea

## Referencias

- `openspec/specs/tasks/spec.md` (línea base)
- `openspec/specs/intake-items/spec.md` (precedente de idempotencia)
- `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` (origen del ancla de procedencia externa y de «Clave local y externa conviven», que este delta presupone)
- `openspec/changes/40-jira-import-usuario/specs/jira-import/spec.md` (consumidor del ancla)
