# Spec — Convenciones de API y plataforma (api-conventions)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Contrato transversal del backend: envelope de respuestas, formato de errores, soft delete, timestamps, inicialización de esquema y seed, y configuración por entorno.

## Alcance as-built

- Routers bajo `/api/v1`. PKs UUID en todos los modelos.
- **Envelope**: listas `{"data": [...], "meta": {"total": n}}`; recurso único `{"data": {...}}`; acciones `{"data": ..., "message": "..."}`.
- **Errores**: `{"detail", "code", "status"}` (+ `errors` en 422), vía `AppException` + `register_exception_handlers`. Mensajes en español colombiano.
- **Soft delete**: `is_active` + `deleted_at` en la mayoría de modelos de dominio; ausente en tablas de unión y en `Notification` (ciclo de vida por status).
- **Timestamps**: `created_at` / `updated_at` server-side en todos los modelos.
- **Esquema y seed**: en startup, `db_init.init_db` crea el esquema con `Base.metadata.create_all` y ejecuta `seed_default` idempotente (org "Solercia", 3 dependencias, roles ADMIN/MANAGER/MEMBER, 8 menús, role_menus, admin + 3 usuarios demo, 4 alert rules, proyectos/tareas demo). CERO revisiones Alembic (solo .gitkeep).
- **Config** (pydantic-settings): DATABASE_URL (asyncpg), REDIS_URL (declarado, SIN uso), JWT_*, cookies, CORS (localhost:4200 + devtunnels), UPLOAD_DIR, ALERT_SCHEDULER_INTERVAL_HOURS.

## Requisitos

- **R1**: Toda respuesta exitosa DEBE usar el envelope: `data` siempre presente; `meta` en listas; `message` en acciones.
- **R2**: Todo error DEBE serializarse como `{"detail", "code", "status"}` (con `errors` adicional en validaciones 422) a través de `AppException` y los handlers registrados.
- **R3**: El borrado de entidades de dominio DEBE ser suave (`is_active` + `deleted_at`); las consultas DEBEN excluir registros borrados.
- **R4**: `seed_default` DEBE ser idempotente: arranques repetidos no duplican datos.

### Escenarios centrales

**R1 — Envelope de lista**
- Dado cualquier endpoint de lista
- Cuando responde con éxito
- Entonces el cuerpo es `{"data": [...], "meta": {"total": n}}`.

**R2 — Error tipado**
- Dado una petición por un recurso inexistente
- Cuando el servicio lanza la excepción de dominio
- Entonces el cliente recibe `{"detail": "...", "code": "...", "status": 404}`.

**R4 — Seed idempotente**
- Dado una base de datos ya sembrada
- Cuando la aplicación reinicia
- Entonces `seed_default` no crea duplicados.

## Limitaciones y deuda conocida

- SIN paginación: las listas devuelven todo y `meta.total = len` (el contrato `?page&size&sort&order` del CLAUDE.md no existe).
- NO existen `created_by` / `updated_by` (auditoría del CLAUDE.md sin implementar).
- Esquema por `create_all` en startup: Alembic instalado pero sin ninguna revisión — no hay camino de migraciones.
- REDIS_URL declarado y sin uso real.
- docs/API.md desactualizado: no lista comments, attachments, notifications, alert-rules, by-key, subtasks, velocity ni close.
- Sin linters ni type-checking (ruff/mypy ausentes).

## Referencias

- backend/app/main.py (lifespan, routers, handlers)
- backend/app/shared/ (exceptions.py, base_model.py, pagination-envelope helpers)
- backend/app/db_init.py, backend/app/config.py
- backend/alembic/ (vacío: solo .gitkeep)
