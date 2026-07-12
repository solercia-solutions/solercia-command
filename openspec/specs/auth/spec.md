# Spec — Autenticación (auth)

> **Origen**: línea base as-built (2026-07-11)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Autenticación de usuarios con JWT: emisión de access tokens Bearer y refresh tokens rotatorios vía cookie httpOnly, más los endpoints de identidad (`/auth/me`) y de navegación permitida (`/auth/me/menus`).

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | /api/v1/auth/login | Valida credenciales; devuelve access token y setea cookie de refresh |
| POST | /api/v1/auth/refresh | Rota la cookie de refresh (jti nuevo) y emite un nuevo access token |
| POST | /api/v1/auth/logout | Elimina la cookie de refresh (204) |
| GET | /api/v1/auth/me | Usuario autenticado + roles RBAC |
| GET | /api/v1/auth/me/menus | Árbol de menús accesibles según los roles del usuario |

El módulo solo tiene service (sin modelos propios); se apoya en `User` (users) y en el catálogo RBAC (roles/menus).

## Requisitos

- **R1**: El access token DEBE ser un JWT Bearer con expiración de 30 minutos.
- **R2**: El refresh token DEBE viajar en cookie httpOnly con vigencia de 7 días y `SameSite=lax`; el flag `Secure` lo gobierna `COOKIE_SECURE` (apagado por defecto).
- **R3**: Cada llamada a refresh DEBE rotar la cookie: jti nuevo y access token nuevo.
- **R4**: Las contraseñas DEBEN verificarse con bcrypt directo (truncamiento a 72 bytes).
- **R5**: `GET /auth/me/menus` DEBE devolver únicamente los menús otorgados a los roles del usuario, en estructura de árbol.

### Escenarios centrales

**R1/R2 — Login exitoso**
- Dado un usuario activo con credenciales válidas
- Cuando envía `POST /auth/login`
- Entonces recibe un access token (30 min) en el cuerpo y una cookie de refresh httpOnly de 7 días.

**R3 — Rotación de refresh**
- Dado un cliente con cookie de refresh vigente
- Cuando llama `POST /auth/refresh`
- Entonces recibe un access token nuevo y la cookie se reemplaza con un jti distinto.

**Logout**
- Dado un usuario autenticado
- Cuando llama `POST /auth/logout`
- Entonces la respuesta es 204 y la cookie de refresh queda eliminada.

**R5 — Menús por rol**
- Dado un usuario cuyo rol tiene grants sobre un subconjunto de menús
- Cuando llama `GET /auth/me/menus`
- Entonces recibe solo ese subconjunto, anidado según `parent_id`.

## Limitaciones y deuda conocida

- Sin blacklist de tokens: el jti no se persiste, por lo que logout NO invalida refresh tokens del lado del servidor.
- `COOKIE_SECURE` apagado por defecto (apto solo para desarrollo).
- bcrypt trunca la contraseña a 72 bytes en silencio.
- CERO tests del módulo (login, refresh, logout, me y menus sin cobertura).

## Referencias

- backend/app/modules/auth/ (router.py, service.py, schemas.py, dependencies.py)
- backend/app/shared/security.py
- backend/app/dependencies.py
