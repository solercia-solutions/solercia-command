# Solercia Command — Backend

API de Solercia Command para coordinar proyectos y trabajo multi-tenant, construida con FastAPI, SQLAlchemy 2.0
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
| `SEED_DEMO_DATA`              | `false` — enciende solo para demos; con `false` la semilla NUNCA crea `ana@`/`carlos@`/`diana@` ni sus proyectos, tareas o el sprint demo. La semilla estructural (organización `Solercia`, catálogo RBAC, `admin@solercia.com`) siempre corre, sin importar este valor. |
| `LLM_PROVIDER`                | `fake` — selecciona el adaptador `LlmPort` activo (`fake`, `openai_compatible`, `anthropic`), leído en cada llamada, nunca en el import. |
| `LLM_BASE_URL`                | vacío — URL base del proveedor; DEBE estar en `LLM_BASE_URL_ALLOWLIST` o el adaptador rechaza la petición antes de construirse (anti-SSRF). |
| `LLM_MODEL`, `LLM_API_KEY`    | vacíos — modelo y credencial del proveedor; `LLM_API_KEY` nunca se expone (solo su presencia, como booleano). |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`, `LLM_MAX_RETRIES`, `LLM_MAX_BACKOFF_SECONDS` | `60.0` / `1024` / `2` / `30.0` — límites deterministas de la llamada y de los reintentos. |
| `LLM_JSON_MODE`               | `json_object` — forma del cuerpo de salida estructurada (`json_object`, `json_schema_openai`, `json_schema_llamacpp`). |
| `LLM_BASE_URL_ALLOWLIST`      | Ollama/llama.cpp locales + `https://api.anthropic.com` — única lista de destinos HTTP permitidos para el puerto LLM. |

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
| GET    | `/api/v1/assistant/health` | Estado del proveedor de IA activo (`LlmPort`); `admin`/`manager` únicamente, `?probe=true` opcional |

## Metodologías (patrón Strategy)

Cada metodología define columnas de tablero, estados permitidos y banderas de
funcionalidad. `methodology_info` se adjunta a cada proyecto en la respuesta.

| Metodología | Columnas                                  | Sprints | Estimación | Backlog |
| ----------- | ----------------------------------------- | ------- | ---------- | ------- |
| planner     | Sin iniciar / En curso / Completada       | No      | none       | No      |
| kanban      | Backlog / Doing / Done                    | No      | hours      | No      |
| scrum       | To Do / In Progress / In Review / Done    | Sí      | points     | Sí      |
| custom      | (vacío, definido por el usuario)          | No      | none       | No      |

## Activación del proveedor LLM local

Por defecto `LLM_PROVIDER=fake` (sin red, sin costo). Para probar contra un
modelo local con [Ollama](https://ollama.com):

1. Levanta Ollama en el host y descarga el modelo, p. ej.
   `ollama pull qwen3.5:9b-q4_K_M`.
2. Exporta las variables `LLM_*` según dónde corra el proceso que las lee:
   - **Desde el host** (`pytest`, script suelto): `LLM_BASE_URL=http://localhost:11434/v1`.
   - **Desde el contenedor** (`docker compose up`): `LLM_BASE_URL=http://host.docker.internal:11434/v1`
     (en Linux `host.docker.internal` no resuelve — la sonda responde
     `reachability=unreachable` con un motivo legible, no un error crudo).
   - En ambos casos: `LLM_PROVIDER=openai_compatible`, `LLM_MODEL=qwen3.5:9b-q4_K_M`
     (o cualquier alternativa ya descargada en Ollama).
   - Ambas URLs ya viven en `LLM_BASE_URL_ALLOWLIST` por defecto; una URL fuera
     de esa lista se rechaza antes de cualquier petición.
3. Reinicia el backend (`docker compose up -d --build backend` o el proceso
   local) para que tome las variables nuevas.
4. Verifica con la sonda manual (requiere un token `admin`/`manager`):

   ```bash
   curl -s -H "Authorization: Bearer <token>" \
     "http://localhost:8081/api/v1/assistant/health?probe=true"
   ```

   `reachability` responde `ok` si Ollama contesta en `/v1/models`, o
   `unreachable` con un motivo legible si no. `anthropic` nunca se sondea
   (`not_probed`, sondear consumiría cuota); `fake` siempre reporta `ok`.

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

## Scripts operativos

### Purga de datos demo y bootstrap de SDMUJER

`backend/scripts/purge_demo_data.py` es una CLI delgada, dueña de su propia
transacción, que borra los datos demo (organización `Acme Consultores`,
usuarios `ana@`/`carlos@`/`diana@`, proyectos y conector `fake`) y
bootstrapea la jerarquía operativa `SDMUJER > {SEGURIDAD, PANDORA}`. Corre
**siempre** con `-m` desde `backend/` (así `sys.path[0]` es el cwd y
`import app.*` resuelve sin parchear rutas):

```bash
cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia
```

Por defecto corre en modo **dry-run**: ejecuta el mismo código de purga y
bootstrap y termina en `rollback`, así que el reporte impreso es exactamente
lo que un `--execute` haría — nada cambia en la base. El `DATABASE_URL` por
defecto apunta a `postgres:5432` (solo resoluble dentro de la red de
Docker); `--database-url` es obligatorio para correr desde el host.

**Runbook de ejecución real** (contra `gestion_proyectos-postgres-1` /
`solercia`), en este orden exacto:

1. **Compuerta primero**: desplegar con `SEED_DEMO_DATA=false` —
   `docker compose up -d --build backend` — y confirmar que
   `ana@`/`carlos@`/`diana@` no reaparecen tras el reinicio.
2. **Respaldo desde el host** (`pg_dump` no existe en la imagen del
   backend):

   ```bash
   mkdir -p /Users/camilocalderont/Proyectos/SOLERCIA/backups
   docker exec gestion_proyectos-postgres-1 pg_dump -U app solercia > /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql
   ```

   Confirmar que el archivo resultante pesa más de 0 bytes.
3. **Dry-run**:

   ```bash
   cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia
   ```

4. **Revisión humana explícita** del reporte impreso (alcance planeado,
   inventario, conectores con propietario) — punto de no retorno antes de
   continuar.
5. **Ejecución real**, agregando `--execute --backup-file <ruta del paso
   2>`. El script exige el respaldo (existe y pesa más de 0 bytes) ANTES de
   tocar la base; confirmar código de salida `0` e invariantes I1-I8 en
   PASS en el reporte.
6. **Reinicio con reconstrucción de imagen** (obligatorio para que el
   código nuevo y `SEED_DEMO_DATA` tomen efecto):
   `docker compose up -d --build backend`.
7. **Reverificación post-reinicio**: repetir el dry-run y confirmar que
   ningún dato demo reaparece (`ana@`/`carlos@`/`diana@`, org `Acme
   Consultores`, conector `fake`).
8. **`--purge-upload-files`** (opcional): agrega este flag a `--execute`
   solo si se decide limpiar de `backend/uploads/` los ficheros
   referenciados por los `attachments` que la purga borra. Nunca hace un
   borrado genérico del directorio — borra únicamente los ficheros con
   `stored_name` de esas filas, después del `commit`.

**Códigos de salida**:

| Código | Significado |
|---|---|
| 0 | Éxito (dry-run o execute) con todas las invariantes en PASS |
| 1 | Error de uso: `--execute` sin `--backup-file`, o respaldo inexistente/de tamaño 0 |
| 2 | Guarda de seguridad activada (cuenta conectada de un usuario a borrar, alcance que toca lo protegido) — no se escribió nada |
| 3 | Alguna invariante en FAIL — transacción revertida, sin `commit` |
| 4 | Excepción inesperada — transacción revertida |

**Rollback** (el backend debe estar detenido para que la semilla no corra a
mitad de la restauración):

```bash
docker compose stop backend
docker exec gestion_proyectos-postgres-1 psql -U app -d solercia -v ON_ERROR_STOP=1 \
  -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO app; GRANT ALL ON SCHEMA public TO public;'
docker exec -i gestion_proyectos-postgres-1 psql -U app -d solercia -v ON_ERROR_STOP=1 \
  < /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql
docker compose start backend
```

Los ficheros borrados con `--purge-upload-files` **no son recuperables**
desde el volcado (no incluye binarios) — por eso el flag está apagado por
defecto.

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
