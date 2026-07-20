# Proposal: 25 · Aislamiento multiempresa (scoping por organization_id)

## Intent

El aislamiento por `organization_id` es hoy 100% manual, consulta por consulta: `TenantMixin` (`app/shared/base_model.py:50-58`) no aplica ningún filtro global; cada repository filtra a mano (directo o vía join al padre: tasks/boards/sprints → Project). La auditoría módulo por módulo no encontró fugas, pero ese contrato de seguridad —la invariante de que la consulta de una empresa jamás devuelve datos de otra— no está fijado por ninguna prueba de regresión. Un refactor futuro o un módulo nuevo puede introducir una fuga cross-tenant sin que nada la detecte. El cambio 25 blinda esa invariante con TDD antes de que 26 (admin-empresas) habilite membresías multiempresa y el selector de empresa activa, que aumentan la superficie de riesgo.

## Scope

### In Scope
- Batería sistemática de tests de fuga cross-tenant por módulo (~28 módulos: projects, tasks, sprints, boards, users, roles, dependencies, activity, search, dashboard, org_role_templates, reminders, assets, notifications, labels, checklists, time_logs, comments, attachments, task_links, alert_rules, menus, connectors, intake, glpi_sync, jira_import, organizations). Con dos empresas sembradas, la consulta autenticada como empresa A nunca devuelve ids de empresa B (listados, detalle, búsqueda global, métricas y dashboards, dependencias, apariencia, plantillas/equipos).
- Corrección de cualquier fuga que los tests revelen (scoping en repository/service).
- Aserción de que conectores YA cumplen: `Connector` por empresa (TenantMixin + UNIQUE(organization_id, provider)), `ConnectedAccount` por usuario, credenciales Fernet aisladas (`app/modules/connectors/models.py`).
- Documentación del contrato multiempresa: qué es tenant-scoped vs. global por diseño (catálogo `menus`; plantillas `system` de `org_role_templates`), con test explícito de "catálogo compartido" para esos casos.

### Out of Scope
- Resolución/cambio de empresa activa, claim de organización en el JWT y selector en UI → **frontera con el cambio 26** (`admin-empresas`). Hoy la empresa activa es la primera membresía por `created_at` (`app/dependencies.py:128-146`, `app/modules/auth/service.py:34-44`); 25 congela el contrato de aislamiento sin tocar esa resolución.
- CRUD de empresas y membresías multiempresa (cambio 26).
- Filtro global de tenant (event listener de SQLAlchemy): se mantiene el scoping manual salvo que una fuga lo exija.
- Migración a schema-por-tenant (hardening futuro). Frontend.

## Capabilities

### New Capabilities
- `multi-tenant-isolation`: contrato de aislamiento por `organization_id` fijado con tests de fuga cross-tenant por módulo y superficie global-por-diseño documentada.

### Modified Capabilities
- None (correcciones esperadas a nivel de implementación, no de requisito; sin migración salvo hallazgo).

## Approach

TDD sobre la fixture existente `two_orgs`/`_seed_org_data` (`backend/tests/conftest.py:376-475`, siembra orgs A/B). Por cada módulo con lectura: sembrar A y B, autenticar como miembro de A y afirmar que la respuesta solo contiene datos de A y nunca de B. Módulos globales por diseño reciben test de "catálogo compartido" en vez de aserción de aislamiento. Las fugas se corrigen en el repository/service (filtro por `organization_id` o join al padre). El contrato se documenta en un `.md` de referencia. Suite base: 1158 tests.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/tests/**` | New | Batería de tests de fuga cross-tenant por módulo |
| `backend/app/modules/*/repository.py` | Modified | Solo si un test revela fuga |
| `openspec/specs/multi-tenant-isolation/` | New | Contrato documentado (scoped vs. global) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Fuga oculta en un módulo poco cubierto | Media | El propio test la expone; corregir en repository |
| Global-por-diseño confundido con fuga | Media | Test explícito de catálogo compartido (menus, plantillas system) |
| Contrato se rompe al llegar el 26 | Media | Tests seedean por org y siguen válidos con membresías múltiples |
| Costo de siembra doble en muchos tests | Baja | Reusar fixture `two_orgs`; helpers de aserción compartidos |

## Rollback Plan

Cambio principalmente aditivo (tests + doc). Revertir los commits de tests y de cualquier corrección de scoping; sin migración esperada. Si una corrección de repository causara regresión, se revierte de forma aislada.

## Dependencies

- Ninguna dependencia SDD bloqueante. Declara la frontera con **26-admin-empresas** (resolución de empresa activa, claim JWT, membresías multiempresa): 25 fija el contrato, 26 amplía la superficie respetándolo.

## Success Criteria

- [ ] Test de fuga cross-tenant por cada módulo tenant-scoped; A nunca ve datos de B.
- [ ] Módulos globales-por-diseño con test de catálogo compartido.
- [ ] Conectores verificados por-empresa y por-usuario mediante test.
- [ ] Contrato multiempresa documentado (scoped vs. global).
- [ ] Suite backend en verde (≥1158 tests).

## Proposal question round

Supuestos a validar con el usuario: (1) 25 es blindaje por tests + doc del contrato, sin cambiar la resolución de empresa activa (eso es 26); (2) el scoping manual se mantiene —no se introduce filtro global de SQLAlchemy— salvo que una fuga lo obligue; (3) `menus` y las plantillas `system` de `org_role_templates` son globales por diseño y se prueban como catálogo compartido, no como fuga.
