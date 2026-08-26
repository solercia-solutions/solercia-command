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

Reinstanciar la misma plantilla en la misma organización (clave `(organization_id, template_id, node_id)`, SIN `lead_user_id`) DEBE reconciliar: crear ÚNICAMENTE los nodos aún faltantes (por nombre bajo el padre esperado), reutilizar cada nodo ya generado sin importar el `lead_user_id` con el que se reinstancie, y NUNCA duplicar un proyecto ya generado por esa clave. Si el `lead_user_id` de la reinstanciación difiere del responsable actual del nodo, el sistema DEBE actualizar `Project.lead_user_id` y la fila del ledger al nuevo responsable en TODOS los proyectos reutilizados del árbol, en vez de crear un árbol paralelo. Un conflicto irreconciliable — cuando el historial del ledger es incompatible con el árbol que se va a reconciliar — DEBE rechazarse con un mensaje de error claro y un código específico (`template_tree_conflict`, HTTP 409), sin modificar el árbol existente ni el ledger. El caso concreto cubierto por esta versión: un nodo CONTENEDOR (`area`, con al menos un hijo en el árbol de la plantilla) cuyo proyecto del ledger ya no existe o fue soft-eliminado, mientras al menos uno de sus hijos activos sigue referenciándolo como padre — recrear el contenedor le daría un id nuevo, dejando a esos hijos activos apuntando a un proyecto muerto. Un nodo HOJA soft-eliminado NO es un conflicto: se recrea normalmente (ver escenario de reconciliación del nodo faltante). Otras variantes del conflicto (ej. un ledger apuntando a un proyecto de otra organización) quedan fuera del alcance de esta versión porque `ledger_for` ya filtra por `organization_id` a nivel de consulta y ese caso no es alcanzable hoy con el modelo de datos actual. La operación completa DEBE ejecutarse en una sola transacción.
(Previously: la clave de idempotencia incluía `lead_user_id`; reinstanciar con un responsable distinto no encontraba ledger y recreaba el árbol completo duplicado.)

#### Scenario: Reinstanciación con el mismo responsable es no-op
- DADO un árbol ya instanciado completo para `(organización A, plantilla, María)`
- CUANDO se reinstancia con el mismo `lead_user_id`
- ENTONCES no se crea ningún proyecto nuevo y el árbol sigue siendo el mismo

#### Scenario: Reinstanciación con OTRO responsable reconcilia el lead, no duplica
- DADO un árbol ya instanciado completo para `(organización A, plantilla, María)`
- CUANDO se reinstancia la misma plantilla con `lead_user_id = Carlos`
- ENTONCES sigue existiendo un único árbol, `Project.lead_user_id = Carlos` en todos sus nodos, y la fila del ledger de cada nodo queda con `lead_user_id = Carlos`

#### Scenario: Reinstanciación reconcilia el nodo faltante con el lead vigente
- DADO un árbol instanciado donde el equipo "PIGA" fue eliminado (soft delete) después de la primera instanciación
- CUANDO se reinstancia la misma plantilla con cualquier `lead_user_id`
- ENTONCES se crea únicamente "PIGA" con ese `lead_user_id`, encadenado al padre correcto, sin duplicar el resto del árbol

#### Scenario: Conflicto irreconciliable se rechaza sin modificar el árbol
- DADO un árbol instanciado donde el nodo contenedor raíz (ej. "Planeación") fue soft-eliminado mientras sus equipos hijos permanecen activos
- CUANDO se intenta reinstanciar esa plantilla con cualquier `lead_user_id`
- ENTONCES la operación se rechaza con `409 template_tree_conflict`, sin crear proyectos nuevos, sin reconciliar ningún lead y sin modificar una sola fila del ledger existente

#### Scenario: Fallo a mitad de instanciación no deja proyectos parciales
- DADO una instanciación que falla al crear el cuarto de cinco proyectos
- CUANDO ocurre el error
- ENTONCES ningún proyecto de esa instanciación queda persistido

### Requirement: Migración reversible del constraint de idempotencia por nodo

La migración que introduce `UNIQUE(organization_id, template_id, node_id)` DEBE, en la MISMA migración: (1) deduplicar las filas existentes del ledger que compartan `(organization_id, template_id, node_id)` con distinto `lead_user_id`, conservando una sola fila por nodo antes de crear el índice único; (2) ser reversible, restaurando en el `downgrade` el `UNIQUE(...,lead_user_id)` anterior sin perder ninguna fila del ledger.

#### Scenario: Migración aplica sobre datos con duplicados existentes
- DADO filas del ledger con el mismo `(organization_id, template_id, node_id)` y distinto `lead_user_id` (duplicados OAP‑TI)
- CUANDO se ejecuta la migración `upgrade`
- ENTONCES el ledger queda con una sola fila por `(organization_id, template_id, node_id)` y el nuevo `UNIQUE` se crea sin error

#### Scenario: Migración es reversible
- DADO el nuevo constraint aplicado
- CUANDO se ejecuta `downgrade`
- ENTONCES se restaura `UNIQUE(organization_id, template_id, node_id, lead_user_id)` sin perder ninguna fila del ledger

### Requirement: Asignación de project_kind por el generador

Al generar el árbol de una plantilla, el sistema DEBE asignar `Project.project_kind = area` a todo nodo con al menos un hijo en la plantilla, y `Project.project_kind = proyecto` a todo nodo hoja (sin hijos), incluida una plantilla de un solo nodo.

#### Scenario: Nodo con hijos queda como area
- DADO la plantilla "Jefe OAP‑TI" (sombrilla con 2 ramas y 8 equipos)
- CUANDO se instancia
- ENTONCES la sombrilla "OAP‑TI" y sus 2 ramas quedan con `project_kind = area`

#### Scenario: Nodo hoja queda como proyecto
- DADO la misma instanciación
- CUANDO se revisan los 8 equipos generados
- ENTONCES cada equipo (nodo hoja) queda con `project_kind = proyecto`

#### Scenario: Plantilla de un solo nodo queda como proyecto
- DADO la plantilla "Equipo de desarrollo" (solo sombrilla, sin hijos)
- CUANDO se instancia
- ENTONCES el proyecto generado queda con `project_kind = proyecto`

### Requirement: Limpieza de duplicados OAP‑TI existentes

El sistema DEBE incluir una migración de datos o comando idempotente que detecte árboles duplicados generados por la misma plantilla y organización (mismo `template_id` + `organization_id`, nombres de nodo iguales, `code` distinto), conserve el árbol más antiguo con tareas asociadas, reasigne las tareas de los duplicados al superviviente, deje los duplicados en soft-delete y reconcilie el ledger para que apunte al superviviente.

#### Scenario: Limpieza reasigna tareas y conserva el árbol con historial
- DADO dos árboles OAP‑TI duplicados en la misma organización, uno con tareas activas y otro sin tareas
- CUANDO se ejecuta la limpieza
- ENTONCES el árbol con tareas sobrevive activo, las tareas del duplicado quedan reasignadas a él, y el duplicado queda soft-deleted

#### Scenario: Ejecutar la limpieza dos veces es un no-op
- DADO que la limpieza ya se ejecutó una vez sobre una organización
- CUANDO se ejecuta de nuevo
- ENTONCES no se reasigna ninguna tarea adicional ni cambia el estado de ningún proyecto

#### Scenario: Empate sin criterio determinista se reporta, no se adivina
- DADO dos árboles duplicados con la misma antigüedad y el mismo número de tareas
- CUANDO se ejecuta la limpieza
- ENTONCES el caso queda registrado para resolución manual y NINGÚN árbol se soft-elimina automáticamente

### Requirement: No regresión de contratos de idempotencia

Los contratos de prueba del cambio 23 que verificaban duplicación por `lead_user_id` distinto DEBEN actualizarse a la nueva clave `(organization_id, template_id, node_id)`; la suite backend completa DEBE permanecer en verde tras el cambio.

#### Scenario: Suite completa en verde tras el cambio
- DADO los contratos actualizados de idempotencia, reconciliación, project_kind y limpieza de duplicados
- CUANDO se ejecuta la suite completa del backend
- ENTONCES todos los tests pasan, incluidos los preexistentes de `org-role-templates`

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

### Requirement: La purga de datos demo preserva el catálogo de plantillas de sistema

La operación de mantenimiento que purga datos demo (capability `data-maintenance`) DEBE borrar el árbol de proyectos instanciado por una plantilla de sistema (sombrilla, ramas y equipos generados) y sus filas de `org_role_template_instantiations` correspondientes cuando ese árbol pertenece al alcance demo, pero NUNCA DEBE borrar una fila de `org_role_templates` ni de `org_role_template_nodes` (catálogo de sistema, `organization_id IS NULL`, `is_system=true`). Tras la purga, `ensure_system_templates` sigue re-sembrando el catálogo en cada arranque sin duplicarlo.

#### Scenario: La purga borra el árbol instanciado y el ledger, no el catálogo
- DADO un árbol OAP-TI instanciado en la organización demo, con sus 12 filas en `org_role_template_instantiations`
- CUANDO se ejecuta la purga con `--execute`
- ENTONCES los proyectos de ese árbol y sus filas de `org_role_template_instantiations` quedan en 0, y las 5 `org_role_templates` de sistema permanecen intactas

#### Scenario: El catálogo sigue disponible tras la purga
- DADO que la purga terminó y el backend reinicia (`ensure_system_templates` corre de nuevo)
- CUANDO se consulta `GET /org-role-templates`
- ENTONCES se siguen recibiendo las 5 plantillas de sistema, sin duplicados

## Referencias

- `openspec/specs/project-hierarchy/spec.md` (parent_project_id, ciclos, profundidad, roll-up)
- `openspec/changes/23-org-role-templates/proposal.md`
