# Delta for tasks

> Base: `openspec/specs/tasks/spec.md`. Este delta AGREGA el ancla de
> procedencia externa que permite reimportar desde sistemas externos (Jira,
> cambio 40) sin duplicar; no modifica ningún requisito existente de clave
> legible, estados o filtros.

## ADDED Requirements

### Requirement: Ancla de procedencia externa (source + external_key)

`Task` DEBE tener las columnas nulables `source` (identifica el sistema de origen, ej. `jira`) y `external_key` (clave original en ese sistema, ej. la clave Jira del issue). Cuando ambas columnas tienen valor, el par (`source`, `external_key`) DEBE ser único dentro de la organización a la que pertenece la tarea (vía su proyecto). Una tarea creada manualmente (sin origen externo) DEBE conservar ambas columnas nulas, sin restricción de unicidad. El patrón aplica de forma análoga a `Sprint` y `Project` (mismo par `source`/`external_key`), detallado a nivel de diseño.

#### Scenario: Tarea importada conserva su procedencia
- Dado un issue Jira con clave `PROJ-123` importado a la organización
- Cuando se crea la tarea local
- Entonces queda con `source="jira"` y `external_key="PROJ-123"`

#### Scenario: Tarea manual sin ancla
- Dado una tarea creada manualmente en la plataforma, sin origen externo
- Cuando se consulta su procedencia
- Entonces `source` y `external_key` quedan nulos, sin conflicto de unicidad con ninguna otra tarea

### Requirement: Reconciliación idempotente por procedencia externa

Al recibir una tarea con el mismo (`source`, `external_key`) que una ya existente dentro de la misma organización, el sistema DEBE actualizar sus campos base (título, estado mapeado, estimación, sprint) en la fila ya anclada en lugar de crear una nueva. Un conflicto ambiguo (mismo ancla con datos incompatibles entre sí) DEBE rechazarse con un mensaje claro en lugar de sobrescribir silenciosamente.

#### Scenario: Reimportar actualiza en vez de duplicar
- Dado una tarea ya anclada a `source="jira"`, `external_key="PROJ-123"` con título "Versión antigua"
- Cuando se reimporta el mismo issue con título "Versión antigua (editado)"
- Entonces la tarea existente actualiza su título y no se crea una segunda tarea

### Requirement: Clave local y clave externa conviven como referencias distintas

El `task_key` local (código de proyecto + `task_number`) sigue siendo el identificador legible de la plataforma; `external_key` DEBE exponerse como referencia adicional visible en el detalle de la tarea, sin reemplazar ni alterar el cálculo del `task_key` local.

#### Scenario: Tarea importada muestra ambas claves
- Dado una tarea importada con `task_key="SDM-42"` y `external_key="PROJ-123"`
- Cuando se consulta el detalle de la tarea
- Entonces se muestran ambas claves, cada una identificando su propio sistema

## Referencias

- `openspec/specs/tasks/spec.md` (línea base)
- `openspec/specs/intake-items/spec.md` (precedente de ancla de procedencia + idempotencia)
- `openspec/changes/40-jira-import-usuario/specs/jira-import/spec.md` (consumidor del ancla)
