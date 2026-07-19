# Proposal: 20 · SSO con Keycloak (OIDC como segundo método de login)

## Intent

Hoy el único inicio de sesión es usuario/contraseña contra BD (bcrypt) que emite el JWT propio (access 30 min + refresh en cookie httpOnly). Las entidades que ya operan un IdP corporativo (Keycloak) no pueden reutilizar sus credenciales, MFA ni políticas centrales. OLA 2 ítem 3 pide un **segundo** método —SSO OIDC— que **conviva** con el actual: la plataforma redirige al IdP, valida el callback y emite **su propio** JWT con permisos locales. Keycloak **solo autentica**; los roles y el RBAC se siguen gobernando aquí.

## Scope

### In Scope
- **Flujo OIDC Authorization Code + PKCE** (backend): `GET /auth/sso/{provider}/login` (redirige al IdP) y `GET /auth/sso/{provider}/callback` (valida + emite el JWT propio).
- **Validación del ID token**: firma vía JWKS del issuer + `iss`/`aud`/`exp`/`nonce`; `state` + PKCE contra CSRF e interceptación del código.
- **Enlace/aprovisionamiento por correo verificado** (`email_verified`): tabla nueva `federated_identities` (`user_id`, `provider`, `issuer`, `subject`, `email`; único `(issuer, subject)`). Toggle `SSO_AUTO_PROVISION` (solo enlazar vs. crear usuario nuevo).
- **Config por variables de entorno** genéricas por proveedor (`SSO_ENABLED`, `SSO_AUTO_PROVISION`, `OIDC_{PROVIDER}_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI`); Keycloak = una config, sin acoplar su Admin API.
- **Migración Alembic aditiva**: `federated_identities` + `users.hashed_password` nullable (usuarios solo-SSO).
- **Frontend (unidad mínima)**: botón «Ingresar con SSO» en la pantalla de login y manejo del callback/refresh en el SPA. El backend fija la cookie de refresh y redirige al SPA, que emite el access vía `/auth/refresh`; nada más de UI queda incluido.

### Out of Scope
- Logout federado (back-channel), aprovisionamiento SCIM, sincronización de roles desde Keycloak, refresh contra el IdP.

## Capabilities

### New Capabilities
- `sso-oidc`: login OIDC (authorization code + PKCE), validación del ID token, enlace/aprovisionamiento por correo y emisión del JWT propio.

### Modified Capabilities
- `auth`: se añade el SSO como segundo punto de entrada que converge en el mismo JWT / refresh / `/me`; el login por credenciales no cambia de contrato.

## Approach

`OidcClient` genérico (discovery `.well-known/openid-configuration`, intercambio de código, caché de JWKS) parametrizado por `OidcProviderConfig` desde env — Keycloak es una instancia. `login` genera `state`+`nonce`+`code_verifier`, los guarda en Redis con TTL corto y redirige. `callback` valida `state`, canjea el código con `code_verifier`, valida el ID token, resuelve el usuario por correo verificado (enlaza si existe, aprovisiona si no y `SSO_AUTO_PROVISION`), y reutiliza `create_access_token`/`create_refresh_token`. El access token nunca viaja en la URL: el callback fija la cookie de refresh y el SPA lo canjea. TDD estricto (happy path + error + permisos).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/auth/` | Modified | router/service/schemas SSO; reutiliza la emisión de JWT |
| `backend/app/modules/auth/oidc/` | New | `OidcClient` + config de proveedor genérica |
| `backend/app/modules/users/models.py` | Modified | `hashed_password` nullable |
| `federated_identities` (modelo + migración) | New | Identidades federadas; único `(issuer, subject)` |
| `backend/app/config.py` | Modified | Settings OIDC por proveedor |
| `docs/diagrams/er-model.md` (diagrama ER vivo) | Modified | **Obligatorio**: agregar `federated_identities` al ER |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Apropiación de cuenta por enlace de correo no verificado | Med | Exigir `email_verified=true`; rechazar el enlace si falta |
| CSRF / interceptación del código de autorización | Med | `state` + PKCE (S256) + `redirect_uri` en allowlist |
| ID token forjado o `iss`/`aud` incorrectos | Med | Validar firma JWKS + `iss`/`aud`/`exp`/`nonce` |
| Acoplarse a Keycloak | Low | Cliente OIDC estándar por discovery; proveedor = config |
| Alterar `users.hashed_password` (tabla sensible) | Low | Migración aditiva nullable + downgrade; login credencial intacto |

## Rollback Plan

Cambio aditivo. Revertir el merge y aplicar `downgrade` (elimina `federated_identities`, revierte `hashed_password` a NOT NULL — requiere que ningún usuario solo-SSO exista). Con `SSO_ENABLED=false` los endpoints SSO quedan inertes; el login por credenciales nunca se toca.

## Dependencies

- Reutiliza la línea base as-built `auth` (emisión JWT/refresh) y `users` + RBAC.
- Requiere Redis (ya presente) para el estado efímero `state`/PKCE.
- Un realm/cliente Keycloak de prueba para los tests de integración.

## Success Criteria

- [ ] Ambos métodos conviven: credenciales y SSO emiten el mismo JWT propio.
- [ ] El callback valida firma/`iss`/`aud`/`nonce`/`state`/PKCE; rechaza tokens inválidos.
- [ ] El usuario SSO se enlaza por correo verificado si existe; se aprovisiona si no (según `SSO_AUTO_PROVISION`).
- [ ] Config 100% por env; un segundo IdP OIDC funcionaría agregando solo variables.
- [ ] Migración con `downgrade` probado; suite backend verde (TDD estricto).
- [ ] ER (`docs/DATA-MODEL.md`) actualizado con `federated_identities`.
