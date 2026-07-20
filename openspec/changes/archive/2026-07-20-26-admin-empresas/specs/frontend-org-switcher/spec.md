# frontend-org-switcher Specification

## Purpose

Selector de empresa activa en el layout del frontend Angular: lista las empresas del usuario con su rol, persiste la elección y, al cambiar, refresca por completo el contexto de la aplicación (stores de dominio, menús, tema, notificaciones, WebSocket) para que ninguna vista muestre datos de la empresa anterior.

## Requirements

### Requirement: Selector de empresa activa en el layout

El sistema DEBE mostrar en el layout (header/sidebar) un selector con todas las empresas donde el usuario tiene membresía, cada una con su rol, obtenidas del endpoint "mis empresas" de `organizations-admin`.

#### Scenario: Selector lista las empresas del usuario

- DADO un usuario miembro de dos empresas
- CUANDO abre el selector de empresa activa
- ENTONCES ve ambas empresas listadas con su rol en cada una

#### Scenario: Usuario con una sola empresa

- DADO un usuario miembro de una sola empresa
- CUANDO abre el layout
- ENTONCES el selector muestra esa empresa como activa, sin obligar a elegir

### Requirement: Cambio de empresa activa refresca todo el contexto

Al seleccionar una empresa distinta, el sistema DEBE: persistir la elección en `localStorage`, reiniciar los stores de dominio (proyectos, tareas, dashboard, notificaciones), recargar el menú de navegación y reconectar el WebSocket con el nuevo scope, sin dejar datos residuales de la empresa anterior visibles.

#### Scenario: Cambio de empresa refresca todo el contexto

- DADO un usuario en la empresa X con datos cargados en pantalla
- CUANDO selecciona la empresa Y en el selector
- ENTONCES los stores de dominio se reinician, el menú se recarga, el WebSocket reconecta con el scope de Y, y ninguna vista conserva datos de X

#### Scenario: La elección persiste entre recargas

- DADO un usuario que eligió la empresa Y como activa
- CUANDO recarga la página
- ENTONCES la aplicación arranca con Y como empresa activa, leída de `localStorage`

### Requirement: Interceptor inyecta el header en toda petición autenticada

El interceptor HTTP DEBE agregar `X-Organization-Id` con la empresa activa vigente en toda petición autenticada a la API mientras exista una empresa seleccionada.

#### Scenario: Petición de dominio lleva el header vigente

- DADO una empresa activa Y ya seleccionada
- CUANDO cualquier feature dispara una petición a la API
- ENTONCES la petición incluye `X-Organization-Id: Y`

### Requirement: Estado de error no rompe el layout

Si el cambio de empresa activa falla (red o `403`), el sistema DEBE mostrar un mensaje de error legible y DEBE conservar el contexto de la empresa anterior sin romper el layout ni dejarlo en un estado inconsistente.

#### Scenario: Falla al cambiar de empresa conserva el contexto anterior

- DADO un usuario en la empresa X
- CUANDO intenta cambiar a una empresa Y y la petición falla
- ENTONCES se muestra un error y el layout sigue mostrando el contexto de X sin datos parciales de Y

### Requirement: Textos en español colombiano formal

Todo texto visible del selector (etiquetas, estado vacío, mensajes de error, `aria-label`) DEBE usar español colombiano formal con tuteo, sin voseo rioplatense.

#### Scenario: Tuteo formal en las etiquetas del selector

- DADO cualquier texto visible del selector de empresa activa
- CUANDO se redacta
- ENTONCES usa formas como "selecciona", "verifica", nunca "seleccioná", "verificá"
