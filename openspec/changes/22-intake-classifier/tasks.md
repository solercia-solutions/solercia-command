# Tasks: 22 · Clasificador de insumos (almacenamiento + reglas tema→respondiente + correo→tarea)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~2.500–2.700 (producción ~1.250: modelos ~180, schemas ~150, repository ~200, service ~220, router ~150, `classifier.py` ~120, sink en `connectors/repository.py` ~40, config ~10, migración ~90, docs ER/C4 ~50, delta condicional `app/integrations/` ~30; **pruebas TDD ~1.300**: migración, matcher puro, ingesta/idempotencia, endpoints de ítems/reglas/clasificador, sink de credenciales, multi-tenant/RBAC) |
| 400-line budget risk | **High** (4 capacidades — 3 nuevas + 1 delta — más un posible delta condicional en `app/integrations/`; ningún lote individual debería superar ~450 líneas si se respeta la partición de abajo) |
| Chained PRs recommended | Yes (adaptado: sin PRs nuevos — commits secuenciales sobre `feat/consume-solercia-ui`) |
| Estrategia de entrega | Commits convencionales directos a la rama actual, un commit por lote; `size:exception` ya aceptada por el orquestador (`delivery_strategy: exception-ok`) |
| Estrategia de encadenado | stacked-to-main (adaptada a commits directos, sin abrir PRs) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota**: `exception-ok` cubre el excedente sobre 400 líneas a nivel de la entrega completa; la partición en 7 lotes (0-bis condicional + 1..6) es igualmente obligatoria por `work-unit-commits` para mantener cada commit revisable (~≤60 min) y con rollback independiente. Este cambio es el ÚLTIMO apply de la serie: 14 (`app/integrations/`, `connectors`) y 21 (jerarquía de proyectos) deben estar aplicados antes de iniciar la Fase 1.

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 0-bis (condicional) | Delta aditivo a `app/integrations/`: exponer `on_tokens_refreshed` en `AccessContext` si el 14 no lo dejó | `feat(integrations): agrega sink on_tokens_refreshed a AccessContext (delta aditivo)` | `cd backend && pytest tests/test_integrations_access_context.py tests/test_integration_ports.py tests/test_adapter_microsoft365.py -v` | N/A — sin adaptador real cableado aún; runtime harness se reproduce en el Lote 6 (sink connectors) | Revert commit; campo opcional nuevo con default `None`, ningún consumidor existente (14/15) se rompe |
| 1 | Migración 00NN (4 tablas) + modelos + config + docs ER/C4 en el mismo commit | `feat(intake): migracion 00NN, modelos base y docs ER/C4 del modulo intake` | `cd backend && alembic upgrade head && pytest tests/test_intake_migration.py -v` | `alembic upgrade head` / `alembic downgrade -1` contra BD desechable (patrón `test_boards_backfill_migration.py`) | Revert commit + `alembic downgrade -1` (elimina las 4 tablas, ningún dato de otros módulos se toca) |
| 2 | Almacenamiento e ingesta pull idempotente con `IntakeRun` (`intake-items`) | `feat(intake): almacenamiento e ingesta pull idempotente con bitacora IntakeRun` | `cd backend && pytest tests/test_intake_items_service.py tests/test_intake_items_endpoints.py -v` | `httpx.AsyncClient` contra el router montado + adaptador `fake` de 14 (patrón `test_notification_deliveries_endpoint.py`) | Revert commit; sin migración propia, endpoints nuevos sin dependientes fuera de `intake/` |
| 3 | CRUD de `IntakeRule` + motor puro de clasificación (`intake-rules`) | `feat(intake): CRUD de reglas tema-respondiente y motor de clasificacion puro` | `cd backend && pytest tests/test_intake_rules_endpoints.py tests/test_intake_classifier_matcher.py -v` | N/A — matcher puro sin BD/HTTP; runtime harness se reproduce en el Lote 4 (wiring) | Revert commit; `classifier.py` puro sin efectos colaterales, sin dependientes aún |
| 4 | Clasificación automática al final del pull + proyecto default real + `TaskService.create_task` real + asignado no elegible | `feat(intake): clasificacion automatica tras pull con proyecto default y creacion real de tareas` | `cd backend && pytest tests/test_intake_classifier_endpoints.py -k "TestAutoConversion or TestDefaultProject" -v` | `httpx.AsyncClient` + adaptador `fake`, flujo `POST /intake/pull` real creando `Task`/`Project` reales | Revert commit; `service.py` recupera su forma del Lote 3, `Task`/`Project` ya creados quedan huérfanos pero autónomos |
| 5 | Triage manual (`convert`) + `IntakeSettings` (get/patch) | `feat(intake): reclasificacion manual desde triage y configuracion de proyecto por defecto` | `cd backend && pytest tests/test_intake_classifier_endpoints.py -v` | `httpx.AsyncClient` real: `POST /intake/items/{id}/convert` sobre un ítem `pending` sembrado | Revert commit; endpoint aislado, sin dependientes |
| 6 | Sink `on_tokens_refreshed` → persistencia de credenciales rotadas + verificación final de suite | `feat(connectors): persiste credenciales rotadas tras refresco en lectura durante intake pull` | `cd backend && pytest tests/test_intake_connectors_sink.py -v` | `alembic upgrade head` contra `solercia_test` + flujo real `POST /intake/pull` → `GET /intake/items?status=pending` → `POST /intake/items/{id}/convert` | Revert commit; se retira la llamada de persistencia en `connectors/repository.py`, sin afectar el CRUD del 14 |

## Fase 0 — Preflight en vivo (sin commit, gate obligatorio antes de la Fase 1)

- [x] 0.1 [Pre-requisito] Verificar el head real de Alembic: `cd backend && alembic heads`. Este cambio es el ÚLTIMO apply de la serie (después de 14 y 21): fijar `down_revision` de 1.4 al head real confirmado — NO asumir `0014` (ya reclamado por 21; 14 puede renumerar el suyo sobre él). **Verificado**: head en vivo = `0018_add_org_role_templates`; migración 22 = `0019_add_intake`.
- [x] 0.2 [Pre-requisito] Verificar que `app/integrations/` existe con `ports.py` (`Capability`, `*ReaderPort`, `IntegrationAdapter`), `dtos.py` (`MailMessage`/`CalendarEvent`/`ExternalTask`/`MeetingNote`/`Ticket`/`OAuthTokens`) y que `app/modules/connectors/repository.py` expone credenciales cifradas (Fernet). Si falta, bloquear el apply: 22 depende en firme del 14 aplicado. **Verificado**: existe completo.
- [x] 0.3 [Pre-requisito CONDICIONAL] Verificar si `AccessContext` (referenciado por el 14, sin dataclass explícita en su design) expone `on_tokens_refreshed`. Si NO existe → ejecutar la Fase 0-bis ANTES de cablear el sink de la Fase 6. Si SÍ existe → saltar la Fase 0-bis. **Verificado: SÍ existe** (`app/integrations/ports.py::AccessContext.on_tokens_refreshed`, addendum ratificado del 14, consumido por 15/16/22) → **Fase 0-bis se OMITE**.

## Fase 0-bis — Extensión aditiva de `app/integrations/` (Lote 0-bis / Commit condicional, SOLO si 0.3 confirma ausencia)

**OMITIDA** — 0.3 confirmó que `AccessContext.on_tokens_refreshed` ya existe (addendum ratificado del 14). Ningún archivo de este lote se creó.

- [x] 0b.1 ~~RED~~ N/A — sink ya existe, no se extiende.
- [x] 0b.2 ~~GREEN~~ N/A — sink ya existe, no se extiende.
- [x] 0b.3 ~~VERIFY~~ N/A — sink ya existe, no se extiende.

## Fase 1 — Fundación: migración, modelos, config y docs ER/C4 (Lote 1 / Commit 1)

- [x] 1.1 [Foundation] `app/shared/enums.py`: `IntakeItemType` (`email|calendar_event|external_task|meeting_note|ticket`), `IntakeItemStatus` (`pending|converted|ignored|error`), `IntakeRunStatus` (`running|completed|error`) — `str, Enum`, `native_enum=False` (precedente del repo). [IT1,IT2,CL2]
- [x] 1.2 [Foundation] `app/config.py`: `INTAKE_DEFAULT_PROJECT_NAME="Tareas Outlook"`, `INTAKE_PULL_MAX_ITEMS` (patrón `EMAIL_*`/`M365_MAX_PAGES`). [CL5]
- [x] 1.3 [Foundation] `app/modules/intake/models.py`: `IntakeItem` (Pk+Timestamp+SoftDelete+Audit+Tenant), `IntakeRule` (Pk+Timestamp+SoftDelete+Audit+Tenant), `IntakeRun` (Pk+Timestamp+Audit+Tenant, sin soft delete), `IntakeSettings` (Pk+Timestamp+Tenant). [IT1,IT2,RU1,CL5]
- [x] 1.4 [Foundation] `backend/alembic/versions/0019_add_intake.py`: `down_revision="0018"`; `upgrade()` crea las 4 tablas + `UNIQUE(organization_id, connector_id, external_id)` en `intake_items` + `UNIQUE(organization_id)` en `intake_settings`; `downgrade()` elimina en orden inverso. [IT1,IT2]
- [x] 1.5 [Docs — MISMO COMMIT] `docs/diagrams/er-model.md`: agregadas las 4 tablas nuevas + FKs (`connector_id`, `matched_rule_id`, `created_task_id`) como Dominio 8; actualizada la migración más reciente citada a `0019_add_intake`.
- [x] 1.6 [Docs — MISMO COMMIT] `docs/diagrams/c4-architecture.md`: agregado el módulo `intake` en C3 (contenedor backend), relaciones hacia `integrations`(14), `projects`(21) y `tasks`.
- [x] 1.7 RED `backend/tests/test_intake_migration.py` (patrón `test_project_hierarchy_migration.py`, BD desechable + raw SQL): `upgrade` crea las 4 tablas y las 2 unicidades; `downgrade` las elimina en orden inverso sin residuos. [IT1,IT2]
- [x] 1.8 VERIFY confirmado T1.7 en verde; `cd backend && alembic upgrade head && pytest tests/test_intake_migration.py -v` en verde (2/2); `alembic check` sin diff (`test_migrations_baseline.py` 4/4 verde contra el head 0019 completo); `app/db_init.py` registra los 4 modelos.

## Fase 2 — Almacenamiento e ingesta pull (Lote 2 / Commit 2, `intake-items`)

- [x] 2.1 [Foundation] `app/modules/intake/schemas.py`: `IntakeItemRead`, filtros de listado (`status`, `item_type`, `connector_id`), `IntakeRunRead`. [IT4]
- [x] 2.2 [Foundation] `app/modules/intake/repository.py`: `upsert_item(...)` idempotente por `(organization_id, connector_id, external_id)`, `list_items(filters)`, `get_item(id)`, `create_run`/`close_run`, `list_runs`. [IT1,IT2,IT4,IT5]
- [x] 2.3 [Foundation] `app/modules/intake/service.py`: `pull(organization_id, actor)` — por cuenta conectada, `adapter.port_for(cap).list_*(ctx, limit=INTAKE_PULL_MAX_ITEMS)` → DTO→`IntakeItem` → `upsert_item` → conteos en `IntakeRun`; error en una cuenta cierra su `IntakeRun` en `error` sin bloquear las demás. [IT1,IT2,IT3]
- [x] 2.4 [Foundation] `app/modules/intake/router.py`: `POST /intake/pull` (`require_role(admin,manager)`), `GET /intake/items`, `GET /intake/items/{id}`, `GET /intake/runs`. [IT3,IT4,IT5]
- [x] 2.5 [Foundation] `app/main.py`, `app/db_init.py`: `include_router(intake_router, prefix=API_PREFIX)`.
- [x] 2.6 RED `backend/tests/test_intake_items_service.py`: upsert nuevo vs duplicado (`items_duplicated++`); ítem ya `converted` no se reclasifica ni duplica tarea; conector sin `connected_account_id` (GLPI) se ingesta sin error. [IT1,IT2] — DOS AsyncSession independientes ligadas al `engine` para probar commits reales (lección savepoint).
- [x] 2.7 RED `backend/tests/test_intake_items_endpoints.py` (httpx `AsyncClient`, adaptador `fake` de 14, `two_orgs`): admin pull exitoso con conteos correctos; member → 403 sin `IntakeRun`; cuenta con token irrecuperable cierra `error` sin bloquear la cuenta sana; filtro `?status=pending`; `GET /intake/items/{id}` de otra organización → 404. [IT1,IT3,IT4,IT5]
- [x] 2.8 VERIFY confirmado T2.6/T2.7 en verde; `cd backend && pytest tests/test_intake_items_service.py tests/test_intake_items_endpoints.py tests/test_intake_migration.py -v` en verde (11/11); `ruff check .`/`mypy app` limpios.

## Fase 3 — Reglas + motor puro de clasificación (Lote 3 / Commit 3, `intake-rules`)

- [x] 3.1 [Foundation] `app/modules/intake/schemas.py` (ampliar): `IntakeRuleCreate/Read/Update` (`criteria`, `rule_order`, `is_active`, `convert_to_task`, `target_project_id?`, `task_priority`, `assignee_id?`). [RU1,RU2,RU5]
- [x] 3.2 [Foundation] `app/modules/intake/repository.py` (ampliar): CRUD de `IntakeRule` (soft delete), `list_active_rules_ordered(organization_id)` (`is_active=true ORDER BY rule_order ASC`). [RU1,RU3,RU4]
- [x] 3.3 [Foundation] `app/modules/intake/service.py` (ampliar): CRUD de reglas org-scoped, `DELETE` como soft delete excluida de la evaluación. [RU1,RU4]
- [x] 3.4 [Foundation] `app/modules/intake/router.py` (ampliar): `POST/GET/GET{id}/PATCH/DELETE /intake/rules`, escritura `require_role(admin,manager)`, lectura cualquier miembro. [RU1]
- [x] 3.5 [Foundation] `app/modules/intake/classifier.py`: `ClassifierPort` (Protocol) + `RuleBasedClassifier` puro (sin BD/HTTP) + matcher (`unicodedata.NFKD`+`casefold`) contra `origin_actor|domain|title|snippet|source_provider|connector_id` (AND intra-regla); retorna la primera regla activa por `rule_order` que casa. [RU2,RU3,RU4,RU5,CL1]
- [x] 3.6 RED `backend/tests/test_intake_rules_endpoints.py`: manager crea regla activa por defecto; member → 403; dos condiciones AND (solo casa si ambas se cumplen); `DELETE` excluye la regla de listados y de la evaluación futura. [RU1,RU2,RU4]
- [x] 3.7 RED `backend/tests/test_intake_classifier_matcher.py` (unit puro, sin BD): folding sin tildes+case-insensitive; dos reglas casan → gana `rule_order` menor; regla inactiva no compite aunque casaría; regla sin `target_project_id` retorna contrato "usar default". [RU3,RU4,RU5]
- [x] 3.8 VERIFY confirmado T3.6/T3.7 en verde; `cd backend && pytest tests/test_intake_rules_endpoints.py tests/test_intake_classifier_matcher.py -v` en verde (13/13); `ruff check .`/`mypy app` limpios. Corrección adicional: datos huérfanos de una corrida fallida previa (Lote 2) contaminaban `test_connectors_oauth_flow.py` — limpiados manualmente y blindados con try/finally en `test_intake_items_service.py`.

## Fase 4 — Clasificación automática wired (Lote 4 / Commit 4, `intake-classifier` automático)

- [x] 4.1 [Foundation] `app/modules/intake/service.py` (ampliar): `_ensure_default_project(organization_id)` — get-or-create perezoso vía `ProjectService.create_project(organization_id, ProjectCreate(methodology="planner", name=IntakeSettings.default_project_name or INTAKE_DEFAULT_PROJECT_NAME))` (service real, respeta jerarquía del 21: proyecto raíz sin `parent_project_id`), persiste en `IntakeSettings.default_project_id`, reutiliza en llamadas posteriores. [CL5]
- [x] 4.2 [Foundation] `app/modules/intake/service.py` (ampliar): `classify_and_convert(item)` — `RuleBasedClassifier.classify`; si casa y `convert_to_task=true`: pre-valida `assignee_id` con `TaskRepository.is_org_member` (mismo chequeo de `TaskService._verify_assignee`) ANTES de llamar `create_task` — no elegible → `item.status=pending` + `matched_rule_id` como motivo registrado/consultable (DESVIACIÓN documentada: sin columna `rejection_reason` dedicada — ver Deviations del apply-progress), SIN crear membresía; elegible → `TaskService.create_task(organization_id, project_id, TaskCreate(...))` (service real, nunca SQL directo) → `item.status=converted`, `created_task_id`, `matched_rule_id`, `classified_at`; `convert_to_task=false` → `item.status=ignored` (NO pasa a triage); sin regla → `item.status=pending`. [CL1,CL2,CL3,CL4,CL5]
- [x] 4.3 [Foundation] `app/modules/intake/service.py` (ampliar): `pull(...)` invoca `classify_and_convert` sobre cada ítem nuevo `pending` al cierre de la ingesta de cada cuenta, sin llamada adicional del usuario. [CL1]
- [x] 4.4 RED `backend/tests/test_intake_classifier_endpoints.py::TestAutoConversion`: pull con reglas activas clasifica los 5 ítems nuevos (adaptador `fake`: 5 capacidades) sin llamada extra; correo con `target_project_id`+`priority=high`+`assignee_id=U1` crea `Task` real correcta (verificado con sesiones REALMENTE independientes) y el ítem queda `converted` con `matched_rule_id`/`created_task_id`; `convert_to_task=false` → `ignored` sin `Task`; `assignee_id` no-miembro → `Task` NO creada, ítem `pending`, `matched_rule_id` registrado, CERO membresías nuevas; sin regla coincidente → `pending`, sin `matched_rule_id`. [CL1,CL2,CL3,CL4]
- [x] 4.5 RED `backend/tests/test_intake_classifier_endpoints.py::TestDefaultProject`: primer uso crea `Project` `planner` "Tareas Outlook" y lo registra en `IntakeSettings`; segundo uso reutiliza el mismo proyecto (sesiones independientes); nombre configurado antes del primer uso se respeta. [CL5]
- [x] 4.6 VERIFY confirmado T4.4/T4.5 en verde (7/7); `cd backend && pytest tests/test_intake_classifier_endpoints.py -v tests/test_intake_rules_endpoints.py -v` en verde; `ruff check .`/`mypy app` limpios.

## Fase 5 — Triage manual + IntakeSettings (Lote 5 / Commit 5, `intake-classifier` manual)

- [x] 5.1 [Foundation] `app/modules/intake/schemas.py` (ampliar): `IntakeConvertRequest` (`priority`, `assignee_id`), `IntakeSettingsRead/Update` (`default_project_name`). [CL6,CL8]
- [x] 5.2 [Foundation] `app/modules/intake/service.py` (ampliar): `convert_manual(item_id, priority, assignee_id, actor)` — solo sobre `status=pending`; `TaskService.create_task` real en el proyecto default (`_ensure_default_project`); `created_task_id` asignado, `matched_rule_id` permanece `None`; error de validación si ya está `converted`. `get_settings`/`update_settings` (`PATCH` restringido a `admin|manager`). [CL6,CL8]
- [x] 5.3 [Foundation] `app/modules/intake/router.py` (ampliar): `POST /intake/items/{id}/convert` (cualquier miembro), `GET /intake/settings` (cualquier miembro), `PATCH /intake/settings` (`admin|manager`). [CL6,CL8]
- [x] 5.4 RED `backend/tests/test_intake_classifier_endpoints.py::TestManualTriage`: conversión manual crea `Task` en el default, `matched_rule_id` nulo; reconvertir un ítem `converted` → error de validación sin segunda `Task`; reasignar la tarea vía endpoint vigente de `tasks` NO rompe `created_task_id`/`matched_rule_id`; `PATCH /intake/settings` → member 403, admin/manager 200; `IntakeSettings` aislado por organización. [CL6,CL7,CL8]
- [x] 5.5 VERIFY confirmado T5.4 en verde; `cd backend && pytest tests/test_intake_classifier_endpoints.py -v` en verde (12/12); `ruff check .`/`mypy app` limpios.

## Fase 6 — Sink connectors + verificación final (Lote 6 / Commit 6, delta `connectors`)

- [ ] 6.1 [Foundation] `app/modules/connectors/repository.py` (ampliar): `save_refreshed_credentials(connected_account_id, tokens)` — cifra (Fernet, mismo mecanismo del callback OAuth) y persiste `access_token`/`refresh_token`/`expires_at` rotados; NO sobrescribe si el refresco falla. [CN1]
- [ ] 6.2 [Foundation] `app/modules/intake/service.py` (ampliar): antes de `adapter.port_for(cap).list_*`, si `expires_at` vencido → `adapter.refresh(refresh_token)` → sink `on_tokens_refreshed` (directo si 0.3 confirmó existencia, o vía el delta de la Fase 0-bis) → `connectors.save_refreshed_credentials`; si `refresh` falla → NO sobrescribe credenciales, cuenta en error recuperable, `IntakeRun` de esa cuenta cierra `error`. [CN1]
- [ ] 6.3 RED `backend/tests/test_intake_connectors_sink.py`: token vencido se refresca y persiste (`access_token_enc != plaintext`, nunca en logs/respuestas) antes de leer; refresco fallido NO sobrescribe credenciales y el `IntakeRun` cierra `error`; token vigente NO dispara `refresh` ni modifica `ConnectionCredentials`. [CN1]
- [ ] 6.4 VERIFY confirmar T6.3 en ROJO antes de GREEN; `cd backend && pytest tests/test_intake_connectors_sink.py -v` en verde.
- [ ] 6.5 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa en verde sin regresión sobre el baseline previo; `ruff check .`/`mypy app` limpios; `alembic check` sin diff.
- [ ] 6.6 VERIFY runtime harness: `alembic upgrade head` contra `solercia_test` + flujo real `POST /intake/pull` → `GET /intake/items?status=pending` → `POST /intake/items/{id}/convert` sobre el adaptador `fake` de 14, confirmando el caso guía correo→tarea con proyecto default y regla con `assignee_id`.

## Trazabilidad de requisitos

**intake-items**: IT1 Almacenamiento con vínculo al origen · 1.3,1.7,2.2,2.6,2.7 — IT2 Idempotencia org+conector+external_id · 1.3,1.4,1.7,2.2,2.3,2.6 — IT3 Ingesta manual con bitácora `IntakeRun` · 2.3,2.4,2.7 — IT4 Consulta y filtrado · 2.1,2.2,2.4,2.7 — IT5 Aislamiento multi-tenant · 2.2,2.4,2.7

**intake-rules**: RU1 CRUD con permisos por rol · 3.1,3.2,3.3,3.4,3.6 — RU2 Criterios AND · 3.1,3.5,3.6,3.7 — RU3 Precedencia por `rule_order` · 3.2,3.5,3.7 — RU4 Reglas inactivas excluidas · 3.2,3.3,3.5,3.6,3.7 — RU5 Acción de conversión (default) · 3.1,3.5,3.7

**intake-classifier**: CL1 Ejecución tras cada ingesta · 3.5,4.3,4.4 — CL2 Conversión cuando casa · 1.1,4.2,4.4 — CL3 Asignado no elegible bloquea · 4.2,4.4 — CL4 Sin regla → triage · 4.2,4.4 — CL5 Proyecto por defecto perezoso · 1.2,1.3,4.1,4.2,4.5 — CL6 Reclasificación manual · 5.1,5.2,5.3,5.4 — CL7 Trazabilidad estable ante cambios de la tarea · 5.4 — CL8 Multi-tenant y RBAC de configuración · 5.1,5.2,5.3,5.4

**connectors (delta)**: CN1 Persistencia de credenciales rotadas tras refresco · 6.1,6.2,6.3
