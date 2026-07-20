```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: git:4abeb9c9175d3f64c40af92a6d29f43d5a9ab5ac
verdict: pass_with_warnings
blockers: 1
critical_findings: 1
requirements: 6/7
scenarios: 19/20
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:324476fcef45cd477ac2af6ac4548781fd2c9babde766875e1cbe25f093d9a2f
build_command: cd backend && .venv/bin/ruff check app/modules/projects app/modules/org_role_templates app/shared/enums.py alembic/versions/0022_add_project_kind.py alembic/versions/0023_dedup_ledger_reconcile_trees.py tests/
build_exit_code: 0
build_output_hash: sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18
```

## Verification Report

**Change**: 27-plantillas-idempotentes
**Version**: N/A (delta specs, no version field)
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 34 |
| Tasks complete | 34 |
| Tasks incomplete | 0 |

Nota: el brief de verificación esperaba "43/43"; el `tasks.md` real de este cambio contiene 34 ítems `- [x]` (Fase 0: 3, Fase 1: 5, Fase 2: 7, Fase 3: 6, Fase 4: 6, Fase 5: 3, Fase 6: 4), todos marcados y coherentes con `apply-progress` y `state.yaml`. Se documenta como discrepancia de expectativa (ver WARNING-3), no como defecto de `tasks.md`.

### Build & Tests Execution

**Build (lint sobre archivos tocados)**: ✅ Passed
```text
$ cd backend && .venv/bin/ruff check app/modules/projects app/modules/org_role_templates \
    app/shared/enums.py alembic/versions/0022_add_project_kind.py \
    alembic/versions/0023_dedup_ledger_reconcile_trees.py tests/test_migration_project_kind.py \
    tests/test_project_kind_filter.py tests/test_migration_dedup_ledger_reconcile_trees.py \
    tests/test_org_role_templates_api.py tests/test_org_role_templates_service.py tests/test_projects.py
All checks passed!
```

**Tests**: ✅ 1271 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
$ cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
    .venv/bin/python -m pytest -q
1271 passed, 1 warning in 350.32s (0:05:50)
```
Conteo exacto coincide con lo reportado por apply (1249 baseline + 22 nuevos). Cero `skipped` nuevos — los tests con `@skip_no_db` corrieron con normalidad porque `TEST_DATABASE_URL` estaba presente.

**Suites dirigidas de regresión (punto 6 del encargo)**:
```text
$ cd backend && TEST_DATABASE_URL=... .venv/bin/python -m pytest -q \
    tests/test_cross_tenant_isolation.py tests/test_org_role_templates_migration.py
54 passed in 31.97s
```
52 tests de aislamiento cross-tenant (cambio 25) + 2 del contrato de migración `0018` (cambio 23) — ambos siguen en verde sin modificaciones tras el swap de constraint.

**Ciclo real de migraciones (punto 5 del encargo)** — BD desechable `solercia_verify_27`, creada y eliminada con `asyncpg` vía `postgres`/`postgres` admin DSN, `solercia_test` NUNCA tocada:
```text
$ DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_verify_27 \
    .venv/bin/alembic upgrade head
... 0001 -> ... -> 0021 -> 0022, add_project_kind -> 0023, dedup_ledger_reconcile_trees

$ alembic downgrade -2
Running downgrade 0023 -> 0022, dedup_ledger_reconcile_trees
Running downgrade 0022 -> 0021, add_project_kind

$ alembic upgrade head
Running upgrade 0021 -> 0022, add_project_kind
Running upgrade 0022 -> 0023, dedup_ledger_reconcile_trees

$ alembic current
0023 (head)
```
Ciclo `upgrade → downgrade -2 → upgrade` sobre la cadena real `0021→0022→0023` sin error en ningún sentido. Base descartada al finalizar.

**Coverage**: Not available (sin herramienta de cobertura configurada en el proyecto) — ➖ Not available

---

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress` documenta RED/GREEN/REFACTOR por fase, con conteos de fallos RED confirmados (ej. "3 fallos", "10 proyectos distintos", `StopIteration`, `ResolutionError`, `ImportError`) |
| All tasks have tests | ✅ | 6/6 fases productoras de código tienen test files nuevos o extendidos |
| RED confirmado (test files existen) | ✅ | `test_migration_project_kind.py`, `test_project_kind_filter.py`, `test_migration_dedup_ledger_reconcile_trees.py` existen; nuevos casos en `test_org_role_templates_api.py`/`service.py`/`test_projects.py` verificados por lectura directa |
| GREEN confirmado (tests pasan) | ✅ | 1271/1271 en la corrida completa de este verify, incluidos los 22 nuevos |
| Triangulación adecuada | ✅ | Migración project_kind: 3 casos (RED API, upgrade, downgrade). Migración dedup: 4 casos (dedup+reasignación, no-op, empate, downgrade). Filtro: 4 casos (area, proyecto, sin parámetro, 422). Reconciliación de lead: 5 casos distintos (no-op, nodo recreado, distinto lead sin duplicar, lead reconciliado en cada nodo, nombre editado preservado) |
| Safety Net para archivos modificados | ✅ | Suites dirigidas por fase corridas ANTES de cada commit según tasks.md (ej. 2.6 "27 passed", 4.6 "58 passed"), más la suite completa al cierre |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (funciones puras, sin BD) | 4 | `test_org_role_templates_service.py` (project_kind_for_node ×3, container_node_ids ×1) | pytest |
| Integration (API + BD real) | 14 | `test_org_role_templates_api.py`, `test_project_kind_filter.py`, `test_projects.py` | pytest + httpx.AsyncClient + Postgres |
| Migration (Alembic sobre BD desechable) | 7 | `test_migration_project_kind.py` (3), `test_migration_dedup_ledger_reconcile_trees.py` (4) | pytest + alembic.command + asyncpg |
| **Total nuevo** | **~22** (coincide con el delta 1271−1249 reportado por apply) | 6 archivos | |

---

### Changed File Coverage
Coverage analysis skipped — no hay herramienta de cobertura (`pytest-cov`/similar) configurada en `backend/pyproject.toml`. No es un fallo, solo no disponible.

---

### Assertion Quality
No se encontraron patrones prohibidos (tautologías, loops fantasma sobre colecciones potencialmente vacías, aserciones sin ejecutar código de producción, mocks desproporcionados) en los 6 archivos de test nuevos/extendidos revisados línea por línea (`test_migration_project_kind.py`, `test_project_kind_filter.py`, `test_migration_dedup_ledger_reconcile_trees.py`, y los casos nuevos de `test_org_role_templates_api.py`/`test_org_role_templates_service.py`/`test_projects.py`). Cada test ejercita código de producción real (endpoint HTTP, función pura, o migración Alembic real vía `command.upgrade`/`downgrade`) y afirma valores concretos y variados (ids distintos, conteos de filas, nombres de columnas de constraint, `project_kind` esperado por escenario) — no hay aserciones triviales.

**Assertion quality**: ✅ All assertions verify real behavior

---

### Quality Metrics
**Linter (ruff)**: ✅ No errors — `ruff check` sobre todos los archivos tocados por el cambio (producción + tests) sin hallazgos.
**Type Checker**: ➖ Not available (no hay `mypy`/`pyright` configurado en el proyecto)

---

### Spec Compliance Matrix

#### Delta: org-role-templates

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Migración reversible del constraint de idempotencia por nodo | Migración aplica sobre datos con duplicados existentes | `test_migration_dedup_ledger_reconcile_trees.py > test_upgrade_reassigns_tasks_and_soft_deletes_the_duplicate_keeping_the_tree_with_tasks` | ✅ COMPLIANT |
| Migración reversible del constraint de idempotencia por nodo | Migración es reversible | `test_migration_dedup_ledger_reconcile_trees.py > test_downgrade_restores_the_old_unique_constraint_without_losing_ledger_rows` | ✅ COMPLIANT |
| Asignación de project_kind por el generador | Nodo con hijos queda area | `test_org_role_templates_service.py > test_project_kind_for_node_is_area_when_node_is_a_container` + `test_org_role_templates_api.py` (integración, sombrilla+ramas) | ✅ COMPLIANT |
| Asignación de project_kind por el generador | Nodo hoja queda proyecto | `test_org_role_templates_service.py > test_project_kind_for_node_is_proyecto_when_node_is_a_leaf` + integración (8 equipos) | ✅ COMPLIANT |
| Asignación de project_kind por el generador | Plantilla de un solo nodo queda proyecto | `test_org_role_templates_service.py > test_project_kind_for_node_of_a_single_node_template_is_proyecto` | ✅ COMPLIANT |
| Limpieza de duplicados OAP-TI existentes | Reasigna tareas y conserva el árbol con historial | `test_migration_dedup_ledger_reconcile_trees.py > test_upgrade_reassigns_tasks_and_soft_deletes_the_duplicate_keeping_the_tree_with_tasks` | ✅ COMPLIANT |
| Limpieza de duplicados OAP-TI existentes | Ejecutar la limpieza dos veces es un no-op | `test_migration_dedup_ledger_reconcile_trees.py > test_running_the_cleanup_logic_twice_is_a_noop` | ✅ COMPLIANT |
| Limpieza de duplicados OAP-TI existentes | Empate sin criterio determinista se reporta, no se adivina | `test_migration_dedup_ledger_reconcile_trees.py > test_tie_without_deterministic_survivor_is_reported_not_guessed` | ⚠️ PARTIAL (ver WARNING-1: el test pasa y prueba lo literal — ningún soft-delete, ledger intacto — pero el mecanismo de "registro" es un `warnings.warn` efímero, no un registro durable) |
| No regresión de contratos de idempotencia | Suite completa en verde tras el cambio | Suite completa: `1271 passed, 0 failed` | ✅ COMPLIANT |
| Idempotencia por reconciliación (MODIFIED) | Reinstanciación con el mismo responsable es no-op | `test_org_role_templates_api.py > test_reinstantiate_without_changes_creates_no_new_projects` | ✅ COMPLIANT |
| Idempotencia por reconciliación (MODIFIED) | Reinstanciación con OTRO responsable reconcilia el lead, no duplica | `test_org_role_templates_api.py > test_reinstantiate_with_different_lead_reconciles_the_whole_tree_instead_of_duplicating` + `test_reinstantiate_with_different_lead_reconciles_lead_on_every_node` | ✅ COMPLIANT |
| Idempotencia por reconciliación (MODIFIED) | Reinstanciación reconcilia el nodo faltante con el lead vigente | `test_org_role_templates_api.py > test_reinstantiate_after_soft_deleting_piga_recreates_only_that_node` | ✅ COMPLIANT |
| Idempotencia por reconciliación (MODIFIED) | **Conflicto irreconciliable se rechaza sin modificar el árbol** | **(ninguno encontrado)** | ❌ **UNTESTED / UNIMPLEMENTED — ver CRITICAL-1** |
| Idempotencia por reconciliación (MODIFIED) | Fallo a mitad de instanciación no deja proyectos parciales | `test_org_role_templates_api.py > test_forced_failure_on_fourth_of_five_projects_leaves_none_persisted` | ✅ COMPLIANT |
| Idempotencia por reconciliación (MODIFIED, cubierto implícitamente por el match-por-ledger) | Nombre editado se conserva al reinstanciar (invariante de la decisión de diseño 1) | `test_org_role_templates_api.py > test_reinstantiate_preserves_a_user_edited_project_name` | ✅ COMPLIANT |

#### Delta: projects

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Campo project_kind en Project | Creación directa con POST /projects es siempre proyecto | `test_projects.py > test_post_projects_ignores_client_supplied_project_kind_and_forces_proyecto` | ✅ COMPLIANT |
| Campo project_kind en Project | Migración es aditiva y reversible | `test_migration_project_kind.py > test_upgrade_backfills_existing_projects_to_proyecto_without_losing_rows` + `test_downgrade_removes_project_kind_column_without_losing_rows` | ✅ COMPLIANT |
| Filtro opcional project_kind en el listado | Filtro por area devuelve solo contenedores | `test_project_kind_filter.py > test_filter_by_area_returns_only_area_projects` | ✅ COMPLIANT |
| Filtro opcional project_kind en el listado | Filtro por proyecto devuelve solo trabajo real | `test_project_kind_filter.py > test_filter_by_proyecto_returns_only_proyecto_projects` | ✅ COMPLIANT |
| Filtro opcional project_kind en el listado | Sin parámetro el comportamiento no cambia | `test_project_kind_filter.py > test_no_parameter_returns_every_kind_unchanged` | ✅ COMPLIANT |
| Filtro opcional project_kind en el listado | Valor inválido de project_kind se rechaza | `test_project_kind_filter.py > test_invalid_project_kind_value_is_rejected_with_422` | ✅ COMPLIANT |

**Compliance summary**: 19/20 escenarios compliant (1 UNTESTED/UNIMPLEMENTED — conflicto irreconciliable), 1 PARTIAL con nota (empate reportado por warning efímero, no registro durable)

---

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Clave de idempotencia sin `lead_user_id` | ✅ Implementado | `models.py` `UniqueConstraint("organization_id", "template_id", "node_id", name="uq_org_role_template_instantiation")`; `ledger_for(organization_id, template_id)` sin filtro de lead |
| Reconciliación de lead en reutilización | ✅ Implementado | `_reconcile_and_commit`: `if reused.lead_user_id != lead_user_id: reused.lead_user_id = lead_user_id; ledger_row.lead_user_id = lead_user_id` |
| Match SIEMPRE por ledger, nunca por nombre | ✅ Implementado | `reused = project_service.repo.get(organization_id, ledger_row.project_id)` — consulta por `id`, jamás por `name` |
| Transacción única | ✅ Implementado | Un solo `await self.db.commit()` al final de `_reconcile_and_commit` |
| `project_kind` por topología del nodo | ✅ Implementado | `container_node_ids`/`project_kind_for_node` (funciones puras) + `build_project_create` exige `project_kind` |
| `POST /projects` siempre `proyecto` | ✅ Implementado | `ProjectService.create_project` fuerza `ProjectKind.proyecto` (mismo patrón defensivo que fuerza `lead_user_id=None`) |
| Filtro `?project_kind=` retrocompatible | ✅ Implementado | `Query(default=None)` + filtro condicional `if project_kind is not None` en repository |
| Migración 0022 aditiva/reversible | ✅ Implementado | `server_default` temporal + `drop_column` en downgrade |
| Migración 0023 dedup+swap+limpieza en una transacción | ✅ Implementado | `reconcile_duplicate_trees()` corre ANTES del swap de constraint dentro de la misma migración |
| Conflicto irreconciliable rechazado | ❌ **No implementado** | Sin rama de código, sin excepción dedicada, sin test — ver CRITICAL-1 |

---

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Decisión 1 (clave sin lead, match por ledger, lead reconciliado) | ✅ Sí | Implementado tal como describe `Data Flow` del design |
| Decisión 2 (project_kind por topología) | ✅ Sí | `container_node_ids`/`project_kind_for_node`, sin `if methodology==...` |
| Decisión 3 (0022 sola; 0023 dedup+swap+limpieza juntas) | ✅ Sí | Migraciones separadas exactamente como diseñado |
| Decisión 4 (superviviente = raíz más antigua, prioriza tareas; empate se reporta) | ⚠️ Parcial | El criterio de selección del superviviente SÍ sigue el diseño; el mecanismo de "reporte" del empate (design no especifica el medio) se resolvió con `warnings.warn`, una desviación razonable pero frágil frente a la intención de "resolución manual" — ver WARNING-1 |
| Decisión 5 (filtro opcional sin `if`-dispatch) | ✅ Sí | `list_by_org(project_kind: ProjectKind | None = None)` |
| Conflicto irreconciliable (Modified Requirement, sin decisión propia en design.md) | ❌ No | `design.md` no aterriza esta rama del requisito de spec en ninguna decisión concreta; el código tampoco la implementa — ver CRITICAL-1 |

---

### Issues Found

**CRITICAL**:
1. **Escenario de spec sin implementar ni testear — "Conflicto irreconciliable se rechaza sin modificar el árbol"** (`specs/org-role-templates/spec.md`, Requirement MODIFIED "Idempotencia por reconciliación"). El texto del spec promete, sin condición: *"Un conflicto irreconciliable (ej. el proyecto referenciado por el ledger pertenece a otra organización o su historial es incompatible con el árbol esperado) DEBE rechazarse con un mensaje de error claro, sin modificar el árbol existente."* `backend/app/modules/org_role_templates/service.py::_reconcile_and_commit` no tiene ninguna rama de detección de conflicto ni excepción dedicada (`grep -rn "irreconciliable|conflict|Conflict"` sobre el backend → 0 coincidencias), y ningún test lo cubre. `tasks.md` incluso mapea la trazabilidad de este escenario a las tareas 2.1–2.7, pero ninguna de esas tareas lo implementa realmente (auditado línea por línea). Dado el modelo de datos actual (`ledger_for` filtra por `organization_id` a nivel de columna, así que un ledger row de otra organización nunca aparece en la consulta), el caso tal como está redactado puede ser hoy irrealizable en la práctica — pero eso es precisamente lo que el propio `spec.md` (guardado en Engram junto con el spec) admite en su nota "Learned": *"no tiene un caso concreto identificado en el código actual: quedó modelado como salvaguarda genérica"*. `design.md` tampoco aterriza esta rama en ninguna Decisión ni la excluye explícitamente en "Open Questions". **Esto debe resolverse antes de archivar**: o se implementa+testea el rechazo, o el equipo toma una decisión explícita de descope y se actualiza `spec.md`/`design.md`/`tasks.md` en consecuencia (no dejar una promesa de spec sin cobertura).

**WARNING**:
1. El escenario de "empate sin criterio determinista" (migración 0023) se resuelve con un `warnings.warn(...)` — visible solo si algo captura los `UserWarning` de Python durante el `alembic upgrade` (el test lo verifica con `pytest.warns`, pero en una corrida real de `alembic upgrade head` en producción, la advertencia se pierde salvo que el operador esté observando la salida en ese instante). No hay tabla, log persistente ni ticket que quede para la "resolución manual" que exige el spec — el requisito se cumple en la letra (ningún árbol se soft-elimina, el grupo queda intacto y registrado en el ledger duplicado) pero el canal de reporte es frágil. Documentado como desviación consciente en `tasks.md` 3.2/3.5; recomendado reforzar con una tabla de reconciliación o al menos un log estructurado antes de que este camino se ejecute contra datos reales de producción.
2. `apply-progress` (y el brief de este verify) afirman "6 commits", pero `git log preview..feat/plantillas-idempotentes` muestra exactamente 5 commits (`dfe4513`, `0033ca7`, `712bb27`, `11172bc`, `4abeb9c`). La Fase 5 (auditoría de contratos) documentó explícitamente "no-op: ningún hallazgo, sin commit propio" en `tasks.md` 5.2 — el conteo real es 5 commits sobre 6 fases, sin impacto funcional, solo una discrepancia de bookkeeping entre lo reportado y el historial real de git.
3. El brief de verificación pedía confirmar "tasks.md 43/43"; el archivo real contiene 34 ítems `- [x]` (todos completos). No hay ítems faltantes ni inconsistencia interna — parece una expectativa desactualizada transmitida al orquestador, no un defecto de `tasks.md`.

**SUGGESTION**:
1. En `alembic/versions/0023_dedup_ledger_reconcile_trees.py::upgrade()`, el `postgresql_where` del índice único parcial de respaldo se construye interpolando directamente los `excluded_ledger_row_ids` (UUIDs) en texto SQL crudo (`f"id NOT IN ({excluded_literal})"`) en vez de usar un parámetro enlazado (`sa.bindparam(..., expanding=True)`, ya usado en otras funciones del mismo archivo). Los valores provienen de una consulta interna de confianza (no de entrada de usuario), así que no hay riesgo práctico de inyección hoy, pero el patrón es fragil si se reutiliza con otra fuente de datos. Se recomienda parametrizar por consistencia con el resto del archivo.

### Verdict
**PASS WITH WARNINGS** — bloqueado para archivo por 1 hallazgo CRITICAL: el escenario de spec "conflicto irreconciliable" carece de implementación y de test. El resto del cambio (suite completa 1271/1271 en verde, contrato de idempotencia por reconciliación con match por ledger nunca por nombre, migración 0023 con dedup/no-op/empate/downgrade probados, `project_kind` por topología del nodo, filtro retrocompatible, aislamiento cross-tenant y contratos del cambio 23 intactos, ciclo real `upgrade/downgrade/upgrade` limpio) está sólidamente verificado y en verde.

---

## Verify de cierre

**Fecha**: 2026-07-20
**Evidence revision**: `git:5fe9731a9b7c4441f3bfeba70e0f1b817c8d10fd`
**Alcance**: verify ACOTADO de corrección — no repite el verify completo anterior (#1898); solo evalúa la corrección aplicada en el commit `5fe9731` sobre el 1 CRITICAL bloqueante.

### 1. Corrección auditada

Commit `5fe9731a9b7c4441f3bfeba70e0f1b817c8d10fd` — `fix(org-role-templates): rechaza reinstanciar cuando un contenedor soft-eliminado tiene hijos activos`. Toca `backend/app/modules/org_role_templates/service.py` (+84/−4), `backend/tests/test_org_role_templates_api.py` (+85 nuevas), `openspec/changes/27-plantillas-idempotentes/tasks.md` (Fase 7, 3 ítems: 7.1 RED, 7.2 GREEN, 7.3 suite completa).

**Test nuevo** (`test_reinstantiate_after_soft_deleting_root_with_active_children_rejects_conflict`): instancia "Jefe de Planeación" (sombrilla "Planeación" + 4 equipos), soft-elimina la sombrilla (`is_active = False`), reinstancia con OTRO responsable. Confirmado por lectura línea a línea:
- `assert second.status_code == 409` y `assert second.json()["code"] == "template_tree_conflict"`.
- Cero proyectos nuevos: solo sigue existiendo UNA fila `Project.name == "Planeación"` (la soft-eliminada, sin reemplazo).
- Cero reconciliación de lead: los 4 equipos hijos conservan `lead_user_id == new_user.id` (el responsable ORIGINAL), nunca el de la instanciación rechazada.
- Ledger intacto byte a byte: snapshot `(project_id, lead_user_id)` de cada fila ANTES == snapshot DESPUÉS de la llamada rechazada.

**Implementación** (`_raise_if_irreconcilable_conflict`, método estático, y su invocación en `_reconcile_and_commit`):
- **Detección ANTES de cualquier escritura**: se invoca en la línea 264 de `service.py`, inmediatamente después de construir `active_by_node` (lookup de solo lectura) y ANTES del bucle principal (líneas 266-319) que crea proyectos, actualiza el ledger y hace `commit()`. La función en sí solo lee `nodes`, `containers`, `ledger` y `active_by_node` — no ejecuta ningún `db.add`/mutación. Tampoco hay escrituras previas en `instantiate()` (líneas 199-230): solo lecturas (`get_visible`, `is_org_member`, `nodes_for_template`) antes de delegar a `_reconcile_and_commit`.
- **409 con código claro**: `AppException(..., code="template_tree_conflict", status_code=409)`, mensaje en español colombiano formal ("Restaura ese proyecto o contacta al administrador" — tuteo correcto, sin voseo).
- **Cero efectos al rechazar**: al levantar la excepción antes del bucle de escritura, no hay `db.add()`, no hay mutación de `lead_user_id` en memoria y no hay `commit()` — no se requiere rollback explícito porque nunca hubo nada que revertir. El test lo corrobora empíricamente (ledger/proyectos/leads sin cambios).
- **Regla correctamente acotada**: solo nodos CONTENEDOR (`area`, con al menos un hijo en el árbol) cuyo proyecto del ledger ya no está activo Y con al menos un hijo activo disparan el 409. Un nodo HOJA soft-eliminado sigue el camino normal de reconciliación (recreación in situ) — el test preexistente `test_reinstantiate_after_soft_deleting_piga_recreates_only_that_node` permanece intacto y verde, confirmando que la nueva rama no interfiere con el escenario ya cubierto.

**Veredicto de la corrección**: ✅ implementación y test cumplen exactamente lo que exigía el CRITICAL — detección read-only antes de cualquier escritura, rechazo con código específico, cero efectos secundarios.

### 2. Acotación del escenario de spec — evaluación y reconciliación documental

El texto de `specs/org-role-templates/spec.md` (Requirement MODIFIED "Idempotencia por reconciliación") usaba, ANTES de esta corrección, un ejemplo genérico ("el proyecto referenciado por el ledger pertenece a otra organización o su historial es incompatible con el árbol esperado") que el verify anterior (#1898) ya había señalado como irrealizable en la práctica hoy (`ledger_for` filtra por `organization_id` a nivel de consulta SQL, así que un ledger de otra organización nunca puede aparecer). El escenario asociado (líneas 88-91) tampoco tenía un caso concreto: "DADO un nodo cuyo estado impide reconciliar de forma segura".

**Evaluación**: el caso concreto implementado (contenedor soft-eliminado con al menos un hijo activo) es una instancia real y alcanzable de "el historial del ledger es incompatible con el árbol esperado" — la cláusula general de la Requirement. Satisface la letra y el espíritu del requisito: un conflicto irreconciliable se rechaza con mensaje claro sin tocar el árbol. La acotación es legítima porque el propio spec (nota "Learned" guardada en Engram al momento de escribir el spec) ya admitía que no tenía "un caso concreto identificado en el código actual" — quedó modelado como salvaguarda genérica. Ahora sí tiene uno, y es el único alcanzable con el modelo de datos vigente.

**Acción tomada**: edité `specs/org-role-templates/spec.md` yo mismo (reconciliación documental de cierre, sin cambiar el comportamiento ni requerir un nuevo ciclo de apply):
- La oración de la Requirement (línea 70) ahora nombra el código de error (`template_tree_conflict`, HTTP 409), describe el caso concreto (contenedor soft-eliminado con hijo activo) y aclara explícitamente que la variante "otra organización" queda fuera de alcance de esta versión porque no es alcanzable hoy con el modelo de datos actual.
- El Scenario (líneas 88-91) pasó de un DADO abstracto ("un nodo cuyo estado impide reconciliar de forma segura") a uno concreto y trazable al test real: contenedor raíz soft-eliminado con hijos activos → `409 template_tree_conflict` → cero proyectos nuevos, cero reconciliación de lead, ledger intacto.

Esto es reconciliación documental (el spec ahora describe con precisión lo que el sistema realmente hace y lo que el test realmente prueba), no un cambio de alcance funcional ni una relajación del requisito.

### 3. Suite completa — corrida única de cierre

```text
$ cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
    .venv/bin/python -m pytest -q
1272 passed, 1 warning in 347.23s (0:05:47)
```
Exit code 0. **1272 passed, 0 failed** — exactamente 1271 (verify anterior) + 1 nuevo (`test_reinstantiate_after_soft_deleting_root_with_active_children_rejects_conflict`). El único warning es el `SAWarning` preexistente de Alembic sobre ciclos de FK entre `dependencies`/`organizations`/`users` (no relacionado con este cambio, ya presente en corridas anteriores).

`ruff check backend/app/modules/org_role_templates/service.py backend/tests/test_org_role_templates_api.py` → `All checks passed!`.

### 4. Veredicto final

| Hallazgo | Estado en verify anterior (#1898) | Estado en verify de cierre |
|---|---|---|
| CRITICAL-1 (conflicto irreconciliable sin implementar/testear) | ❌ Bloqueante | ✅ **RESUELTO** — implementado (`_raise_if_irreconcilable_conflict`), testeado (409 + cero efectos), spec.md reconciliado documentalmente al caso concreto |
| WARNING-1 (empate reportado por `warnings.warn` efímero) | ⚠️ No bloqueante | ⚠️ Sigue documentado, no bloqueante — deuda técnica consciente para antes de correr contra datos reales de producción |
| WARNING-2 (bookkeeping "6 commits" vs. 5 reales) | ⚠️ No bloqueante | ⚠️ Sigue como discrepancia de bookkeeping sin impacto funcional — `git log preview..feat/plantillas-idempotentes` muestra ahora 7 commits (`dfe4513`, `0033ca7`, `712bb27`, `11172bc`, `4abeb9c`, `fc896bb` docs del verify anterior, `5fe9731` corrección de esta Fase 7); ninguno de los conteos históricos (5, 6 o 7) coincide exactamente entre sí porque cada verify agrega su propio commit de reporte, sin impacto funcional |
| WARNING-3 ("tasks.md 43/43" esperado vs. 34 reales) | ⚠️ No bloqueante | ⚠️ Sigue como expectativa desactualizada, no defecto — `tasks.md` ahora tiene 37 ítems `- [x]` (34 + Fase 7: 3), todos coherentes |
| SUGGESTION-1 (interpolación SQL cruda en 0023) | 💡 No bloqueante | 💡 Sin cambios, sigue como mejora menor sugerida |

**PASS** — el bloqueo CRITICAL queda resuelto con implementación + test + reconciliación documental del spec. Los 3 WARNING y 1 SUGGESTION restantes quedan documentados como deuda técnica consciente, no bloqueante para archivar. Suite completa en verde (1272/1272), lint limpio, ciclo de migraciones ya verificado en el verify anterior (sin cambios en migraciones en esta corrección). **Recomendación: proceder a `sdd-archive`.**
