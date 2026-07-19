# Design: 17 · Adaptador GLPI (casos + homologación de usuarios)

## Technical Approach

Dos piezas backend que respetan la separación **motor + módulo** del 14 y de `notify`:

1. **Adaptador `app/integrations/adapters/glpi/`** (paquete, no archivo suelto): I/O puro del protocolo REST de GLPI (`apirest.php`). Implementa `TicketReaderPort` del 14 y devuelve el DTO `Ticket` **agnóstico** (con `assignees`). Auth por `api_token` (App-Token + user_token → `session_token`), `session_token` cacheado en Redis con TTL. **Cero ORM, cero lógica de negocio** — el contrato hexagonal del 14 lo mantiene inerte respecto a la homologación.
2. **Módulo `app/modules/glpi_sync/`** (`router → service → repository`, patrón idéntico a `assets`/`connectors`): homologación, cola de "sin homologar", mapeos confirmados, y REST de disparo/resolución. Aquí vive el estado tenant-scoped y la lógica de negocio.

**Por qué separar así**: el adaptador es reutilizable y stateless (frontera del 14); la homologación es ORM tenant-scoped que NO puede vivir en el adaptador. La sync manual llama `get_adapter("glpi").port_for(Capability.tickets)` → `Ticket[]` y el service homologa. TDD estricto con `httpx.MockTransport` (sin GLPI real) + `fakeredis`.

> Decisión de nombre: el módulo es `glpi_sync` (no `glpi` como tanteaba la propuesta): su responsabilidad es *sync on-demand + homologación*, el protocolo GLPI ya lo posee el adaptador. **Supera** el `app/modules/glpi/` tentativo de la propuesta.

## Architecture Decisions

### Ubicación de la homologación: módulo propio vs. dentro del adaptador
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Adaptador puro (`integrations/adapters/glpi/`) + módulo `modules/glpi_sync/` | Espejo del 14: adaptador sin ORM, módulo sin protocolo GLPI | **Elegida** |
| Homologación dentro del adaptador | Mete ORM/tenant en la frontera stateless del 14; rompe `IntegrationAdapter` | Rechazada |

### Auth `api_token` como delta del 14 sin mega-Protocol
El 14 modela solo OAuth (`authorize_url/exchange_code/refresh`) y **rechazó** explícitamente los Protocol con métodos opcionales. GLPI no usa redirección de navegador.
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `credential_kind` en el adaptador + handshake `api_token` separado (`connect(raw)→AccountRef` vía initSession/killSession) | Respeta "un Protocol por responsabilidad"; el service del 14 ramifica por `credential_kind` | **Elegida** |
| Añadir métodos OAuth opcionales al adaptador GLPI | Ramas `None`, justo lo que el 14 descartó | Rechazada |

### Matching por nombre: `difflib` (stdlib) vs `pg_trgm`
`pg_trgm` está habilitado [migración `0008`], pero **`unaccent` NO** — y la normalización exigida es "lower + sin tildes".
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `difflib.SequenceMatcher` + normalización Python (`unicodedata` NFKD) | Cero dependencias, cero extensión nueva; control total de tildes/case; escala bien sobre el set acotado de usuarios/org que la sync manual recorre | **Elegida** |
| `pg_trgm similarity()` | Exige extensión `unaccent` (migración/ext nueva) para puntuar sin acentos | Rechazada |

Email y documento son **igualdad exacta normalizada indexada** (no fuzzy). `pg_trgm` sigue disponible para búsqueda del operador al resolver manual.

### `numero_documento`: unicidad global parcial
`User` **no** tiene `TenantMixin` [código: `users/models.py` sin `organization_id`] → es global. Índice **único parcial** `WHERE numero_documento IS NOT NULL` (permite muchos NULL). Resuelve la pregunta abierta de la propuesta: global, porque el modelo real no está tenant-scoped.

### Cola consolidada por persona (cabecera + detalle de casos)
Ratificado (gana el spec): la sync **dispara por caso** pero la cola **consolida por persona GLPI** — una **cabecera** `glpi_unmatched_assignees` por `(connector_id, glpi_user_id)` (datos del asignado, candidatos, estado) y un **detalle 1:N** `glpi_unmatched_cases` con cada caso afectado. Un caso nuevo de la misma persona se **agrega al detalle** de la cabecera existente (no crea otra fila de persona). Al resolver la **cabecera** se crea el `glpi_user_link` (glpi_user_id ↔ user_id), la cabecera pasa a `resolved` y el detalle queda como **histórico**. Re-sync idempotente: si ya existe link para ese `glpi_user_id` se salta la cola; si ya existe cabecera, solo se hace upsert del caso en el detalle.

## Deltas al 14 (aterrizan en el apply del 17)

| Archivo del 14 | Delta |
|---|---|
| `app/integrations/ports.py` | `class CredentialKind(StrEnum): oauth; api_token`. `IntegrationAdapter` gana `credential_kind`. Extraer OAuth a `OAuthHandshake`; nuevo `ApiTokenHandshake` (`connect`). |
| `app/integrations/dtos.py` | `Ticket` gana `assignees: tuple[ExternalPerson, ...]`; nuevo `ExternalPerson(external_id, display_name, email, document)`. |
| `app/modules/connectors/*` | Ramificación por `credential_kind`; conectar GLPI = guardar credenciales + initSession de validación (sin 302). |

## Data Flow

    POST /glpi-sync/run (admin|manager)
      → service resuelve el connector `glpi` de la org (UNIQUE(org, provider))
      → get_adapter("glpi").port_for(tickets).list_tickets(ctx)
          client: session_token (Redis) ?→ initSession(App-Token+user_token) → SETEX glpi:session:{connector_id}
          GET Ticket (Range paginado) + Ticket/{id}/Ticket_User(type=2) + User + UserEmail
          → Ticket(assignees=[ExternalPerson])   ← DTO agnóstico
      → por asignado: link existente? skip : cascada email→documento→nombre
          email/documento exacto → glpi_user_link (auto) ; nombre → candidatos → upsert cabecera(glpi_user_id) + append caso al detalle
    GET /glpi-sync/unmatched → cabeceras+detalle ; POST /unmatched/{id}/resolve → link + cabecera resolved (detalle = histórico)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/glpi/__init__.py` | Create | `register_adapter(GlpiAdapter())` import-time (precedente `fake`) |
| `app/integrations/adapters/glpi/adapter.py` | Create | `GlpiAdapter`: `credential_kind=api_token`, `capabilities={tickets}`, `port_for` |
| `app/integrations/adapters/glpi/client.py` | Create | httpx: initSession/killSession/Ticket/Ticket_User/User/UserEmail; paginación `Range`; valida `base_url` (esquema http(s) + `GLPI_BASE_URL_ALLOWLIST`) antes de cualquier request |
| `app/integrations/adapters/glpi/session.py` | Create | session_token en Redis (TTL) + re-init 1 vez en 401 |
| `app/integrations/adapters/glpi/mapper.py` | Create | JSON GLPI → `Ticket`/`ExternalPerson` (documento desde campo configurable) |
| `app/integrations/adapters/glpi/errors.py` | Create | `GlpiUnavailable`, `GlpiAuthError` (errores de dominio) |
| `app/modules/glpi_sync/{__init__,models,schemas,repository,service,router}.py` | Create | 3 modelos (link + cola cabecera/detalle); matching; REST; org-scoped; RBAC |
| `app/integrations/{ports,dtos}.py` | Modify | Deltas 14 (CredentialKind, handshakes, `assignees`/`ExternalPerson`) |
| `app/modules/connectors/{service,models,schemas}.py` | Modify | Rama `api_token`; `credential_kind`+`settings` en `connectors` |
| `alembic/versions/0XXX_add_glpi_homologation.py` | Create | `numero_documento`+índice parcial; `connectors.credential_kind`+`connectors.settings JSONB NULL`; 3 tablas GLPI (links + cola cabecera/detalle) |
| `app/db_init.py` | Modify | Import de modelos + `import app.integrations.adapters.glpi` (registro) |
| `app/main.py` | Modify | `include_router(glpi_sync_router, prefix=API_PREFIX)` |
| `app/config.py` | Modify | `GLPI_SESSION_TTL_SECONDS` (default conservador < vida de sesión GLPI); `GLPI_BASE_URL_ALLOWLIST` (anti-SSRF, análogo a `OAUTH_REDIRECT_ALLOWLIST` del 14) |
| `requirements.txt` | Modify | **`httpx`** — hoy solo en `requirements-dev.txt`; primer adaptador HTTP real lo exige en runtime |
| `docs/diagrams/{er-model,c4-architecture}.md` | Modify | **Obligatorio en el apply** (ver Docs) |

## Interfaces / Contracts

```python
# Delta 14 — app/integrations/ports.py
class CredentialKind(StrEnum): oauth = "oauth"; api_token = "api_token"
class ApiTokenHandshake(Protocol):
    async def connect(self, raw: Mapping[str, str]) -> "AccountRef": ...  # initSession+killSession valida
# app/integrations/dtos.py
@dataclass(frozen=True)
class ExternalPerson: external_id: str; display_name: str | None; email: str | None; document: str | None
# Ticket += assignees: tuple[ExternalPerson, ...]

# GLPI apirest.php (anclado a v9.5+/10.x — VERIFICAR contra instancia destino, tarea):
#   POST {base}/initSession   headers: App-Token, Authorization: "user_token <tok>"  -> {session_token}
#   GET  {base}/killSession   headers: Session-Token, App-Token
#   GET  {base}/Ticket        header Range: 0-99 -> 206 + Content-Range: a-b/total ; fields id,name,content,status,priority,date
#   GET  {base}/Ticket/{id}/Ticket_User -> [{users_id, type}]  (type: 1=solicitante, 2=ASIGNADO, 3=observador)
#   GET  {base}/User/{id}     -> {id, name, realname, firstname, registration_number}
#   GET  {base}/User/{id}/UserEmail -> [{email, is_default}]
```

**Tablas nuevas** (mixins de `app/shared/base_model.py`):

| Tabla | Mixins | Campos clave | Unicidad |
|-------|--------|--------------|----------|
| `glpi_user_links` | Pk+Timestamp+SoftDelete+Audit+Tenant | `connector_id FK→connectors CASCADE`, `glpi_user_id String(64)`, `user_id FK→users CASCADE`, `match_method Enum(email\|document\|name\|manual, native_enum=False)`, `glpi_username?`, `glpi_email?` | `UNIQUE(connector_id, glpi_user_id)` |
| `glpi_unmatched_assignees` (cabecera) | Pk+Timestamp+Audit+Tenant | `connector_id FK→connectors CASCADE`, `glpi_user_id String(64)`, `glpi_username?`, `glpi_email?`, `glpi_document?`, `candidates JSONB`, `status Enum(pending\|resolved\|ignored, native_enum=False) default pending`, `resolved_user_id FK→users SET NULL?`, `resolved_at?` | `UNIQUE(connector_id, glpi_user_id)` (una fila por persona) |
| `glpi_unmatched_cases` (detalle 1:N) | Pk+Timestamp | `unmatched_assignee_id FK→glpi_unmatched_assignees CASCADE`, `glpi_ticket_id String(64)`, `glpi_ticket_title?`, `glpi_ticket_status?` | `UNIQUE(unmatched_assignee_id, glpi_ticket_id)` (idempotente por caso) |

**Columnas modificadas**: `users.numero_documento String(32)?` + único parcial; `connectors.credential_kind`, `connectors.settings JSONB NULL` (config genérica no-secreta: `base_url`, `document_field`). El 17 es **dueño** de `connectors.settings` (primer apply de la serie 17→18→19; 18 y 19 NO agregan columna, solo consumen `settings` con su propio namespace). Secretos GLPI reutilizan `connection_credentials`: `access_token_enc`=user_token, `refresh_token_enc`=App-Token, `token_type="glpi"`, `expires_at=NULL` (la vida de sesión la maneja Redis).

## Algoritmo de homologación (por asignado)

```
norm_email(e)   = e.strip().lower()
norm_doc(d)     = ''.join(c for c in d if c.isdigit())
norm_name(s)    = collapse_ws(strip_accents(s).lower())   # unicodedata NFKD
1. link(connector, glpi_user_id) existe?        -> skip (ya homologado)
2. norm_email == norm_email(user.email)?         -> link(match_method=email)     [auto]
3. norm_doc  == user.numero_documento?           -> link(match_method=document)  [auto]
4. difflib ratio(norm_name GLPI, norm_name user) sobre usuarios activos de la org
   -> candidates=[{user_id, score, reason}] ordenados desc
   -> upsert cabecera(connector, glpi_user_id) + append caso al detalle, status=pending  [NUNCA auto]
```
Homónimos: dos usuarios con el mismo nombre normalizado → ambos como candidatos, la fila **permanece `pending`** (confirmación manual obligatoria). Nombre GLPI = `firstname + realname`; nombre plataforma = `primer_nombre segundo_nombre primer_apellido segundo_apellido`.

## Endpoints (`/api/v1/glpi-sync`) + RBAC

| Método | Ruta | Permiso |
|--------|------|---------|
| POST | `/glpi-sync/run` | `require_role(admin, manager)` |
| GET | `/glpi-sync/unmatched` | `require_role(admin, manager)` (visibilidad manager+) |
| POST | `/glpi-sync/unmatched/{id}/resolve` (body: `user_id`) | `require_role(admin, manager)` |
| POST | `/glpi-sync/unmatched/{id}/ignore` | `require_role(admin, manager)` |
| GET | `/glpi-sync/links` | `require_role(admin, manager)` |
| DELETE | `/glpi-sync/links/{id}` | `require_role(admin, manager)` |

Coherente con el 14: `require_role(MemberRole.admin, MemberRole.manager)` sobre `OrganizationMember.role` [14: `app/dependencies.py:149`]. Tokens/documentos JAMÁS en respuestas ni logs.

## Testing Strategy (TDD estricto)

| Layer | What | Approach |
|-------|------|----------|
| Unit adaptador | initSession/killSession; session_token en Redis + reuso; 401→re-init 1 vez+retry; GLPI caído→`GlpiUnavailable`; paginación `Range` ensamblada; `Ticket.assignees` desde Ticket_User type 2 | `httpx.MockTransport` + fixtures JSON reales de GLPI; `fakeredis` |
| Unit homologación | cascada email/documento/nombre; normalización tildes/case/puntos-cédula; homónimos NO auto-confirman; re-sync idempotente salta lo ya enlazado | pytest sin BD |
| Integration `test_glpi_sync.py` | run→cabecera+detalle poblados; segundo caso de la misma persona→se **agrega al detalle** (no duplica cabecera); resolve→link + cabecera `resolved` (detalle histórico); ignore; list cola/links; RBAC (member/viewer→403); multi-tenant (cola org A invisible a org B) | `client` ASGI + fixtures 01 + `two_orgs` |
| Seguridad tokens | App-Token/user_token/session_token nunca en JSON ni logs | asserts sobre respuestas y captura de logs |
| Seguridad SSRF (RED) | `base_url` sin esquema http(s) o fuera de `GLPI_BASE_URL_ALLOWLIST` → rechazado **antes** de cualquier request | conectar/sync con `base_url` interno/no-allowlist → error de dominio, cero HTTP saliente (mock transport sin invocaciones) |

Fixtures JSON en `tests/fixtures/glpi/` (initSession, ticket_list con `Content-Range`, ticket_user, user, user_email).

## Threat Matrix

N/A para los ejes formales (routing/shell, subprocess, automatización VCS/PR, clasificación de ejecutables): el adaptador es cliente HTTP, no shell/subprocess. Los riesgos propios se enumeran como **Security Requirements → RED**: (1) secretos cifrados en reposo y ausentes de respuestas/logs; (2) **SSRF**: `base_url` admin-config → validar esquema http(s) + `GLPI_BASE_URL_ALLOWLIST` [análogo a `OAUTH_REDIRECT_ALLOWLIST` del 14] **antes** de cualquier request (**test RED** en Testing Strategy); (3) aislamiento multi-tenant en cola/links/sync por `organization_id`.

## Docs (obligatorio en el apply, mismo commit del código correspondiente)

- `docs/diagrams/er-model.md`: `glpi_user_links`, `glpi_unmatched_assignees` (cabecera) **1:N** `glpi_unmatched_cases` (detalle), `users.numero_documento`, `connectors.credential_kind`, `connectors.settings JSONB`.
- `docs/diagrams/c4-architecture.md`: adaptador **GLPI** dentro de *Integrations* + módulo `glpi_sync` (cola/mapeos/REST).

## Migration / Rollout

Migración única `0XXX_add_glpi_homologation`. **`down_revision` = head vigente al aplicar** — el 17 aterriza DESPUÉS de 14/20/21; el rev exacto **NO se hardcodea**: **tarea de verificación** = correr `alembic heads` **en vivo** justo antes del apply y anclar el `down_revision` real. `upgrade()`: `numero_documento`+único parcial, `connectors.credential_kind`+`connectors.settings JSONB NULL`, `glpi_user_links`, `glpi_unmatched_assignees` (cabecera), `glpi_unmatched_cases` (detalle). `downgrade()` inverso limpio (drop `glpi_unmatched_cases` → `glpi_unmatched_assignees` → `glpi_user_links` → `connectors.settings` + `connectors.credential_kind` → `numero_documento`), round-trip sin filas vivas. Sin el adaptador `glpi` registrado el núcleo del 14 queda intacto. Rollback = revertir el merge.

## Rejected Alternatives (resumen)

- `pg_trgm/unaccent` para nombre → `difflib` stdlib (sin extensión/dep nueva; control de tildes).
- Métodos OAuth opcionales en el adaptador → `credential_kind` + `ApiTokenHandshake` (fiel al 14).
- Fila por caso individual → **cabecera por persona `(connector_id, glpi_user_id)` + detalle 1:N `glpi_unmatched_cases`** (disparo por caso, consolidación por persona; ratificado por el spec).
- `numero_documento` único por org → **único global parcial** (User no es tenant-scoped en el código real).
- Homologación en el adaptador → módulo `glpi_sync` (adaptador sin ORM).
- Columna secreta nueva en credenciales → reuso de `access_token_enc`/`refresh_token_enc` (user_token/App-Token).

## Open Questions

- [ ] `down_revision` exacto: fijar en el apply tras `alembic heads` (post 14/20/21).
- [ ] Nombres de campos GLPI (`registration_number`, `Ticket_User.type=2`): verificar contra la versión de la instancia destino; el campo de cédula es configurable (`connectors.settings.document_field`, default `registration_number`).
- [ ] TTL de `session_token`: confirmar la vida de sesión del servidor GLPI destino para fijar `GLPI_SESSION_TTL_SECONDS` por debajo de ella.
