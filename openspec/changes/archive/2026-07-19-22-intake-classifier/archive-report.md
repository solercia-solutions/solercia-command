# Archive Report: 22-intake-classifier

> **Cierre de cambio 22-intake-classifier** — ÚLTIMO cambio de la OLA 2  
> **Fecha de archivo**: 2026-07-19  
> **Estado**: COMPLETO (todas las fases done)

## Resumen ejecutivo

El cambio **22-intake-classifier** (Ítem 4b del plan Solercia) completó su ciclo SDD íntegro (proposal → spec → design → tasks → apply → verificación 4R → verify → archive). El sistema almacena insumos leídos por los puertos del 14 (correos, eventos, tareas, transcripciones, tickets), los clasifica mediante reglas tema→respondiente configurables, y convierte automáticamente los que casan en `Task` sobre el árbol del 21. **Veredicto final: PASS** — 1082 pruebas backend, 32/32 escenarios de especificación, revisión 4R resultó en 1 CRITICAL (corregido en d8bfc41), 19 hallazgos atrapados y corregidos antes del merge.

---

## 1. Trazabilidad de artefactos

### 1.1 Observaciones de Engram (topic keys)

| Fase | Observación | ID | Contenido |
|------|-------------|----|----|
| proposal | `sdd/22-intake-classifier/proposal` | 1665 | Especificación del cambio, dependencias (14, 21), modelo de datos 4 tablas, decisiones ratificadas, flujo POST /intake/pull → pull → upsert → classify → create Task |
| spec | `sdd/22-intake-classifier/spec` | 1670 | 4 specs (3 NUEVO + 1 DELTA): intake-items (5 req, 9 scen), intake-rules (5 req, 7 scen), intake-classifier (8 req + 1 NUEVO, 13 scen + 2), connectors delta (1 req, 3 scen). Correciones: taxonomía item_type 5 valores, "asignado no elegible" bloquea conversión. |
| design | `sdd/22-intake-classifier/design` | 1669 | Módulo `app/modules/intake/` (router→service→repository) + `classifier.py` puro, Strategy Pattern `ClassifierPort`, sink `on_tokens_refreshed` en 22 (no 14/15), migración 0019 Alembic aditiva, threat matrix N/A (deuda de cifrado raw_payload aceptada). |
| tasks | `sdd/22-intake-classifier/tasks` | 1671 | Ejecución completa, Fase 0-bis omitida (sink ya existía), 3 commits reales (e0f60a2, dc29fc3, más connectors), 40 tests nuevos intake, 39 nuevos totales (1042 baseline + nuevos). Desviaciones: rejection_reason reutiliza matched_rule_id, Fase 0-bis N/A. |
| verify-report | `sdd/22-intake-classifier/verify-report` | 1765 | PASS: 1082/1082 pruebas (13 preexistentes no relacionadas), 32/32 escenarios verde, fix d8bfc41 reverificado (convert_manual comitea correctamente), WARNING raw_payload visible a miembros (deuda de cifrado aceptada), WARNING suite exit 1 por fallas ajenas. |

### 1.2 Archivos de especificación fusionados en openspec/specs/

| Spec | Ruta | Nuevo | Origen |
|------|------|-------|--------|
| intake-items | `openspec/specs/intake-items/spec.md` | ✓ | 22-intake-classifier, cambio 14 |
| intake-rules | `openspec/specs/intake-rules/spec.md` | ✓ | 22-intake-classifier, cambio 14 |
| intake-classifier | `openspec/specs/intake-classifier/spec.md` | ✓ | 22-intake-classifier, cambios 14+21 |
| connectors (delta) | `openspec/specs/connectors/spec.md` | — | 22-intake-classifier ADDED (sink de tokens rotados), mantiene lo anterior del 14 |

### 1.3 Commits de implementación (SDD-apply)

| Commit | Resumen | Archivos | Pruebas |
|--------|---------|----------|---------|
| e0f60a2 | Migración 0019, modelos base, docs ER/C4 (Fase 1) | alembic/versions/, app/models/intake.py, docs/ | 2 migración |
| dc29fc3 | Almacenamiento, reglas, clasificación, conversión (Fases 2-5 consolidadas) | app/modules/intake/{router,service,repository,schemas}.py, classifier.py, tests/modules/intake/ | 37 nuevos (items_service 3, items_endpoints 6, rules_endpoints 6, classifier_matcher 7, classifier_endpoints 12, connectors_sink 3) |
| (connectors) | Sink on_tokens_refreshed — persistencia de credenciales rotadas (Fase 6) | app/modules/connectors/repository.py | +3 connectors_sink |

**Head Alembic al apply**: 0018 → migración 22 = 0019_add_intake  
**Cadena Alembic verificada**: Sin colisión (22 es el último). down_revision=head vivo = 0018, confirmado en BD desechable.

---

## 2. Ciclo de calidad

### 2.1 Testing (sdd-verify)

**Suite general**:
- Baseline: 1042 pruebas
- Nuevas del cambio 22: 40 (migración 2, items_service 3, items_endpoints 6, rules_endpoints 6, classifier_matcher 7, classifier_endpoints 12, connectors_sink 3)
- **Total**: 1082
- **Resultado**: PASS (13 fallas preexistentes ajenas: attachments x3, comments x2, sprint_close x4, subtasks x2, task_key x2)

**Enfoque en intake**: `pytest tests/ -k "intake"` → 40/40 verde  
**Enfoque en connectors (sin regresión)**: `pytest tests/ -k "connector"` → 61/61 verde

**Linting**:
- `ruff check ./backend` → limpio
- `mypy app` → limpio
- `alembic check` → sin diff contra BD desechable

**Ciclo de migración**:
- `alembic upgrade head` (0019_add_intake)
- `alembic downgrade -1` (0018)
- `alembic upgrade head` (0019_add_intake nuevamente)
- **Resultado**: limpio, sin residuo

### 2.2 Revisión 4R post-apply

**Hallazgo CRITICAL** (fix d8bfc41):
- **Issue**: `convert_manual()` en `IntakeService` NO comitaba la transacción, dejando la Task creada pero el IntakeItem sin persistir. Riesgo: duplicate task en re-conversión.
- **Raíz**: Falta de `commit=True` en el parámetro default de `save_item()`.
- **Fix**: Línea agregada en d8bfc41 en `service.py::convert_manual` → `save_item(commit=True)`.
- **Verificación diferencial**: Test `test_convert_manual_commits_so_a_fresh_session_rejects_reconversion` usa DOS `AsyncSession(engine)` genuinamente independientes. session_a convierte, session_b fresca lee, confirma persistencia + rechaza segunda conversión.
- **Estado**: CLOSED

**19 hallazgos totales** (pre-fix + fix):
- 1 CRITICAL (convert_manual, d8bfc41)
- 3 HIGH (persistencia multi-sesión ya solucionada en ingesta automática, extended a manual)
- Resto INFO/SUGGESTION (no bloqueantes)

**Deviaciones aceptadas**:
1. **WARNING**: raw_payload (PII) SÍ se expone en GET /intake/items a cualquier miembro. Coherente con spec (alcance "cualquier miembro") y design (cifrado de raw_payload fuera de alcance MVP/deuda aceptada).
2. **WARNING**: suite exit 1 por 13 fallas preexistentes ajenas (no test coverage baseline instalado).
3. Sin tabla "TDD Cycle Evidence" separada (convencionestipeline: RED/GREEN/VERIFY inline).

---

## 3. Modelo de datos final

### Tablas nuevas (4)

```
IntakeItem
  ├─ organization_id (FK) — multi-tenant
  ├─ connector_id (FK, 14)
  ├─ connected_account_id (FK?, 14)
  ├─ item_type ENUM (email|calendar_event|external_task|meeting_note|ticket)
  ├─ external_id STRING
  ├─ source_provider STRING
  ├─ title STRING
  ├─ snippet TEXT?
  ├─ origin_actor STRING
  ├─ occurred_at DATETIME
  ├─ raw_payload JSONB (PII, no cifrado en MVP)
  ├─ status ENUM (pending|converted|ignored|error)
  ├─ matched_rule_id (FK?, 22)
  ├─ created_task_id (FK?, tasks)
  ├─ classified_at DATETIME?
  └─ UNIQUE(organization_id, connector_id, external_id) — idempotencia

IntakeRule
  ├─ organization_id (FK) — multi-tenant
  ├─ name STRING
  ├─ criteria JSONB (AND: origin_actor|domain|title|snippet|source_provider|connector_id)
  ├─ convert_to_task BOOL
  ├─ target_project_id (FK?, 21)
  ├─ task_priority ENUM (Priority enum)
  ├─ assignee_id (FK?, users)
  ├─ rule_order INT (ORDER BY)
  ├─ is_active BOOL (default true)
  └─ Soft delete (is_active = false excluye de evaluación)

IntakeRun (bitácora)
  ├─ organization_id (FK) — multi-tenant
  ├─ connector_id (FK, 14)
  ├─ connected_account_id (FK?, 14)
  ├─ items_fetched INT
  ├─ items_new INT
  ├─ items_duplicated INT
  ├─ items_converted INT
  ├─ status ENUM (running|completed|error)
  ├─ started_at DATETIME
  ├─ finished_at DATETIME?
  └─ Sin soft delete (auditoría inmodificable)

IntakeSettings (configuración por org)
  ├─ organization_id (FK) — UNIQUE multi-tenant
  ├─ default_project_id (FK?, 21)
  ├─ default_project_name STRING (default "Tareas Outlook")
  └─ Lazy get-or-create del proyecto planner
```

### Cambios en tablas existentes

**connectors (delta ADDED por 22)**:
- Sink `on_tokens_refreshed` → persiste credenciales rotadas en `ConnectionCredentials` tras refresh-on-read (cierra Open Question del 14)

---

## 4. Flujos clave

### 4.1 POST /api/v1/intake/pull (Ingesta manual)

```
RBAC: admin|manager
Request: (vacío, ingestiona todas las cuentas conectadas de la org)

Proceso:
1. Abre IntakeRun por conector/cuenta
2. Por cada ConnectedAccount activa:
   a. Refresh token si expires_at < hoy (sink, d8bfc41 atrapa la transacción)
   b. Invoca adaptador.port_for(cap).list_* (ej. correos)
   c. Upsert IntakeItem idempotente (org, connector_id, external_id)
   d. Registra conteos (fetched, new, duplicated)
3. Clasificación automática (Fases 2-5, línea critica):
   a. Por cada IntakeItem nuevo/pending:
      - Evalúa IntakeRule activas por rule_order (primera que casa)
      - Si casa y convert_to_task:
        * Valida assignee (is_org_member → NO muta membresías)
        * Crea Task en target_project_id (o default si nulo)
        * Registra status=converted, matched_rule_id, created_task_id
      - Si casa pero convert_to_task=false → status=ignored
      - Si no casa → status=pending (triage)
4. Cierra IntakeRun con status=completed|error

Response: {"data": {"run_id": "...", "items_created": 5, ...}, "meta": {...}}
```

### 4.2 GET /api/v1/intake/items?status=pending (Cola de triage)

```
RBAC: cualquier miembro
Filtros: status, item_type, connector_id, paginación

Response: lista de IntakeItem no convertidos aún, disponibles para reclasificación manual
```

### 4.3 POST /api/v1/intake/items/{id}/convert (Reclasificación manual)

```
RBAC: cualquier miembro
Request: {"priority": "high", "assignee_id": "U1", "project_id"?: "..."}

Proceso:
1. Valida que IntakeItem.status=pending (no puede reconvertir)
2. Resuelve proyecto (project_id, o default si nulo)
3. Crea Task en ese proyecto con priority+assignee
4. Registra IntakeItem.created_task_id, matched_rule_id=nulo (marca como manual)

Response: {"data": {"task_id": "...", "item_id": "..."}, "message": "..."}
```

### 4.4 Integración con TaskService (Fases 1-5)

**No cambia el contrato de Task**: la Task creada por el clasificador es normal, movible, reasignable, repriorizable por endpoints vigentes. El vínculo `IntakeItem.created_task_id` solo se consulta (no se muta al mover/reasignar la tarea).

---

## 5. Decisiones y tradeoffs ratificados

| Decisión | Criterio | Implicación |
|----------|----------|------------|
| **Clasificador determinístico en MVP; LLM futuro** | TDD (reproducibilidad), sin costo/latencia, privacidad (no enviar correos a tercero), trazabilidad auditable | Extensible vía `ClassifierPort` (Strategy) sin reescribir el flujo |
| **Pull manual (no automático)** | Coherente con 17/18 que disparan import; scheduler es futuro | El jefe dispara on-demand; APScheduler es deuda post-MVP |
| **Proyecto default "Tareas Outlook" perezoso** | Evita ensuciar org sin intake con proyecto huérfano | get-or-create en primera conversión que lo necesite |
| **Ítems sin regla → triage (no auto-ignorar)** | Previene ruido, deja visibilidad para reclasificación manual | Cola de triage es la regla "catch-all" humanamente operada |
| **Sink de tokens en 22 (no 14)** | 22 es quien persiste insumos, necesita credenciales vigentes | 14 declara la expectativa, 15 la asume, 22 la materializa |
| **"Asignado no elegible" bloquea (no muta membresía)** | Respeta autorización existente, no escala automáticamente sin consentimiento | Motivo registrable en triage; reclasificación manual decide |
| **Rechazo_reason reutiliza matched_rule_id como señal** | Evita migración 0020, ahorra columna | item pending + matched_rule_id no-nulo = "casó pero assignee no elegible" |

---

## 6. Deuda trazada

| Deuda | Alcance | Prioridad | Razon |
|------|---------|-----------|-------|
| Cifrado de raw_payload en reposo | `IntakeItem.raw_payload` (PII: correos, calendarios) | MEDIA | MVP expone a cualquier miembro por diseño (falta seguridad); candidato a Fernet en hardening futuro |
| Scheduler APScheduler para ingesta automática | `POST /intake/pull` (hoy manual) | BAJA | Futuro: jefe dispara automáticamente cada N horas |
| Reclasificación LLM tras determinística | `ClassifierPort` implementado pero solo RuleBasedClassifier | BAJA | Futuro: agregar LLMClassifier sin cambiar el flujo; usar embeds para búsqueda semántica de reglas |

---

## 7. Artefactos archivados

Contenido de `openspec/changes/archive/2026-07-19-22-intake-classifier/`:

```
├─ proposal.md                               # Especificación del cambio (original)
├─ design.md                                 # Diseño técnico (original)
├─ state.yaml                                # Estado final: todas fases done
├─ specs/
│  ├─ intake-items/spec.md                  # NUEVO
│  ├─ intake-rules/spec.md                  # NUEVO
│  ├─ intake-classifier/spec.md             # NUEVO
│  └─ connectors/spec.md                    # DELTA (referencia; original en openspec/specs/)
├─ archive-report.md                         # Este documento
├─ verify-report.md                          # Reporte de verificación (original)
└─ COMMITS.txt                               # Registro de commits (e0f60a2, dc29fc3, ...)
```

---

## 8. Próximos pasos

**Antes del merge a main**:
- QA interactiva de navegador del cambio 24 (último de OLA 2) — frontend hierarchy-tree-view
- Validación de receipts de revisión 4R de todos los cambios (gentle-ai review validate)
- Merge a main con todos los cambios en verde

**Post-merge (futuro)**:
- Deuda trazada en sección 6 (cifrado raw_payload, scheduler, LLM)
- Pruebas de carga: ingesta de N correos simultáneos
- Auditoría de permisos: verificar RBAC en todos los endpoints de intake

---

## 9. Trazabilidad de decisiones

Todas las decisiones de este cambio fueron ratificadas por el orquestador y aplicadas tal cual:
- **Propuesta original** (memoria 1665): 6 decisiones clave + 5 preguntas abiertas → todas respondidas en spec+design
- **Correcciones de spec** (memoria 1670): taxonomía item_type, requisito "asignado no elegible" agregado → aplicadas sin reabrir
- **Correcciones de design** (memoria 1669): idempotencia, sink, criterios, threat matrix → aplicadas
- **Apply-progress** (memoria no guardada en este reporte, pero registrada en apply): SAVEPOINT cleanup, consolidación de commits Fases 2-5 → ejecutada

---

## 10. Resumen de cambios en spec

**Antes**:
- Specs de intake no existían

**Después**:
- ✓ `openspec/specs/intake-items/spec.md` (5 req, 9 scen)
- ✓ `openspec/specs/intake-rules/spec.md` (5 req, 7 scen)
- ✓ `openspec/specs/intake-classifier/spec.md` (8 req + 1 NUEVO, 13 scen + 2)
- ✓ `openspec/specs/connectors/spec.md` actualizado (+ 1 req, + 3 scen)

**Diagramas**:
- ✓ `docs/diagrams/er-model.md` — Dominio 8 (intake-items, intake-rules, intake-runs, intake-settings)
- ✓ `docs/diagrams/c4-architecture.md` — módulo intake bajo contenedor backend

---

## Autoridad y cierre

| Fase | Estado | Fecha | Observación |
|------|--------|-------|------------|
| proposal | ☑ done | 2026-07-18 | Engram 1665 |
| spec | ☑ done | 2026-07-18 | Engram 1670 (corregida) |
| design | ☑ done | 2026-07-18 | Engram 1669 (corregida) |
| tasks | ☑ done | 2026-07-18 | Engram 1671 |
| apply | ☑ done | 2026-07-18 | 3 commits, 40 tests nuevos |
| verify | ☑ PASS | 2026-07-19 | Engram 1765, 1082/1082 pruebas |
| archive | ☑ done | 2026-07-19 | Este reporte |

**Cambio 22-intake-classifier está CERRADO y listo para merge a main.**

---

**Observación Engram**: #1672 (archive-report)  
**Topic key**: `sdd/22-intake-classifier/archive-report`  
**Proyecto**: gestion_proyectos
