# Delta for projects

## ADDED Requirements

### Requirement: Responsable (lead_user_id) del proyecto

`Project` DEBE soportar un campo opcional `lead_user_id` (referencia a `User`, `ON DELETE SET NULL`) que identifica al responsable/cabeza del proyecto. La instanciación de plantillas organizacionales (`org-role-templates`) DEBE poblarlo en TODOS los proyectos que genera. Los proyectos creados sin plantilla (flujo actual de `POST /projects`) mantienen `lead_user_id = null`.

#### Scenario: Proyecto generado por plantilla expone lead_user_id
- DADO un proyecto creado por la instanciación de una plantilla organizacional
- CUANDO se consulta `GET /projects/{id}`
- ENTONCES la respuesta incluye `lead_user_id` con el id de la persona responsable

#### Scenario: Proyecto creado sin plantilla mantiene compatibilidad
- DADO un usuario que crea un proyecto vía `POST /projects` sin pasar por una plantilla
- CUANDO se consulta el proyecto creado
- ENTONCES `lead_user_id` es `null`, sin romper el contrato actual

#### Scenario: Lista de proyectos expone lead_user_id por elemento
- DADO proyectos generados por instanciación de plantilla
- CUANDO se consulta `GET /projects`
- ENTONCES cada elemento incluye su `lead_user_id` correspondiente
