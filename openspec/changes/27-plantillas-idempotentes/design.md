# Design: 27 · Instanciación idempotente de plantillas y `project_kind`

## Technical Approach

Se desacopla la idempotencia del responsable moviendo la clave del ledger `OrgRoleTemplateInstantiation` de `(organization_id, template_id, node_id, lead_user_id)` a `(organization_id, template_id, node_id)`. `ledger_for` (`repository.py:92-112`) pierde el filtro de lead y devuelve `{node_id: row}` por nodo; `_reconcile_and_commit` (`service.py:191-257`) **reconcilia el lead** en la reutilización (actualiza `Project.lead_user_id` y la fila del ledger) en vez de recrear el árbol. El match es SIEMPRE por ledger (`template_id`+`node_id`), nunca por nombre: como el nombre es editable conservando trazabilidad (decisión 2, OLA_4), la reutilización preserva el nombre editado por el usuario y solo reconcilia el lead. Se añade `Project.project_kind` (enum `area|proyecto`) que el generador asigna por topología del nodo. Dos migraciones Alembic tras `0021` (reservada por el cambio 26): `0022` aditiva de columna y `0023` de reconciliación (dedup + swap de constraint + limpieza de árboles).

## Architecture Decisions

### Decisión 1: idempotencia por nodo, match por ledger, lead reconciliado

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Clave `(org, template, node)`; `ledger_for` sin lead; en reutilización actualizar `Project.lead_user_id`+fila ledger; nombre editado se conserva** | Elimina la duplicación de raíz; una plantilla = un árbol por organización; respeta ediciones del usuario | **Elegida** |
| Match por nombre del proyecto | Se rompe al renombrar (decisión 2); reintroduce duplicados | Rechazada |
| Rechazar si el lead cambia | Contradice la política "reconciliar por defecto" (question round) | Rechazada |

### Decisión 2: `project_kind` por topología del nodo

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Nodo con hijos → `area`; hoja → `proyecto`. Se computa del set de `parent_node_id` de la plantilla; `POST /projects` normal y plantilla de un solo nodo → `proyecto`** | Sin `if methodology==...`; determinista y sin config extra | **Elegida** |
| Marcar el kind en `OrgRoleTemplateNode` | Requiere migrar/semillar plantillas y otra columna | Rechazada |

`ProjectKind` vive en `app/shared/enums.py` (subclase `str`, patrón existente); columna `SAEnum(..., native_enum=False, length=20)` con CHECK, default `proyecto`.

### Decisión 3: split de migraciones — (a) sola; (b)+(c) juntas

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`0022`: columna `project_kind` (aditiva, reversible). `0023`: dedup del ledger + swap de UNIQUE + limpieza de árboles, en UNA transacción** | El nuevo UNIQUE solo se crea tras deduplicar, y el ganador del dedup del ledger ES el árbol superviviente: acoplarlos evita un estado intermedio con árboles huérfanos sin ledger | **Elegida** |
| Split del proposal: `0022` dedup+UNIQUE+columna, `0023` limpieza | Deja árboles sin ledger que `0023` debe re-emparejar por nombre (frágil) | Rechazada |
| Limpieza como comando CLI aparte | Paso manual olvidable; rompe la cadena `alembic upgrade` secuencial de la ola | Rechazada |

### Decisión 4: detección de duplicados y superviviente

Criterio primario (ledger): filas del ledger que comparten `(org, template, node)` pero apuntan a `project_id` distintos (los duplicados reales: leads distintos → proyectos distintos). Los proyectos de los nodos raíz definen los árboles duplicados. Criterio defensivo (sin ledger): mismo `(org, template)`, nombres iguales, `code` distinto. **Superviviente** = árbol raíz más antiguo (`MIN(created_at)`) prefiriendo el que tiene tareas en su subárbol; se reasignan las tareas de los perdedores al superviviente (por posición nodo/nombre), soft-delete de los perdedores y colapso del ledger a una fila por `(org, template, node)` → superviviente, con su `lead_user_id`.

### Decisión 5: filtro opcional `?project_kind=`

`list_by_org` recibe `project_kind: ProjectKind | None`; sin parámetro = comportamiento actual (los tests de aislamiento del cambio 25 siguen verdes). `router.py:37` añade el query param opcional; el service lo pasa al repository. Sin `if`-dispatch.

## Data Flow

    instantiate(org, template, lead)
        │  guards: template visible → lead es miembro
        ▼
    ledger_for(org, template) → {node_id: row}        (sin filtro de lead)
        │
        ├─ nodo con proyecto activo → REUSA · reconcilia lead (Project + row) · nombre intacto
        └─ nodo faltante → crea Project(project_kind = area|hoja) · repunta/inserta fila
        │
        ▼  UN commit  →  un solo árbol por (org, template)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/shared/enums.py` | Modify | + `ProjectKind(area, proyecto)` |
| `.../org_role_templates/models.py` | Modify | UNIQUE sin `lead_user_id` (`uq_org_role_template_instantiation`) |
| `.../org_role_templates/repository.py` | Modify | `ledger_for(org, template)` sin filtro de lead |
| `.../org_role_templates/service.py` | Modify | reconciliar lead en reutilización; `project_kind` por nodo-con-hijos |
| `.../projects/models.py` | Modify | columna `project_kind` |
| `.../projects/schemas.py` | Modify | `project_kind` en `ProjectCreate`(opt)/`ProjectRead` |
| `.../projects/{repository,service,router}.py` | Modify | filtro `?project_kind=` opcional |
| `backend/alembic/versions/0022_add_project_kind.py` | Create | columna aditiva, reversible |
| `backend/alembic/versions/0023_dedup_ledger_reconcile_trees.py` | Create | dedup + swap UNIQUE + limpieza (una tx) |
| `backend/tests/**` | Create/Modify | contratos TDD; actualizar idempotencia del cambio 23 a la nueva clave |

## Interfaces / Contracts

```python
class ProjectKind(str, Enum):
    area = "area"
    proyecto = "proyecto"

async def ledger_for(org, template) -> dict[UUID, OrgRoleTemplateInstantiation]
def build_project_create(node, *, lead_user_id, parent_project_id, project_kind)
# GET /projects?project_kind=area|proyecto   (ausente = colección completa)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `project_kind` por nodo (contenedor vs hoja; nodo único → `proyecto`) | `build_project_create`/set de `parent_node_id` |
| Integration | doble `instantiate` mismo lead → un árbol; distinto lead → un árbol + lead reconciliado; nombre editado se conserva al reutilizar | fixture del cambio 23 |
| Integration | `GET /projects?project_kind=` filtra; sin parámetro no rompe | `client` con/sin query |
| Migration | `0022` upgrade/downgrade; `0023` dedup colapsa a superviviente con tareas, reasigna tareas, aplica nuevo UNIQUE; downgrade honesto | siembra duplicados OAP-TI |
| Regresión | idempotencia del cambio 23 (clave nueva) + aislamiento del cambio 25 (si existe) verdes | suite completa |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. El riesgo es de dominio (migración destructiva de datos), mitigado en Decisión 3/4: una transacción, backup previo y bitácora de reconciliación.

## Migration / Rollout

`0022` (revisa `0021`): añade `project_kind NOT NULL server_default 'proyecto'`, backfill implícito, retira el server_default; downgrade elimina columna + CHECK — reversible. `0023` (revisa `0022`): en una transacción reconcilia duplicados, colapsa el ledger, hace `drop_constraint` del viejo UNIQUE y `create` de `UNIQUE(organization_id, template_id, node_id)`, y backfilla `project_kind` de supervivientes con la regla nodo-con-hijos. **Downgrade honesto**: recrea `UNIQUE(...,lead_user_id)` y elimina el nuevo (reversible); la reasignación de tareas y el soft-delete quedan como **no-op documentado** (no reversible trivialmente) — se revierte manualmente con backup + bitácora. Applies secuenciales; verificar `alembic current` (head real) antes de fijar `down_revision`.

## Open Questions

- [ ] Ninguna bloqueante. Si el cambio 26 renumera su migración, ajustar la cadena `down_revision` de `0022` al head real antes de `apply`.
