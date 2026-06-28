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

- Las colecciones devuelven `{ "data": [...], "meta": { "total": <int> } }`.
- Los recursos individuales devuelven `{ "data": { ... } }`.
- Los errores devuelven `{ "detail": "<mensaje en español>" }` (formato estándar de
  FastAPI), o un arreglo de errores de validación para el `422`.

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

### GET `/api/v1/projects`

Lista los proyectos de la organización del usuario.

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

## Tareas

Endpoints **protegidos** y filtrados por el tenant del token. El `status` de una tarea es
**siempre** uno de los `allowed_statuses` de la metodología del proyecto (el rótulo de una
columna del tablero); el backend lo valida en la capa de service. El estado por defecto al
crear es la **primera** columna de `allowed_statuses`. Ver
`docs/adr/0005-work-items-status-as-column.md`.

### GET `/api/v1/projects/{project_id}/tasks`

Lista las tareas de un proyecto, con filtros opcionales por *query string*.

| Parámetro     | Tipo | Notas                                                           |
| ------------- | ---- | --------------------------------------------------------------- |
| `sprint_id`   | uuid | Filtra por sprint. Usa `sprint_id=null` para ver el backlog.    |
| `status`      | text | Filtra por columna (un valor de `allowed_statuses`).            |
| `assignee_id` | uuid | Filtra por persona asignada.                                    |

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

### GET `/api/v1/projects/{project_id}/sprints`

**Response `200 OK`**

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
      "created_at": "2026-06-26T14:50:00Z"
    }
  ]
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

## Vista ejecutiva (dashboard)

### GET `/api/v1/dashboard/executive`

Endpoint **protegido** y agregado sobre las tareas del tenant del token. Responde «¿quién
hace qué y qué está en riesgo?». Las definiciones de *done*, *active*, *at risk* y *overdue*
se derivan de los `allowed_statuses` de cada proyecto (ver `docs/ARCHITECTURE.md`, sección
«Vista ejecutiva»).

**Request**

```http
GET /api/v1/dashboard/executive HTTP/1.1
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
    "totals": { "projects": 3, "tasks": 27, "overdue": 4, "at_risk": 6 }
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

#### GET `/api/v1/admin/dependencies`

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

#### GET `/api/v1/admin/roles`

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

#### GET `/api/v1/admin/menus`

Devuelve la lista **plana** (con `parent_id`) y además el **árbol** anidado.

**Response `200 OK`**

```json
{
  "data": {
    "flat": [
      { "id": "a4...", "name": "Administración", "icon": "settings", "path": null, "parent_id": null, "order": 3, "is_active": true },
      { "id": "b1...", "name": "Usuarios", "icon": "users", "path": "/admin/users", "parent_id": "a4...", "order": 0, "is_active": true }
    ],
    "tree": [
      {
        "id": "a4...", "name": "Administración", "icon": "settings", "path": null, "order": 3,
        "children": [
          { "id": "b1...", "name": "Usuarios", "icon": "users", "path": "/admin/users", "order": 0, "children": [] }
        ]
      }
    ]
  },
  "meta": { "total": 8 }
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

#### GET `/api/v1/admin/users`

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

| Método | Ruta                                       | Auth | Descripción                                  |
| ------ | ------------------------------------------ | ---- | -------------------------------------------- |
| POST   | `/api/v1/auth/login`                       | No   | Inicia sesión: token en el cuerpo + cookie de refresco. |
| POST   | `/api/v1/auth/refresh`                      | Cookie | Emite un nuevo token de acceso y rota el refresco. |
| POST   | `/api/v1/auth/logout`                       | Cookie | Cierra sesión: borra la cookie de refresco. |
| GET    | `/api/v1/auth/me`                          | Sí   | Devuelve el usuario autenticado (con roles).  |
| GET    | `/api/v1/auth/me/menus`                     | Sí   | Árbol de menús que el usuario puede ver.     |
| GET    | `/api/v1/projects`                         | Sí   | Lista los proyectos del tenant.              |
| POST   | `/api/v1/projects`                         | Sí   | Crea un proyecto.                            |
| GET    | `/api/v1/projects/{id}`                    | Sí   | Devuelve un proyecto por id.                 |
| GET    | `/api/v1/projects/{id}/members`            | Sí   | Lista los miembros asignables del proyecto.  |
| GET    | `/api/v1/projects/{id}/tasks`              | Sí   | Lista las tareas (filtros opcionales).       |
| POST   | `/api/v1/projects/{id}/tasks`              | Sí   | Crea una tarea.                              |
| GET    | `/api/v1/tasks/{id}`                       | Sí   | Devuelve una tarea por id.                   |
| PATCH  | `/api/v1/tasks/{id}`                       | Sí   | Actualiza parcialmente una tarea.            |
| DELETE | `/api/v1/tasks/{id}`                       | Sí   | Elimina una tarea.                           |
| GET    | `/api/v1/projects/{id}/sprints`            | Sí   | Lista los sprints del proyecto (scrum).      |
| POST   | `/api/v1/projects/{id}/sprints`            | Sí   | Crea un sprint (scrum).                      |
| PATCH  | `/api/v1/sprints/{id}`                     | Sí   | Actualiza un sprint (p. ej. cerrarlo).       |
| GET    | `/api/v1/projects/{id}/sprints/{sid}/burndown` | Sí | Datos del burndown del sprint (ideal vs. real). |
| GET    | `/api/v1/dashboard/executive`              | Sí   | Panel ejecutivo agregado del tenant.         |
| GET    | `/api/v1/dashboard/performance`            | Sí   | Rendimiento por colaborador (opcional `sprint_id`). |
| GET    | `/api/v1/admin/dependencies`               | Admin | Lista las dependencias del tenant.          |
| POST   | `/api/v1/admin/dependencies`               | Admin | Crea una dependencia.                       |
| GET    | `/api/v1/admin/dependencies/{id}`          | Admin | Devuelve una dependencia por id.            |
| PATCH  | `/api/v1/admin/dependencies/{id}`          | Admin | Actualiza una dependencia.                  |
| DELETE | `/api/v1/admin/dependencies/{id}`          | Admin | Elimina (lógico) una dependencia.           |
| GET    | `/api/v1/admin/roles`                      | Admin | Lista los roles de RBAC del tenant.         |
| POST   | `/api/v1/admin/roles`                      | Admin | Crea un rol.                                |
| GET    | `/api/v1/admin/roles/{id}`                 | Admin | Devuelve un rol por id.                     |
| PATCH  | `/api/v1/admin/roles/{id}`                 | Admin | Actualiza un rol.                           |
| DELETE | `/api/v1/admin/roles/{id}`                 | Admin | Elimina (lógico) un rol.                    |
| PUT    | `/api/v1/admin/roles/{id}/menus`           | Admin | Reemplaza el conjunto de menús del rol.     |
| GET    | `/api/v1/admin/menus`                      | Admin | Lista de menús (plana + árbol).             |
| POST   | `/api/v1/admin/menus`                      | Admin | Crea un menú (actividad).                   |
| GET    | `/api/v1/admin/menus/{id}`                 | Admin | Devuelve un menú por id.                    |
| PATCH  | `/api/v1/admin/menus/{id}`                 | Admin | Actualiza un menú.                          |
| DELETE | `/api/v1/admin/menus/{id}`                 | Admin | Elimina (lógico) un menú.                   |
| GET    | `/api/v1/admin/users`                      | Admin | Lista los usuarios del tenant.              |
| POST   | `/api/v1/admin/users`                      | Admin | Crea un usuario (nombre desglosado + roles). |
| GET    | `/api/v1/admin/users/{id}`                 | Admin | Devuelve un usuario por id.                 |
| PATCH  | `/api/v1/admin/users/{id}`                 | Admin | Actualiza un usuario.                       |
| DELETE | `/api/v1/admin/users/{id}`                 | Admin | Elimina (lógico) un usuario.                |
| PUT    | `/api/v1/admin/users/{id}/roles`           | Admin | Reemplaza el conjunto de roles del usuario. |

> «Admin» en la columna *Auth* significa: bearer válido **y** rol de RBAC con `code = "ADMIN"`
> (`require_admin`). «Cookie» significa que el endpoint se autentica con la cookie de
> refresco, no con el header `Authorization`.

---

## Modelos de datos del contrato

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
  ]
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
  "name": "string",
  "code": "string | null",
  "is_active": true,
  "created_at": "ISO-8601 timestamp"
}
```

### `Role`

```json
{
  "id": "uuid",
  "code": "string",
  "name": "string",
  "is_active": true,
  "created_at": "ISO-8601 timestamp"
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
  "children": ["Menu"]
}
```

> En las respuestas en **árbol** (`/auth/me/menus`, el `tree` de `/admin/menus`) cada `Menu`
> incluye `children[]`. En la respuesta **plana** (`flat` de `/admin/menus`) se usa
> `parent_id` y no hay `children`.

### `Project`

```json
{
  "id": "uuid",
  "name": "string",
  "description": "string | null",
  "methodology": "planner | kanban | scrum | custom",
  "status": "string",
  "organization_id": "uuid",
  "created_at": "ISO-8601 timestamp",
  "methodology_info": {
    "methodology": "string",
    "default_columns": ["string"],
    "allowed_statuses": ["string"],
    "sprints_enabled": "boolean",
    "estimation_mode": "none | points | hours | both",
    "has_backlog": "boolean"
  }
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
  "completed_at": "ISO-8601 timestamp | null"
}
```

> `status` es texto libre validado contra los `allowed_statuses` de la metodología del
> proyecto (el rótulo de una columna del tablero), no un enum global.

> `completed_at` lo gestiona el backend: se fija en `now()` cuando la tarea entra a la
> columna «done» (`allowed_statuses[-1]`) y vuelve a `null` cuando sale de ella. Es de
> **solo lectura** en el contrato (no se acepta en `POST` ni en `PATCH`); alimenta el
> burndown del sprint y la vista de rendimiento.

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
  "created_at": "ISO-8601 timestamp"
}
```
