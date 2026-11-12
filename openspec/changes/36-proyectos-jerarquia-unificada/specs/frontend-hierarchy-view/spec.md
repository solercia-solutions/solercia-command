# Delta for frontend-hierarchy-view

## MODIFIED Requirements

### Requirement: Acceso desde la navegación

`/projects` DEBE ser la ruta canónica de Proyectos, cargada de forma perezosa, con el árbol como vista PRINCIPAL (ya no la grilla plana). `/hierarchy` DEBE redirigir a `/projects` sin entrada de menú propia. El menú DEBE exponer una única entrada "Proyectos".
(Previously: `hierarchy` era ruta aparte de solo lectura, con su propia entrada de menú.)

#### Scenario: Navegación desde el menú

- DADO un usuario autenticado
- CUANDO hace clic en "Proyectos" del menú
- ENTONCES navega a `/projects` con el árbol como vista principal

#### Scenario: Redirección desde /hierarchy

- DADO un enlace antiguo a `/hierarchy`
- CUANDO la ruta resuelve
- ENTONCES redirige a `/projects` sin error visible

### Requirement: Render top-down con expandir/colapsar

Cada nodo DEBE respetar el anidamiento padre-hijo y terminar en hojas (`project_kind=proyecto`, sin tareas individuales). El chevron, independiente del nombre del nodo, DEBE ser el control de expandir/colapsar.
(Previously: sin un control propio separado del nombre del nodo.)

#### Scenario: Expandir revela los hijos vía chevron

- DADO un área colapsada con subproyectos
- CUANDO se activa su chevron
- ENTONCES los hijos se muestran indentados, sin navegar fuera de la vista

#### Scenario: Proyecto hoja sin hijos

- DADO un proyecto hoja sin subproyectos
- CUANDO se renderiza
- ENTONCES no muestra chevron de expandir/colapsar

### Requirement: Navegación al proyecto

El clic en el NOMBRE del nodo DEBE navegar con `routerLink` a `/projects/{id}` (workspace de tareas), sin importar el `project_kind`: toda área es también un proyecto con workspace propio. El chevron y el control de edición inline NO DEBEN disparar esta navegación.
(Previously: acción explícita "ir al proyecto", sin cubrir nodos área.)

#### Scenario: Clic en el nombre de un proyecto navega al workspace

- DADO un nodo `project_kind=proyecto`
- CUANDO se hace clic en su nombre
- ENTONCES navega a `/projects/{id}` y muestra su workspace

#### Scenario: Clic en el nombre de un área también navega

- DADO un nodo `project_kind=area`
- CUANDO se hace clic en su nombre (fuera del chevron)
- ENTONCES también navega a `/projects/{id}` y muestra el workspace de esa área

## ADDED Requirements

### Requirement: Edición inline de nombre y descripción

Un lápiz al pasar el mouse, o doble clic en el nombre, DEBE activar edición inline de nombre y descripción. Enter DEBE guardar con `PATCH /projects/{id}`; Esc DEBE cancelar sin persistir. Solo `admin`/`manager` DEBEN ver el control de edición; otros roles NO DEBEN verlo.

#### Scenario: Guardar con éxito muestra confirmación

- DADO un admin editando el nombre de un nodo
- CUANDO Enter guarda y `PATCH` responde 200
- ENTONCES el nodo actualiza y aparece un toast de éxito en español colombiano formal

#### Scenario: Error de guardado conserva el valor previo

- DADO un manager editando la descripción
- CUANDO `PATCH` responde con error
- ENTONCES el nodo conserva su valor anterior y aparece un toast de error

#### Scenario: Rol sin permiso no ve el control

- DADO un usuario `member`
- CUANDO visualiza el árbol
- ENTONCES no ve el lápiz de edición en ningún nodo

#### Scenario: Renombrar no rompe la trazabilidad de plantilla

- DADO un proyecto de plantilla (cambio 27) renombrado inline
- CUANDO el 27 reconcilia el subárbol por ledger (`template_id`+`node_id`)
- ENTONCES la reconciliación preserva el nombre editado, sin revertirlo por nombre

### Requirement: Distinción visual por project_kind

Cada nodo DEBE mostrar un ícono o insignia por `project_kind` (`area`/`proyecto`), junto al badge de metodología existente. Si `project_kind` llega ausente o nulo, el sistema DEBE aplicar un fallback visual de `proyecto` sin bloquear el render.

#### Scenario: Árbol con áreas y proyectos mixtos

- DADO nodos de ambos `project_kind`
- CUANDO se renderiza el árbol
- ENTONCES cada nodo muestra el ícono correspondiente a su tipo

#### Scenario: project_kind ausente cae al fallback

- DADO un nodo sin `project_kind` en la respuesta de la API
- CUANDO se renderiza
- ENTONCES se muestra el ícono de "proyecto" por defecto, sin error

### Requirement: Toggle "Solo hojas"

`/projects` DEBE ofrecer un control "Solo hojas" que, al activarse, reemplaza el árbol por la grilla plana filtrada con `GET /projects?project_kind=proyecto`; al desactivarse, DEBE volver a mostrar el árbol completo.

#### Scenario: Activar el toggle muestra la grilla filtrada

- DADO el árbol visible en `/projects`
- CUANDO se activa "Solo hojas"
- ENTONCES se muestra la grilla con únicamente proyectos hoja

#### Scenario: Desactivar el toggle restaura el árbol

- DADO la grilla "Solo hojas" visible
- CUANDO se desactiva el toggle
- ENTONCES se vuelve a mostrar el árbol jerárquico completo

### Requirement: Consolidación del menú de navegación

El seed de menú DEBE consolidarse en una única entrada "Proyectos" apuntando a `/projects`. La limpieza del ítem "Jerarquía" preexistente DEBE ser idempotente: no DEBE fallar ni duplicar filas al ejecutarse varias veces, y DEBE remover esa entrada de organizaciones que ya la tengan sembrada.

#### Scenario: Organización existente pierde el ítem duplicado

- DADO una organización con "Jerarquía" ya sembrada
- CUANDO corre el seed consolidado
- ENTONCES esa entrada se elimina y solo queda "Proyectos"

#### Scenario: Ejecutar el seed dos veces no duplica

- DADO el seed consolidado ya aplicado una vez
- CUANDO se ejecuta nuevamente
- ENTONCES no se crean filas duplicadas ni se produce error

## Referencias

- `openspec/specs/frontend-hierarchy-view/spec.md` — línea base; "Composición del bosque", "Avance roll-up" e "Indicador de metodología" quedan intactos
- `openspec/changes/27-plantillas-idempotentes/specs/projects/spec.md` — `project_kind`, filtro de listado, reconciliación por ledger
