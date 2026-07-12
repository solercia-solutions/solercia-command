# Contrato de API — v1

API REST del backend de **Solercia Project Manager**.

- **Base URL (desde el navegador):** `http://localhost:8000/api/v1`
- **Formato:** JSON (`Content-Type: application/json`).
- **Autenticación:** JWT *bearer*. Tras iniciar sesión, envía el token en cada petición
  protegida mediante el header `Authorization: Bearer <access_token>`.
- **CORS:** el backend permite el origen `http://localhost:4200`.
- **Documentación interactiva:** Swagger UI disponible en `http://localhost:8000/docs`.

> Convención de idioma: los **mensajes visibles** (errores de validación, descripciones)
> se devuelven en **español colombiano formal con tuteo**. Las **claves** del JSON y los
> nombres de campo permanecen en **inglés**.

---

## Convenciones generales

### Encabezados

| Header          | Valor                          | Cuándo                          |
| --------------- | ------------------------------ | ------------------------------- |
| `Content-Type`  | `application/json`             | Peticiones con cuerpo.          |
| `Authorization` | `Bearer <access_token>`        | Todos los endpoints protegidos. |

### Sobre de respuesta

- Las colecciones devuelven el sobre `{ "data": [...], "meta": {...} }` (la forma exacta de
  `meta` depende de si el cliente pidió paginación — ver «Paginación» abajo).
- Los recursos individuales devuelven `{ "data": { ... } }`.
- Los errores devuelven `{ "detail": "<mensaje en español>", "code": "<string>", "status": <int> }`;
  los `422` de validación de esquema añaden además `"errors": [...]` con el detalle
  campo-por-campo.

### Paginación (opt-in)

Los **11 endpoints de lista** marcados con 📄 en «Resumen de endpoints» soportan paginación
**opcional** por *query string*. El contrato es **retrocompatible a propósito**: si el
cliente no envía ningún parámetro de paginación, la respuesta es **byte-idéntica** a la de
antes de este cambio (colección completa + `meta.total`) — es un requisito duro para el
frontend Angular congelado, no una preferencia de diseño.

| Parámetro | Tipo   | Default | Notas                                                                                   |
| --------- | ------ | ------- | ---------------------------------------------------------------------------------------- |
| `page`    | int    | —       | Página (base 1, `page >= 1`). Enviarlo **activa** la paginación. `page < 1` → `422`.     |
| `size`    | int    | `20`    | Registros por página, `1..100`. Fuera de rango → `422`.                                  |
| `sort`    | string | —       | Campo de orden. Cada endpoint define su propia whitelist (ver nota junto a cada `GET` de lista). Fuera de la whitelist → `422`. Enviarlo **activa** la paginación. |
| `order`   | string | `desc`  | `asc` \| `desc`. Cualquier otro valor → `422`.                                            |

**Sin `page` ni `sort`** — comportamiento heredado, byte-compatible:

```json
{ "data": [ /* colección completa */ ], "meta": { "total": 37 } }
```

**Con `page` o `sort`** — paginación activa:

```json
{ "data": [ /* slice de tamaño `size` */ ], "meta": { "page": 2, "size": 20, "total": 37 } }
```

> `size` y `order` siempre tienen un valor por defecto concreto (`20` / `desc`); por sí
> solos **no** activan la paginación — el disparador es enviar `page` o `sort`. Así un
> cliente que reenvía `size=20` (el mismo valor del default) no recibe, sin darse cuenta, un
> `meta` con forma distinta.

**`sort` fuera de la whitelist** — `422`:

```json
{
  "detail": "El campo de orden 'password_hash' no es válido. Campos permitidos: title, created_at, priority.",
  "code": "invalid_sort_field",
  "status": 422
}
```

**Caso especial — `GET /api/v1/admin/menus`**: `meta.tree` (el árbol completo de menús)
**siempre** refleja el catálogo activo completo, con o sin paginación — paginar `data` nunca
recorta el árbol de navegación.

### Códigos de estado

| Código | Significado                                                        |
| ------ | ----------------------------------------------------------------- |
| `200`  | OK — operación de lectura o login exitosos.                        |
| `201`  | Created — recurso creado.                                          |
| `400`  | Bad Request — petición inválida a nivel de negocio.               |
| `401`  | Unauthorized — falta el token o es inválido/expirado.             |
| `403`  | Forbidden — autenticado pero sin permiso sobre el recurso.        |
| `404`  | Not Found — recurso inexistente o de otra organización.          |
| `422`  | Unprocessable Entity — error de validación del esquema.          |

---

## Autenticación

### POST `/api/v1/auth/login`

Intercambia credenciales por un token de acceso. Endpoint **público**.

**Request**

```http
POST /api/v1/auth/login HTTP/1.1
Host: localhost:8000
Content-Type: application/json
```

```json
{
  "email": "admin@solercia.com",
  "password": "Admin123*"
}
```

**Response `200 OK`**

Devuelve el token de acceso y el usuario en el cuerpo, **y** entrega el token de refresco en
una cookie `httpOnly` mediante `Set-Cookie` (no aparece en el cuerpo). Ver `docs/AUTH.md`.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: refresh_token=eyJhbGciOiJIUzI1Ni...; HttpOnly; SameSite=Lax; Path=/
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c",
    "email": "admin@solercia.com",
    "full_name": "Admin Solercia",
    "is_active": true,
    "created_at": "2026-06-27T14:03:11Z",
    "roles": [
      { "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", "code": "ADMIN", "name": "Administrador" }
    ]
  }
}
```

> El `access_token` (vida corta, 30 min) viaja en el cuerpo; el frontend lo guarda en
> memoria. El **refresco** (vida larga, 7 días) solo viaja como cookie `httpOnly`
> `SameSite=Lax` (`Secure` en producción) y nunca se expone a JavaScript. `full_name` es un
> campo **derivado** del nombre desglosado de la persona (ver `docs/DATA-MODEL.md`).

**Response `401 Unauthorized`** — credenciales inválidas

```json
{
  "detail": "Correo o contraseña incorrectos."
}
```

**Response `422 Unprocessable Entity`** — campos faltantes o mal formados

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "email"],
      "msg": "El correo es obligatorio."
    }
  ]
}
```

---

### POST `/api/v1/auth/refresh`

Emite un **nuevo** token de acceso a partir de la cookie de refresco y **rota** la cookie
(emite un refresco nuevo). No requiere header `Authorization`: la cookie `refresh_token`
viaja sola. Endpoint **público** en cuanto al bearer, pero exige la cookie válida. Ver
`docs/AUTH.md`.

**Request**

```http
POST /api/v1/auth/refresh HTTP/1.1
Host: localhost:8000
Cookie: refresh_token=eyJhbGciOiJIUzI1Ni...
```

**Response `200 OK`**

```http
HTTP/1.1 200 OK
Set-Cookie: refresh_token=<nuevo-token-rotado>; HttpOnly; SameSite=Lax; Path=/
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Response `401 Unauthorized`** — la cookie falta, expiró, tiene firma inválida o su `type`
no es `refresh`

```json
{
  "detail": "Tu sesión expiró. Inicia sesión nuevamente."
}
```

---

### POST `/api/v1/auth/logout`

Cierra la sesión: **borra** la cookie de refresco (la reescribe vencida). El frontend
descarta además el token de acceso que tenía en memoria. Endpoint **público** en cuanto al
bearer.

**Request**

```http
POST /api/v1/auth/logout HTTP/1.1
Host: localhost:8000
Cookie: refresh_token=eyJhbGciOiJIUzI1Ni...
```

**Response `204 No Content`** — sin cuerpo.

```http
HTTP/1.1 204 No Content
Set-Cookie: refresh_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/
```

---

### GET `/api/v1/auth/me`

Devuelve el usuario autenticado a partir del token, **incluyendo sus roles** de RBAC.
Endpoint **protegido**.

**Request**

```http
GET /api/v1/auth/me HTTP/1.1
Host: localhost:8000
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response `200 OK`**

```json
{
  "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c",
  "email": "admin@solercia.com",
  "full_name": "Admin Solercia",
  "organization_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "is_active": true,
  "created_at": "2026-06-26T14:03:11Z",
  "roles": [
    { "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", "code": "ADMIN", "name": "Administrador" }
  ]
}
```

> `full_name` es **derivado** (`primer_nombre + ' ' + primer_apellido`); no se almacena como
> columna (ver `docs/DATA-MODEL.md`). `roles` lista los roles de RBAC del usuario
> (`{id, code, name}`).

**Response `401 Unauthorized`** — token ausente, inválido o expirado

```json
{
  "detail": "No has iniciado sesión o tu sesión expiró."
}
```

---

### GET `/api/v1/auth/me/menus`

Devuelve el **árbol de menús** (actividades) que el usuario puede ver, derivado de los menús
que conceden sus roles (`role_menus`), anidado por `parent_id` y ordenado por `order`. El
frontend lo usa para **construir la navegación**. Un usuario con rol `ADMIN` ve todas las
actividades. Endpoint **protegido**. Ver `docs/AUTH.md`.

**Request**

```http
GET /api/v1/auth/me/menus HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    { "id": "a1...", "name": "Proyectos", "icon": "folder", "path": "/projects", "order": 0, "children": [] },
    { "id": "a2...", "name": "Vista de jefe", "icon": "chart", "path": "/executive", "order": 1, "children": [] },
    { "id": "a3...", "name": "Rendimiento", "icon": "gauge", "path": "/performance", "order": 2, "children": [] },
    {
      "id": "a4...", "name": "Administración", "icon": "settings", "path": null, "order": 3,
      "children": [
        { "id": "b1...", "name": "Usuarios", "icon": "users", "path": "/admin/users", "order": 0, "children": [] },
        { "id": "b2...", "name": "Roles", "icon": "shield", "path": "/admin/roles", "order": 1, "children": [] },
        { "id": "b3...", "name": "Actividades", "icon": "menu", "path": "/admin/menus", "order": 2, "children": [] },
        { "id": "b4...", "name": "Dependencias", "icon": "sitemap", "path": "/admin/dependencies", "order": 3, "children": [] }
      ]
    }
  ]
}
```

| Campo            | Tipo            | Notas                                                        |
| ---------------- | --------------- | ----------------------------------------------------------- |
| `id`             | uuid            | Identificador del menú.                                     |
| `name`           | string          | La «actividad» visible en la navegación.                    |
| `icon`           | string \| null  | Nombre del ícono (opcional).                                |
| `path`           | string \| null  | Ruta del frontend; `null` para nodos contenedores (padres). |
| `order`          | int             | Orden de despliegue entre hermanos.                         |
| `children[]`     | array           | Submenús anidados (misma forma, recursiva).                 |

---

## Proyectos

Todos los endpoints de proyectos son **protegidos**. El `organization_id` se deriva del
token; nunca se acepta desde el cuerpo de la petición. Las consultas se filtran por el
tenant del usuario autenticado, de modo que solo se ven los proyectos de su organización.

### GET `/api/v1/projects` 📄

Lista los proyectos de la organización del usuario. Soporta paginación opcional (ver
«Paginación»). Campos ordenables (`sort`): `created_at` (por defecto), `name`, `code`.

**Request**

```http
GET /api/v1/projects HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
      "name": "Portal de clientes",
      "description": "Rediseño del portal de autogestión.",
      "methodology": "scrum",
      "status": "active",
      "organization_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "created_at": "2026-06-20T09:15:00Z"
    },
    {
      "id": "5e7d2a14-1c33-4b9f-8a6e-2f1d0c9b8a7d",
      "name": "Tablero interno",
      "description": null,
      "methodology": "kanban",
      "status": "active",
      "organization_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "created_at": "2026-06-22T16:40:00Z"
    }
  ],
  "meta": {
    "total": 2
  }
}
```

---

### POST `/api/v1/projects`

Crea un proyecto en la organización del usuario. La `methodology` selecciona la Strategy
que define columnas del tablero, estados permitidos, sprints, modo de estimación y backlog
(ver `docs/adr/0002-configurable-methodology-strategy.md`).

**Request**

```http
POST /api/v1/projects HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "name": "Portal de clientes",
  "description": "Rediseño del portal de autogestión.",
  "methodology": "scrum"
}
```

| Campo         | Tipo                                       | Obligatorio | Notas                                            |
| ------------- | ------------------------------------------ | ----------- | ------------------------------------------------ |
| `name`        | string                                     | Sí          | Nombre del proyecto.                             |
| `description` | string                                     | No          | Puede omitirse o enviarse `null`.               |
| `methodology` | `planner` \| `kanban` \| `scrum` \| `custom` | Sí        | Determina el comportamiento del proyecto.       |

**Response `201 Created`**

```json
{
  "data": {
    "id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
    "name": "Portal de clientes",
    "description": "Rediseño del portal de autogestión.",
    "methodology": "scrum",
    "status": "active",
    "organization_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
    "created_at": "2026-06-26T14:05:22Z"
  }
}
```

**Response `422 Unprocessable Entity`** — validación

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "name"],
      "msg": "El nombre es obligatorio."
    },
    {
      "type": "enum",
      "loc": ["body", "methodology"],
      "msg": "La metodología debe ser una de: planner, kanban, scrum, custom."
    }
  ]
}
```

**Response `401 Unauthorized`**

```json
{
  "detail": "No has iniciado sesión o tu sesión expiró."
}
```

---

### GET `/api/v1/projects/{id}`

Devuelve un proyecto por su identificador, solo si pertenece a la organización del usuario.

**Request**

```http
GET /api/v1/projects/3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": {
    "id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
    "name": "Portal de clientes",
    "description": "Rediseño del portal de autogestión.",
    "methodology": "scrum",
    "status": "active",
    "organization_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
    "created_at": "2026-06-20T09:15:00Z",
    "methodology_info": {
      "methodology": "scrum",
      "default_columns": ["To Do", "In Progress", "In Review", "Done"],
      "allowed_statuses": ["To Do", "In Progress", "In Review", "Done"],
      "sprints_enabled": true,
      "estimation_mode": "points",
      "has_backlog": true
    }
  }
}
```

> `methodology_info` lo deriva el backend desde la Strategy de la metodología
> (`get_strategy(project.methodology).to_info()`). El frontend lo usa para construir el
> tablero, las pestañas y los campos de estimación sin condicionales por metodología.

**Response `404 Not Found`** — no existe o pertenece a otra organización

```json
{
  "detail": "El proyecto no existe."
}
```

> Nota de seguridad: un proyecto de otra organización devuelve `404` (no `403`) para no
> revelar su existencia a tenants ajenos.

---

## Miembros del proyecto

Endpoint **protegido**. Devuelve las personas de la organización del proyecto que pueden
asignarse a una tarea. El `project_id` se valida contra el tenant del token.

### GET `/api/v1/projects/{project_id}/members`

**Request**

```http
GET /api/v1/projects/3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f/members HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    {
      "user_id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c",
      "full_name": "Administrador Solercia",
      "email": "admin@solercia.com",
      "role": "admin"
    },
    {
      "user_id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e",
      "full_name": "Laura Gómez",
      "email": "laura.gomez@solercia.com",
      "role": "member"
    }
  ]
}
```

| Campo       | Tipo                                            | Notas                              |
| ----------- | ----------------------------------------------- | ---------------------------------- |
| `user_id`   | uuid                                            | Identificador de la persona.       |
| `full_name` | string                                          | Nombre para mostrar.               |
| `email`     | string                                          | Correo de la persona.              |
| `role`      | `admin` \| `manager` \| `member` \| `viewer`    | Rol en la organización.            |

---

## Búsqueda global

Endpoint **protegido** y filtrado por el tenant del token. Busca simultáneamente en tareas, proyectos y comentarios de la organización del usuario autenticado.

### GET `/api/v1/search` 📄

Búsqueda multi-entidad con paginación **incondicional** (siempre se devuelve `meta` con `page`, `size`, `total`).

| Parámetro | Tipo | Notas |
|-----------|------|-------|
| `q` | string | Consulta (obligatoria). Mínimo 2 caracteres tras trim; consultas más cortas devuelven `422`. |
| `types` | string | Opcional, separado por comas. Valores válidos: `task`, `project`, `comment`. Por defecto todos. Valores inválidos → `422`. |
| `page`, `size`, `sort`, `order` | — | Paginación estándar (ver «Paginación»). `size` por defecto 20, máximo 100. |

**Request**

```http
GET /api/v1/search?q=factura&types=task,project&page=1&size=10 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    {
      "entity_type": "task",
      "id": "7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "title": "Generar factura de junio",
      "snippet": "...Generar **factura** de junio para el cliente XYZ.",
      "project_id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
      "project_name": "Gestión de pagos",
      "task_id": null,
      "task_key": "GES-42"
    },
    {
      "entity_type": "project",
      "id": "5f6e7d8c-9a0b-1c2d-3e4f-5a6b7c8d9e0f",
      "title": "Plataforma de facturación",
      "snippet": "...La **facturación** automatizada para medianos negocios.",
      "project_id": "5f6e7d8c-9a0b-1c2d-3e4f-5a6b7c8d9e0f",
      "project_name": "Plataforma de facturación",
      "task_id": null,
      "task_key": null
    }
  ],
  "meta": {
    "page": 1,
    "size": 10,
    "total": 2
  }
}
```

| Campo | Tipo | Notas |
|-------|------|-------|
| `entity_type` | `task` \| `project` \| `comment` | Tipo de resultado. |
| `id` | uuid | Identificador del resultado. |
| `title` | string | Título o nombre (campo principal de búsqueda). |
| `snippet` | string | Fragmento con la coincidencia resaltada. |
| `project_id` | uuid | Proyecto al que pertenece (o el proyecto mismo si `entity_type=project`). |
| `project_name` | string | Nombre del proyecto. |
| `task_id` | uuid \| null | Solo presente en `entity_type=comment`; identificador de la tarea que contiene el comentario. |
| `task_key` | string \| null | Solo presente en `entity_type=task` o `entity_type=comment`; clave legible de la tarea (ej. `SDM-7`). |

**Response `422 Unprocessable Entity`** — consulta vacía o muy corta

```json
{
  "detail": "La consulta debe tener al menos 2 caracteres.",
  "code": "query_too_short",
  "status": 422
}
```

**Response `422 Unprocessable Entity`** — tipo inválido

```json
{
  "detail": "Tipo de entidad inválido. Valores permitidos: task, project, comment.",
  "code": "invalid_search_type",
  "status": 422
}
```

---

## Tareas

Endpoints **protegidos** y filtrados por el tenant del token. El `status` de una tarea es
**siempre** uno de los `allowed_statuses` de la metodología del proyecto (el rótulo de una
columna del tablero); el backend lo valida en la capa de service. El estado por defecto al
crear es la **primera** columna de `allowed_statuses`. Ver
`docs/adr/0005-work-items-status-as-column.md`.

### GET `/api/v1/projects/{project_id}/tasks` 📄

Lista las tareas de un proyecto, con filtros opcionales por *query string*. Soporta
paginación opcional (ver «Paginación»). Campos ordenables (`sort`): `order` (por defecto,
posición en el tablero), `title`, `status`, `priority`, `due_date`, `created_at`.
**`assignee_name` NO es ordenable** (`422`): es un campo calculado en Python después de la
consulta (resuelve el nombre desde el `assignee_id`), sin columna real que lo respalde.

| Parámetro     | Tipo | Notas                                                           |
| ------------- | ---- | --------------------------------------------------------------- |
| `sprint_id`   | uuid | Filtra por sprint. Usa `sprint_id=null` para ver el backlog.    |
| `status`      | text | Filtra por columna (un valor de `allowed_statuses`).            |
| `priority`    | text | Filtra por prioridad (`critical`, `high`, `medium`, `low`). Valor inválido → `422`. |
| `assignee_id` | uuid | Filtra por persona asignada.                                    |
| `label_id`    | uuid | Filtra por etiqueta (repetible: `?label_id=X&label_id=Y` = unión, cualquiera de las dos). |
| `due_from`    | date | Filtra tareas con `due_date >= due_from` (formato `YYYY-MM-DD`). |
| `due_to`      | date | Filtra tareas con `due_date <= due_to` (formato `YYYY-MM-DD`). Si `due_from > due_to` → `422`. |
| `q`           | text | Filtra por texto libre en título y descripción (mínimo 1 carácter). |
| `page`, `size`, `sort`, `order` | — | Paginación opcional — ver «Paginación».         |

**Request**

```http
GET /api/v1/projects/3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f/tasks?status=In%20Progress HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "project_id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
      "sprint_id": "1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8",
      "title": "Diseñar el formulario de registro",
      "description": "Incluir validación de correo y contraseña.",
      "task_type": "story",
      "status": "In Progress",
      "priority": "high",
      "assignee_id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e",
      "assignee_name": "Laura Gómez",
      "estimation_points": 5,
      "estimation_hours": null,
      "due_date": "2026-07-03",
      "start_date": "2026-06-26",
      "order": 0,
      "risk_flag": false,
      "risk_reason": null,
      "created_at": "2026-06-26T15:10:00Z",
      "completed_at": null
    }
  ],
  "meta": { "total": 1 }
}
```

---

### POST `/api/v1/projects/{project_id}/tasks`

Crea una tarea en el proyecto.

**Request**

```http
POST /api/v1/projects/3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f/tasks HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "title": "Diseñar el formulario de registro",
  "description": "Incluir validación de correo y contraseña.",
  "status": "To Do",
  "priority": "high",
  "assignee_id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e",
  "estimation_points": 5,
  "due_date": "2026-07-03",
  "sprint_id": "1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8",
  "task_type": "story"
}
```

| Campo               | Tipo                                         | Obligatorio | Notas                                                              |
| ------------------- | -------------------------------------------- | ----------- | ------------------------------------------------------------------ |
| `title`             | string                                       | Sí          | Título de la tarea.                                                |
| `description`       | string                                       | No          | Detalle de la tarea.                                              |
| `status`            | text                                         | No          | Una columna de `allowed_statuses`. Por defecto, la primera.       |
| `priority`          | `critical` \| `high` \| `medium` \| `low`    | No          | Por defecto `medium`.                                             |
| `assignee_id`       | uuid                                         | No          | Persona asignada (debe ser miembro de la organización).          |
| `estimation_points` | int                                          | No          | Solo si `estimation_mode` es `points` o `both`.                   |
| `estimation_hours`  | number                                       | No          | Solo si `estimation_mode` es `hours` o `both`.                    |
| `due_date`          | date (`YYYY-MM-DD`)                          | No          | Fecha límite.                                                     |
| `sprint_id`         | uuid                                         | No          | Sprint asociado. `null` u omitido = backlog (en scrum).          |
| `task_type`         | `task` \| `bug` \| `story` \| `epic`         | No          | Por defecto `task`.                                              |

**Response `201 Created`** — devuelve `{ "data": Task }` con la forma del modelo `Task`.

**Response `422 Unprocessable Entity`** — estado fuera de las columnas de la metodología

```json
{
  "detail": "El estado «Hecho» no es válido para este proyecto. Estados permitidos: To Do, In Progress, In Review, Done."
}
```

---

### GET `/api/v1/tasks/{task_id}`

Devuelve una tarea por su identificador, solo si pertenece al tenant del token.

**Response `200 OK`** — `{ "data": Task }`.

**Response `404 Not Found`**

```json
{
  "detail": "La tarea no existe o no tienes acceso a ella."
}
```

---

### PATCH `/api/v1/tasks/{task_id}`

Actualización parcial. Solo se modifican los campos enviados. Cambiar `status` por un valor
de otra columna **mueve la tarea de columna** en el tablero.

**Request**

```http
PATCH /api/v1/tasks/7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "status": "In Review",
  "order": 2
}
```

| Campo (todos opcionales) | Notas                                                              |
| ------------------------ | ------------------------------------------------------------------ |
| `status`                 | Mover de columna. Debe ser un valor de `allowed_statuses`.        |
| `assignee_id`            | Reasignar persona, o `null` para dejar sin asignar.              |
| `priority`               | `critical` \| `high` \| `medium` \| `low`.                        |
| `title`, `description`   | Editar contenido.                                                  |
| `estimation_points`      | Estimación en puntos.                                             |
| `estimation_hours`       | Estimación en horas.                                              |
| `due_date`               | Fecha límite (`YYYY-MM-DD`) o `null`.                            |
| `risk_flag`              | Marca de riesgo (bool). Una tarea con `true` aparece en riesgo.   |
| `risk_reason`            | Motivo del riesgo.                                                |
| `sprint_id`              | Mover a un sprint, o `null` para devolver al backlog.            |
| `order`                  | Posición dentro de la columna.                                   |

**Response `200 OK`** — `{ "data": Task }`.

---

### DELETE `/api/v1/tasks/{task_id}`

Elimina una tarea del tenant.

**Response `204 No Content`** — sin cuerpo.

**Response `404 Not Found`** — no existe o pertenece a otra organización.

---

## Sprints

Endpoints **protegidos**, disponibles cuando la metodología del proyecto tiene
`sprints_enabled = true` (scrum). El `project_id` se valida contra el tenant del token.

### GET `/api/v1/projects/{project_id}/sprints` 📄

Soporta paginación opcional (ver «Paginación»). Campos ordenables (`sort`): `created_at`
(por defecto), `name`, `status`, `start_date`.

**Response `200 OK`** — sin parámetros de paginación (`meta` completo con `total`; con
`page`/`sort` la forma pasa a `{page, size, total}`, ver «Paginación»):

```json
{
  "data": [
    {
      "id": "1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8",
      "project_id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
      "name": "Sprint 1",
      "goal": "Cerrar el flujo de registro.",
      "start_date": "2026-06-26",
      "end_date": "2026-07-10",
      "status": "active",
      "completed_points": 0,
      "closed_at": null,
      "created_at": "2026-06-26T14:50:00Z",
      "created_by": "uuid | null",
      "updated_by": "uuid | null"
    }
  ],
  "meta": { "total": 1 }
}
```

---

### POST `/api/v1/projects/{project_id}/sprints`

**Request**

```json
{
  "name": "Sprint 1",
  "goal": "Cerrar el flujo de registro.",
  "start_date": "2026-06-26",
  "end_date": "2026-07-10"
}
```

| Campo        | Tipo                | Obligatorio | Notas                          |
| ------------ | ------------------- | ----------- | ------------------------------ |
| `name`       | string              | Sí          | Nombre del sprint.            |
| `goal`       | string              | No          | Objetivo del sprint.         |
| `start_date` | date (`YYYY-MM-DD`) | No          | Fecha de inicio.             |
| `end_date`   | date (`YYYY-MM-DD`) | No          | Fecha de cierre planeada.    |

**Response `201 Created`** — `{ "data": Sprint }` con `status` inicial `active`.

**Response `422 Unprocessable Entity`** — la metodología no habilita sprints

```json
{
  "detail": "Esta metodología no habilita sprints."
}
```

---

### PATCH `/api/v1/sprints/{sprint_id}`

Actualización parcial; por ejemplo, cerrar un sprint.

**Request**

```json
{
  "status": "closed"
}
```

| Campo (todos opcionales) | Notas                                          |
| ------------------------ | ---------------------------------------------- |
| `name`, `goal`           | Editar contenido del sprint.                  |
| `start_date`, `end_date` | Ajustar fechas.                               |
| `status`                 | `active` \| `closed`.                          |

**Response `200 OK`** — `{ "data": Sprint }`.

---

### GET `/api/v1/projects/{project_id}/sprints/{sprint_id}/burndown`

Endpoint **protegido**. Devuelve los datos del **burndown** del sprint: el alcance total y dos
series diarias (ideal y real) para graficar el avance. El `project_id` y el `sprint_id` se
validan contra el tenant del token. La definición del cálculo está en `docs/ARCHITECTURE.md`,
sección «Sprints y burndown».

**Request**

```http
GET /api/v1/projects/3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f/sprints/1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8/burndown HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": {
    "sprint": {
      "id": "1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8",
      "name": "Sprint 1",
      "start_date": "2026-06-19",
      "end_date": "2026-07-03",
      "status": "active"
    },
    "total_points": 33,
    "total_tasks": 8,
    "completed_tasks": 4,
    "unit": "points",
    "days": [
      { "date": "2026-06-19", "ideal": 33.0, "actual": 33 },
      { "date": "2026-06-20", "ideal": 30.6, "actual": 33 },
      { "date": "2026-06-21", "ideal": 28.3, "actual": 28 },
      { "date": "2026-06-22", "ideal": 25.9, "actual": 28 },
      { "date": "2026-06-23", "ideal": 23.6, "actual": 20 },
      { "date": "2026-06-24", "ideal": 21.2, "actual": 20 },
      { "date": "2026-06-25", "ideal": 18.9, "actual": 15 },
      { "date": "2026-06-26", "ideal": 16.5, "actual": 13 },
      { "date": "2026-06-27", "ideal": 14.1, "actual": 13 },
      { "date": "2026-06-28", "ideal": 11.8, "actual": null },
      { "date": "2026-06-29", "ideal": 9.4, "actual": null },
      { "date": "2026-06-30", "ideal": 7.1, "actual": null },
      { "date": "2026-07-01", "ideal": 4.7, "actual": null },
      { "date": "2026-07-02", "ideal": 2.4, "actual": null },
      { "date": "2026-07-03", "ideal": 0.0, "actual": null }
    ]
  }
}
```

| Campo             | Tipo                  | Notas                                                                                  |
| ----------------- | --------------------- | -------------------------------------------------------------------------------------- |
| `sprint`          | object                | Datos mínimos del sprint: `id`, `name`, `start_date`, `end_date`, `status`.            |
| `total_points`    | number                | Suma de `estimation_points` de las tareas del sprint (`0` cuando `unit = "tasks"`).    |
| `total_tasks`     | int                   | Número de tareas del sprint.                                                            |
| `completed_tasks` | int                   | Tareas del sprint ya en la columna «done».                                             |
| `unit`            | `"points"` \| `"tasks"` | `"points"` si la metodología estima en puntos; `"tasks"` en caso contrario.          |
| `days[]`          | array                 | Una entrada por día del rango `[start_date, end_date]`.                                |
| `days[].date`     | date (`YYYY-MM-DD`)   | Día del sprint.                                                                         |
| `days[].ideal`    | number                | Línea ideal: descenso lineal de `total` (en `start_date`) a `0` (en `end_date`).      |
| `days[].actual`   | number \| null        | Trabajo restante real al cierre del día; `null` para días **posteriores a hoy**.      |

> La línea `actual` es `total` menos el trabajo completado con `completed_at` en ese día o
> antes; no se proyecta al futuro (de ahí el `null`). Cuando `actual` queda por debajo de
> `ideal`, el sprint va adelantado; por encima, retrasado.

**Response `404 Not Found`** — el sprint no existe o pertenece a otra organización

```json
{
  "detail": "El sprint no existe o no tienes acceso a él."
}
```

---

### POST `/api/v1/sprints/{sprint_id}/close`

Cierra un sprint: calcula `completed_points` (suma de `estimation_points` de las tareas ya
en la columna «done») y mueve las tareas **incompletas** a otro sprint (`target_sprint_id`)
o al backlog (`sprint_id = null`) si se omite. Cerrar un sprint ya cerrado devuelve `409`.

**Request**

```json
{
  "target_sprint_id": "uuid | null"
}
```

| Campo (opcional) | Tipo         | Notas                                                             |
| ----------------- | ------------ | ------------------------------------------------------------------ |
| `target_sprint_id` | uuid \| null | Sprint destino para las tareas incompletas. Omitido/`null` = backlog. |

**Response `200 OK`**

```json
{
  "data": {
    "sprint": { "id": "uuid", "status": "closed", "completed_points": 13, "closed_at": "ISO-8601 timestamp", "...": "resto de campos de Sprint" },
    "tasks_moved": 2
  }
}
```

**Response `409 Conflict`** — el sprint ya estaba cerrado

```json
{ "detail": "El sprint ya está cerrado.", "code": "sprint_already_closed", "status": 409 }
```

---

### GET `/api/v1/projects/{project_id}/velocity`

Reporte de velocity del proyecto: la serie de sprints cerrados, el promedio de puntos
completados y una proyección de cuántos sprints más se necesitan para vaciar el backlog al
ritmo actual.

**Response `200 OK`**

```json
{
  "data": {
    "series": [
      { "sprint_id": "uuid", "name": "Sprint 1", "completed_points": 13, "closed_at": "ISO-8601 timestamp" }
    ],
    "average_velocity": 13.0,
    "backlog_points": 30,
    "projected_sprints": 3
  }
}
```

| Campo                | Tipo             | Notas                                                                       |
| --------------------- | ---------------- | ---------------------------------------------------------------------------- |
| `series[]`            | array            | Sprints cerrados, ordenados por `closed_at` ascendente.                     |
| `average_velocity`    | number           | Promedio de `completed_points` de `series`. `0.0` si no hay sprints cerrados. |
| `backlog_points`      | int              | Suma de `estimation_points` de tareas sin sprint y sin terminar.            |
| `projected_sprints`   | int \| null      | `ceil(backlog_points / average_velocity)`. `null` si `average_velocity == 0`. |

---

## Vista ejecutiva (dashboard)

### GET `/api/v1/dashboard/executive`

Endpoint **protegido** y agregado sobre las tareas del tenant del token. Responde «¿quién
hace qué y qué está en riesgo?». Las definiciones de *done*, *active*, *at risk* y *overdue*
se derivan de los `allowed_statuses` de cada proyecto (ver `docs/ARCHITECTURE.md`, sección
«Vista ejecutiva»).

| Parámetro        | Tipo | Notas                                                                 |
| ----------------- | ---- | ---------------------------------------------------------------------- |
| `threshold_days`  | int  | Opcional, por defecto `3` (`>= 1`). Ventana de `work_gap.no_recent_activity`. |

**Request**

```http
GET /api/v1/dashboard/executive?threshold_days=3 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": {
    "by_assignee": [
      {
        "user": { "id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e", "full_name": "Laura Gómez" },
        "in_progress": [
          {
            "id": "7a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
            "project_id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
            "sprint_id": "1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8",
            "title": "Diseñar el formulario de registro",
            "description": null,
            "task_type": "story",
            "status": "In Progress",
            "priority": "high",
            "assignee_id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e",
            "assignee_name": "Laura Gómez",
            "estimation_points": 5,
            "estimation_hours": null,
            "due_date": "2026-07-03",
            "start_date": "2026-06-26",
            "order": 0,
            "risk_flag": false,
            "risk_reason": null,
            "created_at": "2026-06-26T15:10:00Z"
          }
        ],
        "active_count": 1
      }
    ],
    "at_risk": [
      {
        "id": "9c8b7a6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
        "project_id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f",
        "sprint_id": null,
        "title": "Migrar el login a FastAPI",
        "description": null,
        "task_type": "task",
        "status": "To Do",
        "priority": "critical",
        "assignee_id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c",
        "assignee_name": "Administrador Solercia",
        "estimation_points": null,
        "estimation_hours": 8,
        "due_date": "2026-06-20",
        "start_date": "2026-06-15",
        "order": 1,
        "risk_flag": true,
        "risk_reason": "Bloqueada por dependencia externa.",
        "created_at": "2026-06-15T09:00:00Z"
      }
    ],
    "workload": [
      { "user": { "id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e", "full_name": "Laura Gómez" }, "active_count": 1 },
      { "user": { "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c", "full_name": "Administrador Solercia" }, "active_count": 3 }
    ],
    "projects_progress": [
      {
        "project": { "id": "3c9a1f20-7b88-4e2a-9f10-6d5c4b3a2e1f", "name": "Portal de clientes", "methodology": "scrum" },
        "total": 12,
        "done": 5,
        "in_progress": 7,
        "percent_done": 42
      }
    ],
    "totals": { "projects": 3, "tasks": 27, "overdue": 4, "at_risk": 6 },
    "work_gap": {
      "by_user": [
        {
          "user": { "id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e", "full_name": "Laura Gómez" },
          "hours_logged": 6.0,
          "hours_estimated": 10.0,
          "tasks_assigned": 5,
          "tasks_with_activity": 3
        }
      ],
      "no_recent_activity": [
        { "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c", "full_name": "Administrador Solercia" }
      ]
    }
  }
}
```

| Bloque              | Significado                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------- |
| `by_assignee`       | Por persona: sus tareas activas (`in_progress[]`, no terminadas) y `active_count`.           |
| `at_risk`           | Tareas vencidas-y-no-terminadas (`due_date < now` y no `done`) **o** con `risk_flag = true`. |
| `workload`          | Carga actual por persona (`active_count` = tareas no terminadas asignadas).                  |
| `projects_progress` | Por proyecto: `total`, `done`, `in_progress` (= `total - done`) y `percent_done`.            |
| `totals`            | Conteos globales del tenant: `projects`, `tasks`, `overdue`, `at_risk`.                       |
| `work_gap`          | Cruce asignado vs. realizado (ver detalle abajo).                                             |

**`work_gap`** — bloque aditivo (change 05); solo incluye colaboradores con **al menos una
tarea activa asignada**:

| Campo                             | Significado                                                                                  |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| `by_user[].hours_logged`           | Suma **de todo el histórico** de `TaskTimeLog.hours` del colaborador (no acota por `threshold_days`). |
| `by_user[].hours_estimated`        | Suma de `estimation_hours` de sus tareas **activas** asignadas.                              |
| `by_user[].tasks_assigned`         | Conteo de tareas activas asignadas.                                                          |
| `by_user[].tasks_with_activity`    | De esas, cuántas tienen un `TaskHistory` o `TaskTimeLog` en los **últimos `threshold_days` días**. |
| `no_recent_activity[]`             | Colaboradores con tarea activa asignada y **cero** actividad (ni `TaskHistory` ni `TaskTimeLog`, de cualquiera de sus tareas) en los últimos `threshold_days` días. `{ id, full_name }`. |

---

### GET `/api/v1/dashboard/performance`

Endpoint **protegido** y agregado sobre las tareas del tenant del token. Responde «¿cómo viene
cada persona del equipo?» con métricas comparables por colaborador. Las definiciones se derivan
de los `allowed_statuses` de cada proyecto (ver `docs/ARCHITECTURE.md`, sección «Rendimiento por
colaborador»).

| Parámetro   | Tipo | Notas                                                                       |
| ----------- | ---- | --------------------------------------------------------------------------- |
| `sprint_id` | uuid | Opcional. Si se envía, restringe el cálculo a las tareas de ese sprint.     |

**Request**

```http
GET /api/v1/dashboard/performance?sprint_id=1f2e3d4c-5b6a-7980-a1b2-c3d4e5f6a7b8 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": {
    "collaborators": [
      {
        "user": { "id": "b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e", "full_name": "Laura Gómez" },
        "completed_tasks": 3,
        "completed_points": 13,
        "active_count": 2,
        "overdue_count": 1,
        "on_time_rate": 0.67
      },
      {
        "user": { "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c", "full_name": "Administrador" },
        "completed_tasks": 2,
        "completed_points": 8,
        "active_count": 1,
        "overdue_count": 0,
        "on_time_rate": 1.0
      }
    ],
    "generated_at": "2026-06-27T14:03:11Z"
  }
}
```

| Campo                          | Tipo   | Significado                                                                                       |
| ------------------------------ | ------ | ------------------------------------------------------------------------------------------------ |
| `collaborators[]`              | array  | Una entrada por persona de la organización (o por persona con tareas en el sprint indicado).     |
| `collaborators[].user`         | object | `{ id, full_name }` de la persona.                                                               |
| `collaborators[].completed_tasks`  | int    | Tareas asignadas en la columna «done» (`status == allowed_statuses[-1]`).                    |
| `collaborators[].completed_points` | int    | Suma de `estimation_points` de esas tareas terminadas (las tareas sin puntos aportan `0`).   |
| `collaborators[].active_count` | int    | Tareas asignadas **no** terminadas (carga viva).                                                 |
| `collaborators[].overdue_count`| int    | Tareas asignadas no terminadas con `due_date < now`.                                            |
| `collaborators[].on_time_rate` | number | Proporción `0..1`: tareas terminadas a tiempo sobre las tareas terminadas que tenían `due_date`. |
| `generated_at`                 | timestamp | Instante en que se calculó la foto (ISO-8601).                                                |

> `on_time_rate` solo considera tareas **terminadas con `due_date`**. El numerador son las que
> cumplieron `completed_at.date() <= due_date.date()` (a tiempo); el denominador, todas las
> terminadas con fecha. Es `0` cuando no hay terminadas con `due_date`. Las tareas sin fecha o
> aún sin terminar no entran en el cálculo.

---

## Etiquetas (labels)

Endpoints **protegidos**. Las etiquetas son de **scope de proyecto** (`name` único entre las
etiquetas **activas** de un mismo proyecto; el mismo nombre puede repetirse en proyectos
distintos) y se vinculan a tareas mediante `TaskLabel` (M:N). Eliminar una etiqueta la
desvincula de todas sus tareas — las tareas mismas nunca se modifican.

### GET `/api/v1/projects/{project_id}/labels` 📄

Lista las etiquetas activas de un proyecto. Soporta paginación opcional (ver «Paginación»).
Campos ordenables (`sort`): `name` (por defecto), `created_at`.

**Response `200 OK`**

```json
{
  "data": [
    { "id": "uuid", "project_id": "uuid", "name": "Urgente", "color": "#FF0000", "created_at": "ISO-8601 timestamp" }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/projects/{project_id}/labels`

```json
{ "name": "Urgente", "color": "#FF0000" }
```

| Campo   | Tipo   | Obligatorio | Notas                                                            |
| ------- | ------ | ----------- | ------------------------------------------------------------------ |
| `name`  | string | Sí          | Único entre las etiquetas activas del proyecto.                   |
| `color` | string | Sí          | Color libre (p. ej. hex `#RRGGBB`); el backend no valida el formato. |

**Response `201 Created`** — `{ "data": Label }`.

**Response `422 Unprocessable Entity`** — nombre duplicado entre etiquetas activas del proyecto

```json
{ "detail": "Ya existe una etiqueta activa llamada 'Urgente' en este proyecto.", "code": "duplicate_label_name", "status": 422 }
```

### PATCH `/api/v1/labels/{label_id}`

Renombra y/o recolorea. `name` se revalida contra el resto de etiquetas activas del proyecto.

**Response `200 OK`** — `{ "data": Label }`.

### DELETE `/api/v1/labels/{label_id}`

Borrado lógico: desvincula la etiqueta de todas sus tareas (las tareas quedan intactas).
**Response `204 No Content`**.

### POST `/api/v1/tasks/{task_id}/labels`

Asigna una etiqueta a una tarea. Ambas deben pertenecer al mismo proyecto.

```json
{ "label_id": "uuid" }
```

**Response `201 Created`** — `{ "data": [Label], "meta": { "total": int } }` (las etiquetas
activas de la tarea tras la asignación).

**Response `422 Unprocessable Entity`** — la etiqueta es de otro proyecto

```json
{ "detail": "La etiqueta no pertenece al mismo proyecto de la tarea.", "code": "label_project_mismatch", "status": 422 }
```

### DELETE `/api/v1/tasks/{task_id}/labels/{label_id}`

Desasigna una etiqueta de una tarea (sin efecto si no estaba asignada). **Response `204 No Content`**.

---

## Checklists

Endpoints **protegidos**, anidados bajo una tarea. Desglosan el «cómo» ejecutar una tarea sin
crear subtareas formales. Cada `TaskChecklist` tiene ítems (`ChecklistItem`) marcables; el
progreso (`done`/`total`) se calcula en el backend, nunca se envía desde el cliente.

### GET `/api/v1/tasks/{task_id}/checklists`

Lista los checklists activos de una tarea, cada uno con su progreso embebido. **No es
paginable** en este contrato (colección acotada por tarea, mismo criterio que
`GET /projects/{id}/board`) — siempre devuelve la colección completa, `meta: { total }`.

**Response `200 OK`**

```json
{
  "data": [
    { "id": "uuid", "task_id": "uuid", "title": "Antes de publicar", "order": 0, "created_at": "ISO-8601 timestamp", "done": 2, "total": 5 }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/tasks/{task_id}/checklists`

```json
{ "title": "Antes de publicar", "order": 0 }
```

**Response `201 Created`** — `{ "data": TaskChecklist }` (`done`/`total` en `0` — sin ítems aún).

### PATCH `/api/v1/checklists/{checklist_id}`

Renombra y/o reordena (`title`, `order`, ambos opcionales). **Response `200 OK`** — `{ "data": TaskChecklist }`.

### DELETE `/api/v1/checklists/{checklist_id}`

Borrado lógico. Sus ítems dejan de contar en el progreso agregado. **Response `204 No Content`**.

### GET `/api/v1/checklists/{checklist_id}/items`

Lista los ítems activos de un checklist, ordenados. **No es paginable** (mismo criterio que
la lista de checklists).

**Response `200 OK`**

```json
{
  "data": [
    { "id": "uuid", "checklist_id": "uuid", "text": "Revisar textos", "is_done": false, "order": 0, "created_at": "ISO-8601 timestamp" }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/checklists/{checklist_id}/items`

```json
{ "text": "Revisar textos", "order": 0 }
```

**Response `201 Created`** — `{ "data": ChecklistItem }`.

### PATCH `/api/v1/checklist-items/{item_id}`

Edita el texto y/o reordena (`text`, `order`, ambos opcionales). `is_done` **no** se cambia
aquí — usa el endpoint de toggle. **Response `200 OK`** — `{ "data": ChecklistItem }`.

### PATCH `/api/v1/checklist-items/{item_id}/toggle`

Invierte `is_done` (sin cuerpo). **Response `200 OK`** — `{ "data": ChecklistItem }`.

### DELETE `/api/v1/checklist-items/{item_id}`

Borrado lógico. **Response `204 No Content`**.

---

## Dependencias entre tareas

Endpoints **protegidos**, anidados bajo `/tasks/{task_id}/dependencies` — **nunca** un
prefijo plano `/dependencies` (ese ya lo usa `/api/v1/admin/dependencies`, las áreas
organizacionales; ver «Administración» más abajo — son conceptos distintos sin relación
entre sí). Modelan bloqueos dirigidos entre tareas del **mismo proyecto**
(`blocker` bloquea a `blocked`) con prevención de ciclos (directos y transitivos).

### GET `/api/v1/tasks/{task_id}/dependencies` 📄

Lista, desde la perspectiva de la tarea del path, sus enlaces activos en **ambas
direcciones** (`direction: "blocks"` — esta tarea bloquea a `related_task_id` — o
`direction: "is_blocked_by"` — `related_task_id` bloquea a esta tarea). Soporta paginación
opcional (ver «Paginación»). Campo ordenable (`sort`): `created_at` (único, por defecto).

**Response `200 OK`**

```json
{
  "data": [
    { "id": "uuid", "related_task_id": "uuid", "direction": "is_blocked_by", "created_at": "ISO-8601 timestamp" }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/tasks/{task_id}/dependencies`

Enlaza la tarea del path con `related_task_id`. `type` decide la dirección: con
`"blocks"` (por defecto) la tarea del path bloquea a `related_task_id`; con
`"is_blocked_by"` es al revés — el backend **invierte** el par antes de persistir al par
canónico `blocker -> blocked` (una sola fila dirigida por relación; no hay una fila
`is_blocked_by` separada).

```json
{ "related_task_id": "uuid", "type": "is_blocked_by" }
```

| Campo             | Tipo                          | Obligatorio | Notas                                             |
| ------------------ | ------------------------------ | ----------- | -------------------------------------------------- |
| `related_task_id`  | uuid                           | Sí          | La otra tarea del enlace.                          |
| `type`             | `"blocks"` \| `"is_blocked_by"` | No          | Por defecto `"blocks"`.                            |

**Response `201 Created`** — `{ "data": TaskDependencyRead }` (misma forma que el listado).

**Response `422 Unprocessable Entity`** — casos rechazados:

```json
{ "detail": "Una tarea no puede depender de sí misma.", "code": "dependency_self_loop", "status": 422 }
```
```json
{ "detail": "Solo puedes enlazar tareas del mismo proyecto.", "code": "dependency_project_mismatch", "status": 422 }
```
```json
{ "detail": "Este enlace introduciría un ciclo de dependencias entre tareas.", "code": "dependency_cycle", "status": 422 }
```

### DELETE `/api/v1/tasks/{task_id}/dependencies/{dependency_id}`

Desenlaza (borrado **lógico** — nunca físico; `dependency_id` debe pertenecer a un enlace que
toque la tarea del path). **Response `204 No Content`**.

---

## Comentarios

Endpoints **protegidos**, anidados bajo una tarea. Solo el autor original puede editar o
borrar su propio comentario (`403` en caso contrario). Los `@mention` en el cuerpo (UUID de
usuario embebido) disparan una notificación in-app al usuario mencionado (si es miembro de
la organización y no es el propio autor).

### GET `/api/v1/tasks/{task_id}/comments` 📄

Lista los comentarios de una tarea, del más antiguo al más reciente. Soporta paginación
opcional (ver «Paginación»). Campos ordenables (`sort`): `created_at` (por defecto), `body`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "task_id": "uuid",
      "author_id": "uuid",
      "body": "Buen avance @b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e, ¿lo revisamos mañana?",
      "mentioned_user_ids": ["b2d4f6a8-0c1e-4a3b-9d5f-7e8c9a0b1d2e"],
      "organization_id": "uuid",
      "created_at": "ISO-8601 timestamp",
      "updated_at": "ISO-8601 timestamp",
      "created_by": "uuid | null",
      "updated_by": "uuid | null"
    }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/tasks/{task_id}/comments`

```json
{ "body": "Texto del comentario (puede incluir @uuid para mencionar)." }
```

**Response `201 Created`** — `{ "data": Comment }`.

### PATCH `/api/v1/comments/{comment_id}`

Edita el `body`. Solo el autor original. Las menciones **nuevas** respecto al texto anterior
disparan notificación; las que ya estaban no se repiten.

**Response `200 OK`** — `{ "data": Comment }`. **Response `403 Forbidden`** si no eres el autor.

### DELETE `/api/v1/comments/{comment_id}`

Borrado lógico. Solo el autor original. **Response `204 No Content`**.

---

## Adjuntos

Endpoints **protegidos**, anidados bajo una tarea o un comentario. Suben archivos vía
`multipart/form-data`; el máximo es **10 MB**. El nombre en disco es un UUID (previene
*path traversal*); el nombre original se conserva para la descarga. Se rechazan tipos
activos (HTML/JS/SVG/ejecutables) sin importar la extensión declarada.

### GET `/api/v1/tasks/{task_id}/attachments` 📄

Lista los adjuntos de una tarea, del más reciente al más antiguo. Soporta paginación
opcional (ver «Paginación»). Campos ordenables (`sort`): `created_at` (por defecto),
`original_name`, `size_bytes`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "target_type": "task",
      "target_id": "uuid",
      "original_name": "diseño-formulario.png",
      "content_type": "image/png",
      "size_bytes": 204800,
      "uploaded_by": "uuid",
      "organization_id": "uuid",
      "created_at": "ISO-8601 timestamp",
      "created_by": "uuid | null",
      "updated_by": "uuid | null"
    }
  ],
  "meta": { "total": 1 }
}
```

### POST `/api/v1/tasks/{task_id}/attachments`

`multipart/form-data` con un campo `file`. **Response `201 Created`** — `{ "data": Attachment }`.
**Response `413`** si excede 10 MB; **`422`** si el archivo está vacío o el tipo no está permitido.

### GET `/api/v1/comments/{comment_id}/attachments`

Lista los adjuntos de un comentario. **No es paginable** en este contrato (fuera del alcance
de los 11 endpoints con `page`/`size`/`sort`/`order`) — siempre devuelve la colección
completa, `meta: { total }`.

### POST `/api/v1/comments/{comment_id}/attachments`

Igual que el de tarea, pero anidado bajo un comentario. **Response `201 Created`**.

### GET `/api/v1/attachments/{attachment_id}/download`

Descarga el archivo binario. Responde con `Content-Disposition: attachment` (fuerza la
descarga, nunca renderiza inline) y `X-Content-Type-Options: nosniff`.

---

## Notificaciones

Endpoints **protegidos**. Las notificaciones son generadas por el sistema (menciones,
alertas); no existe un `POST` público para crearlas directamente.

### GET `/api/v1/notifications` 📄

Lista las notificaciones del usuario autenticado. Por defecto solo las **activas**
(`status=active`); `?status=` permite pedir otro estado. Soporta paginación opcional (ver
«Paginación»). Campos ordenables (`sort`): `created_at` (por defecto), `title`, `status`.

| Parámetro | Tipo                                     | Notas                                    |
| --------- | ----------------------------------------- | ----------------------------------------- |
| `status`  | `active` \| `read` \| `resolved` \| `silenced` | Filtra por estado. Por defecto `active`. |
| `page`, `size`, `sort`, `order` | —           | Paginación opcional — ver «Paginación».  |

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "organization_id": "uuid",
      "recipient_user_id": "uuid",
      "rule_type": "task_overdue",
      "title": "Tarea vencida",
      "body": "«Migrar el login a FastAPI» venció hace 2 días.",
      "target_type": "task",
      "target_id": "uuid",
      "dedup_key": "task_overdue:uuid",
      "status": "active",
      "created_at": "ISO-8601 timestamp",
      "updated_at": "ISO-8601 timestamp"
    }
  ],
  "message": "Notificaciones obtenidas.",
  "meta": { "total": 1 }
}
```

### GET `/api/v1/notifications/unread-count`

```json
{ "data": { "count": 3 }, "message": "Conteo de notificaciones no leídas." }
```

### PATCH `/api/v1/notifications/{notification_id}`

Cambia el estado de una notificación propia. Solo acepta transiciones a `read`, `resolved`
o `silenced`.

```json
{ "status": "read" }
```

**Response `200 OK`** — `{ "data": Notification, "message": "...", "meta": {} }`.

---

## Preferencias de notificación

Endpoints **protegidos**. Configuran la frecuencia del resumen de notificaciones por correo electrónico (digest) del usuario autenticado. El sistema aplica defaults sensatos (`frequency: none`) si el usuario no tiene registro previo.

### GET `/api/v1/notification-preferences`

Devuelve la preferencia de digest del usuario autenticado (o defaults si no existe registro).

**Request**

```http
GET /api/v1/notification-preferences HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`** — el usuario sin registro previo recibe defaults:

```json
{
  "data": {
    "frequency": "none",
    "digest_hour": null,
    "digest_weekday": null
  }
}
```

**Response `200 OK`** — el usuario con preferencia activa:

```json
{
  "data": {
    "frequency": "daily",
    "digest_hour": 8,
    "digest_weekday": null
  }
}
```

| Campo            | Tipo                                    | Notas                                                     |
| ---------------- | --------------------------------------- | --------------------------------------------------------- |
| `frequency`      | `none` \| `daily` \| `weekly`          | `none` = sin digest; `daily` = a la hora especificada; `weekly` = en el día/hora especificados. |
| `digest_hour`    | int (0-23) \| null                     | Hora del día (UTC o según configuración de la app) para despachar el digest. Obligatorio si `frequency != "none"`. |
| `digest_weekday` | int (0-6) \| null                      | Día de la semana (0=lunes, 6=domingo) para digest semanal. Obligatorio si `frequency == "weekly"`. |

### PUT `/api/v1/notification-preferences`

Crea o actualiza la preferencia del usuario autenticado. Valida `frequency` y la hora; una preferencia inválida responde `422`.

**Request**

```http
PUT /api/v1/notification-preferences HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "frequency": "daily",
  "digest_hour": 8
}
```

| Campo            | Tipo                                    | Obligatorio | Notas                                                         |
| ---------------- | --------------------------------------- | ----------- | ------------------------------------------------------------- |
| `frequency`      | `none` \| `daily` \| `weekly`          | Sí          | Frecuencia del digest.                                        |
| `digest_hour`    | int (0-23)                              | No          | Requerido si `frequency != "none"`.                           |
| `digest_weekday` | int (0-6)                               | No          | Requerido si `frequency == "weekly"`.                         |

**Response `200 OK`** — `{ "data": NotificationPreference }` (misma forma de respuesta que `GET`).

**Response `422 Unprocessable Entity`** — campos faltantes u mal formados:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "digest_hour"],
      "msg": "La hora debe estar entre 0 y 23."
    }
  ]
}
```

**Response `422 Unprocessable Entity`** — frecuencia inválida:

```json
{
  "detail": "La frecuencia debe ser 'none', 'daily' o 'weekly'.",
  "code": "invalid_frequency",
  "status": 422
}
```

---

## Canal email

### Arquitectura

El sistema envía notificaciones también por correo electrónico como complemento al canal in-app. El envío es **best-effort** (una falla no afecta a la persistencia de la notificación in-app) y se clasifica en dos categorías:

- **Urgentes**: enviadas **inmediatamente** tras la creación de la notificación (ej. `rule_type="license_expired"`).
- **Digest**: agrupadas en un resumen diario o semanal según la preferencia del usuario (ej. `rule_type="task_overdue"`, `rule_type="task_at_risk"`). Si el usuario tiene `frequency="none"`, nunca recibe digest.

### Configuración

| Variable              | Valor por defecto | Descripción                                                              |
| --------------------- | ------------------ | ---------------------------------------------------------------------- |
| `EMAIL_ENABLED`       | `False`            | Master switch. `False` = sin encolado ni envío.                         |
| `EMAIL_BACKEND`       | `"console"`        | Adaptador: `"console"` (captura en memoria, dev/tests) o `"smtp"` (real). |
| `SMTP_HOST`           | `"localhost"`      | Host SMTP (solo si `EMAIL_BACKEND="smtp"`).                            |
| `SMTP_PORT`           | `25`               | Puerto SMTP.                                                            |
| `SMTP_USER`           | `""`               | Usuario SMTP (opcional).                                               |
| `SMTP_PASSWORD`       | `""`               | Contraseña SMTP (opcional).                                            |
| `SMTP_FROM`           | `"noreply@..."`    | Dirección «from» en el encabezado.                                      |
| `EMAIL_MAX_ATTEMPTS`  | `5`                | Reintentos antes de marcar como `failed` (terminal).                    |
| `EMAIL_DIGEST_TZ`     | `"America/Bogota"` | Zona horaria para cálculo de digest.                                    |
| `EMAIL_DISPATCH_INTERVAL_MINUTES` | `5` | Intervalo del job periódico de despacho urgentes/reintentos.            |
| `EMAIL_DIGEST_INTERVAL_MINUTES`   | `30` | Intervalo del job periódico de agregación de digest.                    |

### Outbox transaccional

Las notificaciones urgentes se encolan en la tabla `email_outbox` dentro de la misma transacción que crea la `Notification`, garantizando atomicidad. Si la transacción se revierte, el correo también se revierte. El envío es post-commit best-effort:

1. El sistema llama `enqueue_immediate_email()` dentro de la tx de negocio.
2. La tx hace commit; `email_outbox` tiene filas `status="pending"`.
3. Un job periódico (`email_dispatch`) despacha las filas `pending` (claim atómico, reintentos, marcado `sent`/`failed`).
4. Un fallo de red/SMTP no bloquea ni revierte la tx de negocio.

**Estados de outbox**: `pending` (sin enviar) → `sending` (en despacho, claim para evitar duplicados) → `sent` (éxito) o `failed` (terminal, tras `EMAIL_MAX_ATTEMPTS` fallos, se registra ERROR y no se reintenta).

### Idempotencia

Cada fila de `email_outbox` tiene `dedup_key` único (por organización, tipo de notificación y período). Ejecutar el job dos veces con el mismo estado no genera un segundo correo:

- Digest: dedup_key = `"digest:{user_id}:{período}"`. Las notificaciones se marcan `emailed_at` tras envío; un segundo digest no encuentra notificaciones sin `emailed_at` y no envía.
- Urgentes: dedup_key = `"urgent:{notification_id}"`. La tabla `email_outbox` asegura que no hay dos filas con la misma clave.

---

## Reglas de alerta

Reglas configurables del motor de alertas, org-scoped. **No hay `POST`**: las reglas se
siembran por organización (una por `rule_type`); solo se activan/ajustan. El seed por
defecto crea **5** reglas: `task_overdue`, `task_at_risk`, `sprint_at_risk`,
`workload_imbalance` y `blocked_task` (esta última notifica al `assignee` de una tarea
bloqueada por más de `threshold_params.blocked_days` días — por defecto `3` — cuando el
bloqueador sigue sin completar; ver «Dependencias entre tareas»).

### GET `/api/v1/alert-rules` 📄

Endpoint **protegido** (cualquier miembro autenticado). Soporta paginación opcional (ver
«Paginación»). Campos ordenables (`sort`): `rule_type` (por defecto), `enabled`, `created_at`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "organization_id": "uuid",
      "rule_type": "task_overdue",
      "enabled": true,
      "threshold_params": { "days_before": 3 },
      "is_active": true,
      "created_at": "ISO-8601 timestamp",
      "updated_at": "ISO-8601 timestamp"
    }
  ],
  "message": "Reglas de alerta obtenidas.",
  "meta": { "total": 1 }
}
```

### PATCH `/api/v1/alert-rules/{rule_id}`

Endpoint **protegido y admin** (`require_admin`). Ajusta `enabled` y/o `threshold_params`.

```json
{ "enabled": false }
```

**Response `200 OK`** — `{ "data": AlertRule, "message": "...", "meta": {} }`.

---

## Registro de tiempo (time-logs)

Endpoints **protegidos**. Cada colaborador registra su propio tiempo trabajado en una tarea
(«trabajo realizado»); es la fuente que el bloque `work_gap` de la vista ejecutiva compara
contra `estimation_hours`. **Editar y eliminar son estrictamente del dueño**: un `manager` o
`admin` que intente modificar el registro de otra persona recibe `403`, sin excepción de rol.
La lectura «de todos» (`GET /users/{user_id}/time-logs` y su `summary` de otro usuario) sí
está reservada a `admin`/`manager` — un `member`/`viewer` solo consulta lo propio.

### GET `/api/v1/tasks/{task_id}/time-logs` 📄

Lista las entradas de tiempo de una tarea (cualquier miembro autenticado). Soporta paginación
opcional (ver «Paginación»). Campos ordenables (`sort`): `date` (por defecto), `created_at`,
`hours`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "task_id": "uuid",
      "user_id": "uuid",
      "date": "2026-02-10",
      "hours": 2.5,
      "note": "Avance inicial",
      "created_at": "ISO-8601 timestamp",
      "created_by": "uuid | null",
      "updated_by": "uuid | null"
    }
  ],
  "meta": { "total": 1 }
}
```

> `date` es el alias público de la columna interna `work_date` (`TaskTimeLog.work_date`) —
> el contrato observable usa `date`, la columna puede diferir.

### POST `/api/v1/tasks/{task_id}/time-logs`

Registra tiempo propio (`201`). `user_id` siempre es el usuario autenticado — no se acepta
como input. `hours` es un `Decimal > 0` (máximo `24`); `hours <= 0` responde `422`.

```json
{ "date": "2026-02-10", "hours": 2.5, "note": "Avance inicial" }
```

**Response `201 Created`** — `{ "data": TimeLog }` (ver arriba).

### PATCH `/api/v1/time-logs/{log_id}`

Edita una entrada propia. `403` si el llamante no es el dueño (`log.user_id`), **incluidos**
`manager`/`admin`.

```json
{ "hours": 3 }
```

**Response `200 OK`** — `{ "data": TimeLog }`.

### DELETE `/api/v1/time-logs/{log_id}`

Borrado lógico de una entrada propia. `403` si el llamante no es el dueño, **incluidos**
`manager`/`admin`.

**Response `204 No Content`**

### GET `/api/v1/users/{user_id}/time-logs` 📄

Lista las entradas de un usuario. El propio usuario siempre puede consultarse a sí mismo;
consultar a otro usuario requiere rol `admin` o `manager` (`403` para `member`/`viewer`).
Soporta paginación opcional y filtro de rango de fechas.

| Parámetro   | Tipo | Notas                                   |
| ----------- | ---- | ---------------------------------------- |
| `date_from` | date | Opcional. Filtra `date >= date_from`.    |
| `date_to`   | date | Opcional. Filtra `date <= date_to`.      |

**Response `200 OK`** — misma forma que el listado por tarea, con `meta` de paginación.

### GET `/api/v1/users/{user_id}/time-logs/summary`

Agregación diaria y semanal de horas de un usuario. Mismo control de visibilidad que el
listado por usuario (propio siempre; ajeno solo `admin`/`manager`).

| Parámetro   | Tipo | Notas                                  |
| ----------- | ---- | --------------------------------------- |
| `date_from` | date | Opcional. Acota la ventana agregada.    |
| `date_to`   | date | Opcional. Acota la ventana agregada.    |

**Response `200 OK`**

```json
{
  "data": {
    "daily": [{ "date": "2026-02-16", "hours": 5.0 }],
    "weekly": [{ "week_start": "2026-02-16", "hours": 10.0 }]
  }
}
```

> Si un usuario registra más de una entrada el mismo día (misma o distinta tarea), la
> agregación diaria las suma. `week_start` es el lunes ISO de la semana (`date_trunc('week',
> work_date)` en Postgres); la agregación semanal suma todas las entradas de esa semana.

---

## Historial de actividad (activity)

Endpoints **protegidos** y de **solo lectura**: no existe `PATCH`/`DELETE` sobre una fila de
historial — una petición a esas rutas responde `404` de enrutamiento (la ruta no existe), no
un `403` de autorización. El changelog se genera automáticamente en el backend (nunca es
input del cliente): al cambiar `status`, `assignee_id`, `estimation_points`/
`estimation_hours`, `sprint_id` o `priority` vía `PATCH /tasks/{id}` (`actor_type: "user"`),
y al mover tareas incompletas en `POST /sprints/{id}/close` (`actor_type: "system"`,
`actor_id: null`).

### GET `/api/v1/tasks/{task_id}/history` 📄

Historial completo de una tarea, ordenado por `changed_at` **descendente** por defecto.
Soporta paginación opcional. Campos ordenables (`sort`): `created_at` (por defecto), `field`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "uuid",
      "task_id": "uuid",
      "actor_id": "uuid | null",
      "actor_type": "user | system",
      "field": "status",
      "old_value": "To Do",
      "new_value": "Doing",
      "changed_at": "ISO-8601 timestamp"
    }
  ],
  "meta": { "total": 1 }
}
```

> `changed_at` es el alias público de la columna interna `created_at`
> (`TaskHistory.created_at`) — el contrato observable usa `changed_at`. `actor_id` es `null`
> cuando `actor_type == "system"` (p. ej. el cierre de sprint que mueve tareas al backlog).

### GET `/api/v1/users/{user_id}/activity` 📄

Cambios que un usuario provocó como actor (`actor_id`), filtrables por día o rango. Soporta
paginación opcional.

| Parámetro   | Tipo | Notas                                          |
| ----------- | ---- | ------------------------------------------------ |
| `date`      | date | Opcional. Restringe a un único día calendario.    |
| `date_from` | date | Opcional. Inicio de rango (inclusive).            |
| `date_to`   | date | Opcional. Fin de rango (inclusive).               |

**Response `200 OK`** — misma forma que el historial por tarea, con `meta` de paginación.

---

## Administración (`/admin/*`)

Endpoints **protegidos** por la dependencia `require_admin`: el llamante debe tener un rol de
RBAC con `code = "ADMIN"` en su organización (ver `docs/AUTH.md`). Todos usan el sobre
`{ data, meta }`, mensajes en español y, donde aplica, están **acotados al tenant** del
token (`dependencies`, `roles` y `users` se filtran por `organization_id`; `menus` es
global). Un llamante sin rol `ADMIN` recibe `403`.

```json
{
  "detail": "No tienes permisos de administrador para realizar esta acción."
}
```

### Dependencias

Áreas organizacionales («dependencia»), org-scoped.

#### GET `/api/v1/admin/dependencies` 📄

Soporta paginación opcional (ver «Paginación»). Campos ordenables (`sort`): `name` (por
defecto), `code`, `created_at`.

**Response `200 OK`**

```json
{
  "data": [
    { "id": "d1...", "name": "Dirección", "code": "DIR", "is_active": true, "created_at": "2026-06-27T14:00:00Z" },
    { "id": "d2...", "name": "Tecnología", "code": "TEC", "is_active": true, "created_at": "2026-06-27T14:00:00Z" },
    { "id": "d3...", "name": "Operaciones", "code": "OPS", "is_active": true, "created_at": "2026-06-27T14:00:00Z" }
  ],
  "meta": { "total": 3 }
}
```

#### POST `/api/v1/admin/dependencies`

```json
{
  "name": "Talento Humano",
  "code": "TH"
}
```

| Campo  | Tipo   | Obligatorio | Notas                          |
| ------ | ------ | ----------- | ------------------------------ |
| `name` | string | Sí          | Nombre de la dependencia.      |
| `code` | string | No          | Código corto opcional.         |

**Response `201 Created`** — `{ "data": Dependency }`.

#### GET `/api/v1/admin/dependencies/{id}`

**Response `200 OK`** — `{ "data": Dependency }`. `404` si no existe o es de otra organización.

#### PATCH `/api/v1/admin/dependencies/{id}`

Actualización parcial (`name`, `code`, `is_active`). **Response `200 OK`** — `{ "data": Dependency }`.

#### DELETE `/api/v1/admin/dependencies/{id}`

Borrado lógico (*soft-delete*). **Response `204 No Content`**.

---

### Roles

Roles de RBAC, org-scoped (`code` único por organización).

#### GET `/api/v1/admin/roles` 📄

Soporta paginación opcional (ver «Paginación»). Campos ordenables (`sort`): `name` (por
defecto), `code`, `created_at`.

**Response `200 OK`**

```json
{
  "data": [
    { "id": "r1...", "code": "ADMIN", "name": "Administrador", "is_active": true, "created_at": "2026-06-27T14:00:00Z" },
    { "id": "r2...", "code": "MANAGER", "name": "Líder", "is_active": true, "created_at": "2026-06-27T14:00:00Z" },
    { "id": "r3...", "code": "MEMBER", "name": "Colaborador", "is_active": true, "created_at": "2026-06-27T14:00:00Z" }
  ],
  "meta": { "total": 3 }
}
```

#### POST `/api/v1/admin/roles`

```json
{
  "code": "AUDITOR",
  "name": "Auditor"
}
```

| Campo  | Tipo   | Obligatorio | Notas                                       |
| ------ | ------ | ----------- | ------------------------------------------- |
| `code` | string | Sí          | Código único por organización (p. ej. `AUDITOR`). |
| `name` | string | Sí          | Nombre visible del rol.                     |

**Response `201 Created`** — `{ "data": Role }`.

#### GET `/api/v1/admin/roles/{id}`

**Response `200 OK`** — `{ "data": Role }`. `404` si no existe o es de otra organización.

#### PATCH `/api/v1/admin/roles/{id}`

Actualización parcial (`code`, `name`, `is_active`). **Response `200 OK`** — `{ "data": Role }`.

#### DELETE `/api/v1/admin/roles/{id}`

Borrado lógico del rol. **Response `204 No Content`**.

#### PUT `/api/v1/admin/roles/{id}/menus`

**Reemplaza** el conjunto de menús que concede el rol (sobrescribe `role_menus` del rol con
la lista enviada).

```json
{
  "menu_ids": ["a1...", "a2...", "b1..."]
}
```

| Campo      | Tipo         | Obligatorio | Notas                                                       |
| ---------- | ------------ | ----------- | ----------------------------------------------------------- |
| `menu_ids` | uuid[]       | Sí          | Conjunto completo de menús del rol. Una lista vacía deja al rol sin menús. |

**Response `200 OK`** — `{ "data": Role }` (puede incluir los menús resultantes).

---

### Menús (actividades)

Actividades de navegación, **globales** (sin `organization_id`), jerárquicas vía `parent_id`.

#### GET `/api/v1/admin/menus` 📄

Devuelve la lista **plana** (con `parent_id`) en `data`, y además el **árbol** anidado en
`meta.tree` — el árbol **no** vive dentro de `data`. Soporta paginación opcional sobre
`data` (ver «Paginación»); `meta.tree` **siempre** refleja el catálogo activo completo, con
o sin paginación (ver el caso especial en «Paginación»). Campos ordenables (`sort`): `order`
(por defecto), `name`, `created_at`.

**Response `200 OK`** — sin parámetros de paginación:

```json
{
  "data": [
    { "id": "a4...", "name": "Administración", "icon": "settings", "path": null, "parent_id": null, "order": 3, "is_active": true, "created_at": "2026-06-27T14:00:00Z", "created_by": null, "updated_by": null },
    { "id": "b1...", "name": "Usuarios", "icon": "users", "path": "/admin/users", "parent_id": "a4...", "order": 0, "is_active": true, "created_at": "2026-06-27T14:00:00Z", "created_by": null, "updated_by": null }
  ],
  "meta": {
    "total": 8,
    "tree": [
      {
        "id": "a4...", "name": "Administración", "icon": "settings", "path": null, "order": 3,
        "children": [
          { "id": "b1...", "name": "Usuarios", "icon": "users", "path": "/admin/users", "order": 0, "children": [] }
        ]
      }
    ]
  }
}
```

#### POST `/api/v1/admin/menus`

```json
{
  "name": "Reportes",
  "icon": "report",
  "path": "/admin/reports",
  "parent_id": null,
  "order": 4
}
```

| Campo       | Tipo           | Obligatorio | Notas                                             |
| ----------- | -------------- | ----------- | ------------------------------------------------- |
| `name`      | string         | Sí          | Nombre de la actividad.                           |
| `icon`      | string         | No          | Nombre del ícono.                                 |
| `path`      | string         | No          | Ruta del frontend; `null` para nodos contenedores. |
| `parent_id` | uuid \| null   | No          | Menú padre; `null` para un menú raíz.             |
| `order`     | int            | No          | Orden entre hermanos (por defecto `0`).           |

**Response `201 Created`** — `{ "data": Menu }`.

#### GET `/api/v1/admin/menus/{id}`

**Response `200 OK`** — `{ "data": Menu }`. `404` si no existe.

#### PATCH `/api/v1/admin/menus/{id}`

Actualización parcial (`name`, `icon`, `path`, `parent_id`, `order`, `is_active`).
**Response `200 OK`** — `{ "data": Menu }`.

#### DELETE `/api/v1/admin/menus/{id}`

Borrado lógico del menú. **Response `204 No Content`**.

---

### Usuarios

Gestión de usuarios del tenant. Las contraseñas se *hashean* con bcrypt y **nunca** se
devuelven; `full_name` es derivado.

#### GET `/api/v1/admin/users` 📄

Soporta paginación opcional (ver «Paginación»). Campos ordenables (`sort`):
`primer_apellido` (por defecto), `primer_nombre`, `email`, `created_at`.

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "8f1c2e7a-3b4d-4c5e-9a0b-1d2e3f4a5b6c",
      "email": "admin@solercia.com",
      "primer_nombre": "Admin",
      "segundo_nombre": null,
      "primer_apellido": "Solercia",
      "segundo_apellido": null,
      "full_name": "Admin Solercia",
      "dependency_id": "d1...",
      "is_active": true,
      "created_at": "2026-06-27T14:00:00Z",
      "roles": [
        { "id": "r1...", "code": "ADMIN", "name": "Administrador" }
      ]
    }
  ],
  "meta": { "total": 1 }
}
```

#### POST `/api/v1/admin/users`

```json
{
  "primer_nombre": "Ana",
  "segundo_nombre": "María",
  "primer_apellido": "Torres",
  "segundo_apellido": null,
  "email": "ana@solercia.com",
  "password": "Demo123*",
  "dependency_id": "d2...",
  "is_active": true,
  "role_ids": ["r3..."]
}
```

| Campo              | Tipo         | Obligatorio | Notas                                                    |
| ------------------ | ------------ | ----------- | -------------------------------------------------------- |
| `primer_nombre`    | string       | Sí          | Primer nombre.                                           |
| `segundo_nombre`   | string       | No          | Segundo nombre (puede omitirse o ir `null`).            |
| `primer_apellido`  | string       | Sí          | Primer apellido.                                        |
| `segundo_apellido` | string       | No          | Segundo apellido (puede omitirse o ir `null`).         |
| `email`            | string       | Sí          | Correo único.                                          |
| `password`         | string       | Sí          | **Solo escritura**: se *hashea* con bcrypt y nunca se devuelve. |
| `dependency_id`    | uuid \| null | No          | Dependencia/área de la persona.                        |
| `is_active`        | bool         | No          | Por defecto `true`.                                    |
| `role_ids`         | uuid[]       | No          | Roles de RBAC iniciales del usuario.                   |

**Response `201 Created`** — `{ "data": User }` (sin `password` ni `hashed_password`).

**Response `422 Unprocessable Entity`** — correo duplicado o campos faltantes.

#### GET `/api/v1/admin/users/{id}`

**Response `200 OK`** — `{ "data": User }`. `404` si no existe o es de otra organización.

#### PATCH `/api/v1/admin/users/{id}`

Actualización parcial: cualquier campo del nombre desglosado, `email`, `dependency_id`,
`is_active` y, opcionalmente, `password` (lo vuelve a *hashear*). **Response `200 OK`** —
`{ "data": User }`.

#### DELETE `/api/v1/admin/users/{id}`

Borrado lógico del usuario. **Response `204 No Content`**.

#### PUT `/api/v1/admin/users/{id}/roles`

**Reemplaza** el conjunto de roles del usuario (sobrescribe `user_roles` con la lista
enviada).

```json
{
  "role_ids": ["r1...", "r2..."]
}
```

| Campo      | Tipo    | Obligatorio | Notas                                                   |
| ---------- | ------- | ----------- | ------------------------------------------------------- |
| `role_ids` | uuid[]  | Sí          | Conjunto completo de roles. Una lista vacía deja al usuario sin roles. |

**Response `200 OK`** — `{ "data": User }` con `roles` actualizados.

---

## Resumen de endpoints

Regenerada desde la superficie real de los **22 routers** del backend. 📄 = soporta
paginación opcional (`page`/`size`/`sort`/`order`, ver «Paginación») — son los **20**
endpoints en el alcance de ese contrato.

| Método | Ruta                                       | Auth | 📄 | Descripción                                  |
| ------ | ------------------------------------------ | ---- | -- | -------------------------------------------- |
| POST   | `/api/v1/auth/login`                       | No   |    | Inicia sesión: token en el cuerpo + cookie de refresco. |
| POST   | `/api/v1/auth/refresh`                     | Cookie |  | Emite un nuevo token de acceso y rota el refresco. |
| POST   | `/api/v1/auth/logout`                      | Cookie |  | Cierra sesión: borra la cookie de refresco. |
| GET    | `/api/v1/auth/me`                          | Sí   |    | Devuelve el usuario autenticado (con roles).  |
| GET    | `/api/v1/auth/me/menus`                    | Sí   |    | Árbol de menús que el usuario puede ver.     |
| GET    | `/api/v1/projects`                         | Sí   | 📄 | Lista los proyectos del tenant.              |
| POST   | `/api/v1/projects`                         | Sí   |    | Crea un proyecto.                            |
| GET    | `/api/v1/projects/{id}`                    | Sí   |    | Devuelve un proyecto por id.                 |
| GET    | `/api/v1/projects/{id}/velocity`           | Sí   |    | Reporte de velocity del proyecto.            |
| GET    | `/api/v1/projects/{id}/members`            | Sí   |    | Lista los miembros asignables del proyecto.  |
| GET    | `/api/v1/projects/{id}/tasks`              | Sí   | 📄 | Lista las tareas (filtros + paginación opcionales). |
| POST   | `/api/v1/projects/{id}/tasks`              | Sí   |    | Crea una tarea.                              |
| GET    | `/api/v1/tasks/by-key/{key}`               | Sí   |    | Resuelve una tarea por su clave (`SDM-7`).   |
| GET    | `/api/v1/tasks/{id}`                       | Sí   |    | Devuelve una tarea por id.                   |
| PATCH  | `/api/v1/tasks/{id}`                       | Sí   |    | Actualiza parcialmente una tarea.            |
| DELETE | `/api/v1/tasks/{id}`                       | Sí   |    | Elimina una tarea.                           |
| GET    | `/api/v1/tasks/{id}/subtasks`              | Sí   |    | Lista las subtareas directas de una tarea.   |
| GET    | `/api/v1/projects/{id}/sprints`            | Sí   | 📄 | Lista los sprints del proyecto (scrum).      |
| POST   | `/api/v1/projects/{id}/sprints`            | Sí   |    | Crea un sprint (scrum).                      |
| PATCH  | `/api/v1/sprints/{id}`                     | Sí   |    | Actualiza un sprint (p. ej. cerrarlo).       |
| POST   | `/api/v1/sprints/{id}/close`               | Sí   |    | Cierra un sprint y mueve tareas incompletas. |
| GET    | `/api/v1/projects/{id}/sprints/{sid}/burndown` | Sí |  | Datos del burndown del sprint (ideal vs. real). |
| GET    | `/api/v1/tasks/{id}/comments`              | Sí   | 📄 | Lista los comentarios de una tarea.          |
| POST   | `/api/v1/tasks/{id}/comments`              | Sí   |    | Publica un comentario en una tarea.          |
| PATCH  | `/api/v1/comments/{id}`                    | Sí   |    | Edita un comentario propio.                  |
| DELETE | `/api/v1/comments/{id}`                    | Sí   |    | Elimina (lógico) un comentario propio.       |
| GET    | `/api/v1/tasks/{id}/attachments`           | Sí   | 📄 | Lista los adjuntos de una tarea.             |
| POST   | `/api/v1/tasks/{id}/attachments`           | Sí   |    | Sube un adjunto a una tarea.                 |
| GET    | `/api/v1/comments/{id}/attachments`        | Sí   |    | Lista los adjuntos de un comentario (no paginable). |
| POST   | `/api/v1/comments/{id}/attachments`        | Sí   |    | Sube un adjunto a un comentario.             |
| GET    | `/api/v1/attachments/{id}/download`        | Sí   |    | Descarga el archivo binario de un adjunto.   |
| GET    | `/api/v1/dashboard/executive`              | Sí   |    | Panel ejecutivo agregado del tenant (incl. `work_gap`, opcional `threshold_days`). |
| GET    | `/api/v1/dashboard/performance`            | Sí   |    | Rendimiento por colaborador (opcional `sprint_id`). |
| GET    | `/api/v1/projects/{id}/labels`             | Sí   | 📄 | Lista las etiquetas activas del proyecto.    |
| POST   | `/api/v1/projects/{id}/labels`             | Sí   |    | Crea una etiqueta.                           |
| PATCH  | `/api/v1/labels/{id}`                      | Sí   |    | Renombra/recolorea una etiqueta.             |
| DELETE | `/api/v1/labels/{id}`                      | Sí   |    | Elimina (lógico) una etiqueta y la desvincula de sus tareas. |
| POST   | `/api/v1/tasks/{id}/labels`                | Sí   |    | Asigna una etiqueta a una tarea.             |
| DELETE | `/api/v1/tasks/{id}/labels/{label_id}`     | Sí   |    | Desasigna una etiqueta de una tarea.         |
| GET    | `/api/v1/tasks/{id}/checklists`            | Sí   |    | Lista los checklists de una tarea, con progreso embebido (no paginable). |
| POST   | `/api/v1/tasks/{id}/checklists`            | Sí   |    | Crea un checklist en una tarea.              |
| PATCH  | `/api/v1/checklists/{id}`                  | Sí   |    | Renombra/reordena un checklist.              |
| DELETE | `/api/v1/checklists/{id}`                  | Sí   |    | Elimina (lógico) un checklist.               |
| GET    | `/api/v1/checklists/{id}/items`            | Sí   |    | Lista los ítems de un checklist (no paginable). |
| POST   | `/api/v1/checklists/{id}/items`            | Sí   |    | Crea un ítem en un checklist.                |
| PATCH  | `/api/v1/checklist-items/{id}`             | Sí   |    | Edita el texto y/o reordena un ítem.         |
| PATCH  | `/api/v1/checklist-items/{id}/toggle`      | Sí   |    | Invierte `is_done` de un ítem.               |
| DELETE | `/api/v1/checklist-items/{id}`             | Sí   |    | Elimina (lógico) un ítem.                    |
| GET    | `/api/v1/tasks/{id}/dependencies`          | Sí   | 📄 | Lista los enlaces de dependencia de una tarea (ambas direcciones). |
| POST   | `/api/v1/tasks/{id}/dependencies`          | Sí   |    | Enlaza la tarea con otra (rechaza ciclos, 422). |
| DELETE | `/api/v1/tasks/{id}/dependencies/{dep_id}` | Sí   |    | Desenlaza (borrado lógico, nunca físico).    |
| GET    | `/api/v1/notifications`                    | Sí   | 📄 | Lista las notificaciones del usuario.        |
| GET    | `/api/v1/notifications/unread-count`       | Sí   |    | Conteo de notificaciones activas.            |
| PATCH  | `/api/v1/notifications/{id}`               | Sí   |    | Cambia el estado de una notificación propia. |
| GET    | `/api/v1/notifications/{id}/deliveries`    | Sí   |    | Auditoría de entregas por canal (admin/manager). |
| GET    | `/api/v1/reminders`                        | Sí   | 📄 | Lista los recordatorios personales del usuario. |
| POST   | `/api/v1/reminders`                        | Sí   |    | Crea un recordatorio manual (futuro únicamente; 422 si `remind_at` ≤ ahora). |
| GET    | `/api/v1/reminders/{id}`                   | Sí   |    | Devuelve un recordatorio propio (404 si es ajeno). |
| PATCH  | `/api/v1/reminders/{id}`                   | Sí   |    | Edita `remind_at`/`message` de recordatorio en `scheduled` (422 en otro status). |
| DELETE | `/api/v1/reminders/{id}`                   | Sí   |    | Cancela un recordatorio (solo `scheduled`). |
| GET    | `/api/v1/reminder-rules`                   | Sí   | 📄 | Lista las reglas automáticas de recordatorio del usuario. |
| POST   | `/api/v1/reminder-rules`                   | Sí   |    | Crea una regla (e.g. `task_due_soon` con `lead_days`). |
| PATCH  | `/api/v1/reminder-rules/{id}`              | Sí   |    | Edita `lead_days`, `enabled`, `params` de una regla propia. |
| POST   | `/api/v1/reminders/dispatch`               | Admin |   | Ejecuta el disparo del motor de reminders bajo demanda (retorna conteo creado). |
| GET    | `/api/v1/alert-rules`                      | Sí   | 📄 | Lista las reglas de alerta del tenant.       |
| PATCH  | `/api/v1/alert-rules/{id}`                 | Admin |   | Ajusta `enabled`/`threshold_params` de una regla. |
| GET    | `/api/v1/tasks/{id}/time-logs`             | Sí   | 📄 | Lista las entradas de tiempo de una tarea.   |
| POST   | `/api/v1/tasks/{id}/time-logs`             | Sí   |    | Registra tiempo propio en una tarea.         |
| PATCH  | `/api/v1/time-logs/{id}`                   | Sí   |    | Edita una entrada propia (403 si no es el dueño). |
| DELETE | `/api/v1/time-logs/{id}`                   | Sí   |    | Elimina (lógico) una entrada propia (403 si no es el dueño). |
| GET    | `/api/v1/users/{id}/time-logs`             | Sí   | 📄 | Lista las entradas de un usuario (propio siempre; ajeno solo admin/manager). |
| GET    | `/api/v1/users/{id}/time-logs/summary`     | Sí   |    | Agregación diaria/semanal de horas de un usuario. |
| GET    | `/api/v1/tasks/{id}/history`               | Sí   | 📄 | Historial de cambios de una tarea (desc por defecto). |
| GET    | `/api/v1/users/{id}/activity`              | Sí   | 📄 | Cambios que un usuario provocó (filtro por día/rango). |
| GET    | `/api/v1/admin/dependencies`               | Admin | 📄 | Lista las dependencias del tenant.          |
| POST   | `/api/v1/admin/dependencies`               | Admin |   | Crea una dependencia.                       |
| GET    | `/api/v1/admin/dependencies/{id}`          | Admin |   | Devuelve una dependencia por id.            |
| PATCH  | `/api/v1/admin/dependencies/{id}`          | Admin |   | Actualiza una dependencia.                  |
| DELETE | `/api/v1/admin/dependencies/{id}`          | Admin |   | Elimina (lógico) una dependencia.           |
| GET    | `/api/v1/admin/roles`                      | Admin | 📄 | Lista los roles de RBAC del tenant.         |
| POST   | `/api/v1/admin/roles`                      | Admin |   | Crea un rol.                                |
| GET    | `/api/v1/admin/roles/{id}`                 | Admin |   | Devuelve un rol por id.                     |
| PATCH  | `/api/v1/admin/roles/{id}`                 | Admin |   | Actualiza un rol.                           |
| DELETE | `/api/v1/admin/roles/{id}`                 | Admin |   | Elimina (lógico) un rol.                    |
| PUT    | `/api/v1/admin/roles/{id}/menus`           | Admin |   | Reemplaza el conjunto de menús del rol.     |
| GET    | `/api/v1/admin/menus`                      | Admin | 📄 | Lista de menús: `data` plana + `meta.tree` (siempre completo). |
| POST   | `/api/v1/admin/menus`                      | Admin |   | Crea un menú (actividad).                   |
| GET    | `/api/v1/admin/menus/{id}`                 | Admin |   | Devuelve un menú por id.                    |
| PATCH  | `/api/v1/admin/menus/{id}`                 | Admin |   | Actualiza un menú.                          |
| DELETE | `/api/v1/admin/menus/{id}`                 | Admin |   | Elimina (lógico) un menú.                   |
| GET    | `/api/v1/admin/users`                      | Admin | 📄 | Lista los usuarios del tenant.              |
| POST   | `/api/v1/admin/users`                      | Admin |   | Crea un usuario (nombre desglosado + roles). |
| GET    | `/api/v1/admin/users/{id}`                 | Admin |   | Devuelve un usuario por id.                 |
| PATCH  | `/api/v1/admin/users/{id}`                 | Admin |   | Actualiza un usuario.                       |
| DELETE | `/api/v1/admin/users/{id}`                 | Admin |   | Elimina (lógico) un usuario.                |
| PUT    | `/api/v1/admin/users/{id}/roles`           | Admin |   | Reemplaza el conjunto de roles del usuario. |
| WS     | `/api/v1/ws/notifications`                 | Sí   |    | Canal WebSocket: push de notificaciones en tiempo real (best-effort). |
| GET    | `/api/v1/search`                           | Sí   | 📄 | Búsqueda global multi-entidad + filtros avanzados. |

> «Admin» en la columna *Auth* significa: bearer válido **y** rol de RBAC con `code = "ADMIN"`
> (`require_admin`). «Cookie» significa que el endpoint se autentica con la cookie de
> refresco, no con el header `Authorization`. El `PATCH` de `/alert-rules/{id}` es el único
> endpoint de esta lista con auth mixta: requiere membresía (`Sí`) **y** además `require_admin`.

---

## WebSocket: Notificaciones en tiempo real

Canal WebSocket que empuja notificaciones in-app en el instante de su creación, complementando (no reemplazando) el polling REST de `GET /api/v1/notifications`. **Best-effort**: REST sigue siendo la fuente de verdad. Si el usuario desconecta, la notificación se persiste igual y se recupera al reconectar vía REST.

### GET `/api/v1/ws/notifications` (WebSocket)

Handshake autenticado. El servidor acepta la conexión solo si el token es válido y resuelve a un usuario activo en la organización del token. Con token ausente o inválido, la conexión se rechaza sin handshake.

**Autenticación**

El token se pasa en el **subprotocolo bearer** durante el handshake (`Sec-WebSocket-Protocol: bearer, <access_token>`). El backend extrae el token, valida su firma e identidad, y resuelve `(organization_id, user_id)`. Fallback opcional documentado: query param `?token=<access_token>` (riesgo de fuga en logs de proxy — usar con cuidado).

**Handshake válido → `connection.ack`**

```json
{
  "v": 1,
  "type": "connection.ack",
  "data": {}
}
```

**Handshake inválido → cierre HTTP 403 sin ack**

- Token ausente, expirado o con firma inválida.
- Usuario no encontrado o inactivo.
- Organización resuelta no coincide (multi-tenancy).

**Push: `notification.created`**

Cuando se crea una notificación (por mención en un comentario o por el motor de alertas), el servidor intenta publicarla a todos los sockets abiertos del destinatario. El push llega como:

```json
{
  "v": 1,
  "type": "notification.created",
  "data": {
    "id": "uuid",
    "recipient_user_id": "uuid",
    "rule_type": "mention | alert_task_overdue | alert_blocked_task | reminder | ...",
    "title": "string",
    "body": "string",
    "target_type": "task | comment | ... | null",
    "target_id": "uuid | null",
    "dedup_key": "string",
    "status": "active",
    "created_at": "ISO-8601 timestamp"
  }
}
```

**Heartbeat: `ping` / `pong`**

El servidor envía `ping` periódicamente (intervalo configurable, por defecto 30 segundos). El cliente **debe** responder con `pong` dentro del intervalo de inactividad (por defecto 60 segundos). Si no hay respuesta, el servidor cierra la conexión.

`ping`:
```json
{
  "v": 1,
  "type": "ping",
  "data": {}
}
```

`pong` (desde el cliente):
```json
{
  "v": 1,
  "type": "pong",
  "data": {}
}
```

**Scoping: aislamiento tenant/usuario**

Cada conexión se asocia a `(organization_id, user_id)` resuelto del token. El servidor **nunca** entrega un mensaje de otra organización o de otro usuario al socket. El socket se cierra automáticamente si:
- El usuario se desconecta de la organización (soft delete).
- El token expira (reconexión con nuevo token requerida).
- El cliente no responde a `pong` a tiempo.

**Casos especiales**

| Caso | Comportamiento |
| ---- | --- |
| Usuario desconectado (sin socket WS abierto) | Notificación se persiste igual, recuperable vía REST. |
| Publicador no disponible / fallo de envío | Notificación se persiste igual — REST es la fuente de verdad. |
| Múltiples sockets del mismo usuario | Todos reciben el push (broadcast a todos los sockets del `recipient_user_id`). |
| Deshabilitación: `WS_ENABLED=false` | Endpoint retorna `503` Service Unavailable; REST sigue funcional. |

**Ejemplo de cliente (JavaScript)**

```javascript
const token = "<access_token>";
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/notifications`, `bearer, ${token}`);

ws.onopen = () => {
  console.log("Conectado");
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "connection.ack") {
    console.log("Handshake aceptado");
  } else if (msg.type === "notification.created") {
    console.log("Notificación:", msg.data);
  } else if (msg.type === "ping") {
    // Responder automáticamente si la librería no lo hace
    ws.send(JSON.stringify({ v: 1, type: "pong", data: {} }));
  }
};

ws.onerror = (error) => {
  console.error("Error WS:", error);
};

ws.onclose = () => {
  console.log("Conexión cerrada. Reconectar via REST polling.");
};
```

**Configuración**

| Variable | Default | Descripción |
| ---- | --- | --- |
| `WS_ENABLED` | `true` | Habilita/deshabilita el endpoint WS. Si `false`, retorna `503` (endpoint no disponible). |
| `WS_HEARTBEAT_SECONDS` | `30` | Intervalo en segundos para enviar `ping` al cliente. |
| `WS_IDLE_TIMEOUT_SECONDS` | `60` | Tiempo máximo en segundos sin recibir `pong` antes de cerrar la conexión. |

---

## Auditoría de entregas de notificaciones

### GET `/api/v1/notifications/{id}/deliveries`

Devuelve el historial de entregas (intentos, canales, estado) de una notificación específica. Acceso restringido a usuarios con rol `admin` o `manager` de la organización. Útil para auditar por qué una notificación se envió o falló.

**Permisos**

- ✅ Permitido: `admin`, `manager`
- ❌ Rechazado: `member`, `viewer` (incluido el dueño de la notificación)

**Request**

```http
GET /api/v1/notifications/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/deliveries HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`** — Entregas encontradas

```json
{
  "data": {
    "deliveries": [
      {
        "id": "del-uuid-1",
        "notification_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
        "channel": "email",
        "status": "sent",
        "attempts": 1,
        "last_error": null,
        "sent_at": "2026-07-12T10:30:15Z",
        "created_at": "2026-07-12T10:30:00Z"
      }
    ],
    "digested": false
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `deliveries[]` | array | Entregas registradas para esa notificación. |
| `deliveries[].id` | uuid | Identificador de la fila de entrega. |
| `deliveries[].notification_id` | uuid | FK de la notificación; `null` si es una entrega agregada de digest. |
| `deliveries[].channel` | string | Canal: `email`, `websocket` (best-effort no aparece), u otro adaptador registrado. |
| `deliveries[].status` | string | `pending` (reintento pendiente) \| `sent` (entregado con éxito) \| `failed` (agotados reintentos). |
| `deliveries[].attempts` | int | Número de intentos de envío realizados. |
| `deliveries[].last_error` | string \| null | Mensaje de error del último intento fallido (nunca expone payload ni credenciales). |
| `deliveries[].sent_at` | timestamp \| null | Instante en que se completó el envío exitoso. |
| `digested` | bool | `true` si la notificación fue parte de un digest sin fila individual (hoy no genera fila). |

**Response `403 Forbidden`** — Rol insuficiente

```json
{
  "detail": "No tienes permisos para acceder a esta información.",
  "code": "notification_deliveries_forbidden",
  "status": 403
}
```

**Response `404 Not Found`** — Notificación no existe o pertenece a otra organización

```json
{
  "detail": "La notificación no existe o no tienes acceso.",
  "code": "notification_not_found",
  "status": 404
}
```

---

### Arquitectura de entregas

El hub de notificaciones (`notification-hub`) entrega cada notificación a través de canales registrados. Cada canal declara su **política**:

- **`durable`**: persiste fila en `notification_deliveries`, reintenta según configuración (máximo de intentos), genera log `ERROR` al agotar reintentos. Ejemplos: `email`.
- **`best_effort`**: sin persistencia en `notification_deliveries` (fire-and-forget post-commit). Si no hay destinatario conectado, se pierde silenciosamente. La notificación permanece accesible vía REST. Ejemplos: `websocket`.

El despachador genérico (`dispatch_deliveries`) corre como job periódico: reclama filas `pending` de forma atómica, intenta envío por canal, registra `sent` o `failed` terminal + retry counter. Una notificación urgente (ej. `license_expired`) encola inmediata en `notification_deliveries` en la misma transacción de negocio; no urgentes quedan pendientes de digest con `emailed_at IS NULL`.

---

## Activos de información (assets)

Endpoints **protegidos**. Los activos de información son recursos de la organización (hardware, software, licencias, etc.) con vencimientos de licencia y vínculos a tareas. Lectura permitida a cualquier miembro; escritura (`POST`, `PATCH`, `DELETE`) exige `require_admin`. Todos los activos, licencias y vínculos respetan el aislamiento multi-tenant del usuario autenticado.

### GET `/api/v1/assets` 📄

Lista los activos activos de la organización. Soporta paginación opcional (ver «Paginación»). Campos ordenables (`sort`): `name`, `created_at` (por defecto). Filtros combinables: `asset_type`, `status`, `criticality`, `responsible_id`, `category`, `q` (búsqueda por nombre).

**Request**

```http
GET /api/v1/assets?asset_type=hardware&status=active&page=1&size=20 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      "name": "Servidor principal",
      "description": "Servidor de producción en datacenter.",
      "asset_type": "hardware",
      "category": "servidor",
      "status": "active",
      "criticality": "critical",
      "responsible_id": "u1234567-abcd-ef01-2345-6789abcdef01",
      "acquisition_date": "2024-01-15",
      "location": "Datacenter 1",
      "vendor": "Dell",
      "organization_id": "org-uuid",
      "created_at": "2026-06-27T10:30:00Z",
      "created_by": "admin-uuid",
      "updated_by": "admin-uuid"
    }
  ],
  "meta": {
    "page": 1,
    "size": 20,
    "total": 5
  }
}
```

**Parámetros de filtro**

| Parámetro | Tipo | Notas |
|-----------|------|-------|
| `asset_type` | string | `hardware` \| `software` \| `saas_subscription` \| `information` \| `service` \| `certificate` |
| `status` | string | `active` \| `inactive` \| `retired` \| `under_review` |
| `criticality` | string | `critical` \| `high` \| `medium` \| `low` |
| `responsible_id` | uuid | Filtra activos cuyo responsable es este usuario. |
| `category` | string | Búsqueda exacta del subtipo (p. ej. `"servidor"` dentro de `asset_type=hardware`). |
| `q` | string | Búsqueda por subcadena en el nombre (`ILIKE`), case-insensitive. |

### POST `/api/v1/assets`

Crea un activo. Requiere `require_admin`. `name` y `asset_type` son obligatorios.

**Request**

```json
{
  "name": "Servidor principal",
  "description": "Servidor de producción.",
  "asset_type": "hardware",
  "category": "servidor",
  "status": "active",
  "criticality": "critical",
  "responsible_id": "u1234567-abcd-ef01-2345-6789abcdef01",
  "acquisition_date": "2024-01-15",
  "location": "Datacenter 1",
  "vendor": "Dell"
}
```

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `name` | string | Sí | Nombre del activo. |
| `asset_type` | enum | Sí | Tipo de activo (ver filtro arriba). |
| `category` | string | No | Subtipo libre (hasta 80 caracteres). |
| `status` | enum | No | Por defecto `"active"`. |
| `criticality` | enum | No | Por defecto `"medium"`. |
| `responsible_id` | uuid | No | Usuario responsable del activo (puede ser `null`). |
| `description`, `acquisition_date`, `location`, `vendor` | varios | No | Campos opcionales. |

**Response `201 Created`** — `{ "data": Asset }`.

**Response `403 Forbidden`** — usuario no es admin.

**Response `422 Unprocessable Entity`** — falta campo obligatorio o `asset_type` no válido.

### GET `/api/v1/assets/{id}`

Obtiene un activo específico.

**Response `200 OK`** — `{ "data": Asset }`.

**Response `404 Not Found`** — activo no existe o pertenece a otra organización.

### PATCH `/api/v1/assets/{id}`

Edita un activo (campos opcionales). Requiere `require_admin`.

**Request**

```json
{
  "status": "inactive",
  "criticality": "high"
}
```

**Response `200 OK`** — `{ "data": Asset }`.

**Response `403 Forbidden`** — usuario no es admin.

**Response `404 Not Found`** — activo no existe o pertenece a otra organización.

### DELETE `/api/v1/assets/{id}`

Borrado lógico (`soft delete`). Requiere `require_admin`. Sus licencias también quedan marcadas como borradas, y sus vínculos con tareas se eliminan.

**Response `204 No Content`**.

**Response `403 Forbidden`** — usuario no es admin.

**Response `404 Not Found`** — activo no existe o pertenece a otra organización.

---

### Licencias de activos (anidadas)

#### GET `/api/v1/assets/{asset_id}/licenses` 📄

Lista las licencias activas de un activo. Soporta paginación opcional. Campos ordenables: `expiration_date`, `created_at` (por defecto).

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "lic-uuid",
      "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
      "license_key": "XXXXX-XXXXX-XXXXX",
      "license_type": "subscription",
      "start_date": "2026-01-01",
      "expiration_date": "2027-01-01",
      "seats": 10,
      "cost": 1500.00,
      "auto_renew": true,
      "organization_id": "org-uuid",
      "created_at": "2026-06-27T10:30:00Z",
      "created_by": "admin-uuid"
    }
  ],
  "meta": { "page": 1, "size": 20, "total": 2 }
}
```

#### POST `/api/v1/assets/{asset_id}/licenses`

Crea una licencia para el activo. Requiere `require_admin`. `expiration_date` debe ser posterior a `start_date`.

**Request**

```json
{
  "license_key": "XXXXX-XXXXX-XXXXX",
  "license_type": "subscription",
  "start_date": "2026-01-01",
  "expiration_date": "2027-01-01",
  "seats": 10,
  "cost": 1500.00,
  "auto_renew": true
}
```

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `start_date` | date | Sí | Formato `YYYY-MM-DD`. |
| `expiration_date` | date | Sí | Debe ser `> start_date`. |
| `license_type` | enum | Sí | `perpetual` \| `subscription` \| `trial`. |
| `license_key`, `seats`, `cost`, `auto_renew` | varios | No | `auto_renew` por defecto `false`. |

**Response `201 Created`** — `{ "data": AssetLicense }`.

**Response `422 Unprocessable Entity`** — `expiration_date <= start_date` o fecha inválida.

#### PATCH `/api/v1/asset-licenses/{license_id}`

Edita una licencia (campos opcionales). Requiere `require_admin`.

**Response `200 OK`** — `{ "data": AssetLicense }`.

**Response `404 Not Found`** — licencia no existe o activo está borrado.

#### DELETE `/api/v1/asset-licenses/{license_id}`

Borrado lógico. Requiere `require_admin`.

**Response `204 No Content`**.

**Response `404 Not Found`** — licencia no existe o activo está borrado.

---

### Vínculos activo↔tarea

#### GET `/api/v1/assets/{asset_id}/tasks` 📄

Lista las tareas vinculadas a un activo. Soporta paginación opcional. Campos ordenables: `created_at` (por defecto).

**Response `200 OK`**

```json
{
  "data": [
    {
      "id": "task-uuid",
      "title": "Renovar licencia de software",
      "project_id": "proj-uuid",
      "status": "To Do",
      "due_date": "2027-01-01"
    }
  ],
  "meta": { "total": 1 }
}
```

#### POST `/api/v1/assets/{asset_id}/tasks`

Vincula una tarea EXISTENTE de la misma organización al activo. No crea tareas.

**Request**

```json
{ "task_id": "task-uuid" }
```

**Response `201 Created`** — `{ "data": { "asset_id": "...", "task_id": "..." } }`.

**Response `404 Not Found`** — tarea no existe, pertenece a otra organización, o el activo está borrado.

#### DELETE `/api/v1/assets/{asset_id}/tasks/{task_id}`

Desvincula una tarea del activo.

**Response `204 No Content`**.

**Response `404 Not Found`** — vínculo no existe o activo está borrado.

---

## Alertas de licencia

Las estrategias `license_expiring` y `license_expired` son evaluadas automáticamente por el scheduler de alertas (cada hora por defecto). Ambas generan notificaciones in-app.

### `license_expiring` — Alerta escalonada de próximo vencimiento

Condición: una licencia activa (`is_active = true`, `auto_renew = false`) con un número de días restantes hasta `expiration_date` que entra en una de las bandas configuradas (por defecto `30`, `7`, `1` días). Una sola notificación por banda (`dedup_key = license_expiring:{license_id}:{band}`).

**Semilla predeterminada**

```
rule_type: "license_expiring"
enabled: true
threshold_params: { "lead_days": [30, 7, 1] }
```

**Destinatario**: `responsible_id` del activo (`null` = sin notificación).

**Escenarios**

- Licencia a 30, 7 o 1 día de vencer: notificación con la banda correspondiente.
- Re-corrida sin cruzar el siguiente umbral: sin duplicado.
- Licencia con `auto_renew = true`: nunca notifica.
- Licencia o activo borrados (`is_active = false`): nunca notifican.

### `license_expired` — Alerta de licencia vencida

Condición: una licencia activa (`is_active = true`) cuya `expiration_date` ya pasó. Una sola notificación por `(license_id, recipient)` (`dedup_key = license_expired:{license_id}:{recipient_id}`).

**Semilla predeterminada**

```
rule_type: "license_expired"
enabled: true
threshold_params: {}
```

**Destinatarios**:
- `responsible_id` del activo (si no es `null`).
- Cada usuario con rol `admin` en la organización (independiente del responsable; si hay varios admins, cada uno recibe su notificación).

Ausencia de admins no suprime la notificación al responsable.

---

## Modelos de datos del contrato

> **Auditoría (`created_by`/`updated_by`)**: `User`, `Dependency`, `Role`, `Menu`,
> `Project`, `Task`, `Sprint`, `Comment`, `Attachment`, `AlertRule` y `TimeLog` exponen
> `created_by` y `updated_by` (`uuid | null`) — quién creó/modificó por última vez el
> registro, resuelto del usuario autenticado (nunca aceptado como input del cliente). Son
> `null` en filas creadas antes de esta migración o sembradas por el arranque del sistema
> (`db_init.py`), de forma **permanente** — no hay *backfill* histórico. `TaskHistory` NO
> tiene `created_by`/`updated_by` — usa sus propios `actor_id`/`actor_type` (`user | system`)
> en su lugar, es una fila de auditoría en sí misma y nunca se modifica tras crearse.

### `TokenResponse`

```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

> El login devuelve además `user` (un `User`) en el cuerpo y la cookie `httpOnly`
> `refresh_token`. `refresh` devuelve solo `{access_token, token_type}` y rota la cookie.

### `User`

```json
{
  "id": "uuid",
  "email": "string",
  "primer_nombre": "string",
  "segundo_nombre": "string | null",
  "primer_apellido": "string",
  "segundo_apellido": "string | null",
  "full_name": "string",
  "dependency_id": "uuid | null",
  "organization_id": "uuid",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "roles": [
    { "id": "uuid", "code": "string", "name": "string" }
  ],
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> `full_name` es **derivado** (`primer_nombre + ' ' + primer_apellido`, omitiendo espacios
> sobrantes), no una columna almacenada. `password`/`hashed_password` **nunca** se devuelven
> (la contraseña es de **solo escritura**). `roles` lista los roles de RBAC del usuario. Las
> respuestas de `/auth/me` y `/auth/login` pueden omitir el detalle de nombre desglosado y
> exponer solo `full_name`; los endpoints `/admin/users` sí devuelven el desglose completo.

### `Dependency`

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "name": "string",
  "code": "string | null",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Role`

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "code": "string",
  "name": "string",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "menu_ids": ["uuid"],
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Menu`

```json
{
  "id": "uuid",
  "name": "string",
  "icon": "string | null",
  "path": "string | null",
  "parent_id": "uuid | null",
  "order": "int",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> `Menu` es un catálogo **global** (sin `organization_id`), pero SÍ lleva auditoría
> (`created_by`/`updated_by`) — el criterio de qué se audita es "tiene borrado lógico"
> (`SoftDeleteMixin`), no "está aislado por tenant". En las respuestas en **árbol**
> (`/auth/me/menus`, `meta.tree` de `GET /admin/menus`) cada nodo usa una forma reducida con
> `children[]` (sin `is_active`/auditoría); en la lista **plana** (`data` de
> `GET /admin/menus`) se usa el `Menu` completo de arriba, con `parent_id` y sin `children`.

### `Project`

```json
{
  "id": "uuid",
  "name": "string",
  "description": "string | null",
  "methodology": "planner | kanban | scrum | custom",
  "status": "string",
  "organization_id": "uuid",
  "code": "string | null",
  "created_at": "ISO-8601 timestamp",
  "methodology_info": {
    "methodology": "string",
    "default_columns": ["string"],
    "allowed_statuses": ["string"],
    "sprints_enabled": "boolean",
    "estimation_mode": "none | points | hours | both",
    "has_backlog": "boolean"
  },
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Task`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "sprint_id": "uuid | null",
  "title": "string",
  "description": "string | null",
  "task_type": "task | bug | story | epic",
  "status": "string",
  "priority": "critical | high | medium | low",
  "assignee_id": "uuid | null",
  "assignee_name": "string | null",
  "estimation_points": "int | null",
  "estimation_hours": "number | null",
  "due_date": "date (YYYY-MM-DD) | null",
  "start_date": "date (YYYY-MM-DD) | null",
  "order": "int",
  "risk_flag": "boolean",
  "risk_reason": "string | null",
  "created_at": "ISO-8601 timestamp",
  "completed_at": "ISO-8601 timestamp | null",
  "task_number": "int | null",
  "task_key": "string | null",
  "subtask_progress": "number | null",
  "created_by": "uuid | null",
  "updated_by": "uuid | null",
  "is_blocked": "boolean",
  "blockers": [ { "task_id": "uuid", "title": "string" } ],
  "labels": [ { "id": "uuid", "project_id": "uuid", "name": "string", "color": "string", "created_at": "ISO-8601 timestamp" } ],
  "checklist_progress": "number | null"
}
```

> `task_key` es la clave legible (`SDM-7` = `{código del proyecto}-{task_number}`),
> asignada de forma atómica y secuencial por proyecto. `subtask_progress` (`0.0..1.0`) solo
> se calcula en el detalle de una tarea individual (`GET /tasks/{id}`); es `null` en listas
> y en tareas sin subtareas.

> `status` es texto libre validado contra los `allowed_statuses` de la metodología del
> proyecto (el rótulo de una columna del tablero), no un enum global.

> `completed_at` lo gestiona el backend: se fija en `now()` cuando la tarea entra a la
> columna «done» (`allowed_statuses[-1]`) y vuelve a `null` cuando sale de ella. Es de
> **solo lectura** en el contrato (no se acepta en `POST` ni en `PATCH`); alimenta el
> burndown del sprint y la vista de rendimiento.

> `is_blocked`/`blockers[]`, `labels[]` y `checklist_progress` (`0.0..1.0` \| `null`) siguen
> el mismo criterio que `subtask_progress`: **solo** se calculan en el detalle de una tarea
> individual (`GET /tasks/{id}` o `GET /tasks/by-key/{key}`) para evitar N+1 sobre el
> listado; en `GET /projects/{id}/tasks` estos cuatro campos no se recalculan (quedan en su
> valor por defecto: `false`, `[]`, `[]`, `null`). `blockers[]` solo incluye bloqueadores
> **activos e incompletos** (`completed_at IS NULL`); se vacía automáticamente cuando el
> bloqueador se completa. `checklist_progress` es `null` cuando la tarea no tiene ítems de
> checklist (ni checklists, ni checklists vacíos).

### `Sprint`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "name": "string",
  "goal": "string | null",
  "start_date": "date (YYYY-MM-DD) | null",
  "end_date": "date (YYYY-MM-DD) | null",
  "status": "active | closed",
  "completed_points": "int",
  "closed_at": "ISO-8601 timestamp | null",
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Comment`

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "author_id": "uuid",
  "body": "string",
  "mentioned_user_ids": ["uuid-as-string"],
  "organization_id": "uuid",
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> `author_id` (quién escribió el comentario, campo de negocio) y `created_by` (auditoría
> genérica) suelen coincidir pero son conceptualmente distintos — `author_id` gobierna el
> permiso de editar/borrar (`403` si no coincide con el caller); `created_by`/`updated_by`
> son el rastro de auditoría transversal a los 11 modelos.

### `Attachment`

```json
{
  "id": "uuid",
  "target_type": "task | comment",
  "target_id": "uuid",
  "original_name": "string",
  "content_type": "string",
  "size_bytes": "int",
  "uploaded_by": "uuid",
  "organization_id": "uuid",
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Notification`

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "recipient_user_id": "uuid",
  "rule_type": "string",
  "title": "string",
  "body": "string",
  "target_type": "string | null",
  "target_id": "uuid | null",
  "dedup_key": "string",
  "status": "active | read | resolved | silenced",
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp"
}
```

> `Notification` **no** lleva auditoría (`created_by`/`updated_by`): no tiene
> `SoftDeleteMixin` (se generan siempre por el sistema, nunca por un `POST` de cliente), así
> que queda fuera del criterio de los 11 modelos auditados.

### `AlertRule`

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "rule_type": "string",
  "enabled": "boolean",
  "threshold_params": { "...": "objeto libre, depende de rule_type" },
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "updated_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

### `Label`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "name": "string",
  "color": "string",
  "created_at": "ISO-8601 timestamp"
}
```

> Scope de **proyecto**: `name` es único entre las etiquetas **activas** de un mismo
> proyecto (el mismo nombre puede repetirse en proyectos distintos). El vínculo M:N con
> `Task` (`TaskLabel`) no expone un modelo propio en el contrato — se lee siempre como
> `labels[]` embebido en `Task`, o como la lista `{ data: [Label], meta: { total } }` que
> devuelve `POST /tasks/{id}/labels` tras asignar.

### `TaskChecklist`

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "title": "string",
  "order": "int",
  "created_at": "ISO-8601 timestamp",
  "done": "int",
  "total": "int"
}
```

> `done`/`total` los calcula el backend a partir de los `ChecklistItem` activos del
> checklist (nunca se envían desde el cliente). Un checklist recién creado empieza en
> `done: 0, total: 0`.

### `ChecklistItem`

```json
{
  "id": "uuid",
  "checklist_id": "uuid",
  "text": "string",
  "is_done": "boolean",
  "order": "int",
  "created_at": "ISO-8601 timestamp"
}
```

### `TaskDependencyRead`

```json
{
  "id": "uuid",
  "related_task_id": "uuid",
  "direction": "blocks | is_blocked_by",
  "created_at": "ISO-8601 timestamp"
}
```

> Forma devuelta tanto por `GET /tasks/{id}/dependencies` (cada fila) como por
> `POST /tasks/{id}/dependencies` (el enlace recién creado). `direction` se calcula **desde
> la perspectiva de la tarea del path**: `"blocks"` = esta tarea bloquea a
> `related_task_id`; `"is_blocked_by"` = `related_task_id` bloquea a esta tarea. Internamente
> se persiste una única fila dirigida por relación (`blocker_task_id`/`blocked_task_id`,
> clase `TaskDependency`, tabla `task_dependencies`, módulo `task_links` — deliberadamente
> distinto del módulo/tabla/clase `Dependency` de «Administración», que son áreas
> organizacionales sin relación alguna con este concepto).

### `TimeLog`

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "user_id": "uuid",
  "date": "2026-02-10",
  "hours": 2.5,
  "note": "string | null",
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> Clase `TaskTimeLog`, tabla `task_time_logs`, módulo `time_logs`. `date` es el alias
> público de la columna `work_date`; `hours` es `Decimal(5,2) > 0` (máximo `24`). Sin
> `unique`: un usuario puede registrar varios tramos el mismo día (misma o distinta tarea) —
> la agregación de `summary` los suma.

### `TaskHistory`

```json
{
  "id": "uuid",
  "task_id": "uuid",
  "actor_id": "uuid | null",
  "actor_type": "user | system",
  "field": "status",
  "old_value": "string | null",
  "new_value": "string | null",
  "changed_at": "ISO-8601 timestamp"
}
```

> Clase `TaskHistory`, tabla `task_history`, módulo `activity`. Fila *append-only*: no hay
> `PATCH`/`DELETE`. `changed_at` es el alias público de la columna `created_at`. Campos
> rastreados: `status`, `assignee_id`, `estimation_points`, `estimation_hours`, `sprint_id`,
> `priority` (no incluye `due_date`). `actor_id` es `null` cuando `actor_type == "system"`
> (p. ej. `POST /sprints/{id}/close` moviendo tareas incompletas al backlog).

### `Asset`

```json
{
  "id": "uuid",
  "name": "string",
  "description": "string | null",
  "asset_type": "hardware | software | saas_subscription | information | service | certificate",
  "category": "string | null",
  "status": "active | inactive | retired | under_review",
  "criticality": "critical | high | medium | low",
  "responsible_id": "uuid | null",
  "acquisition_date": "date (YYYY-MM-DD) | null",
  "location": "string | null",
  "vendor": "string | null",
  "organization_id": "uuid",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> `asset_type` está anclado a estándares ITAM (ISO/IEC 27005, ISO/IEC 19770-1/-3, ITIL 4).
> `category` es un subtipo libre (hasta 80 caracteres, sin validación) para granularidad sin
> migración — ejemplos: en `hardware` puede ser `"servidor"`, `"endpoint"`; en `software`,
> `"SO"`, `"app_negocio"`. `responsible_id` es el usuario responsable del activo (puede ser `null`).

### `AssetLicense`

```json
{
  "id": "uuid",
  "asset_id": "uuid",
  "license_key": "string | null",
  "license_type": "perpetual | subscription | trial",
  "start_date": "date (YYYY-MM-DD)",
  "expiration_date": "date (YYYY-MM-DD)",
  "seats": "int | null",
  "cost": "decimal (12,2) | null",
  "auto_renew": "boolean",
  "organization_id": "uuid",
  "is_active": true,
  "created_at": "ISO-8601 timestamp",
  "created_by": "uuid | null",
  "updated_by": "uuid | null"
}
```

> Composición 1:N bajo `Asset`: `asset_id` con FK `CASCADE`. Si el activo padre se borra
> lógicamente (`is_active = false`), sus licencias también — nunca quedan huérfanas.
> `auto_renew = true` excluye la licencia del alerta `license_expiring` (pero sigue
> alertando en `license_expired` si llega a pasar la fecha).

### `AssetTask`

```json
{
  "asset_id": "uuid",
  "task_id": "uuid",
  "organization_id": "uuid",
  "created_at": "ISO-8601 timestamp"
}
```

> Tabla de unión M:N (patrón `TaskLabel`). PK es `(asset_id, task_id)` — no hay `id` propio.
> Sin `SoftDeleteMixin` — es **hard delete** al desvincular (permite re-vinculación sin
> activación de filas blandas). Lleva `TenantMixin` (divergencia deliberada de `TaskLabel`)
> para scoping directo por `organization_id` sin join contra `Asset`/`Task`. FK ambas con
> `CASCADE`.
