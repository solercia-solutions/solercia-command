# Spec — Archivos adjuntos (attachments)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Adjuntos sobre tareas y comentarios, con almacenamiento en disco local, nombre almacenado único, límite de tamaño, bloqueo de ejecutables y descarga autenticada.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET/POST | /api/v1/tasks/{id}/attachments | Lista y carga de adjuntos de una tarea |
| GET/POST | /api/v1/comments/{id}/attachments | Lista y carga de adjuntos de un comentario |
| GET | /api/v1/attachments/{id}/download | Descarga autenticada |

Modelo `Attachment` (Pk + Timestamp + SoftDelete + Tenant):

| Campo | Descripción |
|-------|-------------|
| target_type, target_id | Polimórfico: task \| comment |
| original_name | Nombre original del archivo |
| stored_name | Nombre en disco (uuid único) |
| content_type, size_bytes | Metadatos |
| uploaded_by | Usuario que cargó el archivo |

Almacenamiento: disco local bajo `UPLOAD_DIR` (por defecto `./uploads`).

## Requisitos

- **R1**: Cada archivo DEBE guardarse con un `stored_name` único (uuid), conservando `original_name` para la descarga.
- **R2**: La carga DEBE rechazar archivos que excedan el límite de tamaño configurado.
- **R3**: La carga DEBE bloquear archivos ejecutables.
- **R4**: La descarga DEBE exigir autenticación; no hay URLs públicas.

### Escenarios centrales

**R1 — Carga y descarga**
- Dado una tarea existente
- Cuando se carga `informe.pdf`
- Entonces queda en disco con nombre uuid y `GET /attachments/{id}/download` lo devuelve con su nombre original.

**R3 — Ejecutable bloqueado**
- Dado un intento de carga de `script.exe`
- Cuando se envía a `POST /tasks/{id}/attachments`
- Entonces la API rechaza el archivo.

**R4 — Descarga autenticada**
- Dado un adjunto existente
- Cuando se solicita la descarga sin token válido
- Entonces la petición es rechazada.

## Limitaciones y deuda conocida

- Almacenamiento en disco local: no apto para múltiples réplicas ni contenedores efímeros (sin S3/objeto).
- Sin límites de cuota por organización ni escaneo antivirus.
- Sin paginación en listas.
- Cobertura: test_attachments (5 tests). Sin tests de permisos.

## Referencias

- backend/app/modules/attachments/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/config.py (UPLOAD_DIR)
- backend/tests/test_attachments.py
