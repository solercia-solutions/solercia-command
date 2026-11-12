# Proposal: 17 · Adaptador GLPI (casos + homologación de usuarios)

## Intent

Extraer casos/soportes de GLPI (tickets con su técnico asignado) sobre el núcleo read-only del 14 y **homologar** cada persona asignada contra los usuarios de la plataforma por correo, número de documento o nombre. Lo que no se homologue de forma determinística cae en una **cola visible "sin homologar"** para resolución manual, sin perder la trazabilidad del responsable real de cada caso.

### Anclaje API REST de GLPI (`apirest.php`)

| Recurso | Uso |
|---|---|
| `initSession` / `killSession` | Auth `App-Token` + `user_token` (o login/pass) → `session_token`; `Session-Token`+`App-Token` en cada llamada |
| `Ticket` / `Ticket/:id` | Casos: `name`, `content`, `status`, `priority`, `date` (paginación por header `Range`) |
| `Ticket_User` | Vínculo ticket↔usuario por `type` — **asignado = type 2** (1 solicitante, 3 observador) |
| `User` + `UserEmail` | `realname`/`firstname`, `registration_number` (portador usual de la cédula), correo por defecto |

> A verificar contra la versión GLPI destino en spec/design.

## Scope

### In Scope
- Adaptador `glpi` (capability `tickets`) registrado en el núcleo del 14; auth por **api_token** (no OAuth): App-Token+user_token cifrados, `session_token` cacheado en Redis con TTL y re-init al vencer.
- Extracción de casos con **asignados** (Ticket_User type 2 → User).
- **Motor de homologación**: determinístico por correo y documento; heurístico por nombre (normalizado, sin acentos) que solo sugiere, nunca auto-confirma.
- Persistencia nueva: `glpi_user_links` (mapeos confirmados) + `glpi_unmatched_assignees` (cola de pendientes con candidatos sugeridos).
- REST: listar/resolver/ignorar la cola; listar/revocar mapeos.
- Columna `users.numero_documento` (nullable, index) para habilitar el match por cédula.

### Out of Scope
- Almacenar casos como ítems de entrada (cambio 22). Escritura hacia GLPI. Auto-confirmar el match por nombre. Adaptadores 15/16/18/19. Frontend.

## Extensiones mínimas al 14 — **coordinación del orquestador**

El 14 modela **solo OAuth**. GLPI exige:
1. **Credencial `api_token`**: `credential_kind = oauth|api_token`; ruta de auth sin redirección de navegador (registro directo de tokens → initSession). Afecta `integration-ports` (protocolo de adaptador) y `connectors` (modelo de credenciales).
2. **Asignados en el DTO `Ticket`**: hoy solo trae `requester`; añadir `assignees` (identidad de persona externa: id/nombre/correo/registro) — es el ancla de la homologación.

> Decidir con el orquestador si estas extensiones aterrizan en el 14 (aún no aplicado) o como deltas `modified` del 17.

## Capabilities

### New Capabilities
- `glpi-adapter`: adaptador GLPI (api_token, initSession, lectura de tickets + asignados).
- `user-homologation`: motor de match + tablas de mapeos y cola + REST de resolución.

### Modified Capabilities
- `integration-ports`: credencial `api_token` + `assignees` en el DTO `Ticket` (coordinación).
- `connectors`: `credential_kind` en el modelo de credenciales (coordinación).

## Approach

Orden de match por asignado: **correo → documento → nombre**. Los dos primeros (normalizados) auto-confirman con `match_method`; el nombre produce candidatos y encola. La cola se deduplica por persona GLPI (una fila por `glpi_user_id`, con la lista de casos afectados); al resolver se crea el `glpi_user_link` y se cierran los casos asociados. Adaptador en `app/integrations/adapters/glpi.py`; homologación en `app/modules/glpi/` (router→service→repository). TDD estricto.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `app/integrations/adapters/glpi.py` | New | Adaptador GLPI api_token + lectura de tickets/asignados |
| `app/modules/glpi/` | New | Homologación, cola, mapeos, REST |
| `app/modules/users/models.py` + migración | Modified | Columna `numero_documento` |
| 14 `integration-ports` / `connectors` | Modified | api_token + `assignees` (coordinación) |
| `docs/diagrams/er-model.md` | Modified | **Obligatorio en apply**: `glpi_user_links`, `glpi_unmatched_assignees`, `numero_documento` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Falso positivo por nombre (homónimos) | High | El nombre nunca auto-confirma; confirmación manual obligatoria |
| Cédula ausente en GLPI o en la plataforma | Med | Match por documento opcional; degrada a correo/nombre |
| `session_token` de GLPI expira | Med | Cache Redis con TTL + re-init; tokens cifrados en reposo |
| 14 sin credencial api_token | High | Extensión declarada; bloquea hasta coordinar con el 14 |

## Rollback Plan

Área aislada. Revertir el merge; el `downgrade` elimina `glpi_user_links`, `glpi_unmatched_assignees` y `numero_documento`. Sin el adaptador `glpi` registrado, el núcleo del 14 queda intacto y no afecta ningún flujo existente.

## Dependencies

- **14-integration-ports** (núcleo hexagonal + modelo de credenciales + DTO `Ticket`), incluidas las dos extensiones api_token/`assignees`.
- Redis (session token GLPI). Instancia GLPI de prueba para las pruebas de integración.

## Success Criteria

- [ ] El adaptador `glpi` lee casos con asignados vía initSession/Ticket/Ticket_User/User sin tocar el núcleo del 14.
- [ ] El match determinístico por correo y documento auto-confirma; el nombre solo sugiere.
- [ ] Los no homologados quedan en la cola y se resuelven manualmente creando el mapeo.
- [ ] `numero_documento` disponible; tokens GLPI cifrados, nunca en respuestas ni logs.
- [ ] `docs/diagrams/er-model.md` actualizado (2 tablas + columna).

## Proposal question round

> Ejecutor delegado (sin diálogo en vivo). Supuestos a ratificar antes de spec/design:

1. ¿La cola se deduplica por persona GLPI (asumido) o por caso individual?
2. ¿`numero_documento` es único global o único por organización?
3. ¿El `registration_number` de GLPI porta la cédula, o se mapea otro campo/plugin?
4. ¿Algoritmo de similitud de nombre: exacto normalizado (asumido) o fuzzy con umbral?
5. ¿La sincronización es manual (endpoint) o programada (APScheduler)?
