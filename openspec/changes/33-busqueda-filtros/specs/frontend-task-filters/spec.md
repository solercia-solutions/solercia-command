# Spec — Filtros de tareas en frontend (frontend-task-filters)

## Propósito

Barra de filtros compartida entre el backlog agrupado (30) y el cronograma Gantt (`sprint-gantt`): una única fuente de estado y predicado/anotación reutilizada por ambas vistas. El filtro por asignado se resuelve en servidor (contrato extendido del cambio 32); búsqueda, épica, tipo y rango de fechas se resuelven en cliente sobre el set ya cargado. Todos los filtros combinan en AND.

## Requisitos

### Requirement: Fuente única de estado de filtros compartida

La feature `filter-tasks` DEBE exponer un único estado de filtros (búsqueda, asignados seleccionados, épica, tipo, rango de fechas) y un predicado/anotación de resultado, consumido sin duplicación por el backlog y por el Gantt.

#### Scenario: Mismo resultado en backlog y Gantt
- DADO un usuario que aplica un filtro en la barra compartida
- CUANDO cambia de la vista backlog a la vista Gantt sin modificar el filtro
- ENTONCES el Gantt refleja el mismo conjunto de tareas filtradas/resaltadas que el backlog

### Requirement: Filtro por asignado resuelto en servidor

Al seleccionar uno o más avatares, el frontend DEBE recargar las tareas del proyecto pasando `assignee_id` repetido por cada usuario seleccionado y DEBE renderizar la respuesta del servidor tal cual (incluidos los padres de contexto `is_context=true`), sin recalcular la regla del 32 en cliente.

#### Scenario: Selección de dos avatares recarga con multi-selección
- DADO un usuario que selecciona los avatares de A y B
- CUANDO confirma la selección
- ENTONCES el frontend solicita `?assignee_id={A}&assignee_id={B}` y muestra las tareas devueltas, incluidos los padres de contexto atenuados

#### Scenario: Deselección restaura el listado completo
- DADO un usuario con avatares seleccionados
- CUANDO limpia la selección de avatares
- ENTONCES el frontend recarga sin `assignee_id` y muestra todas las tareas del proyecto

### Requirement: Fila de avatares con overflow y selección accesible

La fila de avatares DEBE mostrar hasta N avatares y agrupar el resto bajo un indicador "+N" expandible; DEBE permitir multi-selección y anotar cada avatar y el indicador con atributos `aria-*` (rol, estado seleccionado, nombre del asignado).

#### Scenario: Overflow agrupa asignados excedentes
- DADO un proyecto con más asignados que el máximo visible
- CUANDO se renderiza la barra de filtros
- ENTONCES los excedentes se agrupan bajo "+N" y expandirlo permite seleccionarlos con soporte de lector de pantalla

### Requirement: Búsqueda resalta y auto-expande sin ocultar

La búsqueda por `task_key` o texto parcial del título DEBE resaltar la subcadena coincidente y auto-expandir cualquier sección o grupo colapsado con coincidencia, SIN ocultar las tareas que no matchean.

#### Scenario: Búsqueda expande una sección colapsada con match
- DADO un sprint colapsado que contiene la tarea `SDM-42`
- CUANDO el usuario busca "42"
- ENTONCES la sección se auto-expande, `SDM-42` aparece resaltada y el resto de tareas sigue visible sin resaltar

#### Scenario: Búsqueda sin coincidencias no oculta el árbol
- DADO un texto de búsqueda que no matchea ninguna tarea
- CUANDO se aplica
- ENTONCES se muestra el estado vacío sin colapsar ni eliminar la estructura existente

### Requirement: Filtro por épica derivado de la jerarquía

El filtro por épica DEBE derivarse en memoria siguiendo `parent_task_id` (subtarea → historia → épica), sin depender de `epic_id`, y al seleccionar una épica DEBE mostrar toda su descendencia.

#### Scenario: Selección de épica muestra su descendencia
- DADO una épica con historias y subtareas anidadas por `parent_task_id`
- CUANDO el usuario la selecciona en el dropdown
- ENTONCES se muestran la épica y toda su descendencia

### Requirement: Filtros por tipo de tarea y rango de fechas

El dropdown de tipo DEBE filtrar por `task_type` y el selector de rango DEBE filtrar por fecha, ambos resueltos en cliente sobre el set cargado.

#### Scenario: Filtro combinado de tipo y fechas
- DADO tareas de distinto tipo y con vencimientos variados
- CUANDO el usuario selecciona tipo "bug" y un rango de fechas
- ENTONCES solo se resaltan/muestran las tareas tipo bug con vencimiento dentro del rango

### Requirement: Combinación AND entre todos los filtros

Todos los filtros activos (servidor: asignado; cliente: búsqueda, épica, tipo, fechas) DEBEN combinarse en AND: una tarea solo cuenta como resultado si cumple simultáneamente cada filtro activo.

#### Scenario: Tres filtros combinados
- DADO un asignado seleccionado, un tipo elegido y un texto de búsqueda activos a la vez
- CUANDO los tres filtros están activos
- ENTONCES solo se muestran/resaltan las tareas que cumplen los tres criterios

### Requirement: Chips de filtros activos y limpiar filtros

La barra DEBE mostrar un chip por cada filtro activo y una acción "Limpiar filtros" que DEBE remover todos los filtros (incluida la recarga sin `assignee_id` si aplicaba).

#### Scenario: Limpiar filtros restaura el estado inicial
- DADO varios filtros activos con sus chips visibles
- CUANDO el usuario pulsa "Limpiar filtros"
- ENTONCES desaparecen los chips, se recarga sin `assignee_id` y se muestran todas las tareas sin resaltado

### Requirement: Estado vacío sin coincidencias

Cuando la combinación de filtros no produce ninguna tarea visible, el sistema DEBE mostrar "No hay tareas que coincidan con los filtros" en lugar de una lista vacía sin explicación.

#### Scenario: Ningún resultado tras combinar filtros
- DADO un tipo y un rango de fechas que ninguna tarea cumple a la vez
- CUANDO se aplican ambos filtros
- ENTONCES se muestra el mensaje "No hay tareas que coincidan con los filtros"
