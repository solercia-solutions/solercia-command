# integration-ports Specification

> **Origen**: cambio [14-integration-ports](../../../changes/14-integration-ports/proposal.md)

## Propósito

Núcleo hexagonal **solo-lectura** para leer insumos externos (correo, calendario, tareas externas, notas/transcripciones de reuniones y tickets/casos) sin acoplar el negocio a un proveedor específico (Microsoft Graph, Google, GLPI, etc.). Un adaptador nuevo se registra sin editar el núcleo; el núcleo lee el comportamiento desde el adaptador, nunca con `if provider == ...`. Los adaptadores reales (Microsoft 365, Google, GLPI, Jira, MCP) se conectan en cambios futuros (15–19) sobre esta base, sin tocarla.

## Ubicación

`backend/app/integrations/`: `ports.py` (protocolos de lectura por capacidad), `registry.py` (registro de adaptadores), `oauth.py` (handshake genérico — orquesta `authorize`/`callback` delegando en el adaptador), `crypto.py` (cifrado simétrico de tokens), `adapters/fake.py` (adaptador de pruebas en memoria).

## Requisitos

### Requirement: Puertos de lectura por capacidad

El núcleo DEBE exponer un puerto (protocolo/interfaz) de solo lectura por cada capacidad soportada: correo, calendario, tareas externas, notas/transcripciones de reuniones y tickets/casos. Cuando dos proveedores comparten semántica equivalente (ej. Outlook y Gmail para correo), DEBEN implementar el MISMO puerto en lugar de puertos separados por proveedor.

#### Scenario: Un puerto sirve a varios proveedores de correo
- Dado el puerto de lectura de correo (`MailReadPort`)
- Cuando un adaptador de Outlook y uno de Gmail implementan la capacidad "correo"
- Entonces ambos exponen el mismo contrato de puerto, sin puertos duplicados por proveedor

#### Scenario: Ningún puerto expone escritura
- Dado cualquiera de los puertos definidos (correo, calendario, tareas externas, notas, tickets)
- Cuando se revisa su contrato
- Entonces solo define operaciones de lectura; no existe ningún método de creación, edición o respuesta hacia el proveedor

### Requirement: Registro de adaptadores extensible en import-time

El sistema DEBE mantener un registro de adaptadores poblado en import-time (mismo precedente que `app/notify/registry.py`). Agregar un adaptador nuevo DEBE requerir únicamente registrar la clase nueva, sin editar `ports.py`, `oauth.py` ni ningún otro archivo del núcleo.

#### Scenario: Adaptador nuevo se registra sin tocar el núcleo
- Dado un adaptador de prueba implementado en un módulo aparte
- Cuando se registra en `registry.py` en import-time
- Entonces el núcleo lo reconoce por su `provider` sin que se haya editado `ports.py` ni `oauth.py`

#### Scenario: Consulta del registro por proveedor
- Dado dos adaptadores registrados con `provider` distinto
- Cuando el núcleo busca un adaptador por su `provider`
- Entonces obtiene la instancia correcta sin recorrer condicionales `if provider == ...` en el código de negocio

### Requirement: Identidad de personas asignadas en el puerto de tickets

El DTO `Ticket` DEBE incluir una colección `assignees` con la identidad de cada persona externa asignada al caso (id externo, nombre, correo y campo de documento cuando el proveedor lo exponga), además del `requester` ya existente. El puerto `TicketReaderPort` DEBE poblar `assignees` para cualquier proveedor que module la relación ticket↔persona por rol (ej. "asignado"), no solo para GLPI.

#### Scenario: Ticket con asignado incluye su identidad completa
- Dado un ticket externo con una persona asignada
- Cuando el adaptador lo traduce al DTO `Ticket`
- Entonces `assignees` contiene al menos un elemento con id/nombre/correo de esa persona

#### Scenario: Ticket sin asignado expone lista vacía
- Dado un ticket externo sin ninguna persona asignada
- Cuando el adaptador lo traduce al DTO `Ticket`
- Entonces `assignees` es una lista vacía, nunca `null`

### Requirement: Puerto de solo lectura de recursos externos (`external_resources`)

El núcleo DEBE exponer un puerto de solo lectura `ExternalResourceReaderPort` para la capacidad `external_resources`, con las operaciones `list_resources`, `read_resource(uri)` y `list_tools` (descubrimiento), y DTOs agnósticos del proveedor: `ExternalResource`, `ExternalTool`, `ExternalResourceContent`. El puerto PUEDE declarar `call_tool`, pero esta operación DEBE quedar gateada por el enforcement de solo lectura del adaptador (default-deny + `readOnlyHint` + allowlist); el puerto en sí NUNCA ejecuta ni interpreta el contenido devuelto por el proveedor.

#### Scenario: El puerto expone descubrimiento y lectura sin credenciales de escritura
- Dado un adaptador que implementa la capacidad `external_resources`
- Cuando el núcleo invoca `list_resources`, `read_resource` o `list_tools` a través del puerto
- Entonces recibe DTOs agnósticos del proveedor (`ExternalResource`/`ExternalTool`/`ExternalResourceContent`), sin exponer detalles del transporte concreto

#### Scenario: `call_tool` solo está disponible si el adaptador declara enforcement de solo lectura
- Dado un adaptador que implementa `external_resources` y declara `call_tool`
- Cuando el núcleo intenta invocar `call_tool` sin que el adaptador aplique default-deny + `readOnlyHint` + allowlist
- Entonces el adaptador queda fuera de contrato para esa operación; el núcleo no expone `call_tool` sin ese enforcement

### Requirement: Protocolo de adaptador uniforme

Todo adaptador DEBE declarar: `provider`, las capacidades que soporta (subconjunto de correo/calendario/tareas externas/notas/tickets/**recursos externos**), el modo de adquisición de credencial y los puertos de lectura que implementa. El modo de adquisición de credencial PUEDE ser **intercambio de tokens OAuth** (el núcleo orquesta `authorize`/`callback` invocando al adaptador, sin conocer los detalles del proveedor) O **adquisición directa** (token estático o sin credencial, declarada explícitamente por el adaptador), en cuyo caso el núcleo NO orquesta `authorize`/`callback` para ese adaptador.

Para `credential_kind=oauth`, el adaptador DEBE declarar el intercambio de tokens OAuth (canje de código por tokens) y el núcleo orquesta `authorize`/`callback` invocándolo. Para `credential_kind=api_token`, el adaptador DEBE declarar un método de validación/inicio de sesión directo con las credenciales ya registradas (ej. `initSession` de GLPI), sin `authorize_url` ni `exchange_code`; el núcleo NO DEBE generar `state` ni redirección de navegador para este tipo de credencial. Para adaptadores con **adquisición directa de credencial** (token/none), el núcleo acepta la credencial en el registro sin orquestar `authorize`/`callback`.

#### Scenario: El núcleo delega el canje de tokens al adaptador
- Dado un adaptador que declara soporte de intercambio de tokens OAuth
- Cuando el núcleo recibe el código de autorización en el callback
- Entonces delega el canje de tokens al adaptador correspondiente por su `provider`, sin lógica específica del proveedor en el núcleo

#### Scenario: Adaptador que no soporta una capacidad queda excluido de ese puerto
- Dado un adaptador que solo declara soporte de "correo"
- Cuando el núcleo intenta usarlo para el puerto de "calendario"
- Entonces el adaptador no aparece disponible para ese puerto

#### Scenario: Adaptador con adquisición directa de credencial omite authorize/callback
- Dado un adaptador (ej. `mcp`) que declara adquisición directa de credencial (token estático o sin credencial)
- Cuando se registra un conector para ese adaptador
- Entonces el núcleo acepta la credencial directamente en el registro, sin generar `state` ni exigir el flujo `authorize`/`callback`

### Requirement: Adaptador fake en memoria para pruebas de contrato

El sistema DEBE incluir un adaptador `fake` en memoria, sin llamadas HTTP reales, capaz de simular el flujo OAuth (`authorize`/`callback`) y de responder a cada puerto de lectura con datos de prueba. DEBE usarse para validar la forma de los puertos y del protocolo de adaptador antes de que exista un adaptador real.

#### Scenario: El fake pasa las pruebas de contrato de cada puerto
- Dado el adaptador `fake` registrado
- Cuando se ejecutan las pruebas de contrato de correo, calendario, tareas externas, notas y tickets
- Entonces el fake responde a cada puerto sin realizar ninguna llamada HTTP real

#### Scenario: El fake simula el flujo OAuth completo
- Dado el adaptador `fake` registrado como proveedor de prueba
- Cuando se ejecuta `authorize` seguido de `callback` contra el fake
- Entonces se completa el flujo (state generado, "tokens" simulados devueltos) sin tocar servicios externos

### Requirement: Frontera solo-lectura estricta en esta ola

Ningún puerto, adaptador ni el núcleo de integraciones DEBE exponer operaciones de escritura hacia el proveedor externo (crear evento, responder correo, crear ticket, mutar un recurso, etc.) en esta ola. La única excepción acotada es `call_tool` del puerto `external_resources`, y SOLO cuando el adaptador aplica default-deny + `readOnlyHint` + allowlist explícita por conector; esa excepción nunca habilita una operación cuyo propósito declarado sea escribir o mutar el servicio externo.

#### Scenario: Los puertos no tienen método de escritura que invocar
- Dado los puertos definidos en `ports.py`
- Cuando se busca un método de escritura hacia el proveedor (crear, editar, responder, mutar)
- Entonces no existe tal método en ningún puerto del núcleo, salvo `call_tool` gateado de `external_resources`

#### Scenario: El protocolo de adaptador no declara operaciones de escritura
- Dado el protocolo de adaptador definido para esta ola
- Cuando un adaptador nuevo lo implementa
- Entonces solo puede declarar capacidades de lectura y el modo de adquisición de credencial, nunca una operación de escritura hacia el proveedor

#### Scenario: `call_tool` sin enforcement de solo lectura no cuenta como excepción válida
- Dado un adaptador que declara `call_tool` sin default-deny, sin `readOnlyHint` o sin allowlist explícita
- Cuando se evalúa contra la frontera de solo lectura
- Entonces esa declaración viola la frontera y no queda amparada por la excepción de `external_resources`

## Referencias

- `openspec/changes/14-integration-ports/proposal.md`
- Precedente de registro: `backend/app/notify/registry.py` (patrón de registro de canales, aplicado aquí a adaptadores de integración)
- `openspec/specs/connectors/spec.md` (consume este núcleo desde la sección REST de conectores)
