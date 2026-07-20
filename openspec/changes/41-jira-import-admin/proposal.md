# Proposal: 41 · Importación Jira modo administrador (sitio completo, por lotes y reanudable)

## Intent

El cambio 40 importa proyecto(s) elegidos con la cuenta de un usuario. Con credenciales de admin del sitio Jira, la entidad necesita traer TODO el sitio de una sola operación: todos los proyectos, tableros y sprints históricos. Viabilidad PROBADA el 2026-07-20 contra `idartes-tecnologia.atlassian.net` (`ADMINISTER: True`, 36 proyectos, 31 tableros, sprints desde 2021). Un import de esa escala es largo y frágil: si falla a mitad no puede reiniciarse desde cero ni duplicar. Este cambio añade descubrimiento masivo, selección múltiple, cola por lotes con estado persistido, reanudación idempotente y progreso visible — sobre el pipeline de persistencia del 40.

## Scope

### In Scope
- Descubrimiento masivo: listar TODOS los proyectos del sitio con conteos (épicas/historias/subtareas/sprints, tableros) vía nuevos métodos del `JiraClient` (project/board/sprint search).
- Selección múltiple con "seleccionar todo" en la UI de Conexiones.
- Cola de importación por lotes: nueva persistencia `import_jobs` (header) + `import_job_projects` (detalle) con estado por proyecto (`pending/running/done/failed`) y contadores de entidades importadas.
- Reanudación: reintentar un job procesa solo proyectos `pending/failed`; los `done` se saltan. Sin duplicar (idempotencia del 40 por clave Jira).
- Progreso visible: `GET .../import-jobs/{id}` con detalle por proyecto; la UI hace polling.
- Throttling básico: proceso proyecto-por-proyecto reutilizando el backoff 429 del cliente.

### Out of Scope
- El pipeline de persistencia proyecto→sprints→tareas (lo aporta el 40; 41 lo invoca).
- Push por WebSocket del progreso (el módulo `realtime` está acoplado a notificaciones; se difiere, polling primero).
- Lenguaje tipo JQL y sincronización incremental recurrente (visión futura).
- Importación desde Microsoft/Google.

## Capabilities

### New Capabilities
- `jira-import-admin`: descubrimiento del sitio completo + orquestación de import por lotes reanudable con estado persistido (`import_jobs`) y progreso consultable.

### Modified Capabilities
None (el pipeline de persistencia y la idempotencia por clave Jira los define el cambio 40; 41 los consume).

## Approach

`POST .../jira/import-jobs {project_keys[]}` crea el job (`pending`) y encola su procesamiento en segundo plano; un runner recorre proyecto por proyecto llamando al pipeline del 40 (JQL `project = <KEY>`), y persiste avance/contadores/errores en `import_job_projects` tras cada proyecto (commit por proyecto → reanudable). Reintentar el mismo job reprocesa solo `pending/failed`. La UI hace polling de `GET .../import-jobs/{id}`. Credenciales del sitio: se registran por la UI de Conexiones (`POST /connectors/{id}/credentials`) o `.env` local del backend y se persisten cifradas con `INTEGRATIONS_FERNET_KEY`; el token JAMÁS entra al repositorio ni a commits (reúsa `connectors`).

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/jira_import/*` | Modified | Endpoints de descubrimiento y de jobs, service de orquestación por lotes |
| `backend/app/modules/jira_import/models.py` | New | `ImportJob` + `ImportJobProject` (estado + contadores) |
| `backend/app/integrations/adapters/jira/client.py` | Modified | `list_projects/list_boards/list_sprints` con conteos |
| `backend/alembic/` | New | Migración de las tablas de jobs |
| `frontend/src/features/.../connectors` | Modified | Descubrimiento, selección múltiple, panel de progreso |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Import largo excede timeout HTTP | Alta | Ejecución en segundo plano; commit por proyecto; progreso por polling |
| Rate limit de Jira en sitio grande | Media | Proyecto-por-proyecto secuencial + backoff 429 existente + throttling |
| `JIRA_MAX_PAGES=20` trunca proyectos enormes | Media | Config elevable por sitio; marcar `truncated` en el detalle |
| 40 sin aplicar → sin pipeline de persistencia | Alta | Gating: apply del 41 tras apply+verify del 40 |
| Fuga del token del sitio | Alta | Cifrado Fernet reusado; nunca en repo/commits/logs |

## Rollback Plan

Revertir commits de módulo/adapter/frontend y bajar la migración (`downgrade` elimina `import_jobs`/`import_job_projects`). Las entidades ya importadas quedan (idempotentes); no requieren reversa. Sin datos huérfanos: los jobs son metadatos de proceso.

## Dependencies

- `40-jira-import-usuario`: pipeline de persistencia proyecto→sprints→tareas e idempotencia por clave Jira original.
- `connectors` (archivado): cifrado Fernet de credenciales, `settings.base_url`, RBAC.
- `18-adapter-jira` (archivado): `JiraClient` (anti-SSRF, backoff 429, paginación) que se extiende.

## Success Criteria

- [ ] El descubrimiento lista todos los proyectos del sitio con conteos.
- [ ] "Seleccionar todo" encola un job con todos los proyectos.
- [ ] Un job interrumpido se reanuda sin duplicar (solo `pending/failed`).
- [ ] La UI muestra progreso por proyecto (estado + contadores) por polling.
- [ ] El token nunca aparece en repo, commits ni logs; se persiste cifrado.
- [ ] TDD: descubrimiento, orquestación, reanudación y throttling con mocks (`httpx.MockTransport`).

## Proposal question round

Estas preguntas buscan afinar reglas de negocio del PRD antes de fijar el spec. Supuestos por validar:
1. **RBAC**: ¿el import masivo del sitio queda restringido a `admin` (más conservador por el radio de impacto) o se permite también `manager` como en el 40? Supuesto: solo `admin`.
2. **Concurrencia**: ¿procesar proyecto-por-proyecto estrictamente secuencial (más amable con el rate limit) o permitir concurrencia acotada (2–3) configurable? Supuesto: secuencial.
3. **Un job activo por conector**: ¿se bloquea lanzar un segundo job mientras uno corre para el mismo conector (evita carreras y duplicados)? Supuesto: sí, uno activo por conector.
4. **Alcance del sitio**: ¿"todo el sitio" incluye proyectos archivados/inactivos de Jira o solo los activos? Supuesto: solo activos, con filtro opcional.
5. **Progreso**: ¿polling es aceptable para el MVP (WebSocket diferido) o se requiere push en tiempo real desde ya? Supuesto: polling.

Segunda ronda disponible para revisar el modelo de ejecución en segundo plano (runner asyncio vs. APScheduler) o el detalle de contadores por entidad.
