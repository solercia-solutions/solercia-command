# Design: 38 · OAuth de Microsoft 365 y Google reparado end-to-end

## Technical Approach

Corrección de config + service + un caso de uso nuevo, sin migración Alembic. `authorize()`
deja de derivar el `redirect_uri` de `OAUTH_REDIRECT_ALLOWLIST[0]` (página SPA, puerto :4200)
y usa un callback backend canónico configurable por env. El plumbing del `redirect_uri` por el
`state_payload` YA existe (`handle_oauth_callback` → `_complete_oauth_callback` reusa
`payload["redirect_uri"]` en `exchange_code`), así que basta cambiar el VALOR que `authorize()`
almacena — el canje y el authorize quedan con la MISMA URL exacta que se registra en Azure/Google.
`OAUTH_REDIRECT_ALLOWLIST` pasa a gobernar SOLO el `redirect_to` (retorno del navegador al SPA).
Nuevo caso de uso `test_connection` en `ConnectorService` (endpoint
`POST /connectors/{id}/accounts/{account_id}/test`) que descifra el token, refresca si venció,
ejerce el puerto read-only primario del adapter con `limit=1` y devuelve `ok + muestra`. Referencia
`specs/connectors/spec.md` (delta MODIFIED de este cambio).

## Architecture Decisions

### Decisión 1: callback backend canónico por env explícito

| Opción | Tradeoff | Decisión |
|---|---|---|
| **`OAUTH_CALLBACK_URL` (URL completa explícita)** | Se registra EXACTA en la consola del IdP; una sola fuente de verdad | **Elegida** |
| Derivar de `PUBLIC_BASE_URL` + ruta fija `/api/v1/connectors/oauth/callback` | No existe `PUBLIC_BASE_URL`; Docker mapea 8081→8000 y devtunnel cambia la URL por sesión → derivación frágil | Rechazada |

`authorize()` usa `settings.OAUTH_CALLBACK_URL` y ya NO lee el `redirect_uri` del caller ni cae en
`allowlist[0]`. `OAUTH_REDIRECT_ALLOWLIST` se limpia (fuera `:4200/settings/connectors`) y su
semántica queda restringida a `redirect_to`; se añade el origen del túnel `/connections` (vía env,
sin recompilar). `GOOGLE_OAUTH_REDIRECT_URI` (solo documental — el adapter nunca lo usa) se realinea
al callback canónico. **Matriz de URLs**:

| Entorno | `OAUTH_CALLBACK_URL` | `OAUTH_REDIRECT_ALLOWLIST` (redirect_to) |
|---|---|---|
| Local | `http://localhost:8081/api/v1/connectors/oauth/callback` | `http://localhost:4242/connections` |
| Túnel (IdP real) | `https://<tunnel>/api/v1/connectors/oauth/callback` | `https://<tunnel-front>/connections` |

### Decisión 2: flujo exacto (state firmado + redirect_to)

`authorize()` construye la URL del IdP con `redirect_uri = OAUTH_CALLBACK_URL`; el `state` (opaco,
single-use, en Redis vía `state_store.put`) transporta `connector_id/organization_id/user_id`
(resueltos del ticket efímero existente) + `redirect_uri` canónico + `return_to` (front, validado
por allowlist). El callback canjea, persiste cifrado (Fernet, transacción única existente) y 302 al
front con `?connected=1` o `?error=<código>`. El ticket firmado actual (`create_authorize_ticket`
/`resolve_authorize_ticket`) no cambia.

### Decisión 3: catálogo de errores del callback (es-CO)

| Código | Causa | Mensaje UI (tuteo) |
|---|---|---|
| `oauth_provider_error` | IdP reportó error / el usuario canceló | "El proveedor rechazó la autorización o la cancelaste." |
| `oauth_state_invalid` | state ausente/expirado/reusado | "El enlace de conexión expiró. Intenta conectar de nuevo." |
| `oauth_code_exchange_failed` | `exchange_code` falló (nuevo mapeo) | "No pudimos completar la conexión con el proveedor." |
| `provider_not_registered` | adapter ausente | "El proveedor del conector no está disponible." |
| `oauth_unexpected_error` | fallo inesperado tras consumir state | "Ocurrió un error inesperado. Intenta más tarde." |

La página de Conexiones mapea `?error=<código>` con un diccionario i18n por código (reemplaza el
banner genérico actual que muestra el código crudo).

### Decisión 4: probe read-only reusable (frontera con el 39)

| Opción | Tradeoff | Decisión |
|---|---|---|
| **`_run_readonly_probe(adapter, ctx)` selecciona la capability primaria por orden de preferencia ∩ `adapter.capabilities` y llama su `list_*(limit=1)`** | Reusa los puertos existentes (15/16); cero `if provider==`; el 39 lo consume tal cual | **Elegida** |
| Método nuevo `probe()` en cada port | Duplica lógica read-only ya existente; toca el `Protocol` del 14 | Rechazada |

38 implementa el helper reusable en `ConnectorService`; el 39 lo invocará desde
`POST /connectors/{id}/probe`. Orden declarativo: `(calendar, mail, tickets, external_tasks,
meeting_notes, external_resources)` → primera capability soportada. La selección lee el comportamiento
DESDE el adapter (regla de oro), nunca ramifica por proveedor.

### Decisión 5: refresh on-expiry

Si `credentials.expires_at <= now` (o el read devuelve 401) se refresca con
`adapter.oauth.refresh(refresh_token)` y se reintenta UNA vez. Se aprovecha el sink
`AccessContext.on_tokens_refreshed` (ya diseñado en `ports.py`) para re-cifrar y persistir los tokens
nuevos vía `save_credentials`. Si el refresh falla → `oauth_refresh_failed` con mensaje claro.

## Data Flow

    SPA /connections ─XHR─► POST authorize-ticket ─► ticket
        └─navega─► GET .../authorize?ticket=&redirect_to=<front>
                        │ authorize(): redirect_uri = OAUTH_CALLBACK_URL
                        │ state{connector,org,user,redirect_uri,return_to} → Redis
                        ▼ 302 IdP (Azure/Google)  ──login──►
    GET .../connectors/oauth/callback?code=&state=
        │ pop(state) → exchange_code(code, redirect_uri) → Fernet upsert (1 tx)
        ▼ 302 <return_to>?connected=1 | ?error=<código>

    Probar conexión: POST .../accounts/{id}/test
        └─ decrypt → (refresh si vencido) → port primario list_*(limit=1) → {ok, sample}

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/app/config.py` | Modify | `OAUTH_CALLBACK_URL`; limpiar `OAUTH_REDIRECT_ALLOWLIST` (:4200) y `GOOGLE_OAUTH_REDIRECT_URI` |
| `backend/app/modules/connectors/service.py` | Modify | `authorize()` usa `OAUTH_CALLBACK_URL`; `test_connection` + `_run_readonly_probe`; mapear `oauth_code_exchange_failed` |
| `backend/app/modules/connectors/router.py` | Modify | `POST /connectors/{id}/accounts/{account_id}/test` (owner ∨ admin/manager) |
| `backend/app/modules/connectors/schemas.py` | Modify | `ConnectionTestResult` |
| `backend/.env.example` | New | `OAUTH_CALLBACK_URL`, `OAUTH_REDIRECT_ALLOWLIST`, `M365_*`, `GOOGLE_OAUTH_*` (sin secretos) |
| `frontend/.../connectors.service.ts` | Modify | `testConnection(connectorId, accountId)` |
| `frontend/.../connections.component.ts` | Modify | Botón "Probar conexión"; errores es-CO por código |
| `frontend/.../i18n (es-CO)` | Modify | Diccionario de códigos + textos del probe |
| `backend/tests/test_connectors_oauth_*` | Modify/New | TDD con provider `"fake"` |

## Interfaces / Contracts

```python
# config.py
OAUTH_CALLBACK_URL: str = "http://localhost:8081/api/v1/connectors/oauth/callback"

# schemas.py
class ConnectionTestResult(BaseModel):
    ok: bool
    capability: str          # p. ej. "calendar"
    sample: str | None       # dato de muestra ("3 eventos"), NO datos importados
    refreshed: bool          # hubo refresh de token

# service.py — frontera que el 39 reusa
async def test_connection(self, organization_id, account_id, membership) -> ConnectionTestResult
async def _run_readonly_probe(self, adapter, connector, ctx) -> ConnectionTestResult
```

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | `authorize()` guarda `OAUTH_CALLBACK_URL` como `redirect_uri`; ya no cae en allowlist[0]; `redirect_to` fuera de allowlist → 422 | provider `"fake"` |
| Integration | callback OK canjea+persiste cifrado; provider_error/state_invalid/code_exchange_failed → 302 `?error=<código>`; `test` OK/expirado(refresh)/proveedor caído; RBAC owner vs member vs admin | fixtures `google/*.json`, `test_connectors_oauth_flow.py` |
| E2E (manual) | Registro real en Azure/Google + túnel devtunnel; conectar y "Probar conexión" desde `/connections` | guía de prueba |

## Threat Matrix

N/A — sin shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni selección de
repositorio Git (las filas de `references/threat-matrix.md` no aplican). Los invariantes de seguridad
propios del OAuth (open-redirect: `redirect_to` validado contra allowlist; `redirect_uri` canónico
NO elegible por el caller; token nunca en URL/logs; `state` single-use anti-replay) se cubren como
escenarios de seguridad en Testing Strategy, no como filas de esa matriz.

## Migration / Rollout

Sin migración de datos ni Alembic. Rollback: revertir commits de config/service/router/schemas/front/
tests + `.env.example`; los conectores y cuentas existentes quedan intactos. El operador debe registrar
el `OAUTH_CALLBACK_URL` EXACTO en Azure/Google antes del e2e real (paso manual documentado).

## Open Questions

- [ ] Operación read-only exacta por proveedor si `calendar` no está autorizado: fallback a `mail`
  (ya en el orden de preferencia); confirmar en spec si M365 debe preferir perfil/`Calendars.Read`.
- [ ] RBAC final del endpoint `test`: owner ∨ admin/manager (propuesto, espejo de `disconnect_account`).

## Forecast de tamaño (para sdd-tasks)

Estimado ~330–420 líneas (config ~15, service `authorize`+`test_connection`+`_run_readonly_probe`
~120, router+schema ~40, front botón+servicio+i18n ~90, `.env.example` ~40, tests ~90).
`400-line budget risk: Medium`. `Decision needed before apply: No`. `Chained PRs recommended: No`
(corte opcional: slice backend config+service vs slice frontend+.env si cruza el presupuesto).
