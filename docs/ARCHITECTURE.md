# Arquitectura — Solercia Command

Este documento describe la arquitectura del MVP de **Solercia Command**, un centro
operativo de trabajo multi-tenant que reemplaza a Jira/Planner. Captura las decisiones
de diseño transversales; las decisiones puntuales con alternativas evaluadas viven en
los registros de decisión (`docs/adr/`).

> Convención de idioma: el código, los identificadores, los comentarios y los nombres de
> archivo se escriben en **inglés**. Los textos visibles para la persona usuaria (mensajes
> de API, errores de validación, etiquetas de UI) se escriben en **español colombiano formal
> con tuteo**. Detalle completo en `docs/adr/0004-stack-and-conventions.md`.

---

## 1. Visión general del sistema

El sistema se compone de cuatro servicios que se levantan con un único comando
(`docker compose up --build`):

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                                │
│                                                                        │
│  ┌────────────────┐        ┌────────────────────┐                      │
│  │  frontend      │  HTTP  │  backend           │   asyncpg            │
│  │  Angular 20    │ ─────► │  FastAPI (uvicorn) │ ──────────┐          │
│  │  Tailwind 3    │ :8000  │  :8000             │           ▼          │
│  │  ng serve      │        │                    │     ┌────────────┐   │
│  │  :4200         │        │  router → service  │     │ postgres   │   │
│  └────────────────┘        │       → repository │     │ 16         │   │
│         ▲                  └─────────┬──────────┘     │ db:solercia│   │
│         │ navegador                  │                └────────────┘   │
│         │ http://localhost:4200      │ cache / colas (futuro)          │
│         │                            ▼                                 │
│  ┌──────┴───────────┐         ┌────────────┐                           │
│  │ Persona usuaria  │         │ redis 7    │                           │
│  └──────────────────┘         └────────────┘                           │
└──────────────────────────────────────────────────────────────────────┘
```

| Servicio   | Tecnología                         | Puerto contenedor | Puerto host |
| ---------- | ---------------------------------- | ----------------- | ----------- |
| `frontend` | Angular 20 standalone + Tailwind 3 | 4200              | 4200        |
| `backend`  | FastAPI + uvicorn                  | 8000              | 8000        |
| `postgres` | PostgreSQL 16                      | 5432              | 5432        |
| `redis`    | Redis 7                            | 6379              | 6379        |

- **API base desde el navegador:** `http://localhost:8000/api/v1`
- **CORS:** el backend permite el origen `http://localhost:4200`.
- **Conexión a la base de datos:** `postgresql+asyncpg://app:app@postgres:5432/solercia`
- **Redis** queda aprovisionado para necesidades futuras (caché de sesión, colas de
  tareas, invalidación). El MVP no depende de él en su ruta crítica.

### Criterio de aceptación del MVP

`docker compose up --build` levanta los cuatro servicios; la persona usuaria inicia
sesión en `http://localhost:4200` y crea un proyecto que persiste en PostgreSQL.

---

## 2. Arquitectura del backend (FastAPI)

El backend sigue una **arquitectura por capas** con una dirección de dependencia
estricta de afuera hacia adentro. Cada capa solo conoce a la capa inmediatamente
inferior; nunca se salta una capa ni se invierte la dirección.

```
HTTP request
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Router  (api/v1/*)                                          │
│  - Declara rutas, status codes y modelos de respuesta.      │
│  - Resuelve dependencias (auth, sesión DB, tenant actual).  │
│  - Valida entrada/salida con esquemas Pydantic v2.          │
│  - No contiene reglas de negocio.                           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Service  (services/*)                                       │
│  - Orquesta las reglas de negocio del caso de uso.          │
│  - Aplica la Strategy de metodología.                       │
│  - Coordina varios repositorios dentro de una transacción.  │
│  - Lanza errores de dominio (traducidos a HTTP en el router).│
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Repository  (repositories/*)                                │
│  - Único punto de acceso a la base de datos.                │
│  - Construye queries SQLAlchemy 2.0 async.                  │
│  - Aplica SIEMPRE el filtro por organization_id (tenant).   │
│  - No conoce HTTP ni reglas de negocio.                     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Models  (models/*)  — SQLAlchemy 2.0 declarative + asyncpg  │
└─────────────────────────────────────────────────────────────┘
```

### Estructura de carpetas sugerida

```
backend/
  app/
    main.py                 # creación de la app FastAPI, routers, CORS, lifespan
    core/
      config.py             # Settings con pydantic-settings (lee DATABASE_URL, etc.)
      database.py           # engine async, AsyncSession, get_session()
      security.py           # hashing de contraseñas, emisión/verificación de JWT
    api/
      deps.py               # dependencias: get_current_user, get_tenant_id
      v1/
        auth.py             # POST /auth/login, GET /auth/me
        projects.py         # CRUD de proyectos
    services/
      auth_service.py
      project_service.py
    repositories/
      user_repository.py
      project_repository.py
    models/
      base.py               # DeclarativeBase, columnas comunes (id, timestamps)
      user.py
      organization.py
      project.py
    schemas/
      auth.py               # LoginRequest, TokenResponse, UserOut
      project.py            # ProjectCreate, ProjectOut, ProjectListResponse
    strategies/
      methodology.py        # Strategy de metodología (planner/kanban/scrum/custom)
    bootstrap/
      seed.py               # create_all + seed idempotente al arrancar
  alembic/                  # andamiaje presente, migraciones diferidas (ADR 0003)
  pyproject.toml
  Dockerfile
```

### Principios aplicados

- **Inyección de dependencias** mediante el sistema `Depends` de FastAPI: la sesión de
  base de datos, el usuario autenticado y el `organization_id` del tenant se inyectan en
  el router y se propagan hacia abajo. Las capas no instancian sus propias dependencias.
- **Single Responsibility:** el router habla HTTP, el service decide, el repository
  persiste. Una regla de negocio nunca vive en un router ni en un repository.
- **Async de extremo a extremo:** SQLAlchemy 2.0 async + asyncpg evitan bloquear el event
  loop de uvicorn.
- **Pydantic v2 + pydantic-settings:** validación de entrada/salida y configuración
  tipada leída desde variables de entorno.

---

## 3. Multi-tenancy a nivel de fila (`organization_id`)

El MVP es multi-tenant mediante **aislamiento por fila**: cada tabla con datos de tenant
incluye una columna `organization_id` (UUID, FK a `organizations`). Todas las consultas se
filtran por el `organization_id` del usuario autenticado.

```
JWT (sub=user_id) ──► get_current_user ──► user.organization_id
                                                  │
                                                  ▼
                                  get_tenant_id (dependencia)
                                                  │
                  cada repository agrega: WHERE organization_id = :tenant_id
```

- El `organization_id` **no** se acepta desde el cuerpo de la petición para operaciones de
  tenant; se deriva del token. Esto evita que un cliente lea o escriba datos de otra
  organización.
- El filtro por tenant se concentra en la **capa de repository**, de modo que ningún
  service u olvido en un router pueda exponer datos cruzados.

La justificación de elegir aislamiento por fila frente a esquema-por-tenant, y el plan de
endurecimiento futuro (índices compuestos, Row-Level Security de PostgreSQL), están en
`docs/adr/0001-multitenancy-row-level.md`.

---

## 4. Metodología configurable — patrón Strategy

Cada proyecto declara una **metodología** (`planner | kanban | scrum | custom`). En lugar
de dispersar condicionales (`if methodology == "scrum": ...`) por todo el código, el
comportamiento se encapsula en una **Strategy** seleccionada por proyecto.

Cada estrategia define:

| Atributo          | Significado                                                          |
| ----------------- | ------------------------------------------------------------------- |
| `board_columns`   | Columnas por defecto del tablero.                                   |
| `allowed_statuses`| Estados de tarea permitidos.                                        |
| `sprints_enabled` | Si la metodología habilita sprints.                                 |
| `estimation_mode` | Modo de estimación (p. ej. `none`, `hours`, `story_points`).        |
| `has_backlog`     | Si la metodología expone un backlog.                                |

```
ProjectService.create(...)
        │
        ▼
MethodologyStrategyFactory.for(methodology)  ──►  PlannerStrategy
                                                  KanbanStrategy
                                                  ScrumStrategy
                                                  CustomStrategy
        │
        ▼
strategy.board_columns / allowed_statuses / sprints_enabled / estimation_mode / has_backlog
```

Esto mantiene el `ProjectService` cerrado a modificación y abierto a extensión: agregar una
metodología nueva es crear una clase Strategy y registrarla en la factory, sin tocar la
lógica existente. El detalle y las alternativas descartadas están en
`docs/adr/0002-configurable-methodology-strategy.md`.

---

## 5. Arrancado del esquema y datos semilla

Para el MVP, al iniciar la aplicación se ejecuta `Base.metadata.create_all` (creación de
tablas si no existen) seguido de un **seed idempotente** que garantiza la organización por
defecto y la persona usuaria administradora:

- **Admin semilla:** `admin@solercia.com` / `Admin123*`

Alembic queda **andamiado pero diferido**: las migraciones controladas se incorporan al
salir del MVP. La razón y la ruta de migración están en
`docs/adr/0003-mvp-schema-bootstrap.md`.

---

## 6. Arquitectura del frontend (Angular 20)

El frontend usa **Angular 20 standalone** (sin NgModules) con **Tailwind 3** como motor de
CSS (`darkMode: 'class'`). La organización sigue **Feature-Sliced Design (FSD)**: el código
se agrupa por funcionalidad y por nivel de abstracción, no por tipo técnico.

```
frontend/src/app/
  app.config.ts             # bootstrap: providers, router, interceptors HTTP
  app.routes.ts             # rutas raíz (lazy por feature)
  core/                     # singletons transversales
    auth/                   # AuthService, guard, JWT interceptor
    http/                   # configuración base de HttpClient
  shared/                   # piezas reutilizables sin reglas de negocio
    ui/                     # componentes de presentación (botón, input, card)
    theme/                  # tokens de tema (ver abajo)
  features/                 # cada feature es una rebanada vertical
    auth/
      pages/login/          # smart component: orquesta el caso de uso
      ui/                   # presentational components de la feature
    projects/
      pages/project-list/
      pages/project-create/
      data/                 # acceso a API (ProjectApi), modelos del feature
```

### Patrón container / presentational

- **Smart (container):** las `pages/*` resuelven datos vía servicios, manejan estado y
  navegación.
- **Presentational:** los componentes en `shared/ui` y `features/*/ui` reciben datos por
  `@Input` y emiten eventos por `@Output`; no conocen servicios ni la API.
- Antes de escribir un componente nuevo se verifica si ya existe uno reutilizable en
  `shared/ui` (regla de no duplicación de la guía del proyecto).

### Tokens de tema

El tema se define con **design tokens** mapeados en la configuración de Tailwind, de modo
que los componentes consuman variables semánticas en lugar de colores crudos. Esto permite
el modo claro/oscuro mediante la clase en `<html>` (`darkMode: 'class'`).

```
:root            --color-bg, --color-surface, --color-primary, --color-text, ...
.dark            (sobrescribe los mismos tokens)
tailwind.config  theme.extend.colors → bg/surface/primary/text apuntan a los tokens
componentes      class="bg-surface text-text"  (semántico, no "bg-white text-black")
```

### Comunicación con el backend

- `HttpClient` con `baseUrl = http://localhost:8000/api/v1`.
- Un **interceptor** agrega el header `Authorization: Bearer <token>` a las peticiones
  autenticadas y maneja el `401` global.
- El contrato exacto de endpoints está en `docs/API.md`.

---

## 7. Resumen del modelo de datos

Entidades núcleo del MVP. Todas las tablas de tenant incluyen `organization_id`.

```
organizations
  id              uuid    PK
  name            text
  created_at      timestamptz

users
  id              uuid    PK
  organization_id uuid    FK → organizations.id
  email           text    UNIQUE
  hashed_password text
  full_name       text
  is_active       bool
  created_at      timestamptz

projects
  id              uuid    PK
  organization_id uuid    FK → organizations.id
  name            text
  description     text    NULL
  methodology     enum    (planner | kanban | scrum | custom)
  status          text
  created_at      timestamptz

organization_members
  id              uuid    PK
  organization_id uuid    FK → organizations.id
  user_id         uuid    FK → users.id
  role            enum    (admin | manager | member | viewer)
  created_at      timestamptz

sprints
  id              uuid    PK
  organization_id uuid    FK → organizations.id   (tenant)
  project_id      uuid    FK → projects.id
  name            text
  goal            text    NULL
  start_date      date    NULL
  end_date        date    NULL
  status          enum    (active | closed)
  created_at      timestamptz

tasks
  id                uuid    PK
  organization_id   uuid    FK → organizations.id   (tenant)
  project_id        uuid    FK → projects.id
  sprint_id         uuid    FK → sprints.id   NULL   (null = backlog, en scrum)
  title             text
  description       text    NULL
  task_type         enum    (task | bug | story | epic)
  status            text    -- columna del tablero: un valor de allowed_statuses de la Strategy
  priority          enum    (critical | high | medium | low)
  assignee_id       uuid    FK → users.id   NULL     (una sola persona asignada)
  estimation_points int     NULL
  estimation_hours  numeric NULL
  start_date        date    NULL
  due_date          date    NULL
  "order"           int                              (posición dentro de la columna)
  risk_flag         bool
  risk_reason       text    NULL
  created_at        timestamptz
  completed_at      timestamptz NULL                 (instante en que la tarea entró a la columna «done»; null si no está terminada)

task_time_logs
  id              uuid    PK
  organization_id uuid    FK → organizations.id   (tenant)
  task_id         uuid    FK → tasks.id
  user_id         uuid    FK → users.id            (dueño del registro — quién trabajó las horas)
  work_date       date                             (alias de API: "date")
  hours           numeric(5,2)                     (> 0, hasta 24; sin UNIQUE — se suman varios tramos/día)
  note            text    NULL
  created_at      timestamptz

task_history
  id              uuid    PK
  organization_id uuid    FK → organizations.id   (tenant)
  task_id         uuid    FK → tasks.id
  actor_id        uuid    FK → users.id   NULL     (null = actor de sistema)
  actor_type      text                             (user | system)
  field           text                             (status | assignee_id | estimation_points | estimation_hours | sprint_id | priority)
  old_value       text    NULL
  new_value       text    NULL
  created_at      timestamptz                      (alias de API: "changed_at")
```

> **`task_time_logs`/`task_history`** (change 05, «trabajo realizado») son las tablas fuente
> del bloque `work_gap` de la vista ejecutiva (sección 9). `task_time_logs` es un registro
> mutable (`SoftDeleteMixin` + `AuditMixin`): editar/borrar es **estrictamente del dueño**
> (`user_id`), sin excepción de rol — ni `manager` ni `admin` pueden tocar el registro de
> otra persona. `task_history` es **append-only** (sin `SoftDeleteMixin`, sin `AuditMixin`
> — sus propios `actor_id`/`actor_type` cumplen ese rol): se llena por asignación explícita
> desde el servicio que muta la tarea (`TaskService.update_task` con `actor_type=user`,
> `SprintService.close_sprint` con `actor_type=system`), nunca por triggers ni event
> listeners de SQLAlchemy — un `UPDATE` masivo (como el cierre de sprint) no dispara
> eventos por fila, así que el registro tendría huecos si dependiera de ellos.

> **`completed_at` es un campo de evento.** El service lo fija en `now()` cuando el
> `status` de la tarea cambia **a** la última columna (`allowed_statuses[-1]`, la columna
> «done») y lo vuelve a `null` cuando la tarea sale de esa columna. Es el dato mínimo que
> permite reconstruir el burndown de un sprint y el rendimiento por colaborador sin un
> historial de eventos aparte (ver sección 8, «Sprints y burndown», y
> `docs/adr/0007-burndown-and-performance-metrics.md`).

> **`status` es texto, no enum.** El estado de una tarea es uno de los
> `allowed_statuses` que devuelve la Strategy de la metodología del proyecto (es decir,
> el rótulo de una columna del tablero). No se valida contra un enum global de estados;
> la justificación está en `docs/adr/0005-work-items-status-as-column.md`.

### Relaciones

```
organizations 1 ───< users               (vía organization_members: una organización tiene muchos usuarios)
organizations 1 ───< projects            (una organización tiene muchos proyectos)
projects      1 ───< sprints             (un proyecto scrum tiene muchos sprints)
projects      1 ───< tasks               (un proyecto tiene muchas tareas)
sprints       1 ───< tasks               (una tarea puede pertenecer a un sprint; null = backlog)
users         1 ───< tasks               (assignee_id: una tarea tiene a lo sumo una persona asignada)
tasks         1 ───< task_time_logs      (una tarea tiene muchos registros de tiempo trabajado)
users         1 ───< task_time_logs      (user_id: quién registró el tiempo — el dueño del registro)
tasks         1 ───< task_history        (una tarea tiene muchas filas de historial, append-only)
users         1 ───< task_history        (actor_id, NULL = cambio de sistema)
```

### Forma de `Project` expuesta por la API

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
    "methodology": "scrum",
    "default_columns": ["To Do", "In Progress", "In Review", "Done"],
    "allowed_statuses": ["To Do", "In Progress", "In Review", "Done"],
    "sprints_enabled": true,
    "estimation_mode": "points",
    "has_backlog": true
  }
}
```

> `methodology_info` es un campo **derivado** (no se almacena): el service lo calcula con
> `get_strategy(project.methodology).to_info()` y lo adjunta antes de serializar. El
> frontend deriva de él el tablero, las pestañas y los campos de estimación, en lugar de
> repetir condicionales por metodología.

### Entidades de trabajo incorporadas en esta fase

`sprints` y `tasks` ya forman parte del modelo (ver el bloque anterior y la sección
«Work items y tablero»). El diseño de la Strategy se mantiene como única fuente de verdad:
las columnas del tablero, los estados permitidos, la disponibilidad de sprints, el modo de
estimación y el backlog se derivan de `methodology_info`, no de condicionales dispersos.

---

## 8. Work items y tablero

Esta fase incorpora las **tareas** (work items) y los **sprints**, y con ellos el tablero
operativo del proyecto. La regla de diseño central es que **el tablero no tiene tablas
propias**: las columnas del tablero **son** los `allowed_statuses` de la Strategy de la
metodología, y el **estado de una tarea es su columna**.

### Modelo de `Task` y `Sprint`

- Ambas entidades son multi-tenant (`organization_id`) y reutilizan los mixins de
  `app/shared/base_model.py`: `PkMixin` (UUID), `TimestampMixin` (`created_at`,
  `updated_at`), `SoftDeleteMixin` (`is_active`, `deleted_at`) y `TenantMixin`
  (`organization_id`). Su forma de tabla está en la sección 7.
- Una `Task` pertenece siempre a un `project_id`; opcionalmente a un `sprint_id`.
- **Asignación única:** `assignee_id` es una sola FK a `users`. Una tarea tiene a lo sumo
  una persona responsable (no es una relación M:N). El porqué y el costo de esta decisión
  están en `docs/adr/0005-work-items-status-as-column.md`.

### El estado es la columna (regla de oro)

```
project.methodology ──► get_strategy(methodology) ──► allowed_statuses()
                                                              │
                                                              ▼
                            ["To Do", "In Progress", "In Review", "Done"]   (scrum)
                                                              │
                            cada rótulo ES una columna del tablero
                                                              │
                            Task.status ∈ allowed_statuses    (texto, no enum global)
```

- `Task.status` es un **string** validado en la **capa de service** contra
  `get_strategy(project.methodology).allowed_statuses()`. Si el valor no pertenece a esa
  lista, el service lanza un `AppException` con mensaje en español.
- El **estado por defecto** de una tarea nueva es `allowed_statuses[0]` (la primera columna).
- Mover una tarea de columna en el tablero es, simplemente, `PATCH /tasks/{id}` con un
  nuevo `status` perteneciente a `allowed_statuses`. No existe ninguna tabla
  `board` ni `column`.
- El enum global `TaskStatus` de `app/shared/enums.py` **no** gobierna `Task.status`;
  los estados reales los define la Strategy (por ejemplo `Backlog | Doing | Done` en
  kanban, o `Sin iniciar | En curso | Completada` en planner).

> **Metodología `custom`:** su Strategy devuelve `allowed_statuses` vacío. Un proyecto
> custom no tiene columnas predefinidas; la definición de su tablero por parte de la
> persona usuaria queda fuera del alcance de esta fase (ver consecuencias del ADR 0005).

### Backlog y sprints (scrum)

- El **backlog** no es una tabla aparte: es el conjunto de tareas del proyecto con
  `sprint_id = null`. «Mover al sprint» es asignar `sprint_id`; «devolver al backlog» es
  ponerlo en `null`.
- Los **sprints** solo aplican cuando `methodology_info.sprints_enabled` es `true` (scrum).
  Un `Sprint` tiene estado `active | closed`; cerrarlo es `PATCH /sprints/{id}` con
  `status = closed`.
- El service rechaza crear sprints en metodologías con `sprints_enabled = false`,
  manteniendo la coherencia con la Strategy.

### Sprints y burndown

El **burndown** muestra cuánto trabajo queda por terminar en un sprint a medida que avanzan
los días, contrastando el ritmo **ideal** (consumo lineal del alcance) con el ritmo **real**.
Lo sirve `GET /projects/{project_id}/sprints/{sprint_id}/burndown` (ver `docs/API.md`).

El diseño se apoya en una sola pieza de datos nueva, `Task.completed_at`, en lugar de una
tabla de historial de eventos:

```
Task.status pasa a allowed_statuses[-1] (columna «done»)  ──►  completed_at = now()
Task.status sale de la columna «done»                     ──►  completed_at = null
```

Como «done» es la **última** columna de la Strategy, el evento de completar es coherente con
la misma regla que usa el resto del sistema (vista ejecutiva, rendimiento): no se codifica
«qué es estar terminado» por metodología, se deriva de `allowed_statuses[-1]`.

#### Unidad: puntos o tareas

El burndown mide el alcance en **puntos** cuando la metodología del proyecto estima en
puntos, y en **tareas** (conteo) en caso contrario:

| `estimation_mode`     | `unit`     | `total`                                         |
| --------------------- | ---------- | ----------------------------------------------- |
| `points` o `both`     | `"points"` | suma de `estimation_points` de las tareas del sprint |
| `none` o `hours`      | `"tasks"`  | número de tareas del sprint                     |

> Para scrum (`estimation_mode = "points"`) la unidad es `"points"`. Las tareas sin
> `estimation_points` aportan `0` al total en modo puntos, de modo que no inflan ni reducen
> el alcance artificialmente.

#### Línea ideal vs. línea real

Para cada día del rango `[start_date, end_date]` del sprint se calculan dos series:

- **`ideal[d]`** — descenso **lineal** desde `total` en `start_date` hasta `0` en
  `end_date`. Con `N` días entre el inicio y el cierre (inclusive), el ideal del día `i`
  (con `i = 0` en `start_date`) es `total * (1 - i / (N - 1))`. Es una recta de referencia,
  no depende de los datos reales.
- **`actual[d]`** — trabajo que **aún queda** al cierre del día `d`:
  `total - (trabajo completado con completed_at.date() <= d)`. El «trabajo completado» suma
  `estimation_points` (modo puntos) o cuenta tareas (modo tareas) cuya `completed_at` cae en
  ese día o antes. La línea real **no se proyecta al futuro**: `actual[d] = null` para todo
  día posterior a hoy, así la gráfica no dibuja una recta plana sobre fechas que todavía no
  ocurren.

```
GET /projects/{project_id}/sprints/{sprint_id}/burndown
   │
   ├─ sprint:           { id, name, start_date, end_date, status }
   ├─ total_points      suma de puntos del sprint (0 si la unidad es "tasks")
   ├─ total_tasks       número de tareas del sprint
   ├─ completed_tasks   tareas del sprint ya en la columna «done»
   ├─ unit              "points" | "tasks"  (según estimation_mode del proyecto)
   └─ days[]:           [{ date: "YYYY-MM-DD", ideal: number, actual: number | null }]
```

El frontend dibuja ambas series con un **SVG sin librería de gráficas** (ver
`docs/adr/0007-burndown-and-performance-metrics.md`): cuando la línea real queda **por
debajo** de la ideal el sprint va adelantado; cuando queda **por encima**, va retrasado.

---

## 9. Vista ejecutiva (vista de jefe)

La **vista ejecutiva** es un panel de solo lectura, agregado sobre las tareas del tenant,
pensado para que una persona líder responda «¿quién está haciendo qué y qué está en
riesgo?». Lo sirve `GET /dashboard/executive` (ver `docs/API.md`).

Todas las consultas se ejecutan en la capa de repository **filtradas por
`organization_id`** (el tenant del token), de modo que el panel nunca cruza datos de otra
organización.

### Definiciones derivadas de la Strategy

El panel no codifica «qué significa estar terminado» por metodología; lo deriva de los
`allowed_statuses` de cada proyecto:

| Concepto      | Derivación                                                                       |
| ------------- | -------------------------------------------------------------------------------- |
| **done**      | `task.status == allowed_statuses[-1]` (la última columna del tablero).           |
| **active**    | tarea **no** terminada: `task.status != allowed_statuses[-1]`.                    |
| **in progress** | en el panel se reporta como las tareas `active` (no terminadas) de la persona. |
| **at risk**   | `due_date < now` y la tarea no está `done`, **o** `risk_flag = true`.             |
| **overdue**   | `due_date < now` y la tarea no está `done`.                                       |

### Bloques que devuelve el panel

```
GET /dashboard/executive?threshold_days=N  (tenant del token, N por defecto = 3)
   │
   ├─ by_assignee:        por persona → sus tareas activas (in_progress[]) + active_count
   ├─ at_risk:            tareas vencidas-y-no-terminadas o con risk_flag = true
   ├─ workload:           por persona → active_count (carga actual)
   ├─ projects_progress:  por proyecto → total, done, in_progress, percent_done
   ├─ totals:             { projects, tasks, overdue, at_risk }
   └─ work_gap:           cruce asignado vs. realizado (ver subsección dedicada abajo)
```

- `percent_done = round(done / total * 100)` por proyecto (0 cuando `total = 0`).
- `at_risk` se evalúa por proyecto usando el último estado de **ese** proyecto, porque la
  columna «done» depende de la metodología y por tanto difiere entre proyectos.
- Las personas listadas provienen de `organization_members` del tenant (las mismas que son
  asignables a tareas).

### Rendimiento por colaborador

La **vista de rendimiento** responde «¿cómo viene cada persona del equipo?» con un puñado de
métricas comparables entre colaboradores. La sirve `GET /dashboard/performance` (ver
`docs/API.md`), opcionalmente acotada a un sprint con `?sprint_id=<uuid>`.

Al igual que la vista ejecutiva, todo se calcula en la capa de repository **filtrado por
`organization_id`** (el tenant del token) y «estar terminado» se deriva de
`allowed_statuses[-1]` de cada proyecto, no de un enum global. Cuando se pasa `sprint_id`, el
cálculo se restringe a las tareas de ese sprint.

Por cada colaborador del tenant se reportan:

| Métrica            | Definición                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| `completed_tasks`  | Tareas asignadas que están en la columna «done» (`status == allowed_statuses[-1]`).                |
| `completed_points` | Suma de `estimation_points` de esas tareas terminadas (las tareas sin puntos aportan `0`).         |
| `active_count`     | Tareas asignadas **no** terminadas (`status != allowed_statuses[-1]`): la carga viva de la persona. |
| `overdue_count`    | Tareas asignadas **no** terminadas con `due_date < now` (vencidas y pendientes).                   |
| `on_time_rate`     | Proporción `0..1` de cumplimiento a tiempo (ver abajo).                                              |

#### `on_time_rate` — cumplimiento a tiempo

`on_time_rate` mide qué tan seguido la persona termina **dentro del plazo**. Solo cuentan las
tareas **terminadas que tenían `due_date`**, para no castigar ni premiar tareas sin fecha:

```
denominador = tareas terminadas (en «done») de la persona que tenían due_date
numerador   = de esas, las que se completaron a tiempo: completed_at.date() <= due_date.date()
on_time_rate = numerador / denominador        (0..1; 0 cuando el denominador es 0)
```

Una persona que cierra sus compromisos en o antes de la fecha límite tiende a `1.0`; cerrar
**después** del `due_date` (tarde) baja la tasa. Las tareas sin `due_date` o aún sin terminar
no entran en el cálculo. El payload incluye `generated_at` (instante del cómputo) para que la
UI muestre cuándo se tomó la foto.

### Cruce asignado vs. realizado (`work_gap`)

El bloque `work_gap` (change 05, «trabajo realizado») responde «¿lo asignado se está
ejecutando de verdad?», cruzando lo planeado (`Task.estimation_hours`) contra lo
efectivamente trabajado (`TaskTimeLog`) y contra el rastro de actividad de cada tarea
(`TaskHistory`). Vive **dentro** de `GET /dashboard/executive` como un bloque más — no hay
un endpoint `/dashboard/discrepancy` separado; `performance` no se toca.

```
DashboardService.executive(org_id, threshold_days=3)
   │
   ├─ list_for_org(org_id)                         → tareas activas del tenant (ya cargadas)
   ├─ TimeLogRepository.hours_by_user(org_id)       → GROUP BY sobre task_time_logs (todo el histórico)
   ├─ TimeLogRepository.last_activity_by_user       → última fecha de time-log por usuario
   ├─ ActivityRepository.last_activity_by_actor     → último created_at de historial por actor
   ├─ {TimeLog,Activity}Repository
   │     .task_ids_with_recent_entries(org, cutoff) → ids de tarea con actividad en la ventana N
   └─ _work_gap()                                   → cruza todo en Python, sin N+1
```

Por colaborador con **al menos una tarea activa asignada**:

| Campo                  | Definición                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| `hours_logged`           | Suma **de todo el histórico** de `TaskTimeLog.hours` (no acota por `threshold_days`).           |
| `hours_estimated`        | Suma de `estimation_hours` de sus tareas activas asignadas (calculado en Python, sin query extra). |
| `tasks_assigned`         | Conteo de tareas activas asignadas.                                                              |
| `tasks_with_activity`    | De esas, cuántas tienen un `TaskHistory` **o** `TaskTimeLog` en los últimos `threshold_days` días. |
| `no_recent_activity[]`   | Colaboradores con tarea activa asignada y **cero** actividad (ninguna fuente) en los últimos `threshold_days` días — o que nunca registraron actividad. |

`threshold_days` (query param `?threshold_days=N`, por defecto `3`, `>= 1`) gobierna
únicamente `tasks_with_activity` y `no_recent_activity`; `hours_logged`/`hours_estimated`
son siempre acumulados totales. El costo es fijo (2-3 agregaciones `GROUP BY` + la carga de
tareas que `executive()` ya hacía) sin importar cuántas personas o tareas tenga la
organización — mismo patrón O(1) del resto del panel.

---

## 10. Workspace del frontend guiado por metodología

El frontend **no** ramifica por metodología con condicionales dispersos. Al abrir un
proyecto consume `methodology_info` (incluido en la respuesta del proyecto) y **deriva**
toda la interfaz a partir de él. Una metodología nueva no requiere cambios en el workspace
(diseño abierto/cerrado; ver `docs/adr/0006-frontend-methodology-driven-workspace.md`).

```
project.methodology_info
   │
   ├─ sprints_enabled  ──► muestra/oculta la pestaña «Sprints»
   ├─ has_backlog      ──► muestra/oculta la pestaña «Backlog»
   ├─ allowed_statuses ──► columnas del tablero (una por estado, en orden)
   └─ estimation_mode  ──► campos de estimación del formulario de tarea:
                              none   → sin campos
                              points → solo estimation_points
                              hours  → solo estimation_hours
                              both   → ambos
```

### Pestañas, columnas y drag-and-drop

- **Pestañas:** «Tablero» siempre; «Backlog» solo si `has_backlog`; «Sprints» solo si
  `sprints_enabled`. La vista derivada evita un componente por metodología.
- **Columnas:** el tablero renderiza una columna por cada valor de `allowed_statuses`, en
  orden. Cada tarjeta de tarea vive en la columna igual a su `status`.
- **Drag-and-drop (Angular CDK):** al soltar una tarjeta en otra columna, el contenedor
  emite `PATCH /tasks/{id}` con el `status` (rótulo) de la columna destino; el orden dentro
  de la columna se persiste con `order`. No hay estado de tablero local que mantener en
  sincronía: la columna **es** el estado.
- **Asignación y estimación:** el formulario de tarea ofrece un selector de persona
  (alimentado por `GET /projects/{id}/members`) y los campos de estimación que dicte
  `estimation_mode`.

El patrón container/presentational se mantiene: las `pages/*` orquestan datos y llamadas a
la API; los componentes de tablero, columna y tarjeta son presentacionales y reciben todo
por `@Input` / `@Output`.

---

## 11. Decisiones registradas (ADR)

| ADR                                                   | Tema                                                        |
| ----------------------------------------------------- | ----------------------------------------------------------- |
| `adr/0001-multitenancy-row-level.md`                  | Multi-tenancy por fila vía `organization_id` para el MVP.   |
| `adr/0002-configurable-methodology-strategy.md`       | Metodología por proyecto con patrón Strategy.               |
| `adr/0003-mvp-schema-bootstrap.md`                    | `create_all` + seed idempotente; Alembic diferido.          |
| `adr/0004-stack-and-conventions.md`                   | Stack tecnológico y convenciones de idioma.                 |
| `adr/0005-work-items-status-as-column.md`             | El estado de la tarea es su columna; un solo `assignee_id`. |
| `adr/0006-frontend-methodology-driven-workspace.md`   | Workspace del frontend derivado de `methodology_info`.      |
| `adr/0007-burndown-and-performance-metrics.md`        | `completed_at` como evento mínimo; burndown ideal vs. real; métricas de rendimiento; SVG sin librería. |
| `adr/0008-rbac-and-jwt-refresh.md`                    | RBAC (roles/menús/pivotes), `full_name` calculado por compatibilidad, refresco de JWT en cookie `httpOnly`. |
