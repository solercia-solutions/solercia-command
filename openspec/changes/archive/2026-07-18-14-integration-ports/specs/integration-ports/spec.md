# integration-ports Specification

> **Origen**: cambio [14-integration-ports](../../proposal.md)

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

### Requirement: Protocolo de adaptador uniforme

Todo adaptador DEBE declarar: `provider`, las capacidades que soporta (subconjunto de correo/calendario/tareas externas/notas/tickets), el intercambio de tokens OAuth (canje de código por tokens) y los puertos de lectura que implementa. El núcleo DEBE orquestar `authorize`/`callback` invocando al adaptador a través de este contrato, sin conocer los detalles del proveedor.

#### Scenario: El núcleo delega el canje de tokens al adaptador
- Dado un adaptador que declara soporte de intercambio de tokens OAuth
- Cuando el núcleo recibe el código de autorización en el callback
- Entonces delega el canje de tokens al adaptador correspondiente por su `provider`, sin lógica específica del proveedor en el núcleo

#### Scenario: Adaptador que no soporta una capacidad queda excluido de ese puerto
- Dado un adaptador que solo declara soporte de "correo"
- Cuando el núcleo intenta usarlo para el puerto de "calendario"
- Entonces el adaptador no aparece disponible para ese puerto

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

Ningún puerto, adaptador ni el núcleo de integraciones DEBE exponer operaciones de escritura hacia el proveedor externo (crear evento, responder correo, crear ticket, etc.) en esta ola. Esa capacidad queda explícitamente fuera de alcance.

#### Scenario: Los puertos no tienen método de escritura que invocar
- Dado los puertos definidos en `ports.py`
- Cuando se busca un método de escritura hacia el proveedor (crear, editar, responder)
- Entonces no existe tal método en ningún puerto del núcleo

#### Scenario: El protocolo de adaptador no declara operaciones de escritura
- Dado el protocolo de adaptador definido para esta ola
- Cuando un adaptador nuevo lo implementa
- Entonces solo puede declarar capacidades de lectura y el intercambio de tokens OAuth, nunca una operación de escritura hacia el proveedor

## Referencias

- `openspec/changes/14-integration-ports/proposal.md`
- Precedente de registro: `backend/app/notify/registry.py` (patrón de registro de canales, aplicado aquí a adaptadores de integración)
- `openspec/specs/connectors/spec.md` (consume este núcleo desde la sección REST de conectores)
