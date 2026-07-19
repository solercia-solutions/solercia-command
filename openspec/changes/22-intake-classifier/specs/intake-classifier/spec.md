# intake-classifier Specification

> **Origen**: cambio [22-intake-classifier](../../proposal.md)

## Propósito

Motor determinístico que convierte los `IntakeItem` pendientes en `Task` sobre el árbol de proyectos del 21, aplicando la primera `IntakeRule` activa que casa. Gestiona el proyecto por defecto de la organización, la cola de triage para ítems sin regla y la reclasificación manual, preservando trazabilidad hacia el ítem de origen y la regla que generó cada tarea. Implementado detrás de `ClassifierPort` (Strategy) para permitir un clasificador LLM futuro sin reescribir el resto del flujo.

## Alcance propuesto

| Método | Ruta | Propósito | Rol requerido |
|--------|------|-----------|----------------|
| POST | /api/v1/intake/items/{id}/convert | Conversión manual de un ítem en triage a `Task` | cualquier miembro |
| GET | /api/v1/intake/settings | Consulta la configuración de intake de la organización (proyecto por defecto) | cualquier miembro |
| PATCH | /api/v1/intake/settings | Configura el nombre del proyecto por defecto | admin\|manager |

El motor de clasificación en sí NO expone un endpoint propio: se ejecuta automáticamente al final de cada `POST /intake/pull` (ver `intake-items`), sobre los ítems `pending` recién almacenados.

Modelo: `IntakeSettings` (Pk+Timestamp+Tenant, único por organización): `default_project_id FK?`, `default_project_name` (por defecto "Tareas Outlook").

## Requisitos

### Requirement: Ejecución del clasificador tras cada ingesta

Al finalizar el almacenamiento de los ítems nuevos de un `POST /intake/pull`, el sistema DEBE evaluar cada `IntakeItem` en `status=pending` de esa ejecución contra las `IntakeRule` activas de la organización, por orden de `rule_order`, a través de `ClassifierPort`.

#### Scenario: El pull dispara la clasificación automáticamente

- Dado un pull que almacena 3 ítems nuevos y existen reglas activas
- Cuando el pull termina de almacenar
- Entonces los 3 ítems se evalúan contra las reglas sin llamada adicional del usuario

### Requirement: Conversión a tarea cuando una regla casa

Cuando la primera regla activa que casa tiene `convert_to_task=true`, el sistema DEBE crear una `Task` en `target_project_id` (o el proyecto por defecto si es nulo) con `priority=task_priority` de la regla y `assignee_id` de la regla, y DEBE registrar en el `IntakeItem`: `status=converted`, `created_task_id`, `matched_rule_id`, `classified_at`.

#### Scenario: Correo con dominio conocido se convierte en tarea asignada

- Dado un `IntakeItem` de tipo `email` que casa con una regla de `target_project_id="Seguridad"`, `task_priority=high`, `assignee_id=U1`
- Cuando se clasifica
- Entonces se crea una `Task` en "Seguridad" con `priority=high`, `assignee_id=U1`, y el ítem queda `status=converted` con `matched_rule_id` y `created_task_id`

#### Scenario: Regla con convert_to_task=false no crea tarea

- Dado una regla que casa pero tiene `convert_to_task=false`
- Cuando se clasifica el ítem
- Entonces NO se crea ninguna `Task`; el ítem queda marcado `status=ignored`, sin pasar a la cola de triage

### Requirement: Asignado no elegible bloquea la conversión automática

Si la `IntakeRule` que casa con un `IntakeItem` declara un `assignee_id` que NO es miembro activo de la organización (o del proyecto destino, según la validación existente `_verify_assignee`/`is_org_member`), el sistema NO DEBE crear la `Task` automáticamente. El `IntakeItem` DEBE permanecer en `status=pending`, visible en la cola de triage, con el motivo del rechazo registrado y consultable por quien vaya a reclasificar manualmente. El sistema NUNCA DEBE mutar membresías (agregar al usuario asignado como miembro de la organización o del proyecto) para forzar la conversión.

#### Scenario: Regla asigna a un usuario que no es miembro de la organización

- Dado una `IntakeRule` activa que casa con un `IntakeItem` y declara `assignee_id=U9`, donde U9 no es miembro de la organización del ítem
- Cuando se clasifica el ítem
- Entonces NO se crea ninguna `Task`, el ítem permanece `status=pending` en la cola de triage, y el motivo "asignado no elegible" queda registrado

#### Scenario: La conversión rechazada no agrega al usuario como miembro

- Dado el mismo escenario anterior (asignado `U9` no elegible)
- Cuando se rechaza la conversión automática por asignado no elegible
- Entonces no se crea ninguna membresía nueva para `U9` en la organización ni en el proyecto destino

### Requirement: Ítems sin regla coincidente van a triage manual

Si ninguna `IntakeRule` activa casa con un `IntakeItem`, el sistema NO DEBE crear ninguna `Task` automáticamente. El ítem DEBE permanecer en `status=pending`, visible y filtrable en la cola de triage (`GET /intake/items?status=pending`).

#### Scenario: Ítem sin regla coincidente queda pendiente

- Dado un `IntakeItem` cuyos atributos no casan con ninguna regla activa
- Cuando se clasifica
- Entonces el ítem permanece `status=pending`, sin `Task` creada ni `matched_rule_id`

### Requirement: Proyecto por defecto de la organización

El sistema DEBE resolver el proyecto por defecto de forma perezosa: si `IntakeSettings.default_project_id` es nulo la primera vez que se necesita (una regla sin `target_project_id`, o una conversión manual), DEBE crear un `Project` con metodología `planner` y el nombre configurado en `default_project_name` (por defecto "Tareas Outlook"), guardarlo en `IntakeSettings.default_project_id`, y reutilizarlo en adelante. `PATCH /intake/settings` DEBE permitir configurar `default_project_name` antes o después de creado el proyecto.

#### Scenario: Primer uso crea el proyecto por defecto

- Dado una organización sin `IntakeSettings.default_project_id`
- Cuando se clasifica el primer ítem que requiere el proyecto por defecto
- Entonces se crea un `Project` `planner` llamado "Tareas Outlook" y queda registrado en `IntakeSettings`

#### Scenario: Usos posteriores reutilizan el mismo proyecto

- Dado una organización con `IntakeSettings.default_project_id` ya asignado
- Cuando se clasifica un segundo ítem que requiere el proyecto por defecto
- Entonces la tarea se crea en el mismo proyecto existente, sin crear uno nuevo

#### Scenario: Nombre configurado antes del primer uso

- Dado una organización que configuró `default_project_name="Bandeja de Entrada"` vía `PATCH /intake/settings` antes de cualquier conversión
- Cuando se crea el proyecto por defecto por primera vez
- Entonces el proyecto se llama "Bandeja de Entrada", no "Tareas Outlook"

### Requirement: Reclasificación manual desde triage

`POST /api/v1/intake/items/{id}/convert` DEBE permitir a cualquier miembro autenticado convertir manualmente un `IntakeItem` en `status=pending` a `Task` en el proyecto por defecto de la organización, con prioridad y asignado provistos en la petición. La conversión manual DEBE registrar `created_task_id` y DEBE dejar `matched_rule_id` nulo (para distinguir conversión por regla de conversión manual). Un ítem que ya está `converted` NO DEBE poder convertirse de nuevo.

#### Scenario: Usuario convierte manualmente un ítem en triage

- Dado un `IntakeItem` `status=pending` sin regla coincidente
- Cuando un usuario llama `POST /intake/items/{id}/convert` con `priority` y `assignee_id`
- Entonces se crea la `Task` en el proyecto por defecto, el ítem queda `status=converted`, `created_task_id` asignado, `matched_rule_id` nulo

#### Scenario: No se puede reconvertir un ítem ya convertido

- Dado un `IntakeItem` con `status=converted`
- Cuando se llama `POST /intake/items/{id}/convert` sobre él
- Entonces la API responde con un error de validación; no se crea una segunda `Task`

### Requirement: Trazabilidad estable ante cambios posteriores de la tarea

La `Task` creada por el clasificador (automática o manual) DEBE ser una `Task` normal, editable por los endpoints vigentes de `tasks` (mover de proyecto, reasignar, repriorizar, cambiar de estado). Mover o reasignar la tarea después de creada NO DEBE alterar ni romper el vínculo `IntakeItem.created_task_id` ni `IntakeItem.matched_rule_id`.

#### Scenario: Reasignar la tarea no rompe la trazabilidad

- Dado una `Task` creada por el clasificador con su `IntakeItem` de origen enlazado
- Cuando la tarea se reasigna a otro usuario vía el endpoint vigente de `tasks`
- Entonces `IntakeItem.created_task_id` sigue apuntando a la misma tarea, y `matched_rule_id` no cambia

### Requirement: Multi-tenant y RBAC de configuración

`IntakeSettings` DEBE ser único por organización y no visible entre organizaciones. `PATCH /intake/settings` DEBE restringirse a `admin`\|`manager`; `GET /intake/settings` y la conversión manual son accesibles a cualquier miembro autenticado de la organización.

#### Scenario: Member no puede configurar el nombre del proyecto por defecto

- Dado un usuario `member`
- Cuando llama `PATCH /intake/settings`
- Entonces la API responde `403`

## Referencias

- `openspec/changes/22-intake-classifier/specs/intake-items/spec.md`
- `openspec/changes/22-intake-classifier/specs/intake-rules/spec.md`
- `openspec/changes/21-project-hierarchy/specs/project-hierarchy/spec.md` (árbol de proyectos donde caen las tareas)
- `openspec/specs/tasks/spec.md` (`Task` normal, editable por los endpoints vigentes)
