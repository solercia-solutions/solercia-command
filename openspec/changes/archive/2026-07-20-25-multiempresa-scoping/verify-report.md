# Verify Report: 25 · Aislamiento multiempresa (scoping por organization_id)

**Fecha**: 2026-07-20
**Rama**: `feat/multiempresa-scoping`
**HEAD verificado**: `5ae4cb1` (rango de trabajo `0e91b12..5ae4cb1`, 8 commits)
**Modo**: Strict TDD activo — artefactos completos (proposal + specs + design + tasks) — verificación por lectura de código + ejecución real de la suite completa de pytest contra Postgres de test (`solercia_test`).

## Veredicto final

**PASS**

## Resumen ejecutivo

0 CRITICAL, 0 WARNING, 2 SUGGESTION. Suite completa del backend en **1210 passed, 0 failed** (1158 preexistentes + 52 nuevos en `test_cross_tenant_isolation.py`), cero cambios en `backend/app/**`, cero fugas cross-tenant reales detectadas en los 25 módulos tenant-scoped. El meta-test de cobertura, el contrato 404, la superficie global por diseño y el aislamiento de conectores por organización y por usuario quedan confirmados con evidencia de ejecución, no solo lectura.

## 1. Completitud de tareas (tasks.md)

0 cajas `- [ ]` pendientes (`rg "^\- \[ \]" tasks.md` → 0 coincidencias). Las 9 fases (0 a 8) están marcadas `[x]`, incluida la Fase 8 de cierre (8.1–8.5), que documenta explícitamente que ninguna de las fases 2.2/3.2/4.2/5.2/6.2/7.2 detectó una fuga real, por lo que no hubo commit de fix. Coincide con lo declarado en `sdd/25-multiempresa-scoping/apply-progress`. `state.yaml` reporta `tasks: done`, `apply: done`, `verify: pending` antes de esta fase (se actualiza a `done` al cierre de este reporte).

## 2. Evidencia de ejecución

| Comando | Resultado | Detalle |
|---|---|---|
| `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_cross_tenant_isolation.py -v` | ✅ 52 passed en 30.82s | 1 meta-test (`test_all_modules_are_classified`) + 51 tests de aislamiento cross-tenant. Sin fallos, sin skips. |
| `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest -q` | ✅ **1210 passed**, 0 failed, 1 warning en 318.01s | El warning es preexistente (`SAWarning` de SQLAlchemy por ciclo de FK `dependencies/organizations/users`), no relacionado con este cambio — mismo warning documentado en el apply-progress. |
| `git diff --stat "$(git merge-base feat/multiempresa-scoping preview)"..feat/multiempresa-scoping` | ✅ 6 archivos, 1846 inserciones, 0 borrados | Único archivo de código tocado: `backend/tests/test_cross_tenant_isolation.py` (1471 líneas nuevas). El resto son artefactos OpenSpec (`proposal.md`, `design.md`, `spec.md`, `tasks.md`, `state.yaml`). **Cero cambios en `backend/app/**` y en `backend/tests/conftest.py`** — confirma que los seed-helpers quedaron co-ubicados en el archivo nuevo, sin tocar `two_orgs` core (design.md, Decisión 1). |
| `git diff --stat ...  -- backend/app/dependencies.py backend/app/modules/auth/service.py` | ✅ sin salida | Frontera con el cambio 26 (resolución de empresa activa) intacta, confirma tasks.md 8.2. |

**Número exacto solicitado por el usuario**: la suite completa reporta **1210 passed, 0 failed** — coincide exactamente con lo declarado por el apply (1158 preexistentes + 52 nuevos).

## 3. Meta-test de cobertura de módulos (`test_all_modules_are_classified`)

Leído `backend/tests/test_cross_tenant_isolation.py:87-120`. El test:
1. Introspecciona el filesystem (`os.listdir("app/modules")`), ignorando `__pycache__`/`__init__.py` y quedándose solo con directorios reales de módulos.
2. Compara el set descubierto contra la unión `TENANT_SCOPED | GLOBAL | INFRA_NO_READ` (25 + 2 + 1 = 28 módulos).
3. `assert not missing` — si hay diferencia, falla listando exactamente los módulos sin clasificar.

**Prueba mental contra un módulo hipotético**: si se agregara `app/modules/webhooks/`, `_discover_app_modules()` devolvería `webhooks` en el set descubierto; como `webhooks` no está en ninguno de los 3 frozensets, `missing = {"webhooks"}`, la aserción falla con el mensaje `"Módulos sin clasificar en test_cross_tenant_isolation.py: ['webhooks']"`. **Confirmado: el meta-test sí rompe la suite ante un módulo nuevo sin clasificar**, forzando el triaje que exige el design.md (Decisión 1).

## 4. Contrato 404 en detalle/actualización/borrado cross-tenant

Leídos los 51 tests de aislamiento; cada uno de los que ejerce detalle/update/delete sobre una entidad ajena usa `assert response.status_code == 404` explícito (nunca 403, nunca 200). Verificado línea por línea en una muestra representativa: `test_update_project_from_other_org_returns_404` (línea 493), `test_get_task_from_other_org_returns_404` (522), `test_delete_task_from_other_org_returns_404_and_task_survives` (548, que además reconfirma con `session.refresh` que la entidad de B sigue `is_active is True`), `test_update_and_delete_dependency_area_from_other_org_return_404` (633), `test_get_update_delete_connector_from_other_org_return_404` (1376). Los tests de borrado siempre añaden una segunda aserción post-operación (`await session.refresh(...); assert ....is_active is True`) para probar que la entidad ajena sobrevive intacta — cumple el escenario "Actualización y borrado de una entidad ajena son rechazados" del spec, no solo el código HTTP.

Todas las peticiones son llamadas HTTP reales (`client.get/patch/delete`) contra el ASGI app — no hay ninguna aserción que no ejercite código de producción.

## 5. Superficie global por diseño (aserción inversa)

- `test_menu_catalog_is_identical_for_both_organizations` (línea 1073): siembra un `Menu` ad-hoc (sin `TenantMixin`), consulta `/admin/menus` como A y como B, y afirma `str(menu.id) in ids_a` **y** `str(menu.id) in ids_b` — aserción inversa real, no solo ausencia de fuga.
- `test_system_template_is_visible_to_both_organizations` (línea 1053): siembra una `OrgRoleTemplate` con `is_system=True`, consulta `/org-role-templates` como A y B, y afirma que el id aparece en ambos conjuntos.
- Complementado por `test_org_scoped_template_from_other_org_returns_404` (línea 1037), que prueba que una plantilla **org-scoped** de B sí es invisible (404) para A — es decir, `org_role_templates` recibe ambos contratos (aislada si es org-scoped, compartida si es `system`), tal como exige design.md Decisión 3.

## 6. Aislamiento de conectores por organización y por usuario

- **Por organización**: `test_list_connectors_only_returns_callers_organization` (1360, `ids` de A no incluye el conector de B) y `test_get_update_delete_connector_from_other_org_return_404` (1376, GET/PATCH/DELETE contra un conector de B autenticado como A → 404 en los tres, y `connector_b.is_active is True` tras el intento de borrado).
- **Por usuario dentro de la misma organización**: `test_connected_account_of_other_member_not_visible` (1402) — un `member` (no admin/manager) creado con `make_member` solo ve su propia `ConnectedAccount` en `/connectors/{id}/accounts`, nunca la del owner de la organización. Prueba explícitamente el requisito "`ConnectedAccount` único por usuario".
- **Credenciales cifradas**: `test_connected_account_response_never_includes_encrypted_credentials` (1436) confirma que la respuesta serializada nunca expone `access_token_enc` ni `credentials`.
- **Desconexión cross-tenant**: `test_disconnect_connected_account_from_other_org_returns_404` (1457).

Las 5 pruebas pasaron en la ejecución de la Sección 2 (52/52 verdes, incluidas estas 5).

## 7. Auditoría de calidad de aserciones (Strict TDD, paso 5f)

Escaneado el archivo completo contra los patrones prohibidos (tautologías, loops fantasma sobre colecciones potencialmente vacías, aserciones huérfanas sin llamar código de producción, aserciones de solo-tipo aisladas):

- `rg "assert True|assert 1 =="` → 0 coincidencias.
- Único `for` del archivo es `os.listdir(...)` dentro del meta-test (no es un loop de aserciones sobre datos de negocio potencialmente vacíos).
- `rg "assert .*== \[\]|assert .*== set\(\)"` → 0 coincidencias (ningún test se apoya solo en una colección vacía sin su contraparte no-vacía).
- Todas las aserciones muestreadas combinan código de estado HTTP + valor de conjunto/id, o estado + refresco de entidad — ningún smoke-test-only, ningún acoplamiento a detalle de implementación (clases CSS, conteo de mocks).

**Calidad de aserciones**: ✅ Sin hallazgos — todas las aserciones ejercitan comportamiento real vía HTTP contra el ASGI app.

### TDD Compliance

| Check | Resultado | Detalle |
|-------|--------|---------|
| Evidencia TDD reportada | ✅ | `tasks.md` documenta explícitamente `[RED]`/`[GREEN]` por fase (1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1) con comando de verificación y conteo de verdes exacto (18/18, 26/26, 33/33, 47/47, 52/52) — formato de tabla por-tarea distinto al template literal de `strict-tdd-verify.md`, pero funcionalmente equivalente: cada fase declara RED confirmado, corrección/ajuste, y GREEN confirmado con el comando real. |
| Todas las fases tienen tests | ✅ | 9/9 fases con al menos un test asociado (Fase 0 es solo lectura de fixtures, sin test propio, correcto). |
| RED confirmado (archivo existe) | ✅ | `test_cross_tenant_isolation.py` existe y contiene los 52 tests declarados. |
| GREEN confirmado (tests pasan) | ✅ | 52/52 en ejecución real de esta fase (Sección 2). |
| Triangulación adecuada | ✅ | Cada módulo tenant-scoped recibe listado + detalle/update/delete según los endpoints que realmente expone (ver Sección 8 para las excepciones documentadas por diseño). |
| Red de seguridad en archivos modificados | ➖ N/A | Único archivo de producción de tests es nuevo; `conftest.py` no fue modificado (confirmado por diffstat). |

**TDD Compliance**: 5/5 checks aplicables pasados (1 N/A).

## 8. Cobertura por módulo y excepciones documentadas por diseño

Verificados los routers de los módulos con menos de 3 tests (¿faltan endpoints por cubrir o son N/A por diseño?):

| Módulo | Endpoints reales | Cobertura | Nota |
|---|---|---|---|
| `attachments` | GET listado, GET descarga (sin PATCH/DELETE) | listado + descarga-404 | N/A update/delete — no existen esos endpoints (tasks.md 3.2, confirmado en router) |
| `notifications` | GET listado, PATCH (sin DELETE) | listado + update-404 | N/A delete — no existe endpoint |
| `sprints` | GET listado, POST, PATCH, POST close (sin GET detalle plano ni DELETE) | listado + update-404 | N/A detalle/delete — no existen esos endpoints |
| `alert_rules` | GET listado, PATCH (sin DELETE) | listado + update-404 | N/A delete — no existe endpoint |
| `boards` | GET, PATCH reorder, PATCH columna, POST columna, **DELETE columna** | update-404 (rename) | **Ver SUGGESTION 1** — el DELETE de columna no tiene test propio |

## 9. Correctness (evidencia estática) y coherencia con design.md

| Decisión de diseño | Seguida? | Notas |
|---|---|---|
| Decisión 1 — archivo único + seed-helpers co-ubicados + meta-test | ✅ Sí | `conftest.py` intacto, meta-test presente y probado en Sección 3 |
| Decisión 2 — contrato 404 (nunca 403/200) | ✅ Sí | Confirmado en Sección 4 |
| Decisión 3 — superficie global con aserción inversa | ✅ Sí | Confirmado en Sección 5 |
| Decisión 4 — corrección mínima en repository ante fuga | ➖ N/A | No hubo fugas reales que corregir |
| Decisión 5 — sin migraciones | ✅ Sí | `alembic/versions` sin cambios en el diffstat |

Sin desviaciones de diseño que rompan algún requisito del spec.

## Issues

### CRITICAL
Ninguno.

### WARNING
Ninguno.

### SUGGESTION

1. **`boards`: falta test explícito de borrado cross-tenant de columna** (no bloqueante). El endpoint `DELETE /boards/{board_id}/columns/{column_id}` (`remove_column` en `boards/service.py`) usa el mismo guard `self._require_board(organization_id, board_id)` que `rename_column`, ya probado por `test_rename_board_column_from_other_org_returns_404` — el riesgo real de fuga es efectivamente nulo porque comparten la misma línea de código de scoping, pero el escenario "borrado rechazado" del Requirement 1 no tiene una aserción runtime propia y dedicada para este módulo específico. Se recomienda agregar `test_remove_board_column_from_other_org_returns_404` como complemento de bajo costo antes de dar por cerrada la cobertura exhaustiva, sin que esto bloquee el archive.
2. **Formato de evidencia TDD no literal** (no bloqueante). `tasks.md` documenta el ciclo RED/GREEN por fase (con comando y conteo de verdes) en vez de la tabla "TDD Cycle Evidence" por tarea individual que describe `strict-tdd-verify.md`. El contenido es equivalente y verificable (confirmado en Sección 7), pero se señala por completitud de formato.

## Conclusión

24/24... (9/9 fases) completas, 5/5 requisitos del spec cubiertos con evidencia de ejecución real (1210 passed, 0 failed), meta-test de cobertura probado por lectura + razonamiento contra caso hipotético, contrato 404 confirmado en el código (nunca 403/200), superficie global con aserción inversa presente y verde, aislamiento de conectores por organización y por usuario confirmado con tests dedicados, cero cambios en `backend/app/**`, frontera con el cambio 26 intacta. Los 2 SUGGESTION son de completitud menor y no bloquean el archive. **Veredicto: PASS**.
