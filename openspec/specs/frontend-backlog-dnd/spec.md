# frontend-backlog-dnd Specification

> **Origen**: cambio [31-backlog-drag-drop](../../changes/archive/2026-07-20-31-backlog-drag-drop/)

## Propósito

Arrastrar historias/tareas entre el Backlog y los sprints en la vista agrupada del cambio 30 (`project-workspace`), con Angular CDK DragDrop sobre los ids estables de sección (`sprint-<uuid>` / `backlog`). Persiste vía `PATCH /tasks/{id}` existente (`sprint_id` + `order`); no agrega endpoints nuevos en la UI. El servidor (capability `tasks`, cambio 31) solo bloquea el destino `closed`; las demás reglas de destino se guían en la UI.

## Alcance

| Patrón | Acción | Descripción |
|--------|--------|-------------|
| CDK DragDrop | Arrastrar tarjeta | Cada sección (Backlog, sprint `draft`, sprint `active`) expone un `cdkDropList` con ids estables; cada tarjeta es un `cdkDrag` |
| Reglas de destino | Validación UI | Backlog ↔ sprint (`draft` o `active`) bidireccional; sprint ↔ sprint solo si ambos `draft`; sprints `closed` nunca destino |
| Zona visible | Feedback visual | Resalte de destinos válidos, atenuado de inválidos durante el arrastre |
| Persistencia | Escritura única | Un `PATCH /tasks/{id}` por drop con `sprint_id` (y `order` si aplica) |
| Optimista + rollback | Error handling | Actualización inmediata en la UI; reversión completa + banner de error en español si falla |
| Accesibilidad | Menú "Mover a…" | Dropdown por tarjeta que lista destinos válidos, ejecuta el mismo `PATCH`; ruta equivalente sin arrastre para usuario de teclado |
| Textos | Español formal | Tuteo sin voseo; UI copy, mensajes de error, aria-labels en español colombiano |

## Requisitos

### Requirement: Arrastre entre secciones con CDK

Cada sección de la vista de 30 (Backlog y cada sprint visible) DEBE exponerse como un `cdkDropList` conectado a las demás secciones permitidas, y cada tarjeta DEBE ser un `cdkDrag`. Los ids de conexión DEBEN reutilizar los ids estables de sección (`sprint-<uuid>` / `'backlog'`) de 30.

**Scenario: Arrastrar una tarjeta entre secciones conectadas**
- DADO la vista Backlog con la sección Backlog y dos sprints visibles
- CUANDO el usuario arrastra una tarjeta desde el Backlog a un sprint `draft`
- ENTONCES la tarjeta se suelta en la lista destino usando su id estable

### Requirement: Reglas de destino aplicadas en la UI

El sistema DEBE permitir soltar backlog↔sprint (`draft` o `active`, en ambas direcciones) y sprint↔sprint solo si origen y destino están ambos en `draft`; NO DEBE permitir soltar entre dos sprints donde alguno no sea `draft`. Los sprints `closed` no se renderizan en esta vista (30), por lo que nunca son origen ni destino del arrastre.

**Scenario: Backlog a sprint active permitido**
- DADO una tarjeta en el Backlog y un sprint `active` visible
- CUANDO el usuario la arrastra al sprint `active`
- ENTONCES el soltar se acepta y la tarjeta se reubica

**Scenario: Sprint active a otro sprint active bloqueado**
- DADO dos sprints `active` visibles con tarjetas
- CUANDO el usuario intenta arrastrar una tarjeta de un `active` al otro
- ENTONCES la zona de drop se muestra deshabilitada y el soltar no se acepta

**Scenario: Sprint draft a sprint draft permitido**
- DADO dos sprints `draft` visibles
- CUANDO el usuario arrastra una tarjeta de uno al otro
- ENTONCES el soltar se acepta y la tarjeta se reubica

### Requirement: Zona de drop visible durante el arrastre

Mientras se arrastra una tarjeta, el sistema DEBE resaltar las secciones que son destinos válidos según la regla anterior, y DEBE atenuar o deshabilitar visualmente las secciones inválidas.

**Scenario: Resalte de destinos válidos e inválidos**
- DADO una tarjeta de un sprint `draft` siendo arrastrada
- CUANDO el arrastre está en curso
- ENTONCES el Backlog y los demás sprints `draft` se resaltan como válidos, y los sprints `active` se atenúan como inválidos

### Requirement: Actualización optimista con rollback

Al soltar en un destino válido, el sistema DEBE reubicar la tarjeta de inmediato en la UI antes de la respuesta del servidor, y DEBE enviar `PATCH /tasks/{id}` con `sprint_id` (y `order` si aplica). Si la solicitud falla, DEBE revertir la tarjeta a su sección y posición original y DEBE mostrar un banner de error en español.

**Scenario: Persistencia exitosa**
- DADO una tarjeta soltada en un sprint `draft` válido
- CUANDO `PATCH /tasks/{id}` responde `200`
- ENTONCES la tarjeta permanece en la nueva sección

**Scenario: Rollback ante error de servidor**
- DADO una tarjeta soltada en un destino válido según la UI
- CUANDO `PATCH /tasks/{id}` responde con error (p. ej. `422` del guard o error de red)
- ENTONCES la tarjeta vuelve a su sección y posición original, con un banner de error en español

### Requirement: Alternativa de teclado — menú "Mover a…"

Cada tarjeta DEBE ofrecer un menú contextual "Mover a…" que liste los destinos válidos según las mismas reglas y ejecute el mismo `PATCH /tasks/{id}` al seleccionar uno, como ruta accesible por teclado equivalente al arrastre.

**Scenario: Mover una tarjeta por menú sin arrastre**
- DADO el foco de teclado en una tarjeta del Backlog
- CUANDO el usuario abre "Mover a…" y selecciona un sprint `active` visible
- ENTONCES la tarjeta se reubica mediante el mismo `PATCH /tasks/{id}`

**Scenario: El menú respeta las mismas reglas de destino**
- DADO una tarjeta de un sprint `active`
- CUANDO el usuario abre "Mover a…"
- ENTONCES la lista de destinos NO incluye otros sprints, solo el Backlog

### Requirement: No regresión del modal "mover a sprint" existente

El modal de detalle de tarea que cambia `sprint_id` por desplegable DEBE seguir funcionando sin cambio de contrato; el guard server-side de `closed` (capability `tasks`) aplica también a este flujo por ser el mismo endpoint.

**Scenario: El modal sigue moviendo tareas a sprints abiertos**
- DADO el modal de tarea abierto con el desplegable de sprint
- CUANDO el usuario selecciona un sprint `draft` o `active` y guarda
- ENTONCES la tarea se reasigna igual que antes de este cambio

### Requirement: Textos en español colombiano formal

Todo texto visible del arrastre (zona de drop, menú "Mover a…", mensajes de error, aria-labels) DEBE usar español colombiano formal con tuteo, sin voseo rioplatense.

**Scenario: Tuteo formal en el toast de error**
- DADO un rollback por error del servidor
- CUANDO se muestra el banner de error
- ENTONCES el mensaje usa formas como "verifica" o "intenta de nuevo", nunca "verificá" ni "intentá"

## Limitaciones y deuda conocida

- Sin test runner de frontend en `package.json`; verificación por lectura de fuente, build AOT y ESLint (mismo patrón aceptado del repo).
- Reglas de destino son UX guided (UI enforced), no server enforced — la API solo rechaza destino `closed` (guard de integridad en `tasks`).
- Drag & drop del board kanban (columnas, `move_task_column`) permanece fuera de alcance — sigue por botones de estado, sin CDK.

## Referencias

- backend/app/modules/tasks/ (guard de integridad, endpoint reorder)
- frontend/src/widgets/project-workspace/ (CDK implementation)
- frontend/src/entities/workspace/ (modelo y servicio)
- frontend/src/assets/i18n/es-CO.json (textos)
