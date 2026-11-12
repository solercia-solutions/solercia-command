# Delta for projects

## ADDED Requirements

### Requirement: Columnas nullable de override de calendario laboral en Project

`Project` DEBE tener las columnas nullable `working_hours_per_day` (numérico, admite medias jornadas) y `working_days` (array de enteros ISO 1-7), agregadas mediante una migración aditiva y reversible. Solo el proyecto RAÍZ (`parent_project_id = null`) PUEDE tener valores no nulos en estas columnas; un proyecto con padre (no raíz) NUNCA DEBE persistir un valor propio en ellas — la edición y su validación viven en la capability `work-calendar`. El detalle y la lista de proyectos (`GET /projects`, `GET /projects/{id}`) DEBEN exponer ambos campos, `null` cuando el proyecto no tiene override (no-raíz, o raíz sin configurar).

#### Scenario: Proyecto raíz con override expone sus valores
- DADO un proyecto raíz con `working_hours_per_day=6` y `working_days=[6,7]`
- CUANDO se consulta `GET /projects/{id}`
- ENTONCES la respuesta incluye ambos campos con esos valores

#### Scenario: Proyecto hijo nunca expone override propio
- DADO un proyecto hijo (con `parent_project_id` no nulo)
- CUANDO se consulta `GET /projects/{id}` o `GET /projects`
- ENTONCES ambos campos aparecen como `null`, sin importar el calendario resuelto que herede

#### Scenario: Migración es aditiva y reversible
- DADO proyectos existentes antes de la migración
- CUANDO se ejecuta `upgrade`
- ENTONCES todos quedan con ambas columnas en `null`, sin perder datos
- Y CUANDO se ejecuta `downgrade`
- ENTONCES las columnas se eliminan sin afectar el resto del modelo

## Referencias

- `openspec/specs/projects/spec.md` (línea base)
- `openspec/changes/28-calendario-laboral/specs/work-calendar/spec.md` (validación, permisos, resolución en cascada y endpoints)
- `openspec/changes/27-plantillas-idempotentes/specs/projects/spec.md` (precedente de columna aditiva `project_kind`)
