# Design: 14 · Puertos de integración (núcleo hexagonal + conectores)

## Technical Approach

Dos piezas backend que espejan la separación **motor + módulo** ya establecida (`app/notify/` motor + `app/modules/notifications/` API):

1. **Motor `app/integrations/`** (hermano de `app/notify/`, `app/alerts/`, `app/email/`, `app/realtime/`): puertos de lectura por capacidad (`ports.py`), DTOs agnósticos (`dtos.py`), registro de adaptadores import-time (`registry.py`, precedente `app/notify/registry.py`), handshake OAuth genérico (`oauth.py`), cifrado Fernet (`crypto.py`), store de `state` en Redis con TTL (`state_store.py`) y adaptador fake (`adapters/fake.py`).
2. **Módulo `app/modules/connectors/`** (`router → service → repository`, patrón idéntico a `assets`): CRUD de conectores, `authorize`, callback, listar/desconectar cuentas, con RBAC de 02 y multi-tenant de `TenantMixin`.

El núcleo orquesta authorize/callback leyendo comportamiento DESDE el adaptador registrado (`get_adapter(provider)`), nunca `if provider == …`. Backend-only; solo el fake se registra en esta ola, así que el núcleo queda inerte. TDD estricto contra el fake (sin HTTP real).

## Architecture Decisions

### Estructura: motor `integrations/` + módulo `connectors/`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Motor `app/integrations/` (puertos/registro/oauth/crypto/fake) + módulo `app/modules/connectors/` (CRUD/API) | Espejo exacto de `notify` (motor) + `modules/notifications` (API): el motor no conoce HTTP/ORM del CRUD, el módulo no conoce proveedores | **Elegida** |
| Todo dentro de `app/modules/connectors/` | Mezcla el contrato hexagonal reutilizable (15–19) con el CRUD tenant-scoped; rompe el precedente motor/módulo | Rechazada |

### Un Protocol por capacidad + adaptador declara lo que soporta

Precedente `app/notify/ports.py` (protocolos disjuntos, no uno con métodos opcionales). Cinco puertos read-only (`MailReaderPort`, `CalendarReaderPort`, `ExternalTaskReaderPort`, `MeetingNotesReaderPort`, `TicketReaderPort`) y un `IntegrationAdapter` que declara `provider`, `capabilities: frozenset[Capability]` y el handshake OAuth. Una capacidad a medias no compila como puerto declarado. **Rechazado**: un mega-Protocol con métodos opcionales — difumina el contrato en ramas `None`.

### Provider como `String(50)`, no enum PG

Los proveedores se extienden en 15–19; `String(50)` indexado evita una migración de enum por proveedor. `status` sí como enum `native_enum=False` (precedente `assets`).

### Unicidad por cuenta externa (decisión ratificada #1)

`UNIQUE(connector_id, external_account_id)` — NO `(connector_id, user_id)`: un usuario puede conectar varios buzones del mismo proveedor.

### Credenciales en tabla aislada (decisión ratificada #4)

`connection_credentials` 1:1 con la cuenta, tokens cifrados Fernet (decisión #3). **Rechazado**: columnas cifradas dentro de `connected_accounts` — aísla peor el secreto y amplía la superficie.

### `state` OAuth en Redis (decisión ratificada #2)

`state_store.py` es el **primer cliente Redis real** (hoy `REDIS_URL` y `redis==5.2.1` existen pero solo hay TODOs de lock en `app/alerts/`). `redis.asyncio.from_url(settings.REDIS_URL)`; `SETEX oauth:state:{state}` con TTL y `GETDEL` en el callback → single-use anti-replay. **Rechazado**: tabla `oauth_states` — Redis ya provisionado, TTL nativo, sin migración ni limpieza.

## Data Flow

    Conectar → GET /connectors/{id}/authorize
      → oauth.build_authorize(): genera state → state_store.put (Redis TTL) → adapter.authorize_url(state,redirect_uri,scopes) → 302 al IdP
    IdP → GET /connectors/oauth/callback?code&state   (ruta global, redirect_uri estático)
      → state_store.pop(state) [single-use] valida CSRF → adapter.exchange_code(code) → OAuthTokens
      → crypto.encrypt(access/refresh) → repo.upsert_account(connector_id, external_account_id) + repo.save_credentials
    Lectura (olas 15–19/22): adapter.port_for(cap).list_*(AccessContext(crypto.decrypt(creds))) → DTOs

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/{__init__,ports,dtos,registry,oauth,crypto,state_store}.py` | Create | Puertos+DTOs, registro import-time, handshake genérico, Fernet, Redis state |
| `app/integrations/adapters/{__init__,fake}.py` | Create | Adaptador fake en memoria que se auto-registra (precedente `email/outbox.py`) |
| `app/modules/connectors/{__init__,models,schemas,repository,service,router}.py` | Create | 3 modelos; CRUD + authorize/callback/accounts; org-scoped; RBAC |
| `alembic/versions/0015_add_connectors.py` | Create | 3 tablas, `down_revision="0014"`, downgrade inverso limpio |
| `app/config.py` | Modify | `INTEGRATIONS_FERNET_KEY` (default dev como `JWT_SECRET`), `OAUTH_STATE_TTL_SECONDS`, `OAUTH_REDIRECT_ALLOWLIST` |
| `app/shared/enums.py` | Modify | `ConnectorStatus` = `active\|inactive\|error`; `AccountStatus` = `active\|expired\|revoked\|error` (`str, Enum`, `native_enum=False`). Anclado a OAuth: `expired`=access token vencido (refresh disponible), `revoked`=usuario/IdP revocó el consentimiento, `error`=canje/refresh fallido |
| `app/db_init.py` | Modify | Import de modelos (metadata) + `import app.integrations.adapters.fake` (registro) |
| `app/main.py` | Modify | `include_router(connectors_router, prefix=API_PREFIX)` |
| `requirements.txt` | Modify | `cryptography` (Fernet) — dependencia nueva |
| `requirements-dev.txt` | Modify | `fakeredis` — Redis en memoria para probar `state_store` sin Redis real (estrategia elegida; ver Testing) |
| `docs/diagrams/er-model.md`, `docs/diagrams/c4-architecture.md` | Modify | **Obligatorio en el apply, mismo commit que 0015** (ver sección Docs) |

## Interfaces / Contracts

```python
# app/integrations/dtos.py — frozen, provider-agnostic
@dataclass(frozen=True)
class MailMessage: external_id: str; subject: str; sender: str; recipients: tuple[str,...]; received_at: datetime; snippet: str; body_text: str | None
@dataclass(frozen=True)
class CalendarEvent: external_id: str; title: str; starts_at: datetime; ends_at: datetime; organizer: str; attendees: tuple[str,...]; location: str | None
@dataclass(frozen=True)
class ExternalTask: external_id: str; title: str; status: str; assignee: str | None; due_at: datetime | None; url: str | None
@dataclass(frozen=True)
class MeetingNote: external_id: str; meeting_title: str; occurred_at: datetime; transcript: str; participants: tuple[str,...]
@dataclass(frozen=True)
class Ticket: external_id: str; key: str; summary: str; status: str; priority: str | None; requester: str | None; created_at: datetime
@dataclass(frozen=True)
class OAuthTokens: external_account_id: str; access_token: str; refresh_token: str | None; expires_at: datetime | None; scopes: tuple[str,...]

# app/integrations/ports.py
class Capability(StrEnum): mail="mail"; calendar="calendar"; external_tasks="external_tasks"; meeting_notes="meeting_notes"; tickets="tickets"
class MailReaderPort(Protocol):
    async def list_messages(self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50) -> list[MailMessage]: ...
# …CalendarReaderPort/ExternalTaskReaderPort/MeetingNotesReaderPort/TicketReaderPort: misma forma read-only → DTOs
class IntegrationAdapter(Protocol):
    provider: str
    capabilities: frozenset[Capability]
    def authorize_url(self, state: str, redirect_uri: str, scopes: Sequence[str]) -> str: ...
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens: ...
    async def refresh(self, refresh_token: str) -> OAuthTokens: ...   # firma lista; orquestación de renovación → olas 15–19/22
    def port_for(self, capability: Capability) -> object: ...

# app/integrations/registry.py — dict mutable keyed by provider (precedente notify.registry, list→dict)
_ADAPTERS: dict[str, IntegrationAdapter] = {}
def register_adapter(a: IntegrationAdapter) -> None: _ADAPTERS[a.provider] = a
def get_adapter(provider: str) -> IntegrationAdapter | None: return _ADAPTERS.get(provider)
```

**Tablas** (mixins de `app/shared/base_model.py`):

| Tabla | Mixins | Campos clave | Unicidad |
|-------|--------|--------------|----------|
| `connectors` | Pk+Timestamp+SoftDelete+Audit+Tenant | `provider String(50) idx`, `scopes JSONB`, `status ConnectorStatus` | `UNIQUE(organization_id, provider)` |
| `connected_accounts` | Pk+Timestamp+SoftDelete+Audit+Tenant | `connector_id FK→connectors CASCADE`, `user_id FK→users CASCADE`, `external_account_id String idx`, `display_name`, `status AccountStatus` | `UNIQUE(connector_id, external_account_id)` |
| `connection_credentials` | Pk+Timestamp+Tenant | `connected_account_id FK→connected_accounts CASCADE`, `access_token_enc Text`, `refresh_token_enc Text?`, `expires_at DateTime?`, `token_type`, `scopes JSONB?` | `UNIQUE(connected_account_id)` (1:1) |

**Endpoints `/api/v1/connectors`** (RBAC: `require_role(MemberRole.admin, MemberRole.manager)` para config — **primer consumidor** de `require_role` (`app/dependencies.py:149`, hoy sin uso; opera sobre `OrganizationMember.role`, NO sobre la Role RBAC de `require_admin`); `get_current_membership` conecta/lee su cuenta; ruta PLANA `/connected-accounts/{id}` para desconectar — precedente `assets/router.py:157,175`, `/asset-licenses/{license_id}`):

| Método | Ruta | Permiso |
|--------|------|---------|
| POST/PATCH/DELETE | `/connectors[/{id}]` | `require_role(admin, manager)` |
| GET | `/connectors[/{id}]` | `get_current_membership` |
| GET | `/connectors/{id}/authorize` | membresía (genera state+URL, redirige 302 al IdP) |
| GET | `/connectors/oauth/callback` | valida por `state` (single-use) |
| GET | `/connectors/{id}/accounts` | membresía (propias); admin/manager ven todas |
| DELETE | `/connected-accounts/{id}` | dueño de la cuenta o admin/manager |

Errores IdP: `?error=` → `AppException(code="oauth_provider_error",400)`; state inválido/expirado/reusado → `oauth_state_invalid` 400; provider desconocido → 404. Tokens JAMÁS en respuestas ni logs.

## Security Requirements (OAuth/crypto) → RED tests

| Requisito | Test RED planeado |
|-----------|-------------------|
| Cifrado en reposo | `connection_credentials.access_token_enc != plaintext` y `decrypt == plaintext` |
| Sin fuga de tokens | Ningún token en el JSON de respuesta ni en logs de `authorize`/`callback`/`accounts` |
| Anti-CSRF/replay | State inválido/expirado 400; state reusado (2º callback) 400 (GETDEL single-use) |
| Aislamiento multi-tenant | Conector/cuenta/credencial de org A invisible a org B (filtro `organization_id` en repository) |
| Anti-SSRF/open-redirect | `redirect_uri` fuera de `OAUTH_REDIRECT_ALLOWLIST` rechazado |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | Contrato de cada puerto contra el fake (DTOs); `register_adapter` nuevo sin editar núcleo; crypto round-trip; state TTL/single-use; `capabilities`/`port_for` | pytest sin BD; fake en memoria; Redis vía `fakeredis` (dep dev nueva) |
| Integration `test_connectors.py` | CRUD + RBAC (`require_role(admin, manager)` write: admin y manager permitidos, member/viewer → 403; read con cualquier miembro); `authorize` persiste state + devuelve URL; callback (fake) → cuenta + credenciales cifradas; multi-cuenta mismo user/provider; desconectar vía `DELETE /connected-accounts/{id}` | `client` ASGI + fixtures 01; escritura con `OrganizationMember.role in {admin, manager}` — el fixture `two_orgs` ya siembra `role=admin`, así que NO requiere seed de Role RBAC (a diferencia de `assets`, que sí usaba `rbac_admin`) |
| Integration seguridad/tenant | Las 5 filas de Security Requirements | `two_orgs` + asserts de cifrado/no-fuga/state |

## Threat Matrix

N/A para los ejes formales (routing/shell, subprocess, automatización VCS/PR, clasificación de ejecutables): esta ola solo registra el adaptador fake en memoria, sin HTTP ni subprocess reales (los adaptadores reales son 15–19). Los riesgos propios de OAuth/cifrado NO se omiten: se enumeran arriba como *Security Requirements* con test RED por fila.

## Docs (obligatorio en el apply, mismo commit que 0015)

- `docs/diagrams/er-model.md`: añadir `connectors`, `connected_accounts`, `connection_credentials` con FKs, unicidades y `organization_id`.
- `docs/diagrams/c4-architecture.md`: nuevo componente **Integrations** (puertos+registro+adaptadores), módulo `connectors`, store de state en Redis y cifrado Fernet.

## Migration / Rollout

Aditiva `0015` (`down_revision="0014"`); enums inline `sa.Enum(native_enum=False, length=N)` (sin tipo PG); índices explícitos como `0010`. `downgrade()` elimina en orden inverso (`connection_credentials` → `connected_accounts` → `connectors`) — round-trip sin filas vivas. `INTEGRATIONS_FERNET_KEY` con default dev válido (base64 32B) para que la suite arranque; producción lo sobrescribe. Sin adaptadores reales, el núcleo queda inerte: cero impacto en flujos existentes. Rollback = revertir el merge.

## Rejected Alternatives (resumen)

- Tabla `oauth_states` → Redis (TTL nativo, sin migración).
- Columnas cifradas en la cuenta → tabla `connection_credentials` aislada.
- Provider enum PG → `String(50)` (extensible 15–19 sin migración de enum).
- `UNIQUE(connector_id, user_id)` → `UNIQUE(connector_id, external_account_id)` (multi-buzón).
- Mega-Protocol con métodos opcionales → un Protocol por capacidad + `capabilities` declaradas.
- `POST /authorize` → `GET /connectors/{id}/authorize`: es una navegación de navegador que responde una redirección `302` al IdP; un `POST` rompe el patrón de redirect del navegador y no aporta cuerpo útil (el adaptador arma los parámetros).
- Callback scoped `GET /connectors/{id}/callback` (spec) → **ratificado por el orquestador**: ruta GLOBAL `GET /connectors/oauth/callback`. El `redirect_uri` OAuth debe ser estático y pre-registrado ante el proveedor; un `{id}` en la ruta lo haría variable. El `state` (ya en Redis) transporta la referencia al conector/usuario. Errata quirúrgica anotada en `specs/connectors/spec.md` (línea de ruta + requisito del callback), SUPERA la ruta scoped del spec.
- Config con `require_admin` (Role RBAC, precedente `assets`) → `require_role(MemberRole.admin, MemberRole.manager)` (spec `connectors/spec.md:47`): el spec exige `admin\|manager` sobre `OrganizationMember.role`, no la Role RBAC.

## Open Questions

- [ ] Renovación automática de tokens: `adapter.refresh` + `expires_at` almacenado dejan la frontera lista; la orquestación de refresh-on-expiry se difiere a las olas de lectura (15–19/22).
