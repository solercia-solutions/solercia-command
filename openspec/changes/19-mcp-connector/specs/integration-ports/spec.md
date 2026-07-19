# Delta for integration-ports

> Origen: cambio [19-mcp-connector](../../proposal.md). Extiende el núcleo de [14-integration-ports](../../../14-integration-ports/specs/integration-ports/spec.md).

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Protocolo de adaptador uniforme

Todo adaptador DEBE declarar: `provider`, las capacidades que soporta (subconjunto de correo/calendario/tareas externas/notas/tickets/**recursos externos**), el modo de adquisición de credencial y los puertos de lectura que implementa. El modo de adquisición de credencial PUEDE ser **intercambio de tokens OAuth** (el núcleo orquesta `authorize`/`callback` invocando al adaptador, sin conocer los detalles del proveedor) O **adquisición directa** (token estático o sin credencial, declarada explícitamente por el adaptador), en cuyo caso el núcleo NO orquesta `authorize`/`callback` para ese adaptador.
(Previously: solo contemplaba intercambio de tokens OAuth vía `authorize`/`callback`; ahora admite también adquisición directa de credencial (token/none) para adaptadores como `mcp`.)

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

### Requirement: Frontera solo-lectura estricta en esta ola

Ningún puerto, adaptador ni el núcleo de integraciones DEBE exponer operaciones de escritura hacia el proveedor externo (crear evento, responder correo, crear ticket, mutar un recurso, etc.) en esta ola. La única excepción acotada es `call_tool` del puerto `external_resources`, y SOLO cuando el adaptador aplica default-deny + `readOnlyHint` + allowlist explícita por conector; esa excepción nunca habilita una operación cuyo propósito declarado sea escribir o mutar el servicio externo.
(Previously: prohibición absoluta sin excepciones; ahora se acota la excepción explícita y gateada de `call_tool` de solo lectura sobre `external_resources`.)

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
- `openspec/changes/19-mcp-connector/proposal.md`
- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md` (base)
- `openspec/changes/19-mcp-connector/specs/mcp-connector/spec.md` (enforcement concreto de solo lectura)
