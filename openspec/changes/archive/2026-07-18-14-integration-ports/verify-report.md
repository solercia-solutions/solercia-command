```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:d7b59e3b467242984f0634ce9fe54f8f2bf0214e
verdict: pass
blockers: 0
critical_findings: 0
requirements: 14/14
scenarios: 31/31
test_command: "cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v"
test_exit_code: 1
test_output_hash: sha256:3151d13178ace86772cf0a76799d4cdd2ce55a3ee4cc206c88cab720f0726c13
build_command: "cd backend && ruff check . && mypy app"
build_exit_code: 0
build_output_hash: sha256:8b5e757e1baf25f3332c0191175df30195f6ad0b3873342f4194514709f8f6d7
```

## Verification Report

**Cambio**: 14-integration-ports (núcleo hexagonal de puertos de integración solo-lectura + módulo `connectors` con OAuth genérico)
**Versión**: HEAD en `feat/consume-solercia-ui` = `d7b59e3` (commits del cambio: `0119a92`, `2c05762`, `91ec780`, `d1b99ed`, `881af2e`, `6b33aea`, `d7b59e3`)
**Modo**: Strict TDD

### Nota sobre `test_exit_code: 1`

El comando de suite completa termina con código `1` porque contiene **13 fallas preexistentes, ajenas al cambio 14**, verificadas byte a byte contra la línea base documentada en `sdd/14-integration-ports/apply-progress` (`httpx.LocalProtocolError: Illegal header value b'Bearer '` en `test_attachments.py` (3), `test_comments.py` (2), `test_sprint_close.py` (4), `test_subtasks.py` (2), `test_task_key.py` (2) — total 13, mismos nombres de prueba, mismo error, entorno httpx/conftest no relacionado con `connectors`/`integrations`). Comando alterno acotado únicamente a los 10 archivos de prueba nuevos de este cambio:

```
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
  pytest tests/test_integration_ports_contract.py tests/test_integration_registry.py \
  tests/test_integration_crypto.py tests/test_integration_state_store.py \
  tests/test_integration_fake_adapter.py tests/test_connectors_migration.py \
  tests/test_connectors_crud.py tests/test_connectors_oauth_flow.py \
  tests/test_connectors_security.py tests/test_connected_accounts.py -v
```
→ **54 passed, exit code 0** (24.86s).

### Completeness
| Métrica | Valor |
|--------|-------|
| Tareas totales | 49 |
| Tareas completas | 49 |
| Tareas incompletas | 0 |

### Build & Tests Execution

**Build (ruff + mypy, backend completo)**: ✅ Passed
```text
$ ruff check .
All checks passed!
$ mypy app
Success: no issues found in 205 source files
```

**Tests (suite completa)**: ✅ 642 passed / ❌ 13 failed (preexistentes, confirmadas idénticas a la línea base pre-cambio-14) / ⚠️ 0 skipped
```text
642 passed, 13 failed in 181.48s (0:03:01)
FAILED tests/test_attachments.py::test_upload_and_download_attachment
FAILED tests/test_attachments.py::test_upload_rejects_oversized_file
FAILED tests/test_attachments.py::test_download_requires_auth
FAILED tests/test_comments.py::test_create_comment_with_mentions
FAILED tests/test_comments.py::test_create_comment_empty_body_rejected
FAILED tests/test_sprint_close.py::test_close_sprint_sums_only_done_tasks
FAILED tests/test_sprint_close.py::test_close_sprint_moves_incomplete_to_backlog
FAILED tests/test_sprint_close.py::test_close_sprint_idempotent_409
FAILED tests/test_sprint_close.py::test_velocity_averages_closed_sprints
FAILED tests/test_subtasks.py::test_create_subtask_rejects_points
FAILED tests/test_subtasks.py::test_create_subtask_allows_hours
FAILED tests/test_task_key.py::test_create_task_assigns_task_key
FAILED tests/test_task_key.py::test_get_task_by_key
```
Todas las 13 fallas comparten la misma causa raíz (`httpx.LocalProtocolError: Illegal header value b'Bearer '`), ninguna toca `app/integrations/` ni `app/modules/connectors/`. **Regresión: 0** — mismos 13 nombres de prueba que la línea base documentada antes de iniciar el cambio 14.

**Tests (54 nuevos del cambio 14)**: ✅ 54 passed / ❌ 0 failed — 100% en verde.

**Cobertura**: no se ejecutó `--cov` (no solicitado); evidencia de cobertura de requisitos se basa en el mapeo escenario→prueba de la sección siguiente, con las 54 pruebas ejecutadas en runtime.

### Migración Alembic 0015

| Verificación | Resultado |
|---|---|
| Cadena de revisiones | ✅ `0014 -> 0015 (head)` — sin bifurcaciones, `alembic heads` reporta un único head |
| `upgrade head` en BD desechable (`solercia_verify_cycle`) | ✅ limpio, sin error |
| `alembic check` tras upgrade | ✅ `No new upgrade operations detected.` |
| `downgrade -1` | ✅ limpio (`connection_credentials`→`connected_accounts`→`connectors`, orden inverso correcto) |
| `upgrade head` (segunda vez) | ✅ limpio, idempotente |
| `alembic check` final | ✅ `No new upgrade operations detected.` |
| `UNIQUE(organization_id, provider)`, `UNIQUE(connector_id, external_account_id)`, `UNIQUE(connected_account_id)` | ✅ verificadas en `test_connectors_migration.py` (2/2 verde) |

### Spec Compliance Matrix

**`integration-ports`** (5 requisitos, 10 escenarios)

| Requisito | Escenario | Prueba | Resultado |
|---|---|---|---|
| IP-R1 Puertos de lectura por capacidad | Un puerto sirve a varios proveedores de correo | `test_integration_registry.py::test_two_mail_providers_expose_the_same_port_contract` | ✅ COMPLIANT |
| IP-R1 | Ningún puerto expone escritura | `test_integration_ports_contract.py::test_each_port_declares_only_its_single_read_method` | ✅ COMPLIANT |
| IP-R2 Registro extensible import-time | Adaptador nuevo se registra sin tocar el núcleo | `test_integration_registry.py::test_new_adapter_registers_without_editing_registry_module` | ✅ COMPLIANT |
| IP-R2 | Consulta del registro por proveedor | `test_integration_registry.py::test_get_adapter_resolves_by_provider_without_conditionals` | ✅ COMPLIANT |
| IP-R3 Protocolo de adaptador uniforme | El núcleo delega el canje de tokens al adaptador | `test_integration_fake_adapter.py::test_authorize_then_callback_completes_the_simulated_oauth_flow` | ✅ COMPLIANT |
| IP-R3 | Adaptador sin capacidad queda excluido de ese puerto | `test_integration_fake_adapter.py::test_mail_only_adapter_is_excluded_from_the_calendar_port` | ✅ COMPLIANT |
| IP-R4 Adaptador fake en memoria | El fake pasa las pruebas de contrato de cada puerto | `test_integration_fake_adapter.py::test_fake_adapter_answers_every_port_with_no_real_http_call` | ✅ COMPLIANT |
| IP-R4 | El fake simula el flujo OAuth completo | `test_integration_fake_adapter.py::test_authorize_then_callback_completes_the_simulated_oauth_flow` | ✅ COMPLIANT |
| IP-R5 Frontera solo-lectura estricta | Los puertos no tienen método de escritura que invocar | `test_integration_ports_contract.py::test_each_port_declares_only_its_single_read_method` | ✅ COMPLIANT |
| IP-R5 | El protocolo de adaptador no declara operaciones de escritura | `test_integration_ports_contract.py::test_integration_adapter_protocol_declares_no_write_operation` | ✅ COMPLIANT |

**`connectors`** (9 requisitos, 21 escenarios)

| Requisito | Escenario | Prueba | Resultado |
|---|---|---|---|
| C-R1 Modelo y aislamiento multi-tenant | Conector de otra organización no es visible | `test_connectors_crud.py::test_connector_of_another_org_returns_404_on_get_patch_delete` | ✅ COMPLIANT |
| C-R1 | Cuenta conectada de otra organización | `test_connected_accounts.py::test_connected_account_of_another_org_returns_404_on_get_and_delete` + `test_connectors_security.py::test_connected_account_and_credentials_stay_scoped_to_their_own_org` | ✅ COMPLIANT |
| C-R2 CRUD con permisos por rol | Admin crea un conector | `test_connectors_crud.py::test_create_connector_by_admin_returns_201_with_envelope` | ✅ COMPLIANT |
| C-R2 | Member no puede crear conectores | `test_connectors_crud.py::test_create_connector_rejected_for_member` | ✅ COMPLIANT |
| C-R2 | Cualquier miembro puede listar conectores | `test_connectors_crud.py::test_member_can_list_connectors_without_admin_or_manager_role` | ✅ COMPLIANT |
| C-R3 Varias cuentas del mismo proveedor | Segunda cuenta del mismo proveedor | `test_connectors_oauth_flow.py::test_second_distinct_external_account_creates_a_second_row` | ✅ COMPLIANT |
| C-R3 | Reconexión de la misma cuenta externa no duplica | `test_connectors_oauth_flow.py::test_reconnecting_the_same_external_account_updates_without_duplicating` | ✅ COMPLIANT |
| C-R4 Inicio del flujo OAuth (authorize) | Authorize genera state con TTL y URL del proveedor | `test_connectors_oauth_flow.py::test_authorize_persists_state_and_returns_provider_url` | ✅ COMPLIANT |
| C-R4 | Authorize sobre conector ajeno o inexistente | `test_connectors_oauth_flow.py::test_authorize_on_foreign_or_nonexistent_connector_returns_404_without_state` | ✅ COMPLIANT |
| C-R5 Callback exitoso | Callback válido registra la cuenta y cifra los tokens | `test_connectors_oauth_flow.py::test_successful_callback_creates_account_and_encrypted_credentials` | ✅ COMPLIANT |
| C-R5 | Reutilización del state es rechazada | `test_connectors_oauth_flow.py::test_reused_state_is_rejected_and_creates_nothing_twice` | ✅ COMPLIANT |
| C-R6 Error y expiración del state | State expirado | `test_connectors_oauth_flow.py::test_expired_state_is_rejected_without_creating_an_account` | ✅ COMPLIANT |
| C-R6 | State no coincide (posible manipulación) | `test_connectors_oauth_flow.py::test_unknown_state_is_rejected_without_registering_anything` | ✅ COMPLIANT |
| C-R6 | El proveedor reporta error o cancelación | `test_connectors_oauth_flow.py::test_provider_error_is_rejected_without_partial_records` | ✅ COMPLIANT |
| C-R7 Cifrado y no exposición | Tokens cifrados en base de datos | `test_connectors_security.py::test_tokens_are_encrypted_at_rest_and_decrypt_back` | ✅ COMPLIANT |
| C-R7 | Tokens ausentes en la respuesta de la API | `test_connectors_security.py::test_no_token_leaks_in_authorize_or_callback_json_response` + `test_connected_accounts.py::test_accounts_response_never_includes_token_fields` | ✅ COMPLIANT |
| C-R8 Listado y desconexión | Usuario desconecta su propia cuenta | `test_connected_accounts.py::test_owner_disconnects_own_account_soft_deletes_account_and_credentials` | ✅ COMPLIANT |
| C-R8 | Admin desconecta la cuenta de otro miembro | `test_connected_accounts.py::test_admin_disconnects_another_members_account` (+ `test_manager_also_sees_all_accounts` para el caso manager) | ✅ COMPLIANT |
| C-R8 | Member no puede desconectar la cuenta de otro | `test_connected_accounts.py::test_different_member_cannot_disconnect_someone_elses_account` | ✅ COMPLIANT |
| C-R9 Envelope `{data, message, meta}` | Respuesta de creación con message | `test_connectors_crud.py::test_create_connector_by_admin_returns_201_with_envelope` | ✅ COMPLIANT |
| C-R9 | Respuesta de listado con meta | `test_connectors_crud.py::test_member_can_list_connectors_without_admin_or_manager_role` (asserts `meta.total`) | ✅ COMPLIANT |

**Compliance summary**: 31/31 escenarios COMPLIANT (14/14 requisitos), evidencia de ejecución real (no solo inspección estática) para cada fila.

### Verdict

**PASS WITH WARNINGS**

14/14 requisitos y 31/31 escenarios con prueba cubridora que pasó en ejecución real; 49/49 tareas completas y coherentes con el código; ruff/mypy limpios; migración 0015 con cadena íntegra y ciclo upgrade/downgrade/upgrade + `alembic check` sin diff verificados de forma independiente; los 3 CRITICAL de la revisión 4R están corregidos con evidencia RED→GREEN; `AccessContext` expone `scopes`+`on_tokens_refreshed` confirmado en código y prueba.

**WARNINGS**:
1. `docs/diagrams/er-model.md` líneas 583-587: desactualizado sobre el borrado de `connection_credentials` (afirmaba soft-delete AMBAS filas; correcto es soft-delete de cuenta + DELETE físico de credenciales) — corregido en esta sesión de archivado.
2. Suite completa (`pytest tests/ -v`) termina con exit code 1 por 13 fallas preexistentes ajenas al cambio (no regresión documentada) — no bloqueante pero genera falsa alarma en automatización ciega de exit codes.
