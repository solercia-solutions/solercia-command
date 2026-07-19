# Delta for projects

## ADDED Requirements

### Requirement: Creación de proyecto con padre opcional

`POST /api/v1/projects` DEBE aceptar un campo opcional `parent_project_id` (UUID de otro `Project`). Cuando se envía, la creación DEBE aplicar las validaciones de jerarquía definidas en `project-hierarchy` (mismo tenant, padre activo, sin ciclos, dentro de la profundidad máxima vigente) antes de persistir; si alguna falla, la creación completa DEBE rechazarse y ningún proyecto queda persistido. Cuando se omite, el proyecto se crea como raíz (`parent_project_id = null`), sin cambio respecto al contrato actual.

#### Scenario: Creación con padre válido

- DADO un usuario con membresía activa y un proyecto existente "Seguridad de la Información" en su organización
- CUANDO envía `POST /projects` con `parent_project_id` apuntando a ese proyecto
- ENTONCES el proyecto nuevo queda creado (201) con `parent_project_id` poblado

#### Scenario: Creación sin padre mantiene el comportamiento actual

- DADO un usuario con membresía activa
- CUANDO envía `POST /projects` sin `parent_project_id`
- ENTONCES el proyecto se crea (201) con `parent_project_id = null`, igual que hoy

#### Scenario: Creación con padre inválido rechaza todo el proyecto

- DADO un usuario con membresía activa y un `parent_project_id` que pertenece a otra organización
- CUANDO envía `POST /projects` con ese `parent_project_id`
- ENTONCES la API rechaza la creación completa con un error de validación y ningún proyecto queda persistido

### Requirement: Exposición de parent_project_id en las respuestas

El detalle y la lista de proyectos (`GET /projects`, `GET /projects/{id}`) DEBEN exponer `parent_project_id` (`null` cuando el proyecto es raíz).

#### Scenario: Lista expone la jerarquía

- DADO un proyecto hijo con padre asignado
- CUANDO se consulta `GET /projects`
- ENTONCES el elemento correspondiente incluye `parent_project_id` con el id del padre

#### Scenario: Detalle de un proyecto raíz expone null

- DADO un proyecto sin padre asignado
- CUANDO se consulta `GET /projects/{id}`
- ENTONCES la respuesta incluye `parent_project_id: null`
