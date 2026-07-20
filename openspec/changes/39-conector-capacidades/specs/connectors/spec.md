# Delta for connectors

> Base: `openspec/specs/connectors/spec.md`. Este delta AGREGA dos requisitos
> nuevos (acciones por conector, verificación puntual); no modifica ningún
> requisito existente del CRUD/OAuth/RBAC ya especificado.

## ADDED Requirements

### Requirement: Acciones disponibles por conector derivadas de capabilities y estado de conexión

`GET /connectors/{connector_id}/actions` DEBE derivar la lista de acciones intersectando las `capabilities` del adaptador registrado (`get_adapter(provider).capabilities`) con un catálogo declarativo `Capability → descriptores de acción` (`tickets`→importar proyectos/importar historias/sincronizar; `mail`/`calendar`→leer correo/leer calendario; `external_resources`→explorar recursos/herramientas). El sistema NUNCA DEBE derivar esta lista mediante una condición `if provider == ...`. Cada acción DEBE incluir `key`, `label` (español colombiano formal), `capability`, `state` (`available` | `requires_connection` | `coming_soon`), `kind` (`navigate` | `execute`) y una `description` breve. El `state` DEBE calcularse según exista una `ConnectedAccount` activa del USUARIO QUE LLAMA (no de cualquier miembro de la organización): `available` si el usuario tiene cuenta activa y la operación ya está implementada; `requires_connection` si el usuario no tiene cuenta activa para ese conector; `coming_soon` si la acción existe en el catálogo pero su ejecución aún no está implementada (ej. importar vía API hasta que el cambio 40 aterrice, `key=jira_import` estable). El endpoint DEBE ser accesible a cualquier miembro autenticado (coherente con `GET /connectors`) y DEBE responder `404` si el conector es de otra organización.

#### Scenario: Jira conectado por el usuario devuelve acciones con estados correctos
- Dado un conector Jira con `ConnectedAccount` activa del usuario que llama
- Cuando llama `GET /connectors/{id}/actions`
- Entonces recibe la acción `key=jira_import` en `coming_soon`, y la acción de importar historias por archivo en `available`

#### Scenario: Usuario sin cuenta conectada recibe acciones bloqueadas
- Dado un conector Jira sin `ConnectedAccount` activa del usuario que llama
- Cuando llama `GET /connectors/{id}/actions`
- Entonces las acciones de esa capability llegan en `requires_connection`

#### Scenario: MCP expone acciones de exploración de recursos
- Dado un conector `mcp` con `ConnectedAccount` activa del usuario
- Cuando llama `GET /connectors/{id}/actions`
- Entonces recibe acciones para explorar recursos y herramientas en `available`

#### Scenario: Conector de otra organización
- Dado un conector de la organización A
- Cuando un usuario de la organización B llama `GET /connectors/{id}/actions`
- Entonces la API responde `404`

#### Scenario: Sin sesión
- Dado una petición sin token de autenticación
- Cuando se llama `GET /connectors/{id}/actions`
- Entonces la API responde `401`

### Requirement: Verificación puntual de conexión (probe)

`POST /connectors/{connector_id}/actions/probe` DEBE ejercer una operación de lectura real y acotada (`limit=1` o equivalente) sobre el puerto primario de la capability del adaptador, usando la `ConnectedAccount` del USUARIO QUE LLAMA (nunca la de otro miembro): Jira (listar proyectos accesibles al usuario), M365/Google (puerto de lectura de correo/calendario, sujeto a que el cambio 38 repare OAuth — mientras tanto la acción aparece `requires_connection`/`coming_soon`), MCP (`list_resources`). El probe NO DEBE persistir nada ni disparar un ciclo programado. DEBE devolver un resultado visible: éxito con un detalle concreto de lo verificado, o error con un mensaje claro en español colombiano formal cuando la verificación falla. DEBE responder `404` si el conector es de otra organización y un error controlado si el usuario que llama no tiene cuenta conectada.

#### Scenario: Probe exitoso muestra detalle real
- Dado un conector Jira con `ConnectedAccount` activa del usuario que llama
- Cuando llama `POST /connectors/{id}/actions/probe`
- Entonces recibe éxito con el detalle de los proyectos accesibles verificados

#### Scenario: Usuario sin cuenta conectada no puede probar
- Dado un conector sin `ConnectedAccount` activa del usuario que llama
- Cuando llama `POST /connectors/{id}/actions/probe`
- Entonces la API responde un error controlado y no ejerce ninguna operación externa

#### Scenario: Falla del proveedor externo
- Dado una credencial inválida o expirada en la cuenta conectada del usuario
- Cuando llama `POST /connectors/{id}/actions/probe`
- Entonces recibe un error con mensaje claro en español colombiano formal, sin excepción cruda

#### Scenario: Conector de otra organización
- Dado un conector de la organización A
- Cuando un usuario de la organización B llama `POST /connectors/{id}/actions/probe`
- Entonces la API responde `404`

#### Scenario: El probe no persiste nada
- Dado un probe exitoso sobre un conector Jira
- Cuando se inspecciona el estado del conector y sus cuentas tras el probe
- Entonces ninguna fila fue creada ni modificada
