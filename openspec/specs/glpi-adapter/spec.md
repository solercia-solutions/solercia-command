# glpi-adapter Specification

> **Origen**: cambio [17-adapter-glpi](../../changes/archive/2026-07-19-17-adapter-glpi/proposal.md)

## Propósito

Adaptador de solo lectura para GLPI (`apirest.php`) que extrae casos (tickets) con su persona asignada, autenticándose por `credential_kind=api_token` (App-Token + user_token → `initSession`), sin tocar el núcleo de `integration-ports` ni exponer ninguna operación de escritura hacia GLPI.

## Ubicación

`backend/app/integrations/adapters/glpi.py`.

## Requisitos

### Requirement: Registro del adaptador `glpi` sobre el núcleo

El adaptador `glpi` DEBE registrarse en import-time (precedente `registry.py`) con `provider="glpi"`, `capabilities={tickets}` y `credential_kind=api_token`, sin editar `ports.py`, `oauth.py` ni ningún otro archivo del núcleo.

#### Scenario: Registro sin tocar el núcleo
- Dado el adaptador `glpi` implementado en su propio módulo
- Cuando se registra en `registry.py` en import-time
- Entonces el núcleo lo reconoce por `provider="glpi"` sin que se haya editado ningún archivo del núcleo

### Requirement: Autenticación api_token vía `initSession` con `session_token` cacheado

El adaptador DEBE autenticarse contra GLPI llamando `initSession` con el App-Token y el user_token descifrados del conector, y DEBE cachear el `session_token` resultante en Redis con TTL. Mientras el `session_token` cacheado sea válido, DEBE reutilizarlo en las llamadas subsecuentes (`Session-Token` + `App-Token`) sin volver a llamar `initSession`.

#### Scenario: Primera llamada inicia sesión y cachea
- Dado un conector `glpi` con credenciales válidas y sin `session_token` cacheado
- Cuando el adaptador ejecuta una lectura de tickets
- Entonces llama `initSession` y cachea el `session_token` resultante en Redis con TTL

#### Scenario: Llamada subsiguiente reutiliza el cache
- Dado un `session_token` vigente cacheado para el conector
- Cuando el adaptador ejecuta una nueva lectura
- Entonces reutiliza el `session_token` cacheado sin llamar `initSession` de nuevo

### Requirement: Reinicio de sesión ante expiración

Si GLPI responde que el `session_token` expiró o es inválido, el adaptador DEBE invalidar el valor cacheado y reiniciar sesión (`initSession`) automáticamente, reintentando la operación original UNA vez, de forma transparente al llamador.

#### Scenario: Expiración detectada durante una lectura
- Dado un `session_token` cacheado que GLPI rechaza por expirado
- Cuando el adaptador está listando tickets
- Entonces invalida el cache, reinicia sesión y completa la lectura sin error visible al llamador

#### Scenario: Reinicio de sesión falla
- Dado credenciales del conector revocadas en GLPI
- Cuando el adaptador intenta reiniciar sesión tras una expiración
- Entonces propaga un error controlado sin dejar un `session_token` inválido cacheado

### Requirement: Extracción de tickets con asignados

El adaptador DEBE listar tickets (`Ticket`) y, para cada uno, resolver sus personas asignadas consultando `Ticket_User` filtrando `type=2` (asignado) y resolviendo cada `users_id` contra `User`, poblando `assignees` del DTO `Ticket`. DEBE excluir solicitantes (`type=1`) y observadores (`type=3`) de `assignees`.

#### Scenario: Ticket con un técnico asignado
- Dado un ticket GLPI con un `Ticket_User` de `type=2`
- Cuando el adaptador lo traduce al DTO `Ticket`
- Entonces `assignees` contiene la identidad de esa persona (id, nombre, correo)

#### Scenario: Ticket con solicitante pero sin asignado
- Dado un ticket GLPI solo con `Ticket_User` de `type=1`
- Cuando el adaptador lo traduce al DTO `Ticket`
- Entonces `requester` queda poblado y `assignees` es una lista vacía

### Requirement: Frontera de solo lectura hacia GLPI

El adaptador NUNCA DEBE invocar operaciones de escritura de la API de GLPI (crear, editar o cerrar un ticket, etc.); únicamente `initSession`/`killSession` y lecturas `GET`.

#### Scenario: No existe ningún método de escritura
- Dado el código del adaptador `glpi`
- Cuando se revisan sus llamadas HTTP
- Entonces ninguna usa `POST`/`PUT`/`DELETE` sobre recursos de negocio de GLPI (solo `GET` y el ciclo de sesión)

### Requirement: GLPI inaccesible o credenciales inválidas

Ante timeout, error de red o rechazo de credenciales por parte de GLPI, el adaptador DEBE propagar un error claro y estructurado (sin credenciales ni tokens en el mensaje), sin dejar el conector en un estado inconsistente.

#### Scenario: GLPI no responde
- Dado que la instancia GLPI no responde (timeout)
- Cuando el adaptador intenta una lectura
- Entonces propaga un error claro y estructurado, sin caída silenciosa ni datos parciales

#### Scenario: Credenciales inválidas
- Dado un App-Token o user_token inválido
- Cuando el adaptador llama `initSession`
- Entonces la operación falla con un error claro, sin cachear ningún `session_token`

### Requirement: Aislamiento multi-tenant del adaptador

El adaptador DEBE operar únicamente con las credenciales del conector de la organización solicitante; el `session_token` cacheado en Redis DEBE aislarse por conector, sin compartirse entre organizaciones aunque apunten a la misma instancia GLPI.

#### Scenario: Dos organizaciones con conectores GLPI distintos
- Dado dos conectores `glpi` de organizaciones distintas
- Cuando ambas sincronizan en paralelo
- Entonces cada una usa su propio `session_token` cacheado, sin cruce de sesiones ni de datos

## Referencias

- `openspec/changes/archive/2026-07-19-17-adapter-glpi/proposal.md`
- `openspec/specs/integration-ports/spec.md` (DTO `Ticket.assignees`, `credential_kind`)
- `openspec/specs/connectors/spec.md` (registro directo de credenciales `api_token`)
