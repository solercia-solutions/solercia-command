# Design: 20 · SSO con Keycloak (OIDC como segundo método de login)

## Technical Approach

Se añade un módulo OIDC genérico bajo `backend/app/modules/auth/oidc/` (`OidcClient` + `OidcProviderConfig`) y dos rutas nuevas en `auth/router.py` (`/auth/sso/{provider}/login` y `/callback`). El `login` genera `state`+`nonce`+`code_verifier` (PKCE S256), los guarda en Redis con TTL corto y redirige al IdP. El `callback` valida `state`, canjea el código, valida el ID token (JWKS RS256 + `iss`/`aud`/`exp`/`nonce`), resuelve al usuario por correo verificado y **reutiliza `create_access_token`/`create_refresh_token`/`_set_refresh_cookie` intactos** (`app/shared/security.py`, `auth/router.py:38`). El access token nunca viaja en la URL: el callback fija la cookie de refresh y redirige al SPA, que canjea el access vía `/auth/refresh` (endpoint sin cambios). El login por credenciales (`authenticate`, `auth/service.py:15`) no se toca. Convergen en el mismo `/me` y RBAC local. Se incluye la unidad mínima de frontend (botón + ruta de callback). TDD estricto con IdP falso.

## Architecture Decisions

### D1 — Modelo: tabla `federated_identities` anclada a `(issuer, subject)`
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Tabla `federated_identities` (mixins `PkMixin`/`TimestampMixin`/`SoftDeleteMixin`/`AuditMixin`) | Multi-IdP: un usuario enlaza varias identidades; mantiene `users` limpia; anclaje 1:N | **Elegida** |
| Columnas `oidc_issuer`/`oidc_subject` en `users` | Bloquea multi-IdP y ensucia la tabla más sensible | Rechazada |

Columnas: `user_id` FK→`users.id` (index), `provider` (alias de config, p.ej. `keycloak`), `issuer`, `subject`, `email` (informativo, del enlace inicial). **Unicidad `UNIQUE(issuer, subject)`**: `sub` solo es único por `issuer` (correctitud OIDC), es el anclaje criptográfico de la decisión ratificada; `provider` solo enruta config y no participa del anclaje (refina el `(provider, subject)` del proposal). Tras el primer enlace el correo ya no interviene: se resuelve por `(issuer, subject)`.

### D2 — Cliente OIDC propio con `httpx` + `pyjwt` (no `authlib`)
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `OidcClient` propio: `httpx` (discovery, token, JWKS) + `pyjwt` (RS256) | Deps mínimas; sigue el ethos de `security.py` ("keep dependency surface small"); `pyjwt` ya presente | **Elegida** |
| `authlib` | Dependencia grande que oculta el flujo y acopla más de lo necesario | Rechazada |

Requisitos de dependencias en `requirements.txt`: promover **`httpx`** de `requirements-dev.txt` a producción y añadir **`cryptography`** (o `pyjwt[crypto]`) — RS256 lo exige y hoy solo se usa HS256. JWKS: caché en proceso por `issuer` con TTL, **refetch ante `kid` desconocido** (rotación de llaves). Discovery (`.well-known/openid-configuration`) cacheado con TTL.

### D3 — Estado efímero `state`/`nonce`/`code_verifier` en Redis
`redis.asyncio` (paquete `redis==5.2.1` ya declarado; **primer uso real** en código — hoy Redis solo está configurado). Clave `sso:state:{state}` → `{nonce, code_verifier, provider}`, TTL 300 s, **single-use** (`delete` al consumir). Rationale: CSRF (`state`) y PKCE necesitan store con expiración fuera del proceso (multi-worker uvicorn). Cliente en `app/shared/redis.py` (nuevo helper reutilizable).

### D4 — Enlace/aprovisionamiento por correo verificado
Orden en el `callback`: (1) si existe `federated_identity` por `(issuer, subject)` → usa ese `user`; (2) si no y `email_verified=true` → busca `user` por `email` (enlaza: INSERT identity); (3) si no existe y `SSO_AUTO_PROVISION=true` → crea `user` con `hashed_password=NULL` y **sin roles** (RBAC se asigna después localmente); (4) si `email_verified=false` o auto-provision off sin match → rechaza. Decisión ratificada #1.

### D5 — Contrato frontend-ready + unidad mínima de SPA
El `callback` responde `302` a un landing del SPA (valor fijo de env, allowlist); el SPA llama `AuthService.refresh()` (`auth.service.ts:87`, ya `withCredentials`) → access + rotación de cookie → `me()`. El `redirect_uri` OIDC registrado en Keycloak es el propio `/callback` (valor único de env; allowlist de 1). Frontend mínimo: botón que hace `window.location.href = ${apiBase}/auth/sso/keycloak/login` (redirección de navegador, no `HttpClient`) y ruta `auth/callback` que reutiliza `refresh()`+`me()`.

## Data Flow

    SPA ── click "Ingresar con SSO" ──▶ GET /auth/sso/keycloak/login
       │  Redis SET sso:state:{state}(nonce,verifier) TTL 300s
       └────────── 302 authorization_endpoint (code_challenge S256, state, nonce)
    IdP ── login/MFA ──▶ 302 GET /auth/sso/keycloak/callback?code&state
       │  Redis GET+DEL state · POST token_endpoint(code, verifier) · JWKS RS256
       │  valida iss/aud/exp/nonce/email_verified · enlaza/aprovisiona
       └── create_refresh_token → Set-Cookie · 302 SPA landing (SIN access en URL)
    SPA landing ──▶ POST /auth/refresh (cookie) ──▶ access ──▶ GET /auth/me

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/auth/oidc/{__init__,client,config,jwks}.py` | Create | `OidcClient` (discovery/token/JWKS), `OidcProviderConfig`, caché JWKS |
| `backend/app/modules/auth/sso_service.py` | Create | Orquesta login/callback: state Redis, validación ID token, enlace/aprovisión |
| `backend/app/modules/auth/router.py` | Modify | Rutas `/auth/sso/{provider}/login` y `/callback`; reutiliza `_set_refresh_cookie` |
| `backend/app/modules/auth/schemas.py` | Modify | Schemas SSO (metadata de proveedor / errores) |
| `backend/app/modules/auth/models.py` | Create | `FederatedIdentity` (mixins), `UNIQUE(issuer, subject)`, index `user_id` |
| `backend/app/modules/users/models.py` | Modify | `hashed_password` → `nullable=True` (`models.py:47`) |
| `backend/app/shared/redis.py` | Create | Helper `redis.asyncio` (primer consumidor real de `REDIS_URL`) |
| `backend/app/config.py` | Modify | `SSO_ENABLED`(False), `SSO_AUTO_PROVISION`(False), `SSO_POST_LOGIN_REDIRECT`, `OIDC_{PROVIDER}_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI` |
| `backend/app/db_init.py` | Modify | Importar `FederatedIdentity` |
| `backend/alembic/versions/00XX_add_federated_identities.py` | Create | Tabla + `users.hashed_password` nullable; `down_revision` = head vigente (**tentativo 0014**) |
| `backend/requirements.txt` | Modify | `httpx`, `cryptography` (o `pyjwt[crypto]`) |
| `frontend/src/pages/login/login.component.ts` | Modify | Botón "Ingresar con SSO" (`window.location.href`) |
| `frontend/src/pages/auth-callback/auth-callback.component.ts` | Create | Ruta que canjea `refresh()`+`me()` y navega a `/projects` |
| `frontend/src/app/app.routes.ts` | Modify | Ruta `auth/callback` (sin `authGuard`) |
| `docs/DATA-MODEL.md` | Modify (apply) | ER: `federated_identities` |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class OidcProviderConfig:      # cargado de env por 'provider'
    provider: str; issuer: str; client_id: str; client_secret: str; redirect_uri: str

class OidcClient:              # httpx + pyjwt, por proveedor
    async def authorization_url(self, state, nonce, code_challenge) -> str: ...
    async def exchange_code(self, code, code_verifier) -> dict: ...        # token_endpoint
    async def verify_id_token(self, id_token, nonce) -> dict: ...          # JWKS RS256 + iss/aud/exp/nonce

async def sso_login(provider) -> RedirectResponse: ...                     # state+PKCE en Redis
async def sso_callback(provider, code, state, response) -> RedirectResponse: ...  # emite JWT propio
```

Config env genérica: un segundo IdP OIDC entra agregando `OIDC_{OTRO}_*` sin tocar código.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | `verify_id_token`: firma válida, `iss`/`aud`/`exp`/`nonce` incorrectos, `email_verified=false`; PKCE `code_challenge` S256; caché JWKS + refetch por `kid` nuevo | IdP falso: par RSA de test firma ID tokens; JWKS servido por stub `httpx.MockTransport` |
| Unit | Enlace por `(issuer,sub)` existente; enlace por correo; aprovisión (`hashed_password NULL`, sin roles); `SSO_AUTO_PROVISION=false` sin match → rechazo | pytest, repos con sesión de test |
| Integration | `/login` redirige y escribe `state` en Redis (fakeredis); `/callback` feliz → Set-Cookie refresh + 302 sin access en URL; `state` inválido/reusado, token forjado, `redirect` fuera de allowlist → 4xx | `httpx.AsyncClient` (patrón `conftest.py`) + IdP y JWKS stub |
| Integration | Migración `upgrade`/`downgrade` round-trip; `SSO_ENABLED=false` → endpoints inertes; login credencial intacto | fixture de BD de test |

## Threat Matrix

N/A a la matriz de shell/subproceso/VCS-PR/clasificación de ejecutables (mismo criterio que 08/09). Superficie real cubierta como requisitos con RED tests: **apropiación de cuenta** (exigir `email_verified=true`), **CSRF/interceptación** (`state` single-use + PKCE S256 + `redirect_uri` fijo de env), **ID token forjado** (firma JWKS + `iss`/`aud`/`exp`/`nonce`), **open redirect** (landing SPA en allowlist), **SSRF** (`issuer`/endpoints salen de env de confianza, `provider` validado contra config; nunca de input del usuario), **fuga de `client_secret`** (solo en `.env`, jamás en logs).

## Migration / Rollout

Migración aditiva encadenada al head vigente (`0013`), **número tentativo `0014`**. **Nota de serialización**: los cambios `14-integration-ports` y `21-project-hierarchy` también encadenan migraciones; el orquestador serializa los `apply` y fija el orden final de la cadena, por lo que `down_revision` real puede diferir. `downgrade()` = drop `federated_identities` + `hashed_password` → `NOT NULL` (**guard**: falla si existe algún usuario solo-SSO, `hashed_password IS NULL`). Rollout tras `SSO_ENABLED=false` (endpoints inertes). Rollback = flag off o revertir merge; el login por credenciales nunca se toca. Presupuesto estimado ~900-1000 líneas (oidc+service ~350, model+migración ~120, endpoints ~120, frontend ~120, tests ~300). `Decision needed before apply: Yes` · `Chained PRs recommended: Yes` · `400-line budget risk: Medium`.

## Open Questions

- [ ] `SSO_POST_LOGIN_REDIRECT`: ¿landing fijo del SPA o parámetro validado contra allowlist para deep-link post-login? Propuesta: fijo en MVP.
- [ ] Rotación de correo en el IdP tras el enlace: la identidad se ancla a `(issuer, sub)`, el `email` almacenado queda desactualizado (informativo). ¿Resincronizar en cada callback? Propuesta: sí, actualizar `federated_identities.email` best-effort.
