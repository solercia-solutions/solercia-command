# Design: 41 · Importación Jira modo administrador (sitio completo, por lotes y reanudable)

## Technical Approach

El 41 añade una capa de **orquestación por lotes** sobre el seam
`importar_proyecto(connector, jira_project_key, mapping, *, organization_id, session)`
que expone el 40 — no reescribe persistencia ni idempotencia. Un endpoint admin-only crea un
`ImportJob` (header) con una fila `ImportJobProject` (`pending`) por proyecto seleccionado; el
procesamiento corre en segundo plano vía `asyncio.create_task` recorriendo proyecto por proyecto,
invocando el pipeline del 40 con `project = "KEY"` y **commit por proyecto**. El estado persistido
por proyecto hace la reanudación trivial: reintentar reprocesa solo `pending`/`failed` (los `done`
se saltan; la idempotencia por `external_key` del 40 evita duplicados). Un **heartbeat** en el
header más un **reaper** periódico (job en el `AsyncIOScheduler` que ya arranca la lifespan, patrón
de `reminders`/`email`) detectan jobs `running` huérfanos tras un reinicio y los marcan
`interrupted` (reanudables). La UI hace polling de `GET .../admin-import/jobs/{id}`. Reúsa
`connectors` (credenciales Fernet, `settings.base_url`); el token nunca sale cifrado.

## Architecture Decisions

### D1 — Runner en segundo plano: `asyncio.create_task` con sesión propia

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| APScheduler job inmediato (`next_run_time=now`) | MemoryJobStore no sobrevive reinicio → sin ventaja de reanudación; añade acoplamiento al job store | Rechazada |
| Worker/Celery dedicado | Infra nueva (broker, proceso) para un caso admin ocasional | Rechazada (overkill) |
| `asyncio.create_task` en el loop vivo, abre su **propia** `AsyncSessionLocal()` | Muere si el proceso reinicia — cubierto por heartbeat+reaper+resume; cero infra nueva | **Elegida** |

El request encola la tarea y responde `202` de inmediato. La tarea NO usa la sesión del request
(`get_db` cierra al terminar el request): abre su sesión como los jobs del scheduler.

### D2 — Detección de huérfanos: heartbeat ticker + reaper periódico

Un `running` cuyo proceso murió queda "colgado". La tarea corre un **heartbeat ticker** concurrente
que toca `import_jobs.heartbeat_at` cada `IMPORT_JOB_HEARTBEAT_INTERVAL_SECONDS` (en su propia
sesión corta), desacoplando la liveness de la duración de un proyecto grande. Un job periódico
(`register_import_reaper_job(scheduler)` en la lifespan) marca `running → interrupted` cuando
`heartbeat_at < now - IMPORT_JOB_HEARTBEAT_TIMEOUT_SECONDS`. `interrupted` es reanudable.

### D3 — Modelo de jobs y "un activo por conector"

| Tabla | Claves / columnas | Nota |
|-------|-------------------|------|
| `import_jobs` | `PkMixin, TimestampMixin, TenantMixin, AuditMixin`; `connector_id` (FK CASCADE), `status` (`pending/running/done/partial/failed/interrupted`), `heartbeat_at?`, `started_at?`, `finished_at?`, `projects_total/projects_done/projects_failed` | header agregado |
| `import_job_projects` | `job_id` (FK CASCADE), `jira_project_key`, `status` (`pending/running/done/failed`), `sprints_created/sprints_updated/tasks_created/tasks_updated/tasks_skipped`, `error_detail?`, `truncated`; UNIQUE `(job_id, jira_project_key)` | detalle por proyecto |

Índice único parcial `uq_import_jobs_active_per_connector` sobre `(connector_id) WHERE status IN
('pending','running')`: un segundo job activo → `409`. `interrupted`/`failed` quedan fuera del set
activo, así el resume (`interrupted→running`) y un job nuevo tras rendirse no chocan.

### D4 — Pipeline por proyecto: transacción por proyecto reusando el 40

El runner llama `importar_proyecto(...)` una vez por `KEY`, cada uno con su commit (savepoint del
40 → **reanudable**). Un fallo en un proyecto captura la excepción, hace `rollback` de ESE proyecto,
persiste `import_job_projects.status='failed'` + `error_detail` (mensaje corto, nunca token/traza
sensible) y **continúa** con el siguiente. `ImportSummary` del 40 se mapea a los contadores por
proyecto. `KEY` se valida contra `^[A-Z][A-Z0-9]+$` antes de construir el JQL (guard del 40).

### D5 — Descubrimiento: extensión del `JiraClient` (Agile API)

Nuevos métodos por el mismo `_get` (anti-SSRF, backoff 429, timeout): `list_projects()` →
`/rest/api/3/project/search` (excluye archivados: `status=live`); `list_boards()`/`list_sprints()`
→ `/rest/agile/1.0/board` y `/board/{id}/sprint`, que paginan por **offset** (`startAt/maxResults/
isLast`), no por `nextPageToken` → helper de paginación offset acotado por `JIRA_MAX_PAGES`. Los
conteos de issues por tipo son **best-effort** (JQL `approximate-count` por proyecto); tableros/
sprints salen de la paginación Agile. El import autoritativo lo hace el 40 por proyecto.

### D6 — Endpoints, RBAC y polling

RBAC `require_role(MemberRole.admin)` (solo admin, radio de impacto del sitio completo). Envoltura
`{data, message, meta}`. Scoping multi-tenant por `organization_id`.

## Data Flow

    POST /connectors/{id}/admin-import/discover → JiraClient.list_projects/boards/sprints
         → [{key,name,boards,sprints,counts(best-effort)}]   (no persiste)
    POST /connectors/{id}/admin-import/jobs {project_keys[]} → ImportJob(pending)+N proyectos(pending)
         → asyncio.create_task(runner) → 202
    runner (sesión propia): [heartbeat ticker] ‖ por KEY → importar_proyecto(40) → commit proyecto
         → update ImportJobProject → pausa IMPORT_PROJECT_PAUSE_SECONDS → ... → status header final
    GET  /admin-import/jobs/{id}         → header + detalle por proyecto (polling)
    POST /admin-import/jobs/{id}/resume  → reset running→pending; reprocesa pending/failed → 202
    [scheduler] reaper: running con heartbeat vencido → interrupted

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/jira_import/models.py` | Create | `ImportJob` + `ImportJobProject` (estado + contadores + índice parcial) |
| `app/modules/jira_import/repository.py` | Create | CRUD de jobs, upsert por proyecto, reaper query, guard activo-por-conector |
| `app/modules/jira_import/runner.py` | Create | Runner `asyncio.create_task`, heartbeat ticker, bucle por proyecto sobre el seam del 40 |
| `app/modules/jira_import/{router,schemas,service}.py` | Modify | 4 endpoints admin + schemas discover/job/detalle; orquestación |
| `app/integrations/adapters/jira/client.py` | Modify | `list_projects/list_boards/list_sprints` (+ paginación offset Agile) |
| `app/reminders/scheduler.py`-style `app/jira_import/reaper.py` | Create | `register_import_reaper_job(scheduler)`, registrado en la lifespan |
| `app/main.py` | Modify | Registrar el reaper en el mismo `AsyncIOScheduler` |
| `app/config.py` | Modify | `IMPORT_JOB_HEARTBEAT_INTERVAL_SECONDS`, `_TIMEOUT_SECONDS`, `IMPORT_REAPER_INTERVAL_SECONDS`, `IMPORT_PROJECT_PAUSE_SECONDS` |
| `alembic/versions/00XX_add_import_jobs.py` | Create | Tablas + índice parcial; `down_revision` reanclado al head que deja el 40 |
| `frontend/src/features/.../connectors/*` | Modify | Descubrimiento, selección múltiple + "seleccionar todo", panel de progreso por polling |

## Interfaces / Contracts

```python
# JiraClient (nuevos, mismo _get)
async def list_projects(self, *, include_archived: bool = False) -> list[dict]  # /project/search status=live
async def list_boards(self) -> list[dict]                                        # /rest/agile/1.0/board (offset)
async def list_sprints(self, board_id: int) -> list[dict]                        # /board/{id}/sprint (offset)

# Runner (seam del 40 por proyecto)
async def run_import_job(job_id: uuid.UUID) -> None   # abre AsyncSessionLocal propia; heartbeat ‖ bucle
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | transición de estados header/proyecto; mapeo `ImportSummary`→contadores; reaper marca `interrupted` por heartbeat vencido | funciones puras + reloj inyectado |
| Integration | discover lista proyectos/tableros/sprints con paginación offset; `list_projects` excluye archivados | `JiraClient` + `httpx.MockTransport` |
| Integration | crear job encola N proyectos; runner procesa secuencial y persiste contadores; fallo en un proyecto → `failed` y el lote continúa | seam del 40 mockeado + BD |
| Integration | resume reprocesa solo `pending`/`failed`, salta `done`, sin duplicar; segundo job activo → `409`; RBAC no-admin → `403`; conector ajeno → `404` | AsyncClient + BD |

## Threat Matrix

Frontera aplicable: integración de procesos (HTTP a Jira) + ejecución en segundo plano + persistencia.

| Amenaza | Aplicable | Comportamiento esperado / RED test |
|---------|-----------|-------------------------------------|
| Anti-SSRF (`base_url`) | Sí | Nuevos métodos pasan por el mismo `_get`/constructor validado (sufijo `.atlassian.net`). Sin nueva superficie |
| Inyección JQL | Sí | `run_import_job` arma `project = "KEY"`; validar `KEY` con `^[A-Z][A-Z0-9]+$` antes del JQL. RED test con clave maliciosa |
| Fuga del token | Sí | Fernet `crypto.decrypt`; `error_detail` sanitizado; token nunca logueado/persistido/en repo. RED test: token no aparece en respuesta ni logs |
| Consistencia parcial | Sí | Commit por proyecto + fallo aislado; reanudación idempotente por `external_key` (40). RED test: fallo a mitad → reanuda sin duplicar |
| Carrera / doble job | Sí | Índice único parcial `(connector_id) WHERE status IN ('pending','running')` → `409`. RED test de doble creación |
| Ejecución huérfana | Sí | Heartbeat + reaper marca `running`→`interrupted` reanudable. RED test: heartbeat vencido → `interrupted` |
| Shell / subprocess / VCS / clasificación de ejecutables | N/A | El cambio no ejecuta procesos ni toca VCS |

## Migration / Rollout

Migración `add_import_jobs`: crea `import_jobs` + `import_job_projects` con el índice único parcial.
El `down_revision` debe **reanclarse en apply al head Alembic REAL que deje el 40**
(`add_external_anchor`); el gating ya exige apply+verify+archive del 40 antes del apply del 41.
`downgrade` elimina ambas tablas — son solo metadatos de proceso; las entidades ya importadas
(idempotentes) permanecen sin datos huérfanos.

## Open Questions

- [ ] Confirmar en apply el head real que deja el 40 antes de fijar `down_revision`.
- [ ] Exactitud de conteos en discover: ¿best-effort (`approximate-count`) es suficiente para el MVP
      o la entidad exige conteos exactos por tipo de issue?
- [ ] Timeout de heartbeat vs. proyecto muy grande: el ticker desacopla liveness, pero validar que
      `IMPORT_JOB_HEARTBEAT_TIMEOUT_SECONDS` cubre pausas de red largas sin falsos `interrupted`.
