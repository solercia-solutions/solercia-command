# Tasks: 20 · SSO con Keycloak (OIDC como segundo método de login)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~900–1000 (oidc+service ~350, modelo+migración ~120, endpoints ~120, frontend ~120, tests ~300) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | No (sin cadena de PR en GitHub; ver nota) |
| Split sugerido | Lote A (infra+modelo+migración+ER) → B (OidcClient) → C (sso_service) → D (endpoints+integración) → E (frontend mínimo) |
| Estrategia de entrega | exception-ok — commits directos a `feat/consume-solercia-ui`, uno por lote |
| Estrategia de encadenado | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Nota: sin PR de GitHub; el volumen (~900-1000 líneas, > 2× el presupuesto) se fragmenta en 5 commits secuenciales A→E, cada uno con la suite verde y ruff/mypy limpios; `size:exception` cubre el exceso por lote (delivery_strategy=exception-ok ya aceptado).

### Suggested Work Units

| Unit | Objetivo | Commit | Test enfocado | Arnés | Rollback |
|---|---|---|---|---|---|
| A | Deps + config + `redis.py` (condicional) + `FederatedIdentity`+migración + `hashed_password` nullable + ER vivo | 1 | `pytest tests/test_federated_identities_migration.py -v` | `alembic upgrade head`/`downgrade -1` en BD de test | revierte modelo+migración+ER; `redis.py` solo se toca si no existe |
| B | `OidcClient` (discovery/token/JWKS/PKCE) | 2 | `pytest tests/test_oidc_client.py -v` | IdP falso: RSA de test + `httpx.MockTransport` | revierte `oidc/`; router intacto |
| C | `sso_service.py` (estado Redis + enlace/aprovisión) | 3 | `pytest tests/test_sso_service.py -v` | `fakeredis` + sesión de test | revierte el service; B intacto |
| D | Rutas `/auth/sso/{provider}/login`\`/callback\` + login local intacto | 4 | `pytest tests/test_auth_sso.py tests/test_auth.py -v` | `httpx.AsyncClient` ASGI in-process | revierte las 2 rutas; `/auth/login` sin cambios |
| E | Botón SSO + `auth-callback` + ruta | 5 | `npm run build && npm run lint` (sin harness de test en frontend) | manual: click botón → IdP stub → callback → `/projects` | revierte el componente y la entrada de ruta |

## Lote A — Infra, modelo y migración (Commit 1)

- [x] T01 [Foundation] Verificar el head real de Alembic (`alembic heads`) al aplicar; encadenar `down_revision` sobre ese head (NO asumir `0014`; 14-integration-ports y 21-project-hierarchy también encadenan y se serializan antes). Head real verificado: `0015` (add_connectors). Migración nueva: `0016_add_federated_identities.py`, `down_revision="0015"`.
- [x] T02 [Foundation] `backend/requirements.txt`: promover `httpx`; agregar `cryptography` (o `pyjwt[crypto]`) para RS256/JWKS. `backend/requirements-dev.txt`: agregar `fakeredis`. `cryptography==49.0.0` y `pyjwt==2.10.1` YA estaban en `requirements.txt` (los promovió 14-integration-ports); verificado que `pyjwt` con `cryptography` instalado soporta RS256 (`get_default_algorithms()` incluye `RS256`). `fakeredis>=2.26` YA estaba en `requirements-dev.txt`. Solo se agregó `httpx==0.28.1` a `requirements.txt` (antes solo en dev).
- [x] T03 [Foundation] `backend/app/shared/redis.py`: crear SOLO si no existe (14-integration-ports también lo crea, apply serializado detrás); si existe, reutilizarlo sin tocar su contrato. Ya existía (14-integration-ports) — reutilizado sin cambios; su propio docstring ya anticipaba este cambio 20 como consumidor.
- [x] T04 [Foundation] `backend/app/config.py`: `SSO_ENABLED`, `SSO_AUTO_PROVISION`, `SSO_POST_LOGIN_REDIRECT`, `OIDC_{PROVIDER}_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI`. Las tres primeras son campos fijos de `Settings`; las variables por-proveedor se resuelven dinámicamente vía `os.environ` en `oidc/config.py::load_provider_config(provider)` (Lote B) para que un segundo IdP no requiera tocar `Settings` (R6).
- [x] T05 RED `backend/tests/test_federated_identities_migration.py`: `upgrade`/`downgrade` round-trip; `downgrade` falla si hay usuario `hashed_password IS NULL` (guard). Rojo confirmado moviendo temporalmente la migración fuera del árbol (`Can't locate revision identified by '0016'`), luego restaurada → verde.
- [x] T06 [Foundation] `backend/app/modules/auth/models.py`: `FederatedIdentity` (mixins Pk/Timestamp/SoftDelete/Audit; `user_id` FK indexado; `UNIQUE(issuer, subject)`). `users/models.py`: `hashed_password` → `nullable=True`. `db_init.py`: importar `FederatedIdentity`. `alembic/versions/0016_add_federated_identities.py`: tabla + alter. Efecto colateral necesario: `auth/service.py::authenticate` ahora rechaza `hashed_password IS NULL` ANTES de llamar `verify_password` (mismo mensaje genérico) — cubre auth R4.
- [x] T07 [Foundation] `docs/diagrams/er-model.md`: agregar `federated_identities` y `hashed_password` nullable — MISMO commit que T06.
- [x] T08 VERIFY `pytest tests/test_federated_identities_migration.py -v` → verde (3/3). `pytest tests/ -v` completo → 645 passed / 13 fallas preexistentes (mismas del baseline, sin regresión). `ruff check .` y `mypy app` limpios. Ciclo `alembic upgrade head` → `downgrade -1` → `upgrade head` verificado contra BD desechable (`solercia_migration_cycle`), limpio. Commit `feat(auth): agrega federated_identities y hashed_password nullable`.

## Lote B — OidcClient (Commit 2)

- [x] T09 RED `backend/tests/test_oidc_client.py`: JWKS válida/inválida, `iss`/`aud`/`exp`/`nonce` incorrectos (R2 sso-oidc); PKCE `code_challenge` S256; caché JWKS + refetch por `kid` nuevo. IdP falso: RSA de test + `httpx.MockTransport`. Rojo confirmado (`ModuleNotFoundError: app.modules.auth.oidc.client`) antes de crear el módulo. 12 tests: happy path, `iss`/`aud`/`exp`/`nonce` incorrectos, llave de firma desconocida/forjada, vector RFC 7636 para PKCE S256, caché JWKS (sin refetch por `kid` conocido) y refetch por rotación de `kid`.
- [x] T10 [Core] `backend/app/modules/auth/oidc/{__init__,config,client,jwks}.py`: `OidcProviderConfig`; `OidcClient.authorization_url/exchange_code/verify_id_token`; caché discovery+JWKS por `issuer`. `load_provider_config(provider)` lee `OIDC_{PROVIDER}_*` directo de `os.environ` (no como campos fijos de `Settings`) para que un segundo proveedor sea solo configuración (R6).
- [x] T11 VERIFY `pytest tests/test_oidc_client.py -v` → verde (12/12 en primera corrida). `ruff check`/`mypy app` limpios. Commit `feat(auth): agrega OidcClient (discovery, token, JWKS, PKCE)`.

## Lote C — sso_service (Commit 3)

- [x] T12 RED `backend/tests/test_sso_service.py`: enlace por `(issuer,subject)` existente; enlace por correo verificado; rechazo sin `SSO_AUTO_PROVISION`; aprovisión (`hashed_password NULL`, sin roles); rechazo `email_verified=false` (R3/R4 sso-oidc). Estado en `fakeredis`, TTL 300s, single-use. Rojo confirmado (`ModuleNotFoundError: app.modules.auth.sso_service`) antes de crear el módulo. Se agregó cobertura extra de `require_provider_config` (R6: deshabilitado/proveedor sin configurar/config completa).
- [x] T13 [Core] `backend/app/modules/auth/sso_service.py`: `sso_login`/`sso_callback` — genera/persiste `state+nonce+code_verifier`, orquesta `OidcClient`, resuelve usuario (orden R4), reutiliza `create_access_token`/`create_refresh_token`. `resolve_or_provision_user(db, provider, claims)` implementa el orden R4 de forma testable sin Redis/HTTP; `put_state`/`pop_state` viven en el mismo archivo (sin submódulo aparte, mismo patrón que `app/integrations/state_store.py` pero bajo el prefijo `sso:state:`).
- [x] T14 VERIFY `pytest tests/test_sso_service.py -v` → verde (11/11). `ruff check`/`mypy app` limpios. Nota de mantenimiento: `solercia_test` tenía `users.hashed_password` todavía `NOT NULL` (el fixture `engine` usa `create_all`, que no altera columnas existentes — brecha ya documentada en `test_migrations_baseline.py`, "Brecha residual aceptada"); se corrigió con `ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL` directo sobre `solercia_test` para igualar el modelo. Commit `feat(auth): agrega sso_service (estado Redis + enlace/aprovisión)`.

## Lote D — Endpoints e integración (Commit 4)

- [x] T15 RED `backend/tests/test_auth_sso.py`: `/login` redirige + escribe `state` en Redis (R1); `/callback` feliz → Set-Cookie refresh + 302 sin access en URL (R6 auth); `state` inválido/reusado, `redirect_uri` fuera de allowlist, ID token forjado (R2); error `access_denied` del IdP (R5); `SSO_ENABLED=false` → endpoints inertes (R6 sso-oidc). Rojo confirmado con `git stash` de `router.py`/`oidc/client.py` (rutas inexistentes → 404 genérico de FastAPI, no `sso_disabled`; el resto 4xx/errores no coinciden). Desviación documentada: `redirect_uri` NUNCA es parámetro aceptado por `/login` (no hay allowlist configurable — el `redirect_uri` OIDC es siempre `config.redirect_uri` fijo de env, "allowlist de 1" por diseño D5); el test correspondiente prueba que un `redirect_uri` enviado por el cliente se IGNORA por completo.
- [x] T16 RED `backend/tests/test_auth.py`: usuario `hashed_password` NULL rechazado en login local (auth R4); login dual credencial+SSO conviven (auth R7). Rojo confirmado para el primer caso removiendo temporalmente el guard de `authenticate()` (`AttributeError: 'NoneType' object has no attribute 'encode'` sin manejar); el segundo es un test de composición de unidades ya cubiertas (login local + `resolve_or_provision_user`), sin producción nueva.
- [x] T17 [Core] `backend/app/modules/auth/router.py`: rutas `GET /auth/sso/{provider}/login` y `/callback`, reutiliza `_set_refresh_cookie`. `oidc/client.py`: se agregó `get_http_client()` (singleton `@lru_cache`, mismo patrón que `app/shared/redis.py::get_redis_client`) para que el router y las pruebas compartan/parcheen un único cliente HTTP. Un error del IdP (`error=access_denied`) redirige al SPA con `?error=...` (R5, texto explícito de "redirige"); las demás fallas de `R2` (state inválido/reusado, ID token forjado) responden JSON 4xx, igual que el precedente de `connectors/router.py::oauth_callback`. `schemas.py` NO se modificó — las rutas SSO devuelven `RedirectResponse` (sin cuerpo) o el envelope de error estándar de `AppException`; no hizo falta un schema nuevo (desviación menor respecto a la tabla File Changes del design.md).
- [x] T18 VERIFY `pytest tests/test_auth_sso.py tests/test_auth.py -v` → verde (9/9 + 9/9). `pytest tests/ -v` completo sin regresión. `ruff check .`, `mypy app` limpios. Commit `feat(auth): expone rutas SSO login/callback, valida convivencia con login local`.

## Lote E — Frontend mínimo (Commit 5)

- [x] T19 [Frontend] `frontend/src/pages/login/login.component.ts`: botón «Ingresar con SSO» (`window.location.href = ${apiBase}/auth/sso/keycloak/login`). Se agregó también un divisor visual «o» y las claves `auth.login.ssoButton`/`auth.login.ssoDivider` en `es-CO.json` (español colombiano formal, tuteo).
- [x] T20 [Frontend] `frontend/src/pages/auth-callback/auth-callback.component.ts`: crear — canjea `refresh()`+`me()`, navega a `/projects`. `app.routes.ts`: ruta `auth/callback` sin `authGuard`. Ante error del canje (SSO rechazado/expirado), muestra `auth.callback.error` y regresa a `/login` tras 2.5s. Claves nuevas: `auth.callback.completing`/`auth.callback.error`.
- [x] T21 VERIFY `npm run build && npm run lint` verdes (Node v22.22.3 vía nvm — v22.12.0 activo por defecto no cumplía el mínimo `22.22.3` del CLI de Angular; se documenta para futuras corridas locales). Checklist manual con Keycloak real NO ejecutado en este entorno (sin IdP disponible); el equivalente extremo a extremo (botón → IdP → callback → cookie → `/projects`) está cubierto server-side por `test_auth_sso.py::test_sso_callback_happy_path_sets_refresh_cookie_without_access_in_url` con IdP falso, y el componente de callback reutiliza `AuthService.refresh()`/`me()` ya probados por el resto de la suite del frontend. Commit `feat(frontend): agrega botón SSO y ruta de callback`.

## Trazabilidad de requisitos

`sso-oidc` R1 (T15) · R2 (T09,T15) · R3 (T12) · R4 (T12) · R5 (T15) · R6 (T04,T15) · R7 (T19–T20) · `auth` R4 (T16) · R6 (T13) · R7 (T16).
