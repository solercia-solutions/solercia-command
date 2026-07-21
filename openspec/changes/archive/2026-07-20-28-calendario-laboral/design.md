# Design: 28 · Calendario laboral configurable (empresa → equipo → proyecto)

## Technical Approach

Se persisten dos campos escalares de calendario en dos niveles: `NOT NULL` con
default en `organizations` (default de empresa) y `nullable` en `projects` (override
del equipo raíz), siguiendo el patrón aditivo ya usado (`theme` en 0020,
`parent_project_id` en 0014). Un módulo nuevo Screaming `app/modules/work_calendar/`
concentra la lógica transversal: `WorkCalendarResolver`, su repository (CTE recursivo
que sube al raíz del árbol), schemas Pydantic v2 y el router. La cascada resuelve
`proyecto → override de la raíz → default de empresa → default global (8h, Lun-Vie)`.
Sin caché en el MVP; el resolver expone un único seam `resolve(org_id, project_id) ->
ResolvedCalendar` para que 34/35 lo envuelvan luego en caché por `(org_id,
root_project_id)`. Solo backend, sin UI (proposal §Out of Scope).

## Architecture Decisions

### D1: Persistir como columnas, no tabla `work_calendar`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **2 columnas en `organizations` + 2 nullable en `projects`** | Encaja en el patrón aditivo-nullable existente; cero joins en la cascada | **Elegida** |
| Tabla `work_calendar` dedicada | Solo se justifica con festivos/husos (futuro); join extra hoy | Rechazada — vía de extensión explícita |

### D2: `working_days` como `ARRAY(Integer)` ISO (Lun=1..Dom=7)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`postgresql.ARRAY(Integer)`** | Lista pequeña de enteros tipados, orden canónico, membership indexable; el dato ES eso | **Elegida** |
| JSONB (como `theme`) | Opaco/no tipado; `theme` es un blob que el backend no interpreta — aquí sí valida | Rechazada |
| Máscara de bits (7 bits) | Compacta pero opaca, difícil de validar/leer, no obvia | Rechazada |

Los tests corren sobre Postgres (JSONB + GIN trgm ya en modelos), así que `ARRAY`
es válido en `create_all` (conftest) y Alembic.

### D3: `working_hours_per_day` como `Numeric(4,2)`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`Numeric(4,2)`** | Soporta medias jornadas (7.5, 8.5) sin drift de float; rango ≤24.00 | **Elegida** |
| `Integer` | Más simple pero no expresa 7.5h (jornadas reales) | Rechazada |

### D4: Módulo nuevo `work_calendar` para el resolver

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Módulo `app/modules/work_calendar/` (resolver + repo + schemas + router)** | Screaming Architecture: la capacidad transversal (lee org + projects) grita su nombre; no ensucia projects/organizations | **Elegida** |
| Función suelta en `projects` | La resolución cruza organizations→projects; no pertenece a un solo módulo | Rechazada |

Las columnas viven en los modelos dueños (`organizations`, `projects`); el módulo
nuevo solo aporta resolución + endpoints de la capacidad `work-calendar`.

### D5: Resolución del raíz por CTE recursivo ascendente (una query)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **CTE recursivo hacia arriba** (base = proyecto; term = join a `parent_project_id`; se toma el nodo con `parent_project_id IS NULL`), acotado por `PROJECT_HIERARCHY_MAX_DEPTH` | Un round-trip; interfaz cacheable; mismo estilo que `subtree_height` | **Elegida** |
| Loop de queries (`ancestor_ids`) | Simple y profundidad <5, pero N round-trips; el patrón CTE ya existe en el repo | Rechazada |

### D6: Sin enum `Weekday` — `int` plano + validación Pydantic

Los días son `int` ISO validados en el schema (1..7); un `SAEnum` dentro de `ARRAY`
añade fricción por cero ganancia (el rango es trivial). Constantes de módulo:
`DEFAULT_HOURS_PER_DAY = Decimal("8")`, `DEFAULT_WORKING_DAYS = [1,2,3,4,5]`.

## Data Flow

    resolve(org_id, project_id)
        │
        ▼  CTE ascendente → nodo raíz del árbol (una query)
    root.override (working_hours/working_days no nulos)? ── sí → source=project_root_override
        │ no
        ▼
    organization.default (NOT NULL, siempre presente) ─────→ source=organization_default
        │ (defensivo: fila sin default)
        ▼
    global default (8h, [1..5]) ──────────────────────────→ source=global_default

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/organizations/models.py` | Modify | + `working_hours_per_day` (Numeric, NOT NULL, default 8), `working_days` (ARRAY int, NOT NULL, default {1..5}) |
| `app/modules/projects/models.py` | Modify | + ambas columnas nullable (override; solo la raíz las rellena) |
| `app/modules/work_calendar/{__init__,schemas,repository,resolver,router}.py` | Create | resolver, CTE al raíz, schemas, endpoints |
| `app/modules/organizations/{schemas,router}.py` | Modify | endpoints calendario empresa (o vía router de work_calendar) |
| `app/modules/projects/{schemas,router}.py` | Modify | override raíz + resuelto en ámbito del proyecto |
| `app/main.py` | Modify | registrar router work_calendar |
| `alembic/versions/0024_add_work_calendar.py` | Create | 1 migración aditiva (empresa NOT NULL+default; proyecto nullable) |
| `backend/tests/**` | Create | contratos TDD cascada + validación + permisos + migración |

## Interfaces / Contracts

```python
class CalendarSource(str, Enum):
    project_root_override = "project_root_override"
    organization_default = "organization_default"
    global_default = "global_default"

class WorkCalendarConfig(BaseModel):          # PUT body y config read
    working_hours_per_day: Decimal = Field(ge=1, le=24)
    working_days: list[int] = Field(min_length=1, max_length=7)
    # validator: cada día 1..7, sin duplicados, retorna orden ascendente canónico

class ResolvedCalendar(BaseModel):
    working_hours_per_day: Decimal
    working_days: list[int]
    source: CalendarSource

class WorkCalendarResolver:
    async def resolve(org_id, project_id) -> ResolvedCalendar
```

Endpoints (envelope `{data, message, meta}`):

- `GET /organizations/me/work-calendar` — cualquier miembro; config de empresa.
- `PUT /organizations/me/work-calendar` — `require_admin` (RBAC ADMIN).
- `GET /projects/{id}/work-calendar` — cualquier miembro; override crudo (`null` si no-raíz o sin override).
- `PUT /projects/{id}/work-calendar` — `require_role(admin, manager)`; **solo raíz** (`override_requires_root` 422 si tiene padre); permite limpiar a `null` (heredar).
- `GET /projects/{id}/work-calendar/resolved` — cualquier miembro; `ResolvedCalendar`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Validación: horas 1-24 (acepta 7.5, rechaza 0/25); días no vacío, 1-7, duplicado rechazado, orden canónico devuelto | `WorkCalendarConfig` |
| Unit/Integration | Cascada: hijo→override raíz; raíz con fin de semana; sin override→default empresa; global como último eslabón; resuelto a cualquier profundidad | `WorkCalendarResolver` + fixtures árbol (cambio 27) |
| Integration | Permisos: GET abierto; PUT empresa ADMIN (403 otros); PUT proyecto admin/manager (403 member); `override_requires_root` 422 en no-raíz | `client` |
| Migration | upgrade backfilla defaults de empresa + columnas proyecto nullable; downgrade elimina; reversible | Alembic up/down |
| Regresión | scoping multi-tenant: el resuelto nunca cruza `organization_id` | suite completa |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación
de ejecutables ni integración de procesos. Riesgo de dominio (representación de días,
override en no-raíz) mitigado en D2/D5 y la regla solo-raíz.

## Migration / Rollout

`0024_add_work_calendar.py`: `organizations` recibe ambas columnas `NOT NULL` con
`server_default` (`8` y `'{1,2,3,4,5}'`) → backfill implícito de filas existentes;
`projects` recibe ambas `nullable` sin default. `downgrade()` elimina las cuatro
columnas — aditivo y reversible, sin pérdida de datos de negocio. **Numeración**: se
planifica `0024` tras la cadena esperada 25→26→27 (26 reserva 0021, 27 reserva
0022/0023); el head real en disco es `0020`, así que `down_revision` se **reancla al
head real** verificando `alembic current` en apply (mismo patrón que el design 27).

## Open Questions

- [ ] Ninguna bloqueante. Si 26/27 renumeran su migración, ajustar `down_revision` de `0024` al head real antes de apply.
