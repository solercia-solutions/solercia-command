# org-role-templates Specification

## Propósito

Plantillas organizacionales de alto cargo: perfiles predefinidos, sembrados como datos (no en código), que al instanciarse generan de una sola vez el árbol de proyectos (sombrilla + equipos) de un área usando la jerarquía y el roll-up de `project-hierarchy` (cambio 21), dejando a una persona como responsable (`lead_user_id`) en cada proyecto generado. La instanciación es idempotente por reconciliación.

## Alcance

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/org-role-templates | Lista de plantillas disponibles |
| GET | /api/v1/org-role-templates/{id} | Detalle con árbol completo de nodos |
| POST | /api/v1/org-role-templates/{id}/instantiate | Instancia (o reconcilia) el árbol con `{ lead_user_id }` |

## Catálogo de plantillas de sistema (seed: `organization_id=NULL`, `is_system=true`)

| Plantilla | Sombrilla | Ramas intermedias | Equipos |
|-----------|-----------|--------------------|---------|
| Jefe OAP‑TI | OAP‑TI | Planeación, Tecnología | Planeación: MIPG, PIGA, Políticas, planes y proyectos, Planeación presupuestal. Tecnología: Infraestructura tecnológica, Desarrollo de software, Gobierno digital, Seguridad de la información |
| Jefe de Planeación | Planeación | — | MIPG, PIGA, Políticas, planes y proyectos, Planeación presupuestal |
| Jefe de Tecnología | Tecnología | — | Infraestructura tecnológica, Desarrollo de software, Gobierno digital, Seguridad de la información |
| Gerente de Gestión Corporativa | Gestión Corporativa | — | Tesorería, Subdirección administrativa y financiera, Mantenimiento |
| Equipo de desarrollo | Desarrollo | — | (ninguno; solo sombrilla) |

## Requirements

### Requirement: Catálogo de plantillas de sistema sembradas

El sistema DEBE tener sembradas exactamente las 5 plantillas de sistema del catálogo anterior, cada una con `organization_id = NULL` e `is_system = true`, visibles y consultables por cualquier organización.

#### Scenario: Listado de plantillas disponibles
- DADO un usuario autenticado con membresía activa
- CUANDO consulta `GET /org-role-templates`
- ENTONCES recibe las 5 plantillas de sistema

#### Scenario: Detalle expone el árbol completo
- DADO la plantilla "Jefe OAP‑TI"
- CUANDO consulta `GET /org-role-templates/{id}`
- ENTONCES la respuesta incluye la sombrilla "OAP‑TI", sus ramas "Planeación" y "Tecnología", y los 4 equipos bajo cada rama

### Requirement: Instanciación genera el árbol de proyectos con responsable

`POST /org-role-templates/{id}/instantiate` con `{ lead_user_id }` DEBE crear, en la organización del solicitante, un `Project` por cada nodo de la plantilla, encadenando `parent_project_id` según la estructura del árbol y respetando `PROJECT_HIERARCHY_MAX_DEPTH`, con `methodology = "planner"` y `lead_user_id` igual a la persona indicada en TODOS los proyectos generados (sombrilla, ramas intermedias y equipos).

#### Scenario: Instanciación de plantilla plana
- DADO un `admin` de la organización A y un miembro activo "María"
- CUANDO ejecuta `POST /org-role-templates/{jefe_planeacion_id}/instantiate` con `lead_user_id = María`
- ENTONCES se crean 5 proyectos ("Planeación" raíz + 4 equipos hijos), todos con `lead_user_id = María` y `methodology = planner`

#### Scenario: Instanciación de Jefe OAP‑TI produce 3 niveles
- DADO un `admin` y un miembro activo "Carlos"
- CUANDO instancia "Jefe OAP‑TI" con `lead_user_id = Carlos`
- ENTONCES se crean 11 proyectos: sombrilla "OAP‑TI" (raíz), ramas "Planeación" y "Tecnología" (hijas de la sombrilla) y los 8 equipos (hijos de su rama correspondiente), todos con `lead_user_id = Carlos`

### Requirement: Idempotencia por reconciliación

Reinstanciar la misma plantilla para el mismo `lead_user_id` en la misma organización (clave `(organization_id, template_id, lead_user_id)`) DEBE reconciliar: crear ÚNICAMENTE los nodos aún faltantes (por nombre bajo el padre esperado) y NUNCA duplicar un proyecto ya generado por esa clave. La operación completa DEBE ejecutarse en una sola transacción.

#### Scenario: Reinstanciación sin cambios es no-op
- DADO un árbol ya instanciado completo para `(organización A, plantilla, María)`
- CUANDO se reinstancia con el mismo `lead_user_id`
- ENTONCES no se crea ningún proyecto nuevo

#### Scenario: Reinstanciación reconcilia el nodo faltante
- DADO un árbol instanciado donde el equipo "PIGA" fue eliminado (soft delete) después de la primera instanciación
- CUANDO se reinstancia la misma plantilla y `lead_user_id`
- ENTONCES se crea únicamente "PIGA", encadenado al padre correcto, sin duplicar el resto del árbol

#### Scenario: Fallo a mitad de instanciación no deja proyectos parciales
- DADO una instanciación que falla al crear el cuarto de cinco proyectos
- CUANDO ocurre el error
- ENTONCES ningún proyecto de esa instanciación queda persistido

### Requirement: Validaciones de instanciación

`lead_user_id` DEBE referir a un miembro activo de la organización del solicitante; en caso contrario la instanciación DEBE rechazarse con un error de validación. `POST .../instantiate` DEBE exigir rol `admin` o `manager` en la organización del solicitante.

#### Scenario: lead_user_id que no es miembro se rechaza
- DADO un `admin` de la organización A y un `user_id` sin membresía activa en A
- CUANDO instancia una plantilla con ese `lead_user_id`
- ENTONCES la operación se rechaza con un error de validación y ningún proyecto se crea

#### Scenario: Rol member no puede instanciar
- DADO un usuario con rol `member`
- CUANDO intenta `POST /org-role-templates/{id}/instantiate`
- ENTONCES la petición se rechaza por autorización

#### Scenario: Rol manager instancia exitosamente
- DADO un usuario con rol `manager` y un `lead_user_id` válido
- CUANDO ejecuta la instanciación
- ENTONCES el árbol de proyectos se crea correctamente

### Requirement: Aislamiento multi-tenant

Las plantillas de sistema DEBEN ser de solo lectura y visibles para cualquier organización; la instanciación DEBE escribir SIEMPRE los proyectos generados en la organización del solicitante, nunca en otra.

#### Scenario: La instanciación nunca escribe en otra organización
- DADO un `admin` de la organización A
- CUANDO instancia una plantilla de sistema
- ENTONCES todos los proyectos generados quedan con `organization_id = A`

#### Scenario: Árboles generados no se filtran entre organizaciones
- DADO que la organización A y la organización B instanciaron la misma plantilla "Equipo de desarrollo"
- CUANDO un miembro de A lista sus proyectos
- ENTONCES no ve los proyectos generados por B

## Referencias

- `openspec/changes/21-project-hierarchy/specs/project-hierarchy/spec.md` (parent_project_id, ciclos, profundidad, roll-up)
- `openspec/changes/23-org-role-templates/proposal.md`
