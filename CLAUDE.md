# Solercia Project Manager — CLAUDE.md

## Visión del producto

Sistema de gestión de proyectos multi-tenant que reemplaza Planner y Jira en distintas entidades. Cada tenant (entidad) puede activar módulos según su necesidad:

| Tenant | Reemplaza | Módulos clave |
|--------|-----------|---------------|
| Entidad A (Planner-like) | Microsoft Planner | Tableros, alertas, vista ejecutiva, cruce con trabajo realizado |
| Entidad B (Jira-like) | Jira | Backlog, sprints, estimación, workflows configurables |
| SDMujer | Planner + Inventario | Tareas + inventario de activos de información, alertas de vencimiento de licencias, recordatorios |

### Capacidades transversales

- **Vista ejecutiva**: dashboard para jefes — estado de cada persona, riesgos, carga de trabajo, alertas. Una sola pantalla, sin scroll infinito.
- **Sistema de alertas**: vencimientos, tareas bloqueadas, SLA incumplidos, licencias por vencer. Canales: in-app (toast + badge), email digest configurable.
- **Cruce con trabajo realizado**: registro de actividad diaria vs. tareas asignadas. El jefe ve discrepancias.
- **Recordatorios**: programables por usuario o automáticos por regla (ej: "3 días antes de vencimiento de licencia").
- **Multi-tenant**: cada organización con su configuración, usuarios, proyectos y datos aislados.

## Metodología configurable (decisión de diseño core)

El sistema NO se casa con una metodología por entidad. **Cada proyecto elige su metodología al crearse** y eso define su comportamiento. Implementado con **Strategy pattern** (`app/methodology/`).

`Project.methodology` (enum):
- `planner` — estilo Microsoft Planner (lo que SDMujer ya conoce de Outlook). Buckets como columnas, estados simples (Sin iniciar / En curso / Completada), sin sprints, sin story points.
- `kanban` — flujo continuo, tablero con WIP, sin sprints.
- `scrum` — backlog + sprints + story points (Fibonacci) + workflow To Do → In Progress → In Review → Done. Estilo Jira.
- `custom` — la organización define sus estados y columnas.

Cada strategy expone: `default_columns()`, `allowed_statuses()`, `sprints_enabled`, `estimation_mode (none|points|hours|both)`, `has_backlog`. **Regla de oro**: la API y la UI leen el comportamiento DESDE la strategy, nunca con `if methodology == ...` regado por el código. Método nuevo = clase nueva, cero cambios en el resto.

## Puertos y arranque (docker-compose)

| Servicio | Puerto host | Descripción |
|----------|-------------|-------------|
| frontend (node/Angular) | 4200 | UI |
| backend (uvicorn/FastAPI) | 8000 | API + Swagger en `/docs` |
| postgres | 5432 | Base de datos |
| redis | 6379 | Cache / colas |

`docker compose up` levanta todo. API base: `http://localhost:8000/api/v1`. Tema claro/oscuro conmutable en la UI (hereda el sistema de tokens CSS + ThemeService de boki-front).

## Stack tecnológico

### Backend — FastAPI (Python 3.12+)

- **Framework**: FastAPI con Pydantic v2 para validación
- **ORM**: SQLAlchemy 2.0+ (async, mapped columns)
- **Migraciones**: Alembic
- **Auth**: JWT (access + refresh tokens), bcrypt para hashing
- **Cache/Queue**: Redis (cache de sesiones, cola de notificaciones, pub/sub para alertas en tiempo real)
- **Docs**: Swagger/OpenAPI auto-generado por FastAPI
- **Testing**: pytest + pytest-asyncio + httpx (AsyncClient)
- **Task scheduling**: APScheduler o Celery Beat (para alertas programadas y recordatorios)

### Frontend — Angular 20+ (base: boki-front)

- **Arquitectura**: Feature-Sliced Design (FSD) — ya implementada en boki-front
- **CSS**: Tailwind CSS 3.4+ con sistema de tokens `--bk-*` (renombrar a `--sp-*` para este proyecto)
- **Componentes reutilizables**: heredar de `src/shared/ui/` de boki-front (badge, button, card, checkbox, dropdown, file-upload, form-field, day-picker)
- **State management**: Angular Signals (ya usado en boki-front auth store)
- **Auth**: signal-based JWT con guards funcionales e interceptor (copiar patrón de boki-front)
- **Antes de crear un componente**: verificar si ya existe en `src/shared/ui/` o `src/app/shared/components/`

### Base de datos — PostgreSQL 16+

- **Multi-tenancy (MVP)**: row-level — columna `organization_id` en toda entidad tenant-scoped + filtro global por tenant resuelto desde el JWT. Decisión de arranque: más simple con SQLAlchemy async, rápida al demo y mantenible. **Futuro (hardening)**: migrar a schema-por-tenant si una entidad exige aislamiento físico fuerte. No bloquea el MVP.
- **Redis**: cache de sesiones, notificaciones en tiempo real, colas de alertas

### Archivos base de referencia

- Frontend base: `/Users/camilocalderont/Proyectos/SOLERCIA/solercia_flows/boki-front/`
- Backend base (auth NestJS → migrar a FastAPI): `/Users/camilocalderont/Proyectos/SOLERCIA/solercia_flows/boki-api/`

## Arquitectura backend

### Estructura de carpetas (Screaming Architecture)

```
backend/
├── alembic/                    # Migraciones
├── app/
│   ├── main.py                 # Entry point FastAPI
│   ├── config.py               # Settings (pydantic-settings, .env)
│   ├── database.py             # Engine, session factory, base
│   ├── dependencies.py         # Dependency injection compartida
│   ├── middleware/
│   │   ├── auth.py             # JWT middleware
│   │   ├── tenant.py           # Tenant resolution middleware
│   │   └── cors.py
│   ├── modules/
│   │   ├── auth/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py      # Pydantic models (request/response)
│   │   │   ├── models.py       # SQLAlchemy models
│   │   │   └── dependencies.py
│   │   ├── users/
│   │   ├── organizations/      # Tenants
│   │   ├── projects/
│   │   ├── boards/             # Tableros tipo Planner
│   │   ├── sprints/
│   │   ├── tasks/
│   │   ├── comments/
│   │   ├── labels/
│   │   ├── alerts/             # Motor de alertas
│   │   ├── assets/             # Inventario de activos (SDMujer)
│   │   ├── reminders/
│   │   └── activity_log/       # Registro de actividad
│   └── shared/
│       ├── base_model.py       # Base SQLAlchemy con id, created_at, updated_at, soft delete
│       ├── pagination.py
│       ├── exceptions.py
│       ├── enums.py
│       └── utils.py
├── tests/
├── requirements.txt
├── .env.example
└── Dockerfile
```

### Patrones obligatorios

- **Repository pattern**: cada módulo tiene su repository para queries. El service NUNCA toca SQLAlchemy directamente.
- **Dependency injection**: usar `Depends()` de FastAPI. Services se inyectan en routers, repositories en services.
- **Strategy pattern**: para workflows de tareas configurables por tenant (ej: Planner usa "To Do → Doing → Done", Jira usa workflow custom).
- **Soft delete**: todo modelo hereda `is_active`, `deleted_at`. NUNCA delete físico.
- **Auditoría**: `created_by`, `updated_by` en todo modelo. Automático vía middleware.
- **Multi-tenant**: middleware resuelve tenant desde JWT claim → setea schema en la session de SQLAlchemy.

### API conventions

- Versionado: `/api/v1/`
- RESTful estricto: `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}`, `DELETE /tasks/{id}`
- Respuestas envueltas: `{ "data": {...}, "message": "...", "meta": { "page": 1, "total": 50 } }`
- Errores: `{ "detail": "...", "code": "TASK_NOT_FOUND", "status": 404 }`
- Paginación: query params `?page=1&size=20&sort=created_at&order=desc`
- Filtros: query params `?status=in_progress&assignee_id=uuid&sprint_id=uuid`

## Modelo de datos (entidades core)

### Entidades y relaciones

```
Organization (tenant)
├── User (M:N via OrganizationMember con role)
├── Project
│   ├── Board (1:N — tableros tipo Planner)
│   │   ├── BoardColumn (1:N — columnas: To Do, In Progress, Done...)
│   │   └── Task (N:1 — tarea asignada a columna)
│   ├── Sprint (1:N)
│   │   └── Task (N:1 — tarea asignada a sprint)
│   ├── Backlog → Tasks sin sprint ni board
│   ├── Label (1:N — etiquetas del proyecto)
│   └── Task
│       ├── TaskAssignment (M:N user-task)
│       ├── TaskComment (1:N)
│       ├── TaskAttachment (1:N)
│       ├── TaskChecklist (1:N)
│       │   └── ChecklistItem (1:N)
│       ├── TaskDependency (M:N task-task, tipos: blocks, is_blocked_by)
│       ├── TaskLabel (M:N)
│       ├── TaskTimeLog (1:N — registro de tiempo)
│       └── TaskHistory (1:N — changelog automático)
├── Asset (inventario de activos — módulo SDMujer)
│   ├── AssetLicense (1:N — licencias con fecha de vencimiento)
│   └── AssetTask (M:N — tareas relacionadas al activo)
├── Alert (1:N)
│   ├── AlertRule (1:N — reglas: "X días antes de vencimiento")
│   └── AlertNotification (1:N — notificaciones generadas)
├── Reminder (1:N — recordatorios manuales o automáticos)
└── ActivityLog (1:N — qué hizo cada usuario cada día)
```

### Task — campos core

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | PK |
| project_id | UUID | FK → Project |
| sprint_id | UUID? | FK → Sprint (null = backlog) |
| board_column_id | UUID? | FK → BoardColumn (null = no está en tablero) |
| parent_task_id | UUID? | FK → Task (subtareas) |
| title | str | Título |
| description | text? | Descripción rica (markdown) |
| task_type | enum | epic, story, task, subtask, bug |
| status | enum | backlog, to_do, in_progress, in_review, done, cancelled |
| priority | enum | critical, high, medium, low |
| estimation_points | int? | Story points (Fibonacci: 1,2,3,5,8,13,21) |
| estimation_hours | decimal? | Horas estimadas |
| due_date | datetime? | Fecha límite |
| start_date | datetime? | Fecha de inicio |
| completed_at | datetime? | Fecha de completado |
| order | int | Orden dentro de la columna/sprint/backlog |
| risk_flag | bool | Marcado como riesgo por el sistema o usuario |
| risk_reason | str? | Razón del riesgo |

### Sistema de estimación dual

Las tareas soportan dos tipos de estimación (configurable por proyecto):
- **Story points**: Fibonacci (1,2,3,5,8,13,21) — para sprints y velocity
- **Horas**: estimación en horas — para cruce con tiempo real registrado

### Vista ejecutiva — queries clave

La vista del jefe necesita responder en UNA pantalla:
1. **¿En qué anda cada persona?** → tasks in_progress agrupadas por assignee
2. **¿Qué tiene riesgo?** → tasks con `risk_flag=true` O `due_date < hoy + 3 días` sin completar
3. **¿Cómo va el sprint?** → burndown (story points completados vs. restantes por día)
4. **¿Quién está sobrecargado?** → conteo de tasks activas por persona vs. capacidad
5. **Alertas activas** → notificaciones no leídas/no resueltas

## Arquitectura frontend

### Estructura (FSD — heredada de boki-front)

```
frontend/
├── src/
│   ├── app/                    # App shell, routing, providers
│   ├── pages/                  # Páginas (lazy loaded)
│   │   ├── dashboard/          # Vista ejecutiva
│   │   ├── login/
│   │   ├── projects/
│   │   ├── board/              # Vista tablero (drag & drop)
│   │   ├── backlog/
│   │   ├── sprint/
│   │   ├── task-detail/
│   │   ├── assets/             # Inventario (módulo SDMujer)
│   │   ├── settings/
│   │   └── people/             # Vista de personas y carga
│   ├── widgets/                # Composiciones de features
│   │   ├── layout-shell/
│   │   ├── sidebar/
│   │   ├── task-card/
│   │   ├── sprint-board/
│   │   ├── burndown-chart/
│   │   ├── risk-panel/
│   │   └── alert-center/
│   ├── features/               # Lógica de negocio por feature
│   │   ├── auth/               # Copiar de boki-front
│   │   ├── manage-tasks/
│   │   ├── manage-projects/
│   │   ├── manage-sprints/
│   │   ├── manage-boards/
│   │   ├── manage-assets/
│   │   └── notifications/
│   ├── entities/               # Modelos y API services
│   │   ├── task/
│   │   ├── project/
│   │   ├── sprint/
│   │   ├── board/
│   │   ├── user/
│   │   ├── asset/
│   │   └── alert/
│   └── shared/                 # Copiar base de boki-front
│       ├── ui/                 # Componentes atómicos
│       ├── api/                # Interceptors, base service
│       ├── lib/                # Utilities
│       └── tokens/             # DI tokens, theme
```

## Motor de alertas

### Tipos de alerta

| Tipo | Trigger | Canal |
|------|---------|-------|
| task_overdue | Tarea pasa su due_date sin completarse | In-app + email |
| task_at_risk | Tarea a X días de vencer sin progreso | In-app |
| sprint_at_risk | Sprint con < 50% completado al 75% del tiempo | In-app + email a jefe |
| license_expiring | Licencia de activo a X días de vencer | In-app + email |
| license_expired | Licencia venció | In-app + email urgente |
| workload_imbalance | Usuario con > N tareas activas | In-app a jefe |
| blocked_task | Tarea bloqueada por > X días | In-app |

### Implementación

- **AlertRule**: reglas configurables por organización (ej: "alertar 7, 3 y 1 día antes de vencimiento")
- **Scheduler (Redis + APScheduler)**: job que corre cada hora, evalúa reglas, genera AlertNotification
- **WebSocket**: notificaciones push en tiempo real al frontend
- **Email digest**: resumen diario/semanal configurable por usuario

## Módulo de activos de información (SDMujer)

### Entidades

```
Asset
├── name: str
├── description: text
├── asset_type: enum (software, hardware, license, service, document)
├── status: enum (active, inactive, retired, under_review)
├── responsible_id: UUID → User
├── acquisition_date: date
├── location: str?
├── vendor: str?
├── criticality: enum (critical, high, medium, low)
│
├── AssetLicense (1:N)
│   ├── license_key: str?
│   ├── license_type: enum (perpetual, subscription, trial)
│   ├── start_date: date
│   ├── expiration_date: date
│   ├── seats: int?
│   ├── cost: decimal?
│   └── auto_renew: bool
│
└── AssetTask (M:N → Task)
    # Permite crear tareas asociadas al activo
    # Ej: "Renovar licencia de antivirus" → tarea con due_date = expiration_date - 30 días
```

## Reglas de desarrollo

### Backend

- Todo endpoint debe tener docstring para Swagger
- Todo endpoint debe validar permisos (role-based: admin, manager, member, viewer)
- Queries complejas van en el repository, NUNCA en el router
- Usar `async def` en todos los endpoints y services
- Migrations con nombres descriptivos: `add_risk_flag_to_tasks`
- Tests: mínimo happy path + caso de error + caso de permisos por endpoint

### Frontend

- Componente nuevo → primero verificar si existe en `shared/ui/`
- Signals para estado local, services para estado compartido
- Lazy loading en TODAS las páginas
- Responsive: mobile-first con Tailwind breakpoints
- Accesibilidad: `aria-label` en botones de ícono, roles en regiones

### Git

- Conventional commits: `feat(tasks): add drag and drop reordering`
- Un commit por unidad lógica de trabajo
- Branch naming: `feat/module-name`, `fix/issue-description`

## Prioridad de implementación (MVP → Demo)

### Fase 1 — Core (demo funcional)
1. Auth (registro, login, JWT, refresh)
2. Organizaciones y usuarios (CRUD, roles)
3. Proyectos (CRUD, asignar miembros)
4. Tareas (CRUD, asignar, estimar, estados, prioridades)
5. Backlog (lista de tareas sin sprint)
6. Sprints (crear, asignar tareas, cerrar)
7. Tablero/Board (columnas, drag & drop)
8. Vista ejecutiva básica (quién hace qué, riesgos)

### Fase 2 — Alertas y seguimiento
9. Motor de alertas (reglas, notificaciones in-app)
10. Registro de actividad (time logs, activity log)
11. Comentarios en tareas
12. Subtareas y checklists

### Fase 3 — Activos (SDMujer)
13. CRUD de activos
14. Gestión de licencias con vencimientos
15. Alertas de vencimiento de licencias
16. Vinculación activo ↔ tarea

### Fase 4 — Pulido
17. Email notifications
18. WebSocket real-time
19. Burndown chart
20. Filtros avanzados y búsqueda global
