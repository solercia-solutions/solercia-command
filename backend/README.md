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
  db_init.py           seed idempotente (organización, RBAC, admin, demo); create_all solo para fixtures de test
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
| `INTEGRATIONS_FERNET_KEY`     | llave de desarrollo fija (cámbiala en producción — genera una con `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`) |
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

El entrypoint del contenedor (`backend/docker/entrypoint.sh`) ejecuta
`alembic upgrade head` **antes** de arrancar uvicorn: el esquema lo define la
migración baseline, no `create_all`. Ya con el esquema migrado, el `lifespan`
de la aplicación espera a que Postgres esté listo y siembra de forma
idempotente:

- Organización `Solercia` (slug `solercia`)
- Usuario administrador `admin@solercia.com` / `Admin123*`

Si tu volumen de `pgdata` ya existía antes de este cambio (esquema creado por
`create_all` en versiones previas), séllalo en la revisión baseline una sola
vez —**antes** de levantar `backend`— para que `alembic upgrade head` no
intente recrear tablas ya existentes:

```bash
docker compose run --rm --entrypoint alembic backend stamp head
```

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

## Base de datos de test

`docker-compose.yml` provisiona `solercia_test` junto a `solercia` en el mismo
Postgres, mediante `backend/docker/initdb/create-test-db.sh` montado en
`/docker-entrypoint-initdb.d`. Ese directorio de Postgres solo se ejecuta la
**primera vez** que se crea el volumen de datos (`pgdata`).

Si ya tienes un volumen existente (creado antes de este cambio), crea la base
manualmente una sola vez:

```bash
docker compose exec postgres psql -U app -d solercia -c "CREATE DATABASE solercia_test"
```

## Migraciones

Alembic está configurado en modo async (`alembic/env.py`) y es la **fuente de
verdad del esquema**: `Base.metadata.create_all` ya no crea el esquema en el
arranque de la aplicación (ver la sección "Ejecución" arriba). Toda la línea
base vigente vive en `backend/alembic/versions/0001_baseline.py`, generada con
`alembic revision --autogenerate` contra una base de datos vacía y equivalente
al esquema que antes producía `create_all`.

Todo cambio de modelo SQLAlchemy (campo nuevo, tabla nueva, índice, etc.) se
expresa como una nueva revisión Alembic **antes de mergear**:

```bash
# 1. Modifica el/los modelos en app/modules/**/models.py.
# 2. Con el esquema actual aplicado (alembic upgrade head), genera la revisión:
alembic revision --autogenerate -m "descripcion_del_cambio"
# 3. Revisa el diff generado en backend/alembic/versions/ — el autogenerate
#    no es infalible con renombres de columnas ni con algunos tipos.
# 4. Aplica la migración:
alembic upgrade head
```

`alembic check` (Alembic 1.14+) confirma que el esquema migrado no tiene
diferencias pendientes contra los modelos; `backend/tests/test_migrations_baseline.py`
lo ejecuta como guardia automática contra una base de datos desechable.

## Desarrollo local (sin Docker)

Para correr `pytest`, `ruff` y `mypy` directamente en el host (fuera de los
contenedores) crea un entorno virtual e instala las dependencias de
desarrollo:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

Con Postgres accesible (`docker compose up -d postgres`) y `solercia_test`
provisionada (ver "Base de datos de test" arriba), exporta la URL de test y
corre la suite:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test
pytest tests/ -v
```

Sin `TEST_DATABASE_URL` los tests que necesitan base de datos se saltan con
una razón explícita en el reporte (no fallan ni pasan en falso); los tests
unitarios corren siempre.

Lint y tipos, con cero hallazgos esperados (configurados en
`backend/pyproject.toml`):

```bash
ruff check .
mypy app/
```
