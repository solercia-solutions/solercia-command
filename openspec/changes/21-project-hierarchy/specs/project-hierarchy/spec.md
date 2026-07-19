# project-hierarchy Specification

## Purpose

Jerarquía padre-hijo entre proyectos de una misma organización, con validación de ciclos/profundidad, consulta de árbol y avance consolidado (roll-up) del subárbol. Cada subproyecto conserva su propia metodología (Strategy pattern intacto); esta capability solo agrega la relación estructural y su agregación, sin tocar el comportamiento por metodología de cada proyecto individual.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| PATCH | /api/v1/projects/{id}/parent | Reparenta el proyecto (o lo desvincula con `parent_project_id: null`) |
| GET | /api/v1/projects/{id}/tree | Árbol jerárquico del proyecto y sus descendientes activos |
| GET | /api/v1/projects/{id}/progress | Avance consolidado (roll-up) del proyecto y su subárbol |

Sin modelo propio: reutiliza `Project.parent_project_id` (self-FK, ver delta de `projects`). Todas las consultas se acotan por `organization_id` de la membresía activa del usuario y excluyen proyectos con soft delete (`is_active=false`).

## Requirements

### Requirement: Relación padre-hijo y restricciones estructurales

Un `Project` PUEDE declarar un `parent_project_id` apuntando a otro `Project`. Toda asignación (en creación o reparentado) DEBE cumplir: el padre y el hijo pertenecen a la MISMA `organization_id`, y el padre está activo (`is_active=true`). Cualquier asignación que viole una de estas condiciones DEBE rechazarse con un error de validación específico para la causa.

#### Scenario: Asignación válida de padre en la misma organización

- DADO un proyecto "Seguridad de la Información" activo en la organización A
- CUANDO se asigna como padre de un nuevo proyecto "Desarrollo" de la misma organización A
- ENTONCES la asignación se acepta

#### Scenario: Padre de otra organización rechazado

- DADO un proyecto activo que pertenece a la organización B
- CUANDO un usuario de la organización A intenta asignarlo como `parent_project_id`
- ENTONCES la operación se rechaza con un error de validación (tenant cruzado)

#### Scenario: Padre inactivo rechazado

- DADO un proyecto con soft delete activo (`is_active=false`) en la organización del usuario
- CUANDO se intenta asignarlo como `parent_project_id`
- ENTONCES la operación se rechaza con un error de validación (padre inactivo)

### Requirement: Prevención de ciclos

El sistema DEBE rechazar cualquier asignación de `parent_project_id` que convierta al proyecto en su propio ancestro, de forma directa o transitiva. Un proyecto NUNCA PUEDE ser descendiente de sí mismo.

#### Scenario: Auto-padre directo rechazado

- DADO un proyecto existente P
- CUANDO se intenta asignar `parent_project_id = P.id` (a sí mismo)
- ENTONCES la operación se rechaza con un error de validación (ciclo)

#### Scenario: Ciclo transitivo rechazado

- DADO A es padre de B, y B es padre de C
- CUANDO se intenta reparentar A para que su padre sea C
- ENTONCES la operación se rechaza (A quedaría como ancestro y descendiente de sí mismo a la vez)

### Requirement: Profundidad máxima configurable

La jerarquía DEBE respetar un límite máximo de profundidad, configurable (mecanismo de configuración a definir en diseño), con valor por defecto de **5 niveles**. La profundidad de un proyecto es el número de proyectos en la cadena desde la raíz (sin padre) hasta él mismo, inclusive (una raíz tiene profundidad 1). Toda creación o reparentado que produzca una profundidad mayor al límite vigente DEBE rechazarse con un error de validación.

#### Scenario: Profundidad dentro del límite aceptada

- DADO una cadena de proyectos que alcanza profundidad 5 (el límite por defecto)
- CUANDO se crea ese quinto proyecto con el cuarto como padre
- ENTONCES la creación se acepta

#### Scenario: Profundidad excedida rechazada

- DADO una cadena de proyectos que ya alcanza profundidad 5 (el límite por defecto)
- CUANDO se intenta crear un sexto proyecto encadenado como hijo del quinto
- ENTONCES la creación se rechaza con un error de validación (profundidad excedida)

### Requirement: Reparentado de un proyecto existente

`PATCH /api/v1/projects/{id}/parent` DEBE permitir cambiar el `parent_project_id` de un proyecto existente, incluida su desvinculación (`parent_project_id: null`, el proyecto pasa a ser raíz). El reparentado DEBE aplicar las mismas validaciones que la creación: mismo tenant, padre activo, sin ciclos y dentro de la profundidad máxima vigente.

#### Scenario: Reparentado válido a un nuevo padre

- DADO un proyecto raíz "Desarrollo" y un proyecto activo "Seguridad de la Información" en la misma organización
- CUANDO se hace `PATCH /projects/{desarrollo_id}/parent` con `parent_project_id` apuntando a "Seguridad de la Información"
- ENTONCES "Desarrollo" queda como hijo de "Seguridad de la Información"

#### Scenario: Reparentado a null desvincula el proyecto

- DADO un proyecto hijo con padre asignado
- CUANDO se hace `PATCH /projects/{id}/parent` con `parent_project_id: null`
- ENTONCES el proyecto queda como raíz, sin padre

#### Scenario: Reparentado que crea un ciclo es rechazado

- DADO A es padre de B
- CUANDO se hace `PATCH /projects/{a_id}/parent` con `parent_project_id = B.id`
- ENTONCES la operación se rechaza (ciclo) y la jerarquía existente no cambia

### Requirement: Árbol jerárquico

`GET /api/v1/projects/{id}/tree` DEBE devolver el proyecto solicitado junto con TODOS sus descendientes activos, anidados según `parent_project_id`, sin cruzar la frontera de `organization_id` del usuario autenticado.

#### Scenario: Árbol de tres niveles reproduce la jerarquía

- DADO "Seguridad de la Información" con hijo "Desarrollo", y "Desarrollo" con hijo "Backend"
- CUANDO se consulta `GET /projects/{seguridad_id}/tree`
- ENTONCES la respuesta anida "Desarrollo" bajo "Seguridad de la Información" y "Backend" bajo "Desarrollo"

#### Scenario: Aislamiento de tenant en el árbol

- DADO un proyecto que pertenece a la organización B
- CUANDO un usuario de la organización A consulta `GET /projects/{id_de_B}/tree`
- ENTONCES la API responde 404 (no existe / sin acceso), igual que el resto de endpoints de detalle de `projects`

### Requirement: Avance consolidado por conteo de tareas (roll-up)

`GET /api/v1/projects/{id}/progress` DEBE calcular, para el proyecto solicitado y cada nodo de su subárbol, el avance por CONTEO de tareas: `done` son las tareas cuyo estado es el último estado permitido (`allowed_statuses()[-1]`) de la strategy de metodología de SU PROPIO proyecto, sobre `total` (todas las tareas del proyecto, EXCLUYENDO las de estado `cancelled`). La inclusión de tareas (incluidas subtareas, sin distinguir `parent_task_id`) sigue el mismo criterio que ya usa el cálculo de avance por proyecto existente del dashboard (`_build_projects_progress`: toda tarea cuyo `project_id` es el del nodo cuenta). El valor consolidado del proyecto raíz solicitado DEBE sumar `done` y `total` de él mismo más todos los proyectos activos de su subárbol.

#### Scenario: Roll-up reproduce el ejemplo de negocio

- DADO "Desarrollo" con 8 de 10 tareas done y "Seguridad" con 10 de 10 tareas done, ambos hijos de la sombrilla "Seguridad de la Información" (sin tareas propias)
- CUANDO se consulta `GET /projects/{sombrilla_id}/progress`
- ENTONCES el nodo consolidado de la sombrilla reporta `done=18`, `total=20`

#### Scenario: Tareas cancelled excluidas del denominador

- DADO un proyecto con 10 tareas totales, de las cuales 2 están en estado `cancelled` y 5 están done
- CUANDO se consulta su avance
- ENTONCES `total=8` (10 menos las 2 cancelled) y `done=5`

#### Scenario: Metodologías mixtas en el subárbol

- DADO un padre scrum con un hijo kanban, cada uno con tareas propias
- CUANDO se consulta el avance consolidado del padre
- ENTONCES el `done` de cada nodo se calcula contra el último estado permitido de SU PROPIA strategy antes de sumarse al total consolidado

#### Scenario: Aislamiento de tenant en el roll-up

- DADO un subárbol con proyectos de la organización A y un proyecto sin relación de la organización B
- CUANDO un usuario de A consulta el avance consolidado de su sombrilla
- ENTONCES el resultado no incluye tareas ni proyectos de B

### Requirement: Permisos sobre la jerarquía

`GET .../tree` y `GET .../progress` DEBEN estar disponibles para cualquier miembro autenticado de la organización (`admin`, `manager`, `member`, `viewer`), sin restricción adicional por rol, igual que el resto de lecturas de `projects`. `PATCH .../parent` DEBE exigir rol `admin` o `manager` en la organización del proyecto.

#### Scenario: Miembro member consulta árbol y avance sin restricción

- DADO un usuario con rol `member`
- CUANDO consulta `GET /projects/{id}/tree` o `GET /projects/{id}/progress`
- ENTONCES la API responde 200 con los datos de su organización

#### Scenario: Miembro member no puede reparentar

- DADO un usuario con rol `member`
- CUANDO intenta `PATCH /projects/{id}/parent`
- ENTONCES la petición se rechaza por autorización

#### Scenario: Manager reparenta exitosamente

- DADO un usuario con rol `manager`
- CUANDO ejecuta `PATCH /projects/{id}/parent` con datos válidos
- ENTONCES la operación se aplica

### Requirement: Invariante de borrado suave de un padre con hijos activos

Este cambio NO agrega un endpoint de borrado de proyectos (fuera de alcance del proposal). Aun así, el sistema DEBE preservar el invariante de que ningún `Project` con al menos un hijo activo (`is_active=true`) puede quedar marcado con soft delete. Cualquier mecanismo, presente o futuro, que aplique soft delete a un `Project` DEBE rechazar la operación mientras existan hijos activos, en vez de aplicar cascada automática.

#### Scenario: Soft delete de un padre con hijo activo rechazado

- DADO un proyecto padre con un hijo activo
- CUANDO se intenta marcar el padre con soft delete
- ENTONCES la operación se rechaza con un error de validación

#### Scenario: Soft delete de un padre sin hijos activos permitido

- DADO un proyecto padre cuyos hijos ya están todos con soft delete (o sin hijos)
- CUANDO se intenta marcar el padre con soft delete
- ENTONCES la operación se permite

### Requirement: Contrato de envelope y errores

`PATCH .../parent` DEBE responder con el envelope de acción `{data, message}`. `GET .../tree` y `GET .../progress` DEBEN responder con el envelope de recurso único `{data}`. Todo rechazo de validación de jerarquía (ciclo, profundidad excedida, tenant cruzado, padre inactivo) DEBE responder con el formato de error estándar `{detail, code, status}`, con un `code` específico y distinto por causa de rechazo.

#### Scenario: PATCH exitoso responde con el envelope de acción

- DADO un reparentado válido
- CUANDO se ejecuta `PATCH /projects/{id}/parent`
- ENTONCES la respuesta incluye `data` (proyecto actualizado) y `message`

#### Scenario: Error de validación responde con código distinguible

- DADO un intento de reparentado que produce un ciclo y otro que excede la profundidad máxima
- CUANDO cada uno se ejecuta por separado
- ENTONCES cada respuesta de error trae un `code` distinto que identifica la causa del rechazo

## Limitaciones y deuda conocida

- El estado `cancelled` de `Task` aún NO está implementado en el resto del sistema (deuda trazada en 04-labels-checklists-dependencias, ver `tasks/spec.md`). La exclusión de R6 es válida pero hoy no tiene efecto observable porque ninguna tarea puede tener `status="cancelled"`; aplicará automáticamente en cuanto ese estado exista.
- La metodología `custom` sin `BoardColumn` configuradas tiene `allowed_statuses()` vacío; en ese caso `done=0` para ese nodo (ningún estado coincide con "último permitido"), pero sigue sumando a `total`.
- La vista de árbol visual en frontend (cambio 24) y las plantillas organizacionales (cambio 23) NO forman parte de este alcance.
- El dashboard ejecutivo (`dashboard-executive`) NO se modifica en este cambio; la integración de `progress` con `/dashboard/executive` queda como seguimiento futuro.

## Referencias

- backend/app/modules/projects/ (models.py, repository.py, service.py, router.py, schemas.py)
- backend/app/modules/dashboard/service.py (`_build_projects_progress`, `_StatusBounds` — semántica de referencia para "done")
- backend/app/methodology/ (strategies consumidas por nodo del subárbol)
