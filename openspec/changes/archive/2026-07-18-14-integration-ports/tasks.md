# Tasks: 14 · Puertos de integración (núcleo hexagonal + conectores)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~2.200–2.600 (motor ~830 incl. pruebas + migración/modelos/docs ~395 + CRUD ~415 + OAuth/seguridad ~525 + cuentas conectadas ~265) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote 1 (núcleo `app/integrations/` + Redis compartido) → Lote 2 (migración + modelos + docs) → Lote 3 (CRUD `/connectors` + RBAC) → Lote 4 (OAuth authorize/callback + seguridad) → Lote 5 (cuentas conectadas: listar/desconectar) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, un commit por lote (sin PR) |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota de tamaño por lote**: los Lotes 1 y 4 superan individualmente las 400 líneas por acoplamiento inherente entre `state_store`+`oauth`+`crypto`+adaptador fake (Lote 1) y entre `authorize`/`callback`+las 5 filas de Security Requirements (Lote 4). `delivery_strategy: exception-ok` ya cubre esta excepción; no requiere pregunta adicional antes del apply.

**Serialización con 21-project-hierarchy**: este cambio toma la migración `0014` sobre `down_revision="0013"` — SIEMPRE que `21-project-hierarchy` no la haya tomado antes. El Lote 2 incluye una tarea explícita de verificación del head real de Alembic (probablemente `0014` ya tomado → esta migración será `0015`).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Núcleo hexagonal `app/integrations/` (puertos, DTOs, registro, cifrado, state store Redis, OAuth genérico, adaptador fake) + `app/shared/redis.py` compartido (condicional) | 1 — `feat(integrations): nucleo hexagonal de puertos oauth cifrado y adaptador fake` | `cd backend && pytest tests/test_integration_ports_contract.py tests/test_integration_registry.py tests/test_integration_crypto.py tests/test_integration_state_store.py tests/test_integration_fake_adapter.py -v` | `oauth.build_authorize()`→`oauth.handle_callback()` invocados directamente contra el fake en tests (sin HTTP real), Redis vía `fakeredis` | Revert commit (sin migración propia); `app/integrations/` completo es nuevo y aislado |
| 2 | Migración de tablas + 3 modelos + `docs/diagrams/er-model.md` + `docs/diagrams/c4-architecture.md` | 2 — `feat(connectors): migracion y modelos de conectores cuentas y credenciales cifradas` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_migration.py -v` | Ciclo `alembic upgrade head`/`alembic downgrade -1` contra BD desechable (patrón `test_boards_backfill_migration.py`) | Revert commit + `alembic downgrade -1` (elimina `connection_credentials`→`connected_accounts`→`connectors`, sin filas vivas previas) |
| 3 | CRUD `/connectors` (POST/GET/PATCH/DELETE) con RBAC `require_role(admin,manager)` + envelope | 3 — `feat(connectors): crud de conectores con rbac y aislamiento multi-tenant` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_crud.py -v` | `httpx.AsyncClient` contra el router montado en `app.main` (patrón `test_assets.py`) | Revert commit; ruta y schemas nuevos, sin dependientes fuera del módulo |
| 4 | `authorize`/`callback` OAuth + 5 filas de Security Requirements (cifrado, no-fuga, anti-CSRF/replay, aislamiento tenant, anti-SSRF) | 4 — `feat(connectors): flujo oauth authorize callback con cifrado y anti replay` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_oauth_flow.py tests/test_connectors_security.py -v` | `httpx.AsyncClient` contra `GET /connectors/{id}/authorize` y `GET /connectors/oauth/callback` con el fake registrado; Redis vía `fakeredis` | Revert commit; sin migración propia, sin dependientes fuera del módulo |
| 5 | `GET /connectors/{id}/accounts` + `DELETE /connected-accounts/{id}` + VERIFY final de la suite completa | 5 — `feat(connectors): listado y desconexion de cuentas conectadas` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connected_accounts.py -v` | `httpx.AsyncClient` contra el router montado; VERIFY final `pytest tests/ -v` (suite completa) | Revert commit; ruta plana nueva, sin dependientes |

**Lotes ejecutados y completados**:
- [x] Lote 1: Commit `0119a92`
- [x] Lote 2: Commit `2c05762`
- [x] Lote 3: Commit `91ec780`
- [x] Lote 4: Commit `d1b99ed`
- [x] Lote 5: Commit `881af2e`

**Estado final**: 49/49 tareas marcadas [x]. Suite completa: 642 passed / 13 failed (preexistentes, no regresión). Ruff/mypy limpios. Migración `0015` verificada con ciclo upgrade/downgrade/upgrade. Los 3 CRITICAL de la revisión 4R corregidos en `d7b59e3`.

## Trazabilidad de requisitos

**`integration-ports`**: IP-R1 Puertos de lectura por capacidad (2 esc.) · IP-R2 Registro de adaptadores extensible en import-time (2 esc.) · IP-R3 Protocolo de adaptador uniforme (2 esc.) · IP-R4 Adaptador fake en memoria para pruebas de contrato (2 esc.) · IP-R5 Frontera solo-lectura estricta (2 esc.).

**`connectors`**: C-R1 Modelo de datos y aislamiento multi-tenant (2 esc.) · C-R2 CRUD de conectores con permisos por rol (3 esc.) · C-R3 Varias cuentas del mismo proveedor por usuario (2 esc.) · C-R4 Inicio del flujo OAuth — authorize (2 esc.) · C-R5 Callback exitoso del flujo OAuth (2 esc.) · C-R6 Error y expiración del state en el callback (3 esc.) · C-R7 Cifrado de tokens en reposo y no exposición (2 esc.) · C-R8 Listado y desconexión de cuentas conectadas (3 esc.) · C-R9 Contratos de API envueltos `{data, message, meta}` (2 esc.).

Total: 14 requisitos, 31 escenarios cubiertos por tareas RED explícitas en los Lotes 1–5.
