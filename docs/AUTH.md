# Autenticación y autorización — Solercia Command

Este documento describe cómo **inicia sesión** una persona usuaria, cómo se **mantiene** la
sesión de forma segura (token de acceso de vida corta en el cuerpo + token de refresco en
una cookie `httpOnly`) y cómo se **autoriza** lo que cada quien puede ver y hacer (control
de acceso por roles, RBAC, que además gobierna la navegación).

> Convención de idioma: claves JSON, nombres de campo y código en **inglés**; mensajes
> visibles en **español colombiano formal con tuteo**. El contrato exacto de cada endpoint
> está en `docs/API.md`; las decisiones de diseño, en
> `docs/adr/0008-rbac-and-jwt-refresh.md`.

---

## 1. Modelo de tokens

La sesión se sostiene con **dos** tokens JWT (HS256) con propósitos distintos. Esta
separación es deliberada: el token de acceso es de vida corta y viaja en cada petición; el
de refresco es de vida más larga, se guarda fuera del alcance de JavaScript y solo sirve
para emitir nuevos tokens de acceso.

| Token         | Vida                            | `type`      | Dónde vive                                   | Para qué sirve                                  |
| ------------- | ------------------------------- | ----------- | -------------------------------------------- | ----------------------------------------------- |
| **Acceso**    | `ACCESS_TOKEN_EXPIRE_MINUTES` = **30 min** | `access`    | Cuerpo de la respuesta de login; el frontend lo guarda en memoria y lo envía como `Authorization: Bearer`. | Autenticar cada petición a la API.              |
| **Refresco**  | `REFRESH_TOKEN_EXPIRE_DAYS` = **7 días**   | `refresh`   | Cookie `httpOnly` `SameSite=Lax` (no accesible desde JavaScript). | Obtener un nuevo token de acceso sin volver a pedir credenciales. |

### Contenido (claims)

```text
Access JWT                         Refresh JWT
  sub  = user.id                     sub  = user.id
  type = "access"                    type = "refresh"
  iat  = ahora                       jti  = identificador único del token
  exp  = ahora + 30 min              iat  = ahora
                                     exp  = ahora + 7 días
```

- `sub` es el **identificador del usuario** (UUID), no su correo.
- El claim `type` se **valida en cada decodificación**: un token de refresco no se acepta
  donde se espera uno de acceso, y viceversa. Esto evita usar el token de vida larga como
  credencial directa contra la API.
- El refresco lleva un `jti` (JWT ID) único, lo que habilita su rotación e identificación
  individual (base para una futura lista de revocación; ver «Trabajo futuro»).

### Ajustes de configuración

| Setting                       | Valor por defecto | Descripción                                                                 |
| ----------------------------- | ----------------- | --------------------------------------------------------------------------- |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`              | Vida del token de acceso (minutos).                                         |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `7`               | Vida del token de refresco (días).                                         |
| `REFRESH_COOKIE_NAME`         | `refresh_token`   | Nombre de la cookie del refresco.                                          |
| `COOKIE_SECURE`               | `False` en dev    | Si la cookie exige HTTPS (`Secure`). **Debe ser `True` en producción.**    |
| `COOKIE_SAMESITE`             | `lax`             | Política `SameSite` de la cookie.                                          |
| `JWT_SECRET`, `JWT_ALG`       | —, `HS256`        | Secreto y algoritmo de firma (ya existentes en `app/config.py`).           |

---

## 2. Flujos de sesión

### 2.1 Inicio de sesión — `POST /auth/login`

```text
Navegador                         Backend
   │  POST /auth/login {email,password}
   │ ───────────────────────────────────►
   │                                  verifica credenciales (bcrypt)
   │                                  emite access JWT (30 min)
   │                                  emite refresh JWT (7 días, jti)
   │  200 {access_token, token_type,         │
   │       user: UserRead}                    │
   │  Set-Cookie: refresh_token=...; HttpOnly; SameSite=Lax; Path=/
   │ ◄───────────────────────────────────────
   │  guarda access_token en memoria
```

- La respuesta **mantiene** `access_token` en el cuerpo (compatibilidad con el flujo de
  login actual del frontend), y **además** entrega `user` (`UserRead`, con sus roles).
- El refresco se entrega **solo** como cookie `Set-Cookie` `httpOnly`; nunca aparece en el
  cuerpo de la respuesta ni se expone a JavaScript.
- Credenciales inválidas devuelven `401` con un mensaje en español; no se distingue entre
  «correo no existe» y «contraseña incorrecta».

### 2.2 Refresco — `POST /auth/refresh`

```text
Navegador                         Backend
   │  POST /auth/refresh           (la cookie refresh_token viaja sola)
   │ ───────────────────────────────────►
   │                                  lee la cookie refresh_token
   │                                  valida firma, exp y type == "refresh"
   │                                  emite NUEVO access JWT
   │                                  ROTA el refresh (nuevo jti) y reescribe la cookie
   │  200 {access_token, token_type}         │
   │  Set-Cookie: refresh_token=<nuevo>; HttpOnly; SameSite=Lax; Path=/
   │ ◄───────────────────────────────────────
```

- **Rotación del refresco:** cada `refresh` emite un token de refresco **nuevo** (con nuevo
  `jti`) y reescribe la cookie. Esto limita la ventana de uso de un refresco filtrado y
  sienta la base para detectar reutilización en el futuro.
- Si la cookie falta, está expirada, tiene firma inválida o su `type` no es `refresh`, el
  endpoint responde `401` con un mensaje en español (la persona debe iniciar sesión de
  nuevo).
- El frontend llama a `refresh` cuando una petición protegida devuelve `401` por token de
  acceso expirado; si el refresco también falla, redirige al login.

### 2.3 Cierre de sesión — `POST /auth/logout`

```text
Navegador                         Backend
   │  POST /auth/logout
   │ ───────────────────────────────────►
   │                                  borra la cookie refresh_token
   │  204 No Content                          │
   │  Set-Cookie: refresh_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/
   │ ◄───────────────────────────────────────
   │  descarta el access_token en memoria
```

- El backend **limpia** la cookie de refresco (la sobrescribe vencida). El frontend descarta
  el token de acceso que tenía en memoria. A partir de ahí no hay forma de refrescar.

### 2.4 Identidad y navegación — `GET /auth/me` y `GET /auth/me/menus`

- `GET /auth/me` devuelve el `UserRead` del usuario autenticado, **incluyendo sus roles**
  (`roles: [{id, code, name}]`).
- `GET /auth/me/menus` devuelve el **árbol de menús** que la persona puede ver, derivado de
  los menús que conceden sus roles (`role_menus`), anidado por `parent_id` y ordenado por
  `order`. El frontend usa esta respuesta para **construir la navegación**: solo muestra las
  actividades que el rol concede. Un usuario con rol `ADMIN` ve todas las actividades.

---

## 3. Por qué una cookie `httpOnly` (y no `localStorage`)

El riesgo principal de guardar un token de vida larga en `localStorage` o `sessionStorage`
es el **XSS (Cross-Site Scripting)**: si un atacante logra ejecutar JavaScript en la página
(por una dependencia comprometida, una inyección, etc.), puede leer cualquier valor de
`localStorage` y **robar el token**, suplantando a la persona usuaria mientras el token sea
válido.

La defensa de este diseño es separar responsabilidades:

- El **token de acceso** (vida corta, 30 min) vive **en memoria** del frontend, no en
  `localStorage`. Si hay XSS, la ventana de robo es pequeña y el token caduca pronto. No se
  persiste entre recargas a propósito: tras una recarga se obtiene uno nuevo vía `refresh`.
- El **token de refresco** (vida larga, 7 días) viaja en una cookie marcada `httpOnly`. El
  atributo `httpOnly` hace que **el navegador no exponga la cookie a JavaScript**
  (`document.cookie` no la ve). Aunque haya XSS, el script no puede leer el refresco; el
  navegador la adjunta automáticamente solo en las peticiones a `/auth/refresh`.

Atributos de la cookie y su porqué:

| Atributo        | Valor (dev / prod)         | Mitiga / aporta                                                                |
| --------------- | -------------------------- | ------------------------------------------------------------------------------ |
| `HttpOnly`      | siempre activo             | **XSS**: el JavaScript de la página no puede leer la cookie.                   |
| `SameSite=Lax`  | `lax`                      | **CSRF**: la cookie no se envía en peticiones *cross-site* de terceros (sí en navegación de primer nivel). `Lax` equilibra seguridad y usabilidad para este flujo. |
| `Secure`        | `False` dev / **`True` prod** | **Sniffing**: con `Secure`, el navegador solo envía la cookie por HTTPS.    |
| `Path=/`        | `/`                        | Acota dónde se envía la cookie.                                                |

> **Dev vs. prod — el flag `Secure`.** En desarrollo el frontend corre sobre `http://` (el
> proxy del dev-server de Angular enruta `/api` → `http://backend:8000`), de modo que
> `COOKIE_SECURE` arranca en `False`; con `Secure=True` el navegador **descartaría** la
> cookie sobre HTTP y el login se «perdería» en cada refresco. En **producción** el tráfico
> es HTTPS y `COOKIE_SECURE` **debe** ser `True` (variable de entorno) para que el refresco
> nunca viaje en claro. Es el único parámetro de la cookie que cambia entre entornos.

### Mismo origen (same-origin) y la cookie

El frontend habla con el backend **al mismo origen** a través del proxy del dev-server de
Angular (`frontend/proxy.conf.json` mapea `/api` → `http://backend:8000`; `apiBase = '/api/v1'`).
Como la cookie de refresco es de **primera parte** respecto a ese origen, el navegador la
adjunta automáticamente a `POST /auth/refresh` sin configuración especial de CORS de
credenciales. En `SameSite=Lax` esto es justo lo que se busca: el refresco funciona en el
propio sitio y no se filtra a sitios de terceros.

---

## 4. Autorización (RBAC) — roles, menús y `require_admin`

La autorización del área de administración es **control de acceso basado en roles (RBAC)**.
Se apoya en cuatro tablas (ver `docs/DATA-MODEL.md`):

```text
users ──< user_roles >── roles ──< role_menus >── menus
                                                     │ parent_id (árbol)
```

- **`roles`** — roles de RBAC definidos por organización (`code` único por org), p. ej.
  `ADMIN`, `MANAGER`, `MEMBER`.
- **`user_roles`** — pivote usuario ↔ rol. Una persona puede tener **varios** roles.
- **`menus`** — actividades de la aplicación (nombre, ícono, ruta), jerárquicas vía
  `parent_id`. Son **globales** (no llevan `organization_id`).
- **`role_menus`** — pivote rol ↔ menú. Define **qué actividades concede** cada rol.

### `require_admin`

Es la dependencia que **protege todos los endpoints `/admin/*`**. Verifica que el usuario
autenticado tenga, en su organización, un rol cuyo `code` sea `ADMIN` (resuelto vía
`user_roles → roles`). Si no lo tiene, responde `403` con un mensaje en español.

```python
# Esquema objetivo (app/dependencies.py)
async def require_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    # ¿Tiene el usuario un rol con code == "ADMIN" en su organización?
    has_admin = await _user_has_role_code(db, user.id, "ADMIN")
    if not has_admin:
        raise AppException(
            "No tienes permisos de administrador para realizar esta acción.",
            code="forbidden",
            status_code=403,
        )
    return user
```

> **Dos conceptos de «rol» que conviven, no se mezclan.** El rol de **tenant** vive en
> `organization_members.role` (`admin\|manager\|member\|viewer`) y gobierna `require_role`
> en los endpoints de proyectos/tareas que ya existen — **se mantiene sin cambios**. El rol
> de **RBAC** vive en `roles` + `user_roles` y gobierna `require_admin` y la navegación por
> menús. Conservar `OrganizationMember` para la pertenencia al tenant evita reescribir la
> derivación de `organization_id` y la autorización existente. La justificación está en
> `docs/adr/0008-rbac-and-jwt-refresh.md`.

### La navegación se deriva de los menús del rol

`GET /auth/me/menus` calcula los menús **distintos** que conceden los roles del usuario
(unión sobre `role_menus`), los **anida** por `parent_id` y los ordena por `order`. El
frontend pinta el menú lateral con ese árbol: lo que un rol no concede, sencillamente **no
aparece**. Esto mantiene la navegación y la autorización en una sola fuente de verdad (el
backend), en lugar de codificar el menú en el frontend.

```jsonc
// GET /auth/me/menus  -> árbol que alimenta la navegación
[
  { "id": "...", "name": "Proyectos", "icon": "folder", "path": "/projects", "order": 0, "children": [] },
  {
    "id": "...", "name": "Administración", "icon": "settings", "path": null, "order": 3,
    "children": [
      { "id": "...", "name": "Usuarios",      "icon": "users",  "path": "/admin/users",        "order": 0, "children": [] },
      { "id": "...", "name": "Roles",         "icon": "shield", "path": "/admin/roles",        "order": 1, "children": [] },
      { "id": "...", "name": "Actividades",   "icon": "menu",   "path": "/admin/menus",        "order": 2, "children": [] },
      { "id": "...", "name": "Dependencias",  "icon": "sitemap","path": "/admin/dependencies", "order": 3, "children": [] }
    ]
  }
]
```

---

## 5. Buenas prácticas aplicadas

- **Contraseñas con bcrypt** (`app/shared/security.py`); el hash **nunca** se devuelve en
  ningún esquema de salida (`UserRead` no incluye `hashed_password`).
- **Token de acceso corto** (30 min) para reducir el daño de un robo; **refresco rotado**
  para limitar la vida útil de un refresco filtrado.
- **`httpOnly` + `SameSite=Lax` + `Secure` en prod** para mitigar XSS, CSRF y sniffing.
- **Validación del claim `type`** en cada decodificación: un token no se usa fuera de su
  propósito.
- **Mensajes de error neutros** en el login (no se revela si el correo existe).
- **Autorización en el backend**: `require_admin` protege `/admin/*` y la navegación se
  deriva de los menús del rol, no de banderas del frontend.

## 6. Trabajo futuro

- **Revocación / denylist de `jti`** (con Redis): hoy el refresco se rota pero no se mantiene
  una lista de tokens revocados; un refresco robado es válido hasta su `exp` o hasta el
  siguiente uso legítimo que lo rote. Una denylist por `jti` cerraría esa ventana y
  permitiría detectar reutilización.
- **Detección de reutilización de refresco**: si llega un `jti` ya rotado, invalidar toda la
  cadena de sesión del usuario.
- **Cookie `__Host-`** en producción para endurecer el alcance de la cookie.
