# frontend-hierarchy-view Specification

## Purpose

Vista de solo lectura que renderiza el bosque completo de proyectos de arriba hacia abajo, con avance roll-up consolidado por nodo (estilo 18/20), compuesta en el cliente a partir de `GET /projects`, `GET /projects/{id}/tree` y `GET /projects/{id}/progress` (capability `project-hierarchy`, cambio 21). No reparenta proyectos ni lista tareas individuales; no agrega endpoints de backend.

## Requirements

### Requirement: Acceso desde la navegación

El sistema DEBE exponer una ruta lazy `hierarchy` (distinta de `projects/:id`, sin colisión) enlazada desde la lista de proyectos, con carga diferida del módulo de la página.

#### Scenario: Navegación desde la lista de proyectos

- DADO un usuario autenticado en la lista de proyectos
- CUANDO hace clic en el enlace a la vista jerárquica
- ENTONCES navega a la ruta `hierarchy` con el módulo cargado de forma perezosa

### Requirement: Composición del bosque en el cliente

La vía primaria: el sistema DEBE derivar la estructura y las raíces (`parent_project_id = null`) desde la lista plana `GET /projects` agrupando por `parent_project_id`, y por cada raíz DEBE obtener su avance roll-up con una llamada `GET /projects/{id}/progress` (anidado, cubre todo el subárbol). `GET /projects/{id}/tree` DEBE usarse como fallback OBLIGATORIO de la estructura cuando `GET /projects` no emita `parent_project_id`. En ningún caso DEBE depender de un endpoint de agregación nuevo en backend. (Errata: vía primaria alineada al design por decisión del orquestador.)

#### Scenario: Bosque con varias sombrillas

- DADO tres proyectos raíz en la organización, cada uno con subproyectos
- CUANDO se carga la vista jerárquica
- ENTONCES se muestran las tres raíces anidadas, con la estructura derivada de `GET /projects` (agrupada por `parent_project_id`) y el roll-up de cada raíz resuelto con una llamada a `/progress`

### Requirement: Render top-down con expandir/colapsar

Cada nodo DEBE respetar el anidamiento padre-hijo del árbol, DEBE permitir expandir y colapsar cualquier nodo con hijos, y DEBE terminar en nodos de PROYECTO (sin listar tareas individuales).

#### Scenario: Expandir revela los hijos

- DADO un nodo sombrilla colapsado con subproyectos
- CUANDO el usuario expande el nodo
- ENTONCES los subproyectos hijos se muestran indentados según su nivel de profundidad

#### Scenario: Proyecto raíz sin hijos

- DADO un proyecto raíz sin subproyectos
- CUANDO se renderiza
- ENTONCES se muestra como nodo único, sin control de expandir/colapsar

### Requirement: Avance roll-up visible por nodo

Cada nodo DEBE mostrar su avance consolidado como fracción `done/total` (estilo 18/20) proveniente de `/progress`, y DEBE representarlo también con un indicador visual (barra de avance u equivalente).

#### Scenario: Roll-up de una sombrilla

- DADO una sombrilla con dos subproyectos (8/10 y 10/10 tareas done)
- CUANDO se renderiza su nodo
- ENTONCES muestra `18/20` con una barra de avance proporcional

#### Scenario: Proyecto hoja sin tareas

- DADO un proyecto hoja sin tareas creadas
- CUANDO se renderiza su nodo
- ENTONCES muestra `0/0` sin error visible

### Requirement: Indicador de metodología por proyecto

Cada nodo DEBE mostrar la metodología del proyecto (`planner`, `kanban`, `scrum`, `custom`) con una insignia propia, independiente de la metodología de sus ancestros o descendientes.

#### Scenario: Metodologías mixtas en el subárbol

- DADO un padre `scrum` con un hijo `kanban`
- CUANDO se renderiza el árbol
- ENTONCES cada nodo muestra su propia insignia de metodología

### Requirement: Navegación al proyecto

Cada nodo DEBE ofrecer una acción "ir al proyecto" que navegue con `routerLink` a `/projects/{id}` (workspace del proyecto).

#### Scenario: Clic en un nodo navega al workspace

- DADO un nodo de proyecto visible en el árbol
- CUANDO el usuario activa su acción "ir al proyecto"
- ENTONCES la aplicación navega a `/projects/{id}` y muestra el workspace de ese proyecto

### Requirement: Estados de carga, vacío y error

La página DEBE mostrar un indicador de carga mientras se resuelven las llamadas del bosque, un estado vacío cuando la organización no tiene proyectos, y un error legible por rama cuando alguna llamada falla, sin bloquear el render del resto del bosque.

#### Scenario: Carga inicial

- DADO que el usuario navega a `hierarchy`
- CUANDO las llamadas a `/projects`, `/tree` y `/progress` aún no resuelven
- ENTONCES se muestra un indicador de carga

#### Scenario: Organización sin proyectos

- DADO una organización sin proyectos creados
- CUANDO se carga la vista
- ENTONCES se muestra un mensaje de estado vacío en español colombiano formal

#### Scenario: Falla parcial de una raíz

- DADO que la llamada `/progress` de una de las raíces falla
- CUANDO se renderiza el bosque
- ENTONCES esa rama muestra un mensaje de error y las demás raíces se renderizan con normalidad

### Requirement: Responsive y accesible

La vista DEBE adaptarse mobile-first (Tailwind breakpoints) y DEBE implementar semántica ARIA de árbol: contenedor con `role="tree"`, cada nodo con `role="treeitem"` y `aria-expanded` reflejando su estado, con navegación básica por teclado (Enter/Espacio expande, colapsa o activa "ir al proyecto").

#### Scenario: Uso en viewport móvil

- DADO un ancho de viewport móvil
- CUANDO se renderiza el árbol
- ENTONCES no hay scroll horizontal y los controles son accionables al tacto

#### Scenario: Navegación por teclado expande un nodo

- DADO el foco en un nodo colapsado con hijos
- CUANDO el usuario presiona Enter o Espacio
- ENTONCES el nodo se expande y `aria-expanded` cambia a `true`

### Requirement: Primitivos de @solercia/ui y gap documentado

El árbol DEBE componerse con primitivos de @solercia/ui 0.3.0 (tarjeta, insignia, ícono, spinner, barra de avance), sin markup manual equivalente a los ya disponibles. La ausencia de un componente `SolTree` DEBE documentarse como gap pendiente de aporte a la librería, siguiendo el criterio de `frontend-ui-consumption`.

#### Scenario: Gap de SolTree documentado

- DADO que @solercia/ui 0.3.0 no expone un componente de árbol
- CUANDO se entrega el widget `project-tree`
- ENTONCES queda registrado como gap pendiente de librería, sin bloquear la entrega de esta vista

### Requirement: Textos en español colombiano formal

Todo texto visible de la vista (títulos, etiquetas, estados vacío/error, `aria-label`) DEBE usar español colombiano formal con tuteo, sin voseo rioplatense.

#### Scenario: Tuteo formal en las etiquetas

- DADO cualquier texto visible en la vista jerárquica
- CUANDO se redacta
- ENTONCES usa formas como "verifica", "ingresa", nunca "verificá", "ingresá"
