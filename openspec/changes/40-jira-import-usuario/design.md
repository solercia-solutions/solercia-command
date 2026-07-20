# Design: 40 · Importación Jira por usuario (elegir → previsualizar → importar)

## Technical Approach

Se extiende el módulo `jira_import` (hoy solo-lectura) con un **servicio de escritura
transaccional** que reutiliza el pipeline de extracción/normalización del 18 sin
reescribirlo. El adaptador Jira gana `/rest/api/3/project/search` y tres campos en el
DTO (`original_estimate_seconds`, `assignee_email`, `parent_key`). Un `PreviewBuilder`
puro arma conteos + mapeo propuesto sin persistir; un `JiraProjectImporter` crea
Project/Sprint/Task en **una sola transacción por proyecto**, anclando cada entidad a su
clave Jira `(source='jira', external_key)` para reimportación idempotente. La estimación
usa `seconds_to_hours` (34); el estado se homologa leyendo `allowed_statuses()` DESDE la
strategy destino (scrum), nunca con `if methodology==`.

## Architecture Decisions

### D1 — Servicio de escritura propio, transacción única por proyecto

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Reusar `TaskService.create`/`ProjectService.create` por entidad | N verificaciones + posible commit/flush por operación; no atómico por lote; caro | Rechazada |
| Nuevo `JiraProjectImporter` con repositorio propio, 1 transacción, 2 pasadas | Persistencia ORM directa; rollback total ante fallo; el reimport idempotente hace segura la reejecución | **Elegida** |

Seam para el 41: `async def importar_proyecto(connector, jira_project_key, mapping, *, organization_id, session) -> ImportSummary`. El 41 itera proyectos, cada uno en su savepoint con progreso reanudable; el 40 lo llama una vez.

### D2 — Ancla de procedencia: scope por tabla

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `(organization_id, source, external_key)` en las tres tablas | `tasks`/`sprints` NO tienen `organization_id` (scope transitivo por project) → exigiría denormalizar | Rechazada |
| projects: `(organization_id, source, external_key)`; sprints/tasks: `(project_id, source, external_key)` — partial `WHERE external_key IS NOT NULL` | `project_id` ya implica org (CASCADE); evita denormalizar; adapta el precedente `IntakeItem` a cada scope real | **Elegida** |

### D3 — Jerarquía en dos pasadas (misma transacción)

Pasada 1: upsert de todas las tasks sin `parent_task_id`, `flush` para materializar ids +
índice `{external_key → task_id}`. Pasada 2: enlaza `parent_task_id` resolviendo
`parent_key` contra el índice; padre fuera del set → sin padre + nota en el resumen.

### D4 — Estado Jira → estado destino leído de la strategy

El normalizer del 18 ya entrega `status_bucket` (`todo`/`in_progress`/`done`). El importer
lo proyecta al estado destino con `strategy.allowed_statuses()`: `todo → [0]`,
`done → [-1]`, `in_progress → ` estado interior ("In Progress"). Tabla por defecto en el
preview; el usuario puede editar el override antes de confirmar. Cero `if methodology==`.

### D5 — `task_number` atómico por bloque

`UPDATE projects SET task_counter = task_counter + :n RETURNING task_counter` UNA vez por
import (n = tasks nuevas); asignación secuencial desde `counter - n + 1` (extiende el
`allocate_task_number` existente de bloque 1 a bloque n). Reimport: las tasks ancladas
conservan su `task_number`; solo las nuevas consumen contador.

### D6 — Asignado por email

Nuevo `assignee_email` en el DTO (preserva `fields.assignee.emailAddress`; `assignee_raw`
por `accountId` queda intacto para el `Ticket` fino). Match exacto case-insensitive contra
usuarios de los miembros de la org → `assignee_id`; sin match → `null` + nota.

## Data Flow

    GET  /connectors/{id}/jira/projects → JiraClient./project/search → [{key,name}]
    POST /connectors/{id}/jira/preview   → adapter.import_issues (18) → PreviewBuilder(puro)
                                          → conteos + mapeo propuesto  (NO persiste)
    POST /connectors/{id}/jira/import-project → import_issues → JiraProjectImporter (1 txn):
         upsert Project → upsert Sprints → Tasks pass1(sin padre)+flush → pass2(link) → ImportSummary

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/jira/dtos.py` | Modify | +`original_estimate_seconds`, `assignee_email`, `parent_key` en `NormalizedJiraIssue` |
| `app/integrations/adapters/jira/{client,adapter,normalizer}.py` | Modify | `list_projects()`; `_BASE_SEARCH_FIELDS += ("timeoriginalestimate","parent")`; extraer los 3 campos en canonical/`_build_issue` |
| `app/modules/jira_import/{importer,preview,repository}.py` | Create | `JiraProjectImporter` (seam `importar_proyecto`), `PreviewBuilder`, repo de upsert por `external_key` + `allocate_task_numbers(n)` |
| `app/modules/jira_import/{router,schemas,service}.py` | Modify | 3 endpoints + schemas request/response + `ImportSummary` |
| `app/modules/{projects,sprints,tasks}/models.py` | Modify | `source`/`external_key` nullable + índice único parcial |
| `alembic/versions/00XX_add_external_anchor.py` | Create | Columnas + índices únicos parciales (reanclar `down_revision` en apply) |
| `frontend/src/pages/jira-import/*`, `entities/jira-import/*` | Create | Asistente 3 pasos + tipos/servicio |

## Interfaces / Contracts

```python
# NormalizedJiraIssue (+3 campos, frozen dataclass)
original_estimate_seconds: int | None   # timeoriginalestimate (segundos)
assignee_email: str | None              # fields.assignee.emailAddress
parent_key: str | None                  # fields.parent.key (jerarquía)

# Seam reutilizable por el 41
async def importar_proyecto(
    connector, jira_project_key: str, mapping: ImportMapping,
    *, organization_id: uuid.UUID, session: AsyncSession,
) -> ImportSummary:  # creados/actualizados/omitidos + no_homologados + huerfanas + sin_asignar
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `seconds_to_hours` aplicado; bucket→estado vía `allowed_statuses`; two-pass linking + huérfana; extracción de los 3 campos nuevos | funciones/normalizer puros |
| Integration | preview NO persiste; import crea jerarquía + `task_key` + estimación + clave Jira; reimport reconcilia (0 duplicados); asignado por email vs. sin match | `client` + `httpx.MockTransport` (fixtures Jira, patrón 18) |
| Integration | fallo a mitad de import → rollback total (nada persiste); clave Jira inválida en JQL → 422 | `client` + transporte que falla |

## Threat Matrix

Frontera aplicable: integración de procesos (HTTP a Jira) + persistencia transaccional.

| Amenaza | Aplicable | Comportamiento esperado / RED test |
|---------|-----------|-------------------------------------|
| Anti-SSRF (`base_url`) | Sí | Reutiliza `JiraClient` que valida sufijo `JIRA_BASE_URL_ALLOWED_SUFFIX` en el constructor; `/project/search` pasa por el mismo `_get`. Sin nueva superficie |
| Inyección JQL | Sí | `import-project` arma `project = "KEY"`; validar `KEY` contra `^[A-Z][A-Z0-9]+$` antes de construir el JQL. RED test con clave maliciosa |
| Fuga de credenciales | Sí | Fernet `crypto.decrypt` (precedente 18); tokens nunca logueados ni persistidos por el importer |
| Consistencia parcial | Sí | Fallo → rollback total (1 txn); reimport idempotente hace segura la reejecución. RED test de fallo simulado |
| Shell / subprocess / VCS / clasificación de ejecutables | N/A | El cambio no ejecuta procesos ni toca VCS |

## Migration / Rollout

Migración `add_external_anchor`: agrega `source` (varchar) y `external_key` (varchar)
nullable a `projects`/`sprints`/`tasks`, más índices únicos parciales (D2). El
`down_revision` debe **reanclarse al head Alembic REAL en apply** (en disco hoy = `0021`;
34/39 son cero-migración, pero verificar el head efectivo tras 26-39 antes de fijarlo).
Rollback = `alembic downgrade` quita las columnas; las filas importadas son identificables
por `external_key` para limpieza puntual; ningún dato preexistente se altera.

## Open Questions

- [ ] Confirmar en apply el head Alembic real tras 26-39 antes de fijar `down_revision`.
- [ ] Epic link en proyectos company-managed usa un custom field, no `parent`; el MVP
      cubre team-managed/next-gen vía `fields.parent.key`. ¿Resolver el epic-link custom
      field en el 41 (batch admin)?
