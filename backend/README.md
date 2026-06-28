# Solercia PM — Backend

API del gestor de proyectos Solercia, construida con FastAPI, SQLAlchemy 2.0
async, asyncpg, Pydantic v2 y autenticación JWT.

## Arquitectura

```
app/
  config.py            Configuración (pydantic-settings) desde variables de entorno
  database.py          Engine async, sessionmaker y Base declarativa
  dependencies.py      Dependencias de auth y de alcance por organización
  main.py              App FastAPI, CORS, routers y lifespan (espera de BD + seed)
  db_init.py           create_all + seed del administrador por defecto
  shared/              Mixins de modelo, enums, seguridad y manejo de errores
  methodology/         Patrón Strategy por metodología (planner/kanban/scrum/custom)
  modules/
    auth/              Login y usuario actual
    users/             Modelo de usuario
    organizations/     Organización y membresías
    projects/          router -> service -> repository
```

El flujo de cada módulo respeta la separación **router -> service -> repository**:
el router nunca usa SQLAlchemy directamente.

## Variables de entorno

| Variable                      | Valor por defecto                                          |
| ----------------------------- | ---------------------------------------------------------- |
| `DATABASE_URL`                | `postgresql+asyncpg://app:app@postgres:5432/solercia`      |
| `REDIS_URL`                   | `redis://redis:6379/0`                                      |
| `JWT_SECRET`                  | `dev-secret-change-me` (cámbialo en producción)            |
| `JWT_ALG`                     | `HS256`                                                     |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480`                                                      |
| `CORS_ORIGINS`                | `["http://localhost:4200"]`                                |

## Ejecución

El backend está pensado para correr con Docker Compose junto a Postgres y Redis:

```bash
docker compose up --build
```

La API queda disponible en `http://localhost:8000`. La documentación Swagger
está en `http://localhost:8000/docs`.

Al arrancar, el servicio espera a que Postgres esté listo, crea el esquema y
siembra de forma idempotente:

- Organización `Solercia` (slug `solercia`)
- Usuario administrador `admin@solercia.com` / `Admin123*`

## Endpoints (v1)

Base: `http://localhost:8000/api/v1`

| Método | Ruta              | Descripción                              |
| ------ | ----------------- | ---------------------------------------- |
| POST   | `/auth/login`     | Inicia sesión, retorna el token Bearer   |
| GET    | `/auth/me`        | Retorna el usuario autenticado           |
| GET    | `/projects`       | Lista los proyectos de la organización   |
| POST   | `/projects`       | Crea un proyecto                         |
| GET    | `/projects/{id}`  | Detalle de un proyecto                   |
| GET    | `/api/v1/health`  | Estado del servicio                      |

## Metodologías (patrón Strategy)

Cada metodología define columnas de tablero, estados permitidos y banderas de
funcionalidad. `methodology_info` se adjunta a cada proyecto en la respuesta.

| Metodología | Columnas                                  | Sprints | Estimación | Backlog |
| ----------- | ----------------------------------------- | ------- | ---------- | ------- |
| planner     | Sin iniciar / En curso / Completada       | No      | none       | No      |
| kanban      | Backlog / Doing / Done                    | No      | hours      | No      |
| scrum       | To Do / In Progress / In Review / Done    | Sí      | points     | Sí      |
| custom      | (vacío, definido por el usuario)          | No      | none       | No      |

## Migraciones

Alembic está configurado en modo async (`alembic/env.py`). Las migraciones se
difieren (ADR 0003): el esquema se crea con `create_all` en el arranque. Para
generar la primera migración cuando se decida adoptarlas:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```
