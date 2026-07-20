# Delta for org-role-templates

## ADDED Requirements

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

## MODIFIED Requirements

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

## Referencias

- `openspec/specs/org-role-templates/spec.md` (línea base)
- `openspec/specs/projects/spec.md` (delta hermano de este cambio: campo y filtro `project_kind`)
- `openspec/changes/27-plantillas-idempotentes/proposal.md`
