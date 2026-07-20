# methodology-migration Specification

## Purpose

Habilita a un proyecto existente cambiar su metodología (`planner` ↔ `kanban`
↔ `scrum` ↔ `custom`) mediante un asistente de dos pasos: previsualización
del mapeo de estados/columnas origen → destino, y ejecución transaccional
que remapea tareas, cierra sprints si aplica y actualiza
`Project.methodology`. Vive en `backend/app/modules/projects/`
(router/service nuevos), reutilizando `app/methodology/` (Strategy + factory)
y `BoardService` (`add_column`/`reassign_column_tasks`/`remove_column`) —
cero endpoints de board nuevos, cero migración Alembic.

## Alcance propuesto

| Método | Ruta | Propósito |
|---|---|---|
| GET | /api/v1/projects/{id}/methodology-migration/preview?target=\<methodology\> | Previsualiza estados/columnas origen con conteos, columnas destino requeridas, mapeo propuesto e impacto |
| POST | /api/v1/projects/{id}/methodology-migration | Ejecuta la migración con el mapeo confirmado, transaccional |

Toda operación se acota por `organization_id` de la membresía activa (mismo
patrón que el resto de `projects`) y exige rol `admin` o `manager` del
proyecto.

## Requirements

### Requirement: Previsualización del plan de migración

GET preview DEBE responder: (a) estados/columnas del board actual con el
conteo de tareas activas en cada uno; (b) columnas requeridas del destino
según `get_strategy(target).default_columns()` (para `custom`, las columnas
que el usuario defina en el paso 1); (c) un mapeo propuesto por defecto
(heurística por nombre/orden), editable; y (d) un resumen de impacto:
sprints activos que se cerrarían y estimaciones que dejarían de exhibirse
según `estimation_mode` del destino. DEBE responder 422 si `target` es igual
a la metodología actual del proyecto.

#### Scenario: Preview de scrum a planner

- DADO un proyecto scrum con tareas en `To Do`, `In Progress`, `In Review` y
  `Done`, y un sprint activo
- CUANDO se consulta el preview con `target=planner`
- ENTONCES la respuesta incluye los 4 estados origen con sus conteos, las 3
  columnas destino (`Sin iniciar`, `En curso`, `Completada`), un mapeo
  propuesto, y el impacto indica 1 sprint activo a cerrar

#### Scenario: Preview rechaza migrar a la misma metodología

- DADO un proyecto scrum
- CUANDO se consulta el preview con `target=scrum`
- ENTONCES la API responde 422

### Requirement: Ejecución transaccional del cambio de metodología

POST DEBE recibir el mapeo confirmado (estado/columna origen → estado/columna
destino) y ejecutar, en UNA sola transacción: crear las columnas destino,
reasignar cada tarea a su `status` + `board_column_id` destino según el
mapeo, recalcular `completed_at` (sellarlo si la tarea cae en la columna
"done" del destino — el último estado de `allowed_statuses()` —, limpiarlo si
no), eliminar las columnas origen y persistir `Project.methodology = target`.
Ante cualquier error, DEBE revertir íntegramente (board, tareas, sprints y
metodología quedan como antes de la solicitud).

#### Scenario: Migración exitosa de scrum a planner

- DADO un proyecto scrum con tareas repartidas en sus 4 estados y un mapeo
  exhaustivo confirmado hacia planner
- CUANDO se ejecuta `POST /methodology-migration`
- ENTONCES la API responde 200, `Project.methodology = "planner"`, y cada
  tarea tiene `status` dentro de `allowed_statuses()` de planner con su
  `board_column_id` correspondiente

#### Scenario: Migración exitosa de planner a scrum

- DADO un proyecto planner con tareas en sus 3 estados (sin
  `estimation_points`) y un mapeo exhaustivo confirmado hacia scrum
- CUANDO se ejecuta `POST /methodology-migration`
- ENTONCES la API responde 200, `Project.methodology = "scrum"`, cada tarea
  queda con `status` dentro de `allowed_statuses()` de scrum, y las tareas
  sin puntos siguen siendo válidas (la estimación es opcional)

#### Scenario: Rollback ante error durante la ejecución

- DADO una migración en curso donde falla la reconstrucción de una columna
  destino a mitad de transacción
- CUANDO la ejecución aborta
- ENTONCES ninguna tarea, columna, sprint ni `Project.methodology` queda
  modificado respecto al estado previo a la solicitud

### Requirement: Subtareas se remapean igual que cualquier tarea

Las subtareas (`Task.parent_task_id` no nulo) DEBEN remapearse con el mismo
mapeo estado/columna que cualquier tarea de nivel superior, según su PROPIO
estado actual; el sistema NO DEBE aplicar ninguna regla especial derivada del
estado de su tarea padre.

#### Scenario: Subtarea con estado distinto al de su padre se remapea por su propio estado

- DADO una tarea padre en `In Progress` con una subtarea en `Done`, y un
  mapeo confirmado hacia planner
- CUANDO se ejecuta la migración
- ENTONCES la subtarea queda con el estado destino correspondiente a `Done`
  según el mapeo, aun si difiere del que recibe su tarea padre

### Requirement: Validación de exhaustividad del mapeo

POST DEBE rechazar con 422 y el detalle del/los estado(s) faltante(s) cuando
algún estado o columna origen con al menos una tarea activa no tiene destino
asignado en el mapeo confirmado. Ningún estado origen sin tareas activas
exige mapeo.

#### Scenario: Mapeo incompleto se rechaza

- DADO un proyecto scrum con tareas en `In Review` y un mapeo confirmado que
  no asigna destino para `In Review`
- CUANDO se ejecuta `POST /methodology-migration`
- ENTONCES la API responde 422 con el detalle indicando que `In Review` no
  tiene destino asignado, y ninguna tarea se modifica

### Requirement: Invariante — ninguna tarea queda en estado inválido tras migrar

Al finalizar cualquier ejecución exitosa, TODA tarea del proyecto DEBE tener
`status ∈ allowed_statuses()` de la strategy destino. Esta invariante DEBE
verificarse dentro de la transacción antes de confirmar (commit); si alguna
tarea quedaría fuera de `allowed_statuses()`, la ejecución DEBE abortar y
revertir.

#### Scenario: Invariante se cumple tras cualquier migración exitosa

- DADO cualquier migración ejecutada exitosamente (cualquier par
  origen/destino)
- CUANDO se consulta el estado de cada tarea del proyecto después
- ENTONCES el `status` de cada una pertenece a `allowed_statuses()` de la
  strategy destino, sin excepción

### Requirement: Cierre y desvinculación de sprints activos al migrar a metodología sin sprints

Cuando el destino tiene `sprints_enabled = false`, la ejecución DEBE cerrar
todo sprint en estado `active` del proyecto (mismo efecto que el cierre
manual: acumula `completed_points`, sella `closed_at`) y DEBE desvincular
(`sprint_id = NULL`) las tareas que quedan incompletas de esos sprints,
dentro de la misma transacción. Los sprints ya cerrados y su historial NO se
modifican.

#### Scenario: Migrar de scrum a kanban cierra el sprint activo

- DADO un proyecto scrum con un sprint activo con tareas completadas e
  incompletas
- CUANDO se ejecuta la migración hacia kanban
- ENTONCES el sprint queda `closed` con `completed_points` sellado, las
  tareas incompletas de ese sprint quedan con `sprint_id = NULL`, y las
  tareas completadas conservan su `sprint_id` como historial

### Requirement: Preservación de estimaciones al salir de scrum

`estimation_points` y `estimation_hours` de cada tarea DEBEN conservarse sin
cambios durante la migración, sin importar si el destino los exhibe
(`estimation_mode` del destino). Si el usuario migra de vuelta a una
metodología que sí los exhibe, los valores previos DEBEN seguir disponibles.

#### Scenario: Puntos preservados al migrar de scrum a planner

- DADO una tarea con `estimation_points = 5`
- CUANDO se migra el proyecto de scrum a planner
- ENTONCES la tarea conserva `estimation_points = 5` en la base de datos,
  aunque planner no lo exhiba en la UI

### Requirement: Sin condicionales por metodología en el servicio

Toda decisión de mapeo, columnas requeridas, validación de estados y flags
(`sprints_enabled`, `estimation_mode`, `has_backlog`) DEBE resolverse
consultando la strategy origen (`resolve_board_strategy`) y la strategy
destino (`get_strategy(target)`); el servicio de migración NO DEBE contener
condicionales `if methodology == ...` para decidir su comportamiento.

#### Scenario: Nueva metodología no exige cambios en el servicio de migración

- DADO que se agrega una metodología nueva con su propia clase de strategy
- CUANDO se ejecuta una migración hacia o desde esa metodología
- ENTONCES el servicio de migración funciona sin ninguna modificación de
  código propia de esa metodología

### Requirement: Destino custom exige columnas definidas antes de mapear

Cuando `target = custom`, el paso 1 DEBE exigir que el usuario defina al
menos una columna antes de continuar al mapeo; DEBE rechazarse con 422 si se
intenta ejecutar con cero columnas destino definidas.

#### Scenario: Migrar a custom sin columnas se rechaza

- DADO un intento de migración con `target=custom` y cero columnas destino
  definidas en la solicitud
- CUANDO se ejecuta `POST /methodology-migration`
- ENTONCES la API responde 422 y el proyecto conserva su metodología
  original

### Requirement: Permisos y aislamiento organizacional

Ambos endpoints DEBEN exigir rol `admin` o `manager` de la organización del
proyecto (403 `forbidden` para `member`/`viewer`) y DEBEN acotarse por
`organization_id` de la membresía activa (404 para proyectos de otra
organización).

#### Scenario: Member no puede ejecutar la migración

- DADO un usuario `member` de la organización del proyecto
- CUANDO intenta `POST /methodology-migration`
- ENTONCES la API responde 403

#### Scenario: Proyecto de otra organización no es accesible

- DADO un proyecto que pertenece a otra organización
- CUANDO un admin de una organización distinta consulta su preview o ejecuta
  la migración
- ENTONCES la API responde 404

### Requirement: Asistente de dos pasos en la configuración del proyecto

La UI DEBE ofrecer, en la configuración del proyecto, un asistente de 2
pasos: (1) mapeo de estados/columnas con los valores propuestos por defecto,
editable por el usuario (y definición de columnas si el destino es
`custom`); (2) confirmación con el resumen de impacto (sprints a cerrar,
estimaciones que dejarán de exhibirse) antes de ejecutar. Todo texto visible
DEBE usar español colombiano formal con tuteo.

#### Scenario: El asistente exige confirmación explícita antes de ejecutar

- DADO un usuario que completó el paso 1 con un mapeo exhaustivo
- CUANDO llega al paso 2 y ve el resumen de impacto (incluye el cierre de
  sprints activos, si aplica)
- ENTONCES la ejecución solo se dispara tras una confirmación explícita del
  usuario, nunca automáticamente al completar el paso 1

#### Scenario: Textos en español colombiano formal

- DADO el asistente de migración abierto
- CUANDO se muestran las instrucciones y el resumen de impacto
- ENTONCES usa formas como "verifica" o "confirma", nunca "verificá" ni
  "confirmá"

## Limitaciones y deuda conocida

- Migración de un solo proyecto a la vez (sin migración masiva
  multi-proyecto).
- `TaskHistory` no se reescribe para reflejar los estados anteriores a la
  migración.
- Sin migración Alembic: reutiliza `board_columns`, `tasks` y `sprints`
  existentes.

## Referencias

- `openspec/changes/37-cambio-metodologia/proposal.md`
- `openspec/specs/methodology-strategies/spec.md` (contrato de strategy
  consumido)
- `openspec/specs/boards/spec.md` (`add_column`/`reassign_column_tasks`/
  `remove_column`)
- `openspec/changes/37-cambio-metodologia/specs/projects/spec.md` (delta:
  PATCH sigue rechazando `methodology`)
- `openspec/changes/37-cambio-metodologia/specs/sprints/spec.md` (delta:
  cierre + desvinculación al migrar)
- `backend/app/modules/projects/service.py` (`update_project`,
  `methodology_not_editable`)
