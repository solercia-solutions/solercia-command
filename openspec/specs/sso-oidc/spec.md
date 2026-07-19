# Spec — SSO OIDC (sso-oidc)

## Propósito

Segundo método de login vía Authorization Code + PKCE contra un IdP OIDC (Keycloak u otro por configuración). El IdP solo autentica; la plataforma enlaza o aprovisiona el usuario local por correo verificado y emite su propio JWT con los roles RBAC locales. Convive con el login por credenciales sin reemplazarlo.

## Alcance

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/auth/sso/{provider}/login | Genera state/nonce/PKCE y redirige al IdP |
| GET | /api/v1/auth/sso/{provider}/callback | Valida el retorno del IdP y emite el JWT propio |

Modelo nuevo `FederatedIdentity`: `user_id`, `provider`, `issuer`, `subject`, `email`; único `(issuer, subject)`.

## Requisitos

### Requirement: R1 — Inicio del flujo (Authorization Code + PKCE)

`GET /auth/sso/{provider}/login` DEBE generar `state`, `nonce` y PKCE (S256), persistirlos en Redis con TTL corto, y redirigir al endpoint de autorización del IdP.

#### Scenario: Inicio de sesión SSO

- Dado SSO habilitado (`SSO_ENABLED=true`) para el proveedor
- Cuando el usuario visita `GET /auth/sso/{provider}/login`
- Entonces el sistema redirige al IdP con `state`, `nonce` y `code_challenge` (S256), y guarda el estado efímero en Redis

### Requirement: R2 — Validaciones del callback antes de emitir tokens

El callback DEBE validar `state` (existe, vigente, coincide), `redirect_uri` (pertenece a la allowlist) e ID token (firma JWKS, `iss`/`aud`/`exp`/`nonce`) antes de canjear el código. Cualquier fallo DEBE rechazar la petición sin emitir JWT.

#### Scenario: State inválido o expirado

- Dado un `state` inexistente, ya consumido o vencido en Redis
- Cuando se llama el callback con ese `state`
- Entonces el sistema rechaza la petición y no emite JWT

#### Scenario: Redirect URI fuera de la allowlist

- Dado un `redirect_uri` que no pertenece a la allowlist configurada
- Cuando se solicita el intercambio del código de autorización
- Entonces el sistema rechaza la petición y no continúa el flujo

#### Scenario: ID token inválido

- Dado un ID token con firma, `iss` o `aud` inválidos, o `nonce` que no coincide
- Cuando el callback procesa la respuesta del IdP
- Entonces el sistema rechaza la autenticación y no emite JWT propio

### Requirement: R3 — Correo verificado obligatorio para enlazar

El sistema DEBE exigir `email_verified=true` en el ID token para enlazar o aprovisionar el usuario local. Si es `false`, DEBE rechazar el login sin crear ni enlazar ninguna cuenta.

#### Scenario: Correo no verificado

- Dado un ID token con `email_verified=false`
- Cuando el callback intenta resolver el usuario local
- Entonces el sistema rechaza el login y no crea ni enlaza ninguna cuenta

### Requirement: R4 — Resolución del usuario local por correo/sub

El sistema DEBE resolver el usuario en este orden: (a) identidad federada existente para `(issuer, subject)` → reutilizarla sin duplicar; (b) usuario local con el mismo correo verificado y sin enlace previo → crear el enlace en `FederatedIdentity`; (c) sin usuario y `SSO_AUTO_PROVISION=false` (default) → rechazar sin crear cuenta; (d) sin usuario y `SSO_AUTO_PROVISION=true` → crear el usuario local sin ningún rol RBAC y enlazarlo.

#### Scenario: Callback feliz — enlace de usuario existente

- Dado un usuario local activo cuyo correo coincide con el `email` verificado del ID token, sin enlace previo
- Cuando completa el callback SSO por primera vez
- Entonces el sistema crea el registro en `FederatedIdentity` y emite el JWT propio

#### Scenario: Enlace idempotente por sub

- Dado una identidad federada ya enlazada para `(issuer, subject)`
- Cuando el mismo usuario vuelve a completar el callback SSO
- Entonces el sistema reutiliza el enlace existente, sin duplicarlo, y autentica al mismo usuario local

#### Scenario: Usuario no existente, auto-provisión desactivada

- Dado ningún usuario local con el correo verificado del ID token, y `SSO_AUTO_PROVISION=false`
- Cuando se completa el callback SSO
- Entonces el sistema rechaza el login y no crea ningún usuario

#### Scenario: Usuario no existente, auto-provisión activada

- Dado ningún usuario local con el correo verificado, y `SSO_AUTO_PROVISION=true`
- Cuando se completa el callback SSO
- Entonces el sistema crea el usuario local (sin `hashed_password`), lo enlaza en `FederatedIdentity` y lo autentica sin ningún rol asignado

### Requirement: R5 — Error del IdP en el callback

Si el IdP responde al callback con un parámetro de error (p. ej. `access_denied`), el sistema DEBE manejarlo sin excepción no controlada, NO emitir JWT, y redirigir al SPA indicando el fallo.

#### Scenario: Callback con error del IdP

- Dado el IdP redirige al callback con `error=access_denied` (u otro error OIDC)
- Cuando el backend procesa la respuesta
- Entonces el sistema responde con un error controlado, sin JWT, y redirige al SPA indicando el fallo

### Requirement: R6 — Configuración 100% por variables de entorno

`SSO_ENABLED`, `SSO_AUTO_PROVISION` y `OIDC_{PROVIDER}_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI` DEBEN resolverse desde variables de entorno; agregar un segundo proveedor OIDC NO DEBE requerir cambios de código, solo configuración nueva.

#### Scenario: Nuevo proveedor solo por configuración

- Dado variables `OIDC_{OTRO}_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI` configuradas para un segundo proveedor
- Cuando se solicita `GET /auth/sso/{otro}/login`
- Entonces el sistema inicia el flujo OIDC contra ese proveedor sin cambios de código

### Requirement: R7 — Botón e integración con el SPA

El SPA DEBE mostrar un botón «Ingresar con SSO» en la pantalla de login, que redirige a `GET /auth/sso/{provider}/login`. Tras el callback del backend, el SPA DEBE canjear la cookie de refresh por un access token vía `POST /auth/refresh`, sin que el access token viaje en la URL.

#### Scenario: Botón SSO y callback del SPA

- Dado el usuario en la pantalla de login del SPA
- Cuando hace clic en «Ingresar con SSO» y completa el login en el IdP
- Entonces el backend fija la cookie de refresh y redirige al SPA, que llama `POST /auth/refresh` y obtiene el access token sin exponerlo en la URL

## Referencias

- `openspec/changes/20-sso-keycloak/proposal.md`
- `openspec/specs/auth/spec.md` (emisión de JWT reutilizada)
