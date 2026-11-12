# mcp-connector Specification

> Origen: cambio [19-mcp-connector](../../proposal.md).

## Purpose

Adaptador `mcp` que registra servidores **Model Context Protocol** remotos como conectores del núcleo de integraciones (14), consumidos EN MODO LECTURA vía el puerto `external_resources` (ver `integration-ports`). Sumar un servicio nuevo es configuración (registrar un servidor MCP), no código. Transporte exclusivo: **Streamable HTTP** remoto, con el SDK oficial `mcp` de Python (async). Sin ejecución de herramientas de escritura en esta ola.

## Ubicación

`backend/app/integrations/adapters/mcp.py` (adaptador), `backend/app/modules/connectors/` (registro + REST de lectura), `backend/app/config.py` (`MCP_HOST_ALLOWLIST`, timeouts, topes).

## Alcance REST propuesto

| Método | Ruta | Propósito | Rol requerido |
|--------|------|-----------|----------------|
| GET | /api/v1/connectors/{id}/mcp/resources | Listar recursos del servidor MCP | cualquier miembro |
| GET | /api/v1/connectors/{id}/mcp/resources/read | Leer un recurso (`uri`, con topes) | cualquier miembro |
| GET | /api/v1/connectors/{id}/mcp/tools | Listar tools descubiertas | cualquier miembro |
| POST | /api/v1/connectors/{id}/mcp/tools/{tool_name}/call | Invocar tool allowlisted de solo lectura | cualquier miembro |

El registro (`POST`/`PATCH`/`DELETE /connectors`) reutiliza el CRUD y RBAC (admin/manager) de `connectors`. Toda respuesta sigue el envelope `{data, message, meta}` de `api-conventions`.

## Requisitos

### Requirement: Registro de servidor MCP como conector

Registrar un servidor MCP DEBE crear un conector con `provider = mcp`, URL base, transporte (fijo: Streamable HTTP), modo de auth (`api_token` o `none`) y allowlist de tools por conector. Roles `admin`/`manager` DEBEN poder registrar; cualquier miembro DEBE poder leer.

#### Scenario: Registro con token estático
- Dado un admin de la organización
- Cuando registra un conector MCP con URL base y un token bearer estático
- Entonces el conector queda creado con `credential_kind = api_token` y el token cifrado

#### Scenario: Registro sin autenticación
- Dado un admin de la organización
- Cuando registra un conector MCP hacia un servidor sin autenticación
- Entonces el conector queda creado con `credential_kind = none`

### Requirement: Adaptador auto-registrado, transporte exclusivo Streamable HTTP

El adaptador `mcp` DEBE auto-registrarse en el registro de adaptadores del núcleo (precedente `adapters/fake.py`), sin editar el orquestador. El transporte DEBE ser exclusivamente Streamable HTTP remoto; NINGÚN transporte `stdio`/subprocess DEBE estar disponible.

#### Scenario: Registro en import-time sin editar el núcleo
- Dado el módulo `adapters/mcp.py`
- Cuando la aplicación arranca e importa los adaptadores
- Entonces `mcp` queda disponible por su `provider` sin ediciones a `ports.py` ni al orquestador

#### Scenario: No existe transporte local
- Dado el adaptador `mcp` configurado
- Cuando se revisan sus opciones de transporte
- Entonces solo Streamable HTTP remoto está disponible; no hay opción `stdio`/subprocess

### Requirement: Handshake `initialize` previo a cualquier operación

Toda sesión contra un servidor MCP DEBE ejecutar `initialize` (negociación de capacidades) antes de `resources/list`, `resources/read`, `tools/list` o `tools/call`.

#### Scenario: Initialize exitoso habilita las operaciones siguientes
- Dado un servidor MCP alcanzable
- Cuando el adaptador abre sesión y ejecuta `initialize`
- Entonces las llamadas subsiguientes (`resources/list`, etc.) se ejecutan sobre la sesión negociada

#### Scenario: Servidor inalcanzable en `initialize`
- Dado un servidor MCP caído o inalcanzable
- Cuando el adaptador intenta `initialize`
- Entonces la operación responde un error de dominio claro (ej. `MCP_SERVER_UNREACHABLE`), sin excepción no controlada

### Requirement: Descubrimiento y lectura de recursos con topes de tamaño

`list_resources` y `read_resource(uri)` DEBEN mapear `resources/list`/`resources/read` a los DTOs del puerto. `read_resource` DEBE aplicar un tope de tamaño de respuesta configurado; excederlo DEBE rechazar la lectura con un error de dominio. El contenido se descarta tras medirlo, sin llegar al DTO ni a la respuesta; el buffering transitorio del SDK es inevitable sin streaming (limitación documentada). (Errata: el texto original "sin cargar el contenido completo en memoria" se ajustó a la realidad del SDK por decisión del orquestador — ver `reader.py`'s docstring, judgment-day 4R.)

#### Scenario: Listar recursos disponibles
- Dado un servidor MCP con recursos publicados
- Cuando se llama `list_resources`
- Entonces se recibe la lista de `ExternalResource` disponibles

#### Scenario: Leer un recurso dentro del tope
- Dado un recurso cuyo tamaño está dentro del tope configurado
- Cuando se llama `read_resource(uri)`
- Entonces se recibe su `ExternalResourceContent` completo

#### Scenario: Leer un recurso que excede el tope
- Dado un recurso cuyo tamaño excede el tope configurado
- Cuando se llama `read_resource(uri)`
- Entonces la lectura se rechaza con un error de dominio claro, sin cargar el contenido completo

### Requirement: Descubrimiento e invocación controlada de tools

`list_tools` DEBE mapear `tools/list` a `ExternalTool` (incluyendo el hint `readOnlyHint` si el servidor lo declara). `call_tool` DEBE aplicar **default-deny**: solo ejecuta si la tool está en la allowlist explícita del conector Y está anotada `readOnlyHint: true`; cualquier otro caso se rechaza.

#### Scenario: Listar tools expuestas
- Dado un servidor MCP con tools publicadas
- Cuando se llama `list_tools`
- Entonces se recibe la lista de `ExternalTool` con su `readOnlyHint` si aplica

#### Scenario: Invocar tool allowlisted y de solo lectura
- Dado una tool en la allowlist del conector y anotada `readOnlyHint: true`
- Cuando se llama `call_tool` sobre ella
- Entonces se ejecuta y retorna el resultado

#### Scenario: Tool fuera de la allowlist es rechazada
- Dado una tool NO presente en la allowlist del conector
- Cuando se intenta `call_tool` sobre ella
- Entonces la llamada se rechaza sin contactar al servidor

#### Scenario: Tool allowlisted sin `readOnlyHint` es rechazada
- Dado una tool en la allowlist pero sin `readOnlyHint: true` (o con el hint en `false`)
- Cuando se intenta `call_tool` sobre ella
- Entonces la llamada se rechaza; el hint por sí solo nunca es suficiente

### Requirement: Timeout y topes por llamada

Toda operación contra el servidor MCP DEBE aplicar un timeout configurado. Superarlo DEBE producir un error de dominio claro y liberar la conexión. Las respuestas DEBEN respetar topes de tamaño y de número de elementos por llamada.

#### Scenario: Timeout por llamada
- Dado un servidor MCP que no responde dentro del timeout configurado
- Cuando se ejecuta cualquier operación de lectura
- Entonces la operación falla con un error de dominio claro (ej. `MCP_TIMEOUT`) y la conexión queda liberada

#### Scenario: Tope de tamaño/número de elementos
- Dado una respuesta que excede el tope configurado de tamaño o de número de elementos
- Cuando se procesa esa respuesta
- Entonces se aplica el tope, sin exceder el límite configurado

### Requirement: Validación anti-SSRF de la URL del servidor

La URL base de un servidor MCP DEBE validarse contra una allowlist explícita de hosts y un bloqueo por defecto de rangos de red privados. En producción, la URL DEBE ser `https`.

#### Scenario: URL privada sin allowlist es rechazada
- Dado una URL de servidor MCP que resuelve a un rango de red privado y no está en la allowlist explícita
- Cuando se intenta registrar el conector
- Entonces el registro se rechaza (anti-SSRF)

#### Scenario: Host en la allowlist explícita es permitido
- Dado una URL que resuelve a un rango privado pero está explícitamente en la allowlist de hosts MCP
- Cuando se registra el conector
- Entonces el registro se permite

#### Scenario: `http` rechazado en producción
- Dado un entorno de producción
- Cuando se intenta registrar un conector MCP con URL `http://` (no `https`)
- Entonces el registro se rechaza

### Requirement: Contenido del servidor tratado como dato inerte

Todo contenido devuelto por el servidor MCP (descripciones de recursos/tools, resultados de `read_resource`/`call_tool`) DEBE tratarse como dato NO confiable: NUNCA se ejecuta ni se interpreta como instrucción por el sistema.

#### Scenario: Contenido con texto tipo instrucción no se ejecuta
- Dado un recurso o descripción de tool cuyo contenido incluye texto que simula una instrucción del sistema
- Cuando el adaptador procesa ese contenido
- Entonces se retorna como dato plano al llamador, sin ejecutarse ni interpretarse como comando

### Requirement: Frontera de solo lectura estricta

Ninguna operación del conector MCP DEBE mutar el servicio externo. La única invocación posible (`call_tool`) queda acotada a tools `readOnlyHint` + allowlist (ver `integration-ports`).

#### Scenario: No hay operación de escritura disponible
- Dado el conector MCP configurado
- Cuando se revisan sus operaciones disponibles
- Entonces ninguna crea, edita ni borra datos en el servidor externo

### Requirement: Aislamiento multi-tenant y credenciales no expuestas

Un conector MCP DEBE quedar scoped por `organization_id`. El token del servidor (si existe) NUNCA DEBE aparecer en respuestas de la API ni en logs.

#### Scenario: Conector MCP de otra organización no es accesible
- Dado un conector MCP de la organización A
- Cuando un usuario de la organización B intenta leer sus recursos o tools
- Entonces la API responde `404`

#### Scenario: Token del servidor MCP nunca expuesto
- Dado un conector MCP con token estático configurado
- Cuando se listan recursos, tools, o se inspeccionan los logs
- Entonces el token no aparece en ninguna respuesta ni en ningún log

### Requirement: Servidor MCP fake local para pruebas de contrato

El sistema DEBE incluir un servidor MCP fake in-process (sin red real) que responda `initialize`, `resources/list`, `resources/read`, `tools/list` y `tools/call` (con una tool `readOnlyHint` y una de escritura para validar el rechazo), usado para validar el contrato antes de un servidor real.

#### Scenario: El fake valida el contrato completo sin red real
- Dado el servidor MCP fake
- Cuando se ejecutan las pruebas de contrato de `mcp-connector` contra él
- Entonces responde a cada operación sin abrir ninguna conexión de red real, incluyendo el rechazo de su tool de escritura

## Referencias
- `openspec/changes/19-mcp-connector/proposal.md`
- `openspec/changes/19-mcp-connector/specs/integration-ports/spec.md` (puerto `external_resources`, frontera de solo lectura)
- `openspec/changes/19-mcp-connector/specs/connectors/spec.md` (credencial directa, `credential_kind = none`)
- `openspec/specs/api-conventions/spec.md` (envelope, formato de errores)
- `openspec/specs/multi-tenancy/spec.md` (aislamiento por `organization_id`)
