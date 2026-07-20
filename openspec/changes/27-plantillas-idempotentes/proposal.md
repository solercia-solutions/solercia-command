# Proposal: 27 · Instanciación idempotente de plantillas y `project_kind`

## Intent

Instanciar una plantilla ya aplicada duplica todo el árbol de proyectos. La idempotencia está acoplada al responsable: el ledger `OrgRoleTemplateInstantiation` usa `UNIQUE(organization_id, template_id, node_id, lead_user_id)` (`models.py:110-118`) y `ledger_for` filtra por `lead_user_id` (`repository.py:92-112`). Re-instanciar la MISMA plantilla con OTRO responsable devuelve ledger vacío → `service.py:191-257` recrea un árbol completo (mismos nombres, `code` autogenerado distinto). Ya hay duplicados OAP‑TI en la base. Además, OLA 4 (decisión 3, "equipo = proyecto raíz") pide distinguir contenedores del organigrama del trabajo real con `project_kind`.

## Scope

### In Scope
- Idempotencia por nodo SIN `lead_user_id` en la clave: `UNIQUE(organization_id, template_id, node_id)`; `ledger_for` sin filtro de lead; reconciliar el responsable (si el nodo existe y el lead cambió, actualizar `Project.lead_user_id` y la fila del ledger) en vez de duplicar. Migración del constraint + dedup previo del ledger.
- Nueva columna `Project.project_kind` (enum `area|proyecto`, default `proyecto`, migración aditiva). El generador la asigna: nodo contenedor → `area`, nodo hoja (trabajo real) → `proyecto`.
- Limpieza de duplicados OAP‑TI existentes: migración de datos/comando idempotente que detecta árboles duplicados (mismo `template_id`+`organization_id`, nombres iguales, `code` distinto), conserva el más antiguo (prefiriendo el que tiene tareas), reasigna/absorbe tareas y hace soft‑delete del resto, reconciliando el ledger al superviviente.
- Listado de proyectos con filtro opcional `?project_kind=` (sin parámetro = comportamiento actual).
- TDD: doble instanciación (mismo o distinto lead) → un solo árbol; reconciliación de responsable; asignación de `project_kind`; filtro de listado.

### Out of Scope
- Entidad `Team` (condicionada, decisión 3). Cambios de UI/frontend. Calendario laboral (cambio 28). Edición de nombre en la vista jerárquica (cambio 36).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `org-role-templates`: idempotencia por nodo (sin lead), reconciliación de responsable, asignación de `project_kind` y limpieza de duplicados.
- `projects`: nueva columna `project_kind` y filtro opcional en el listado.

## Approach

Cambiar la clave de idempotencia a `(organization_id, template_id, node_id)` y reconciliar el lead en la reutilización. Regla del generador: nodo con hijos = `area`, hoja = `proyecto` (una plantilla de un solo nodo queda `proyecto`). Dos migraciones Alembic: (1) dedup del ledger + nuevo UNIQUE + columna `project_kind`; (2) limpieza reconciliadora de árboles duplicados. TDD estricto sobre la fixture existente.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/org_role_templates/models.py` | Modified | UNIQUE sin `lead_user_id` |
| `.../org_role_templates/repository.py` | Modified | `ledger_for` sin filtro de lead |
| `.../org_role_templates/service.py` | Modified | Reconciliar lead; asignar `project_kind` por nodo |
| `backend/app/modules/projects/{models,schemas,router,repository}.py` | Modified | Columna + filtro `project_kind` |
| `backend/app/shared/enums.py` | New | Enum `ProjectKind` |
| `backend/alembic/versions/` | New | 2 migraciones (constraint+columna; limpieza de datos) |
| `backend/tests/**` | New | Contratos TDD |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Reasignar tareas de duplicados pierde trazabilidad | Media | Conteo previo; conservar el árbol con tareas; log de reconciliación |
| El nuevo UNIQUE falla sobre datos ya duplicados | Alta | Deduplicar el ledger ANTES de aplicar el constraint en la misma migración |
| Dedup del ledger con leads distintos | Media | Ganador = lead del superviviente (más antiguo con tareas) |
| Regla `project_kind` ambigua para raíz sin hijos | Baja | Definir hoja=proyecto explícito en el spec |
| Romper tests de idempotencia del cambio 23 | Media | Actualizar contratos a la nueva clave |

## Rollback Plan

Migraciones reversibles: el downgrade restaura `UNIQUE(...,lead_user_id)` y elimina `project_kind`. La limpieza de datos NO es trivialmente reversible (el soft‑delete sí, la reasignación de tareas no): ejecutar en una transacción, con backup previo y bitácora de lo reconciliado para revertir manualmente si hace falta.

## Dependencies

- `25-multiempresa-scoping`: el aislamiento por `organization_id` debe estar blindado antes de reconciliar/limpiar datos por empresa. El cambio 26 NO es prerrequisito técnico de este cambio.

## Success Criteria

- [ ] Doble instanciación de la misma plantilla (mismo o distinto lead) produce un solo árbol.
- [ ] Re-instanciar con otro responsable reconcilia el lead, no duplica.
- [ ] `project_kind` asignado: contenedores = `area`, hojas = `proyecto`.
- [ ] `GET /projects?project_kind=` filtra; sin parámetro no rompe clientes.
- [ ] Duplicados OAP‑TI existentes reconciliados sin perder tareas.
- [ ] Migraciones reversibles; suite backend en verde.

## Proposal question round

Supuestos a validar con el usuario: (1) la política por defecto es **reconciliar** (re-instanciar con otro responsable actualiza el lead del árbol existente) y solo se rechaza con mensaje claro si hay un conflicto irreconciliable; (2) al colapsar duplicados gana el árbol **más antiguo con tareas** y las tareas del resto se reasignan a él; (3) la regla del generador es **nodo con hijos = `area`, nodo hoja = `proyecto`**, dejando `proyecto` para plantillas de un solo nodo y para el `POST /projects` normal.
