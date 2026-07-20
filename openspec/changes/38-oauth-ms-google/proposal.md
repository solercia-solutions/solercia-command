# Proposal: 38 · OAuth de Microsoft 365 y Google reparado y probable end-to-end

## Intent

El flujo OAuth de conectores nunca completa el canje del código. La UI de Conexiones dice "conectar" pero la cuenta jamás queda conectada. Diagnóstico con evidencia (no especulación):

- **Punto de fallo raíz — `redirect_uri` apunta al frontend, no al callback del backend.** El front (`connectors.service.ts:authorizeUrl`) manda solo `ticket` + `redirect_to`, NUNCA `redirect_uri`. El backend (`service.py:authorize`, línea 376) hace `redirect = redirect_uri or OAUTH_REDIRECT_ALLOWLIST[0]` → cae en `http://localhost:4200/settings/connectors`, una página SPA que no canjea el `code`. El handler real es la ruta backend `GET /api/v1/connectors/oauth/callback` (`router.py:245`), que NO está en la allowlist ni se usa jamás como destino del `code`.
- **Puertos stale.** Defaults en `config.py` referencian `:4200` (compose); dev corre front `:4242`, backend `:8081`. `GOOGLE_OAUTH_REDIRECT_URI` default = `http://localhost:4200/settings/connectors` (página SPA + puerto viejo).
- **Sin `.env.example`.** `M365_CLIENT_ID/SECRET` y `GOOGLE_OAUTH_CLIENT_ID/SECRET` son `""` por defecto y no hay archivo que documente cómo registrarlos → el authorize sale con `client_id=` vacío.
- **"Conectado" no prueba nada.** No existe operación que ejecute una capability real (calendario/correo) para verificar que el token sirve.

## Scope

### In Scope
- Reparar `redirect_uri`: nuevo setting de URL pública del callback backend (`GET .../connectors/oauth/callback`), configurable por `.env` (localhost:8081 en dev, URL del túnel devtunnel para IdP real). `authorize()` deja de caer en la allowlist del frontend.
- Depurar puertos: `OAUTH_REDIRECT_ALLOWLIST`, `GOOGLE_OAUTH_REDIRECT_URI` coherentes con :4242/:8081; separar `redirect_uri` (callback backend) de `redirect_to` (retorno SPA).
- Crear/actualizar `backend/.env.example` con `M365_*`, `GOOGLE_OAUTH_*` y el callback OAuth documentados.
- Manejo de errores del callback con mensajes claros es-CO en la UI, mapeados por código (`oauth_provider_error`, `oauth_state_invalid`, `provider_not_registered`, `oauth_unexpected_error`).
- Botón "Probar conexión" post-OAuth: endpoint que descifra el token (refresca si venció) y ejecuta una operación real de capability (listar calendario/correo de prueba); la UI muestra el resultado.
- TDD de los endpoints tocados con fake adapter (patrón `test_connectors_oauth_flow.py` / provider `"fake"`).

### Out of Scope
- Importar datos de Planner/Google (cambios 39-41).
- PKCE (diferido desde los cambios 15/16; `state` single-use + `client_secret` se mantienen).
- Registrar apps reales en Azure/Google (config externa del operador).

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `connectors`: `redirect_uri` del authorize se deriva del callback backend configurable (ya no cae en la allowlist del frontend); nuevo requisito "probar conexión" que ejecuta una operación real de capability sobre una cuenta conectada.

## Approach

Introducir `OAUTH_CALLBACK_BASE_URL` (o equivalente) en `settings`; `authorize()` construye el `redirect_uri` hacia `<base>/api/v1/connectors/oauth/callback` en vez del `OAUTH_REDIRECT_ALLOWLIST[0]` del front. `redirect_to` sigue siendo el retorno SPA validado por allowlist. Nuevo caso de uso `test_connection` en `ConnectorService` que reusa el adapter (`get_adapter`) y su puerto read-only; endpoint `POST /connectors/{id}/accounts/{account_id}/test`. Front: botón + mensajes por código. Cero cambios en los adapters (15/16 archivados) más allá de invocarlos.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/config.py` | Modified | Callback backend configurable; limpiar puertos stale |
| `backend/app/modules/connectors/service.py` | Modified | `authorize()` redirect_uri → callback backend; caso `test_connection` |
| `backend/app/modules/connectors/router.py` | Modified | Endpoint "probar conexión" |
| `backend/.env.example` | New | Documentar `M365_*`, `GOOGLE_OAUTH_*`, callback OAuth |
| `frontend/.../connections.component.ts`, `connectors.service.ts` | Modified | Botón "Probar conexión", errores es-CO por código |
| `backend/tests/test_connectors_oauth_*` | Modified/New | TDD con fake adapter |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Redirect URI debe registrarse EXACTO en Azure/Google console | Alta | `.env.example` + guía; valor configurable, no hardcode |
| URL de devtunnel cambia entre sesiones | Media | Callback y allowlist por env, reconfigurables sin recompilar |
| Sin apps reales registradas en dev | Media | Fake adapter cubre TDD; e2e real documentado como paso manual |
| Refresco de token en "probar conexión" | Media | Reusar `adapter.oauth.refresh`; fallar con mensaje claro si expiró |

## Rollback Plan

Revertir los commits de config/service/router/front/tests y el `.env.example`. Sin migración Alembic: rollback puramente de código y configuración; los conectores existentes quedan como estaban.

## Dependencies

- `26-admin-empresas`: conectores y cuentas conectadas son por empresa activa (scoping por `organization_id`).
- Adapters `15-adapter-microsoft365` y `16-adapter-google` (archivados) y el core `14-integration-ports` (`oauth.py`, `state_store`, registry).

## Success Criteria

- [ ] OAuth de M365 y Google completa e2e desde `/connections`: el `code` llega al callback backend, se canjea y la cuenta persiste cifrada (Fernet).
- [ ] El `redirect_uri` apunta al callback backend configurable; ya no cae en una página SPA.
- [ ] "Probar conexión" ejecuta una operación real de capability y muestra el resultado en la UI.
- [ ] Los errores del callback muestran mensaje claro en es-CO según su código.
- [ ] Suite backend en verde con fake adapter; `.env.example` documenta las credenciales.

## Proposal question round

Supuestos a validar con el usuario: (1) el `redirect_uri` correcto es el callback backend `GET /api/v1/connectors/oauth/callback` (no una página SPA), configurable por env para dev (:8081) y túnel; (2) "Probar conexión" ejecuta UNA operación read-only mínima (M365: perfil/`Calendars.Read`; Google: `userinfo`/`calendar.readonly`) y basta con success/fail + un dato de muestra, sin importar datos; (3) el endpoint de prueba vive en el cambio 38 aunque el panel de capacidades completo sea el 39; (4) e2e con apps reales de Azure/Google es un paso manual documentado (el CI usa fake adapter). Segunda ronda disponible para afinar qué operación exacta valida "Probar conexión" por proveedor.
