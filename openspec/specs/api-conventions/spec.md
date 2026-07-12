# Spec — Convenciones de API y plataforma (api-conventions)

> **Origen**: línea base as-built (2026-07-11) + cambios [01-fundacion-tdd](../../changes/archive/2026-07-11-01-fundacion-tdd/), [02-contrato-api](../../changes/archive/2026-07-11-02-contrato-api/)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Contrato transversal del backend: envelope de respuestas, formato de errores, soft delete, timestamps, inicialización de esquema y seed, y configuración por entorno.

## Alcance as-built

- Routers bajo `/api/v1`. PKs UUID en todos los modelos.
- **Envelope**: listas `{"data": [...], "meta": {"total": n [, "page", "size"]}}` (paginación opt-in vía `?page`, `?size`, `?sort`, `?order`); recurso único `{"data": {...}}`; acciones `{"data": ..., "message": "..."}`.
- **Paginación**: offset-based (opt-in). 11 endpoints paginables: tasks, notifications, users, roles, menus, dependencies, projects, sprints, comments, attachments, alert-rules. Sin parámetros de paginación = comportamiento actual (lista completa + `meta{total}`). Whitelist de campos ordenables por endpoint. Validación de límites page≥1, 1≤size≤100 (422 si inválido).
- **Auditoría**: `created_by` / `updated_by` (UUID nullable FK→users.id) en 11 modelos SoftDeleteMixin (AlertRule, Attachment, TaskComment, Dependency, Menu [global], Organization, Project, Role, Sprint, Task, User). Pobladas automáticamente desde usuario autenticado, migración aditiva única, filas preexistentes quedan `NULL`. Expuestas en respuestas (detalle y lista).
- **Errores**: `{"detail", "code", "status"}` (+ `errors` en 422), vía `AppException` + `register_exception_handlers`. Mensajes en español colombiano.
- **Soft delete**: `is_active` + `deleted_at` en la mayoría de modelos de dominio; ausente en tablas de unión y en `Notification` (ciclo de vida por status).
- **Timestamps**: `created_at` / `updated_at` server-side en todos los modelos.
- **Esquema y seed**: El esquema DEBE ser gestionado por revisiones de Alembic versionadas. El arranque asume que las migraciones ya se aplicaron y se limita a ejecutar `seed_default` idempotente (org "Solercia", 3 dependencias, roles ADMIN/MANAGER/MEMBER, 8 menús, role_menus, admin + 3 usuarios demo, 4 alert rules, proyectos/tareas demo). Existe una revisión baseline Alembic que describe el esquema actual.
- **Config** (pydantic-settings): DATABASE_URL (asyncpg), REDIS_URL (declarado, SIN uso), JWT_*, cookies, CORS (localhost:4200 + devtunnels), UPLOAD_DIR, ALERT_SCHEDULER_INTERVAL_HOURS.

## Requisitos

- **R1**: Toda respuesta exitosa DEBE usar el envelope: `data` siempre presente; `meta` en listas; `message` en acciones.
  - **R1.P1** (Paginación opt-in): Toda respuesta de un endpoint de lista DEBE usar `{"data": [...], "meta": {...}}`. El campo `meta` DEBE incluir siempre `total`. Cuando la petición incluye al menos uno de `{page, size, sort, order}`, DEBE aplicarse paginación offset-based y `meta` DEBE incluir además `page` y `size`. SIN parámetros de paginación = comportamiento actual (colección completa, `meta{total}` únicamente). Aplica a 11 endpoints: tasks, notifications, users, roles, menus, dependencies, projects, sprints, comments, attachments, alert-rules.
  - **R1.P2** (Validación de límites): `page` ≥ 1 (entero), `size` ∈ [1, 100] (configurable por endpoint). Valores inválidos → `422` con envelope `{"detail", "code", "status", "errors"}`.
  - **R1.P3** (Whitelist de sort): Cada endpoint DEBE definir `SORTABLE_FIELDS` (dict de nombres a `InstrumentedAttribute`). `sort` fuera de whitelist → `422`. `order` ∈ {asc, desc}.
  - **R1.A1** (Auditoría creación): Los 11 modelos SoftDeleteMixin DEBEN incluir `created_by` y `updated_by` (UUID nullable, FK→users.id). En `POST`, ambos = usuario autenticado. En `PATCH`, solo `updated_by` se modifica. Filas preexistentes quedan `NULL`.
  - **R1.A2** (Auditoría exposición): Endpoints de detalle y lista de los 11 modelos auditados DEBEN exponer `created_by` y `updated_by` (null cuando no pobladas).
- **R2**: Todo error DEBE serializarse como `{"detail", "code", "status"}` (con `errors` adicional en validaciones 422) a través de `AppException` y los handlers registrados.
- **R3**: El borrado de entidades de dominio DEBE ser suave (`is_active` + `deleted_at`); las consultas DEBEN excluir registros borrados.
- **R4**: `seed_default` DEBE ser idempotente: arranques repetidos no duplican datos.
- **R5**: El esquema de base de datos DEBE originarse y evolucionar mediante revisiones de Alembic versionadas. El arranque asume que las migraciones ya se aplicaron y se limita a ejecutar `seed_default` sobre el esquema ya migrado. `seed_default` NO cambia de comportamiento (sigue siendo idempotente).
- **R6**: Todo cambio de esquema posterior a la línea base DEBE expresarse como una nueva revisión de Alembic generada con `alembic revision --autogenerate`, revisada y versionada junto con el código que la origina.

### Escenarios centrales

**R1 — Envelope de lista**
- Dado cualquier endpoint de lista
- Cuando responde con éxito sin parámetros de paginación
- Entonces el cuerpo es `{"data": [...], "meta": {"total": n}}`.

**R1.P1 — Paginación opt-in**
- Dado un endpoint paginable (tasks, users, etc.)
- Cuando se solicita `?page=2&size=10`
- Entonces se devuelven registros 11-20 con `meta{page: 2, size: 10, total: N}`.

**R1.P2 — Validación de límites de paginación**
- Dado un endpoint paginable
- Cuando se solicita `?page=0` o `?size=101`
- Entonces la API responde `422` con error en envelope.

**R1.P3 — Whitelist de sort**
- Dado un endpoint con whitelist `{title, created_at}`
- Cuando se solicita `?sort=password_hash`
- Entonces la API responde `422`.

**R1.A1 — Auditoría en creación y modificación**
- Dado un usuario `U1` que crea una tarea
- Entonces la tarea tiene `created_by = U1.id` y `updated_by = U1.id`.
- Cuando usuario `U2` la modifica
- Entonces `updated_by = U2.id` y `created_by` sigue siendo `U1.id`.

**R1.A2 — Filas preexistentes sin auditoría**
- Dado un registro creado antes de la migración de auditoría
- Cuando se consulta
- Entonces `created_by` y `updated_by` son `null` y la respuesta no falla.

**R2 — Error tipado**
- Dado una petición por un recurso inexistente
- Cuando el servicio lanza la excepción de dominio
- Entonces el cliente recibe `{"detail": "...", "code": "...", "status": 404}`.

**R4 — Seed idempotente**
- Dado una base de datos ya sembrada
- Cuando la aplicación reinicia
- Entonces `seed_default` no crea duplicados.

**R5 — Inicialización de esquema gestionada por Alembic**
- Dado una base de datos vacía
- Cuando se ejecuta `alembic upgrade head`
- Entonces el esquema resultante es equivalente al que hoy produce `Base.metadata.create_all` (mismas tablas y columnas).

**R5 — El arranque ya no recrea el esquema con create_all**
- Dado un entorno donde las migraciones Alembic ya se aplicaron
- Cuando la aplicación arranca
- Entonces el arranque NO ejecuta `create_all` para definir el esquema; solo corre `seed_default` sobre el esquema ya migrado.

**R6 — Cambio de modelo requiere revisión Alembic**
- Dado un modelo SQLAlchemy modificado (campo o tabla nueva)
- Cuando se ejecuta `alembic revision --autogenerate` contra una BD con el baseline aplicado
- Entonces se genera una revisión no vacía que describe el cambio, lista para revisión de código.

## Limitaciones y deuda conocida

- REDIS_URL declarado y sin uso real.
- ~~SIN paginación~~ → RESUELTO en cambio 02-contrato-api: paginación offset-based opt-in en 11 endpoints, validación de límites, whitelist de sort.
- ~~NO existen `created_by` / `updated_by`~~ → RESUELTO en cambio 02-contrato-api: auditoría automática en 11 modelos SoftDeleteMixin, migración aditiva, exposición en respuestas.
- ~~docs/API.md desactualizado~~ → RESUELTO en cambio 02-contrato-api: refrescado con paginación y auditoría reales, 4 módulos antes no documentados.
- ~~Sin linters ni type-checking~~ → RESUELTO en cambio 01-fundacion-tdd: ruff + mypy adoptados con línea base limpia.

## Referencias

- backend/app/main.py (lifespan, routers, handlers)
- backend/app/shared/ (exceptions.py, base_model.py, pagination-envelope helpers)
- backend/app/db_init.py, backend/app/config.py
- backend/alembic/ (vacío: solo .gitkeep)
