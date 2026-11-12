# Delta for intake-classifier

## ADDED Requirements

### Requirement: Bootstrap operativo satisface el proyecto por defecto sin crear "Tareas Outlook"

Cuando `IntakeSettings.default_project_id` ya apunta a un `Project` existente ANTES de que el clasificador lo necesite por primera vez (por ejemplo, porque el bootstrap de la jerarquía SDMUJER de la capability `data-maintenance` lo dejó apuntando a SEGURIDAD), el sistema NO DEBE crear el proyecto perezoso "Tareas Outlook" ni ningún otro proyecto por defecto: DEBE reutilizar directamente el proyecto ya configurado.

#### Scenario: default_project_id preconfigurado evita la creación perezosa
- DADO que el bootstrap de la jerarquía dejó `IntakeSettings.default_project_id` apuntando a SEGURIDAD
- CUANDO se clasifica el primer ítem que requiere el proyecto por defecto
- ENTONCES la tarea se crea en SEGURIDAD y NO se crea ningún proyecto "Tareas Outlook"

#### Scenario: Sin bootstrap previo, el comportamiento perezoso original sigue vigente
- DADO una organización recién creada, sin bootstrap y sin `default_project_id`
- CUANDO se clasifica el primer ítem que requiere el proyecto por defecto
- ENTONCES el sistema SIGUE creando "Tareas Outlook" perezosamente, sin cambios respecto al comportamiento previo
