# Delta for integration-ports

> **Origen**: cambio [17-adapter-glpi](../../proposal.md) sobre el núcleo [14-integration-ports](../../../14-integration-ports/specs/integration-ports/spec.md)

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Protocolo de adaptador uniforme

Todo adaptador DEBE declarar: `provider`, las capacidades que soporta (subconjunto de correo/calendario/tareas externas/notas/tickets), su `credential_kind` (`oauth` o `api_token`) y los puertos de lectura que implementa. Para `credential_kind=oauth`, el adaptador DEBE declarar el intercambio de tokens OAuth (canje de código por tokens) y el núcleo orquesta `authorize`/`callback` invocándolo. Para `credential_kind=api_token`, el adaptador DEBE declarar un método de validación/inicio de sesión directo con las credenciales ya registradas (ej. `initSession` de GLPI), sin `authorize_url` ni `exchange_code`; el núcleo NO DEBE generar `state` ni redirección de navegador para este tipo de credencial.
(Previously: solo declaraba el intercambio de tokens OAuth; no existía el concepto `credential_kind` ni una ruta de autenticación directa)

#### Scenario: El núcleo delega el canje de tokens al adaptador
- Dado un adaptador `oauth` que declara soporte de intercambio de tokens
- Cuando el núcleo recibe el código de autorización en el callback
- Entonces delega el canje de tokens al adaptador correspondiente por su `provider`, sin lógica específica del proveedor en el núcleo

#### Scenario: Adaptador que no soporta una capacidad queda excluido de ese puerto
- Dado un adaptador que solo declara soporte de "correo"
- Cuando el núcleo intenta usarlo para el puerto de "calendario"
- Entonces el adaptador no aparece disponible para ese puerto

#### Scenario: Adaptador `api_token` no participa del flujo OAuth
- Dado un adaptador registrado con `credential_kind=api_token`
- Cuando el núcleo intenta iniciar `authorize`/`callback` sobre él
- Entonces el núcleo rechaza la operación porque el adaptador no declara intercambio de tokens OAuth

## Referencias

- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md` (spec base)
- `openspec/changes/17-adapter-glpi/proposal.md`
