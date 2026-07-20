# Briefing de ejecución — OLA 4 (Solercia Project Manager)

## Goal

Revisa el contenido del archivo `openspec/OLA_4.md` y sigue correctamente sus reglas: es la fuente de verdad de esta ola (fases, cambios SDD, decisiones ya aprobadas por el usuario y Definition of Done). Ejecuta la ola completa de forma autónoma, sin pedir aprobaciones intermedias salvo lo marcado como pendiente en ese documento.

## Rol

Eres el orquestador: coordinas y delegas en subagentes (exploración, escritura, pruebas); no ejecutas todo en un solo hilo. Trabajas de forma autónoma y no paras hasta cumplir la Definition of Done de la sección 7 de `OLA_4.md`.

## Reglas de ejecución (resumen operativo — el detalle vive en OLA_4.md)

1. **Orden de fases**: 4.1 (multi-empresa backend) → 4.2 (backlog estilo Jira) → 4.3 (vista de jefe y proyectos) → 4.4 (conexiones). La fase 4.5 solo si el usuario la confirma.
2. **SDD por cambio**: cada cambio sigue `explore → propose → spec → design → tasks → apply → verify → archive` en `openspec/changes/`. Verifica el consecutivo real en `openspec/changes/archive/` antes de crear cada cambio.
3. **TDD estricto**: prueba primero, implementación mínima, refactor. Suite backend in-process (pytest + httpx AsyncClient/ASGI). Mínimo por endpoint: happy path + error + permisos.
4. **Ramas**: feature branch por cambio partiendo de `preview`; merge a `preview` al cerrar su ciclo con verificación. NUNCA tocar `main`.
5. **Commits**: convencionales en español, sin atribución de IA, staging selectivo.
6. **Patrones**: Repository, Strategy (prohibido `if methodology == ...`), soft delete, auditoría, scoping por `organization_id`, respuestas `{data, message, meta}`. Textos de UI en español colombiano formal (tuteo), nunca voseo.
7. **Entorno local**: usa `./gestion.sh` (on/off/status/logs/rebuild). Front en el host `:4242` con recarga en caliente; backend Docker en `:8081` — tras cambiar código backend ejecuta `./gestion.sh rebuild`. Postgres `:5432`, Redis `:6379`.
8. **Seguridad**: el token de Jira de `/Users/camilocalderont/Proyectos/PERSONAL/AUTOMATINFORMES/.env` jamás se copia al repositorio ni a commits; se registra vía UI de Conexiones o `.env` local y se cifra con `INTEGRATIONS_FERNET_KEY` (sección 5 de OLA_4.md).

## Al terminar (obligatorio)

1. Suite backend completa en verde y migraciones aplicadas.
2. Actualiza la guía de prueba de la ola.
3. Ejecuta `./gestion.sh restart`, verifica front y backend en 200 y **reporta la URL del túnel devtunnel** (sale en `./gestion.sh status`) para que el usuario pruebe desde el celular.
4. Entrega un resumen final: cambios archivados, decisiones tomadas, pendientes y cómo probar cada bloque.
