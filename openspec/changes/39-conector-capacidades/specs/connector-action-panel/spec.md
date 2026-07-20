# Spec — Panel de acciones del conector (connector-action-panel)

## Propósito

Tarjeta de conector expandible que renderiza, DESDE `GET /connectors/{id}/actions`, el panel de acciones disponibles por capability con sus tres estados (disponible / requiere conexión / próximamente) — reemplazando el bloque de botones cableado por `provider`/`credential_kind` en la tarjeta actual. Base reutilizada por los cambios 40 y 41.

## Requisitos

### Requirement: Panel de acciones renderizado desde el endpoint, sin condicionales por proveedor

El bloque de acciones de la tarjeta DEBE pintarse iterando la respuesta de `GET /connectors/{id}/actions`; NO DEBE contener ninguna condición del tipo `@if (connector.provider === ...)` ni `@if (connector.credential_kind === ...)` para decidir qué acción mostrar. Cada acción se renderiza según su propio `state`/`kind`, no según el proveedor del conector.

#### Scenario: Tarjetas de distintos proveedores comparten el mismo bloque de acciones
- Dado conectores Jira, M365 y MCP en la misma organización
- Cuando se expande cada tarjeta
- Entonces el mismo componente de panel de acciones renderiza cada una, sin bloques condicionales por proveedor en la plantilla

### Requirement: Estados visuales de acción (disponible / requiere conexión / próximamente)

Una acción en `available` DEBE renderizarse como botón habilitado (navegación si `kind=navigate`, ejecución con resultado visible si `kind=execute`). Una acción en `requires_connection` DEBE renderizarse deshabilitada con un texto de ayuda que indique conectar la cuenta primero. Una acción en `coming_soon` DEBE renderizarse deshabilitada con una insignia "Próximamente".

#### Scenario: Acción disponible ejecuta o navega
- Dado una acción con `state=available` y `kind=navigate`
- Cuando el usuario la selecciona
- Entonces el frontend navega al flujo correspondiente

#### Scenario: Acción sin conexión aparece deshabilitada con ayuda
- Dado una acción con `state=requires_connection`
- Cuando se renderiza el panel
- Entonces el botón aparece deshabilitado con un texto que invita a conectar la cuenta

#### Scenario: Acción próxima aparece con insignia
- Dado una acción con `state=coming_soon`
- Cuando se renderiza el panel
- Entonces el botón aparece deshabilitado con la insignia "Próximamente"

### Requirement: Resultado del probe visible en el panel

Al ejecutar una acción `kind=execute` (probe), el panel DEBE mostrar el resultado de forma visible sin abandonar al usuario sin retroalimentación: el detalle en caso de éxito o el mensaje de error en español colombiano formal en caso de falla.

#### Scenario: Probe exitoso muestra el detalle
- Dado el usuario ejecuta una acción de verificación disponible
- Cuando la respuesta es exitosa
- Entonces el panel muestra el detalle devuelto por el backend

#### Scenario: Probe fallido muestra un mensaje claro
- Dado el usuario ejecuta una acción de verificación disponible
- Cuando la respuesta es un error
- Entonces el panel muestra un mensaje de error en español colombiano formal, sin bloquear el resto de la tarjeta

### Requirement: Punto de entrada estable de importación Jira

El panel DEBE renderizar la acción de importar historias vía API con la `key` estable `jira_import`. Mientras su `state` sea `coming_soon`, DEBE aparecer deshabilitada con la insignia "Próximamente". La acción de importar historias por archivo (preview actual) DEBE conservarse como una acción propia ya `available`, sin perder funcionalidad.

#### Scenario: `jira_import` próximo no bloquea la importación por archivo
- Dado un conector Jira conectado con `jira_import` en `coming_soon`
- Cuando se expande el panel
- Entonces `jira_import` aparece deshabilitado con "Próximamente" y la acción de importar por archivo sigue disponible y funcional

### Requirement: No regresión de conexión y desconexión de cuentas

Agregar el panel de acciones NO DEBE romper el comportamiento existente de la tarjeta: conectar (`oauth`), abrir credenciales (`api_token`), listar cuentas conectadas y revocarlas DEBEN seguir funcionando igual que antes del cambio.

#### Scenario: Conectar y desconectar siguen funcionando con el panel presente
- Dado una tarjeta con el panel de acciones expandido
- Cuando el usuario conecta una cuenta nueva o revoca una existente
- Entonces la operación se completa igual que en la página actual, sin interferencia del panel

### Requirement: Textos en español colombiano formal (tuteo)

Toda la copia nueva del panel (etiquetas de acción, textos de ayuda, insignias, mensajes de error) DEBE redactarse en español colombiano formal con tuteo, sin voseo rioplatense.

#### Scenario: Texto de ayuda usa tuteo formal
- Dado una acción en `requires_connection`
- Cuando se muestra su texto de ayuda
- Entonces usa formas como "conecta tu cuenta", nunca "conectá tu cuenta"
