# Design: 22 · Clasificador de insumos (almacenamiento + reglas tema→respondiente + correo→tarea)

## Technical Approach

Un módulo `app/modules/intake/` con el patrón `router → service → repository` (idéntico a `assets`/`connectors`) y un **motor de reglas puro** en `classifier.py`. El servicio orquesta el ciclo pull→normalización→upsert idempotente→clasificación→conversión, leyendo insumos por los **puertos del 14** (`adapter.port_for(cap).list_*(ctx)`) para operar contra el `fake` en TDD y contra 15–19 sin acople. La conversión a tarea usa el **service real** `TaskService.create_task` (nunca SQL); el proyecto por defecto se resuelve con `ProjectService.create_project` (metodología `planner`). El sink `on_tokens_refreshed` se implementa aquí y persiste credenciales rotadas por el repositorio de `connectors` (Fernet): el 22 **materializa** la persistencia — la Open Question genérica de renovación de tokens es del 14, y la expectativa específica del sink es del 15 (declarada como contrato sin confirmar), que el 14 NO garantiza (ver Open Questions). Backend-only, tenant-scoped, TDD estricto.

## Architecture Decisions

| Decisión | Elegida | Alternativa rechazada | Rationale |
|----------|---------|-----------------------|-----------|
| Motor de reglas | `ClassifierPort` (Protocol/Strategy) + `RuleBasedClassifier` puro, sin BD ni HTTP | Lógica en el `service` con `if` | Precedente `app/methodology/`; función pura → determinista y unit-testable; puerta a `LLMClassifier` sin reescribir |
| Trazabilidad | Columnas en `intake_items` (`status`, `matched_rule_id`, `created_task_id`, `classified_at`) | Tabla `intake_classifications` aparte | Una clasificación por ítem (primera coincidencia MVP); trace tarea→ítem→regla directo sin join extra |
| Criterios de regla | `criteria JSONB` (lista `{field, operator, value}`, AND) evaluada por matcher puro | Columnas explícitas por criterio | Extensible (campos del spec intake-rules: `origin_actor`/dominio/keywords en título·snippet/`source_provider`/`connector_id`) sin migración por criterio; matcher aislado testeable |
| Matching de texto | `unicodedata.NFKD` + `casefold` (sin tildes, case-insensitive), **stdlib** | Dependencia `unidecode` | Cero dependencia nueva; folding determinista reproducible en tests |
| Ejecución | Pull + clasificación **síncronos** en el request, acotados por `limit`/`MAX_PAGES` | Job/cola async | Precedente 17 (import manual on-demand acotado); scheduler = futuro |
| Conversión | `TaskService.create_task(...)` | INSERT directo a `tasks` | Respeta strategy/board/estimación/auditoría; la tarea nace normal y editable |
| Respondiente no elegible | Si `rule.assignee_id` no es miembro de la org → ítem queda **pending** (triage), no auto-agrega | Agregar como miembro / fallar 422 | Conservador: `create_task._verify_assignee` exige `is_org_member`; no mutamos membresías desde intake |

## Data Flow

```
POST /intake/pull (require_role admin|manager) → abre IntakeRun
  por cuenta conectada:
    expires_at vencido → adapter.refresh → on_tokens_refreshed(sink) → ConnectorRepo.save_credentials (Fernet)
    adapter.port_for(cap).list_*(ctx, limit) → DTOs del 14
    repo.upsert_item  [UNIQUE(org, connector_id, external_id)] → cuenta nuevos/duplicados
    RuleBasedClassifier.classify(item, active_rules ORDER BY rule_order):
      primera regla que casa & convert_to_task →
        ensure_project(rule.target_project_id | default get-or-create) →
        TaskService.create_task(project, title, desc=snippet+origen, priority, assignee_id) →
        item.status=converted, created_task_id, matched_rule_id, classified_at
      sin regla / assignee no elegible → item.status=pending (cola de triage)
  cierra IntakeRun con conteos
POST /intake/items/{id}/convert (triage manual) → create_task en proyecto default
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/intake/{__init__,models,schemas,repository,service,router}.py` | Create | 4 modelos + CRUD reglas + pull + convert; org-scoped; RBAC |
| `app/modules/intake/classifier.py` | Create | `ClassifierPort` + `RuleBasedClassifier` + matcher puro (`unicodedata`) |
| `app/modules/connectors/repository.py` | Modify | Persistir credenciales rotadas tras refresh (sink); sin tocar CRUD ni frontera solo-lectura |
| `app/main.py`, `app/db_init.py` | Modify | `include_router(intake_router)` + registrar modelos en metadata |
| `app/config.py` | Modify | `INTAKE_DEFAULT_PROJECT_NAME="Tareas Outlook"`, `INTAKE_PULL_MAX_ITEMS` (patrón `EMAIL_*`) |
| `alembic/versions/00NN_add_intake.py` | Create | 4 tablas, `down_revision`=head vivo, downgrade inverso |
| `docs/diagrams/er-model.md`, `docs/diagrams/c4-architecture.md` | Modify | Tablas nuevas + módulo `intake` en C3 (mismo commit) |

## Interfaces / Contracts

```python
class ClassifierPort(Protocol):
    def classify(self, item: IntakeItem, rules: Sequence[IntakeRule]) -> IntakeRule | None: ...

# criteria JSONB: [{"field": "origin_actor|domain|title|snippet|source_provider|connector_id",
#                   "operator": "equals|contains|in", "value": "..."}]  (AND intra-regla)
```

Tablas (mixins de `app/shared/base_model.py`):

| Tabla | Mixins | Unicidad |
|-------|--------|----------|
| `intake_items` | Pk+Timestamp+SoftDelete+Audit+Tenant | `UNIQUE(organization_id, connector_id, external_id)` |
| `intake_rules` | Pk+Timestamp+SoftDelete+Audit+Tenant | — (orden por `rule_order`) |
| `intake_runs` | Pk+Timestamp+Audit+Tenant | — |
| `intake_settings` | Pk+Timestamp+Tenant | `UNIQUE(organization_id)` |

`status` como `str, Enum` `native_enum=False` (precedente enums del repo): `pending/converted/ignored/error`.

## Testing Strategy (TDD estricto)

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | Matcher: casa / no casa / prioridad (primera gana); folding sin tildes + case-insensitive; `convert_to_task=false` no crea tarea | pytest sin BD, `RuleBasedClassifier` puro |
| Unit | Sink `on_tokens_refreshed` → `save_credentials` cifra y persiste; token jamás en logs | fake tokens + repo stub |
| Integration | Re-pull idempotente (sin duplicar ítem ni tarea; guardia `created_task_id`); conversión con default get-or-create (`planner`, una sola vez/org); triage (sin regla → pending) + convert manual; assignee no miembro → pending | `client` ASGI + adaptador `fake` + fixtures 01/02 |
| Integration | RBAC `require_role(admin, manager)` en `/intake/pull` (member/viewer → 403); aislamiento multi-tenant (ítems/reglas de org A invisibles a B) | `two_orgs` |
| Migration | `upgrade` crea 4 tablas + unique; `downgrade` inverso limpio; `alembic check` sin diff | BD `solercia_test_migrations` |

## Threat Matrix

N/A para los ejes formales (routing dinámico, shell, subprocess, automatización VCS/PR, clasificación de ejecutables, integración de procesos): 22 no ejecuta procesos ni resuelve rutas; la egress de red vive en los adaptadores 15–19, 22 opera por la abstracción de puertos y el `fake`. Los riesgos de seguridad propios NO se omiten y se cubren con RED tests: cifrado de credenciales rotadas (`access_token_enc != plaintext`), sin fuga de tokens en logs/respuestas, aislamiento multi-tenant por `organization_id` en cada query.

## Migration / Rollout

Aditiva. `down_revision` = **head vivo verificado en el apply** (los applies van serializados por repositorio; 22 es el último): hoy el head en disco es `0014_add_project_parent_id` (21) y 14 renumera su `0014_add_connectors` sobre él → 22 encadena al head resultante (previsto `00NN` posterior a 14+21). `upgrade()` crea las 4 tablas; `downgrade()` elimina en orden inverso (`intake_settings`→`intake_runs`→`intake_rules`→`intake_items`). Sin adaptadores reales el pull queda inerte (opera contra `fake`). Rollback = revertir merge + `downgrade`; las `Task` creadas permanecen normales, `created_task_id` queda huérfano pero autónomo; el sink se retira quitando la llamada de persistencia en `connectors/repository.py`.

## Open Questions

- [x] Ítems sin regla → triage manual (ratificado). Sink de tokens → lo materializa 22 (ratificado).
- [ ] `AccessContext.on_tokens_refreshed` NO está garantizado por el 14 (su design no lo define; el 15 lo declaró como expectativa sin confirmar). Si al aplicar el 22 el campo no existe, este cambio DEBE extender `app/integrations/` primero (delta aditivo propio que exponga el sink) antes de cablearlo — no se asume presente.
- [ ] Cifrado de `raw_payload` (PII de cuerpos): fuera de alcance, deuda documentada (tenant-scoped + soft delete mitigan).
- [ ] Coordinación con 23 (`_create_project_unit`): se usa el público `ProjectService.create_project`; si 23 aterriza primero, migrar la llamada al helper extraído (no bloquea).
