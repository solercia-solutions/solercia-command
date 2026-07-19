# user-homologation Specification

> **Origen**: cambio [17-adapter-glpi](../../proposal.md)

## Propósito

Homologar cada persona asignada de un caso GLPI contra un usuario real de la plataforma, con una cascada determinística (correo → documento → nombre) que solo auto-confirma los dos primeros niveles. El nombre nunca auto-confirma: siempre cae en una cola visible de pendientes con resolución manual. Los mapeos confirmados persisten y se reutilizan en sincronizaciones futuras.

## Ubicación

`backend/app/modules/glpi/` (router → service → repository).

## Requisitos

### Requirement: Documento de identidad para homologación determinística

`users.numero_documento` DEBE ser una columna nueva, nullable, con índice único parcial (`WHERE numero_documento IS NOT NULL`) a nivel de toda la plataforma (mismo alcance global que `email`, sin scoping por organización). Se usa como segundo nivel determinístico de la cascada de homologación.

#### Scenario: Dos usuarios sin documento coexisten
- Dado dos usuarios con `numero_documento` en `NULL`
- Cuando se guardan
- Entonces ambos persisten sin conflicto de unicidad

#### Scenario: Documento duplicado es rechazado
- Dado un usuario existente con `numero_documento="123"`
- Cuando se intenta asignar ese mismo valor a otro usuario
- Entonces la operación es rechazada por la restricción de unicidad

### Requirement: Cascada de homologación por asignado GLPI

Para cada persona asignada extraída de GLPI, el motor DEBE intentar, en este orden: (1) correo exacto normalizado (case-insensitive) contra `users.email`; (2) si no hay match, número de documento contra `users.numero_documento`, leyendo el campo GLPI portador del documento configurado por conector (su valor por defecto lo fija el diseño); (3) si tampoco hay match, nombre normalizado (sin acentos, sin mayúsculas) contra usuarios de la plataforma, generando candidatos que SOLO se sugieren. Los niveles (1) y (2) DEBEN auto-confirmar el mapeo con su `match_method`; el nivel (3) NUNCA DEBE auto-confirmar.

#### Scenario: Match por correo auto-confirma
- Dado un asignado GLPI cuyo correo coincide (normalizado) con el de un usuario de la plataforma
- Cuando corre la cascada
- Entonces se crea el `glpi_user_link` con `match_method=email`, sin pasar por documento ni nombre

#### Scenario: Match por documento auto-confirma
- Dado un asignado GLPI sin correo coincidente pero con documento coincidente
- Cuando corre la cascada
- Entonces se crea el `glpi_user_link` con `match_method=numero_documento`

#### Scenario: Sin correo ni documento, el nombre solo sugiere
- Dado un asignado GLPI sin correo ni documento coincidente, con nombre normalizado similar a un usuario de la plataforma
- Cuando corre la cascada
- Entonces el asignado cae en la cola de pendientes con ese usuario como candidato sugerido, sin crear ningún `glpi_user_link`

#### Scenario: Homónimos nunca auto-confirman
- Dado un nombre normalizado que coincide con DOS usuarios distintos de la plataforma
- Cuando corre la cascada
- Entonces ambos aparecen como candidatos sugeridos en la cola; ninguno se confirma automáticamente

### Requirement: Mapeos confirmados persistentes y revocables

`glpi_user_links` DEBE persistir el mapeo `glpi_user_id` (scoped por conector/organización) → `user_id` de la plataforma, con `match_method` y quién lo confirmó. Una vez confirmado, TODAS las sincronizaciones futuras para ese `glpi_user_id` DEBEN resolverse directo contra el mapeo, sin volver a correr la cascada. Roles `admin`/`manager` DEBEN poder listar y revocar un mapeo; al revocarlo, la persona vuelve a pasar por la cascada en la siguiente sincronización.

#### Scenario: Sincronización repetida reutiliza el mapeo
- Dado un `glpi_user_link` ya confirmado para una persona GLPI
- Cuando llega un nuevo caso de esa misma persona en una sincronización posterior
- Entonces se homologa directo contra el mapeo existente, sin generar entrada de cola ni repetir la cascada

#### Scenario: Admin revoca un mapeo
- Dado un `glpi_user_link` confirmado de la organización del admin
- Cuando lo revoca vía API
- Entonces deja de aplicarse; la siguiente sincronización de esa persona vuelve a pasar por la cascada

#### Scenario: Revocar mapeo ajeno o inexistente
- Dado un `glpi_user_link` inexistente o de otra organización
- Cuando se intenta revocar
- Entonces la API responde `404`

### Requirement: Cola de asignados sin homologar

Cada caso GLPI cuyo asignado no se homologó determinísticamente (ni por correo ni por documento) DEBE generar o actualizar una entrada visible en `glpi_unmatched_assignees`. Las entradas de la MISMA persona GLPI (mismo `glpi_user_id`) DEBEN consolidarse en un único registro con la lista de casos afectados, sin duplicar la persona en la cola.

#### Scenario: Primer caso sin homologar de una persona
- Dado un asignado GLPI sin match determinístico y sin entrada previa en la cola
- Cuando se procesa su caso
- Entonces se crea una entrada nueva en `glpi_unmatched_assignees` con ese caso

#### Scenario: Segundo caso sin homologar de la misma persona
- Dado una entrada existente en la cola para un `glpi_user_id`
- Cuando llega otro caso sin homologar de esa misma persona
- Entonces el caso se agrega a la entrada existente, sin crear una fila duplicada de la persona

### Requirement: Resolución manual de la cola

El sistema DEBE exponer listar, resolver e ignorar entradas de la cola vía API, gateado a roles `admin`/`manager`. Resolver una entrada (asignando un usuario de la plataforma) DEBE crear el `glpi_user_link` confirmado con `match_method=manual`, DEBE retirar la entrada de la cola, y DEBE homologar automáticamente los casos ya listados en ella y los que lleguen en sincronizaciones futuras para esa misma persona GLPI. Ignorar una entrada DEBE retirarla de la vista activa sin crear ningún mapeo.

#### Scenario: Resolver una entrada crea el mapeo y drena la cola
- Dado una entrada pendiente con candidatos sugeridos
- Cuando un admin la resuelve asignando el usuario correcto
- Entonces se crea el `glpi_user_link` y la entrada desaparece de la cola activa

#### Scenario: Sincronización futura homologa directo tras resolver
- Dado un `glpi_user_link` creado al resolver una entrada
- Cuando una sincronización posterior trae un caso nuevo de esa misma persona
- Entonces se homologa directo, sin volver a aparecer en la cola

#### Scenario: Ignorar una entrada sin crear mapeo
- Dado una entrada pendiente en la cola
- Cuando un admin la marca como ignorada
- Entonces se retira de la vista activa sin crear ningún `glpi_user_link`

### Requirement: Sincronización manual on-demand

El sistema DEBE exponer un endpoint de sincronización manual (`POST`) por conector que dispare la extracción de tickets con asignados y ejecute la cascada de homologación sobre cada uno. La sincronización programada queda fuera de alcance de esta ola.

#### Scenario: Admin dispara la sincronización
- Dado un conector `glpi` activo de la organización del admin
- Cuando llama el endpoint de sincronización manual
- Entonces se extraen los tickets, se homologan los que aplican determinísticamente y el resto actualiza la cola

#### Scenario: Sincronización sobre conector ajeno
- Dado un conector `glpi` de otra organización
- Cuando se intenta disparar su sincronización
- Entonces la API responde `404`

### Requirement: Aislamiento multi-tenant de la homologación

`glpi_user_links` y `glpi_unmatched_assignees` DEBEN estar scoped por organización (vía conector). Ningún mapeo ni entrada de cola de una organización DEBE ser visible ni resoluble desde otra organización.

#### Scenario: Cola de otra organización no es accesible
- Dado una entrada de la cola de la organización A
- Cuando un usuario de la organización B intenta listarla o resolverla
- Entonces la API responde `404` o la excluye del listado

## Referencias

- `openspec/changes/17-adapter-glpi/proposal.md`
- `openspec/changes/17-adapter-glpi/specs/glpi-adapter/spec.md` (extracción de tickets + `assignees`)
- `openspec/specs/multi-tenancy/spec.md` (aislamiento por `organization_id`)
