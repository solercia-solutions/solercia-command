# Design: 29 · Sprint borrador (creación con solo nombre + autonombre)

## Technical Approach

Cambio aditivo, sin migración: `Sprint.status` es `String(20)` validado en el
servicio (`_ALLOWED_STATUSES`) y `start_date`/`end_date` ya son nullable, así que
`draft` se agrega ampliando el whitelist. `create_sprint` deriva el estado de las
fechas presentes (retrocompatible: crear con fechas → `active` de siempre; sin
fechas → `draft`). El nombre se autocalcula con una **función pura**
`next_sprint_name(previous, project_code)`, testeable sin BD; el servicio solo le
inyecta el último sprint por `created_at`. Se añade `POST /sprints/{id}/start`
(espeja `/close`) que valida fechas antes de `draft→active`. El gate sigue leyendo
`get_strategy(project.methodology).sprints_enabled` (sin `if methodology ==`). El
frontend renderiza estado por-badge y acciones contextuales por estado.

## Architecture Decisions

### D1: Autonombre como función pura en `sprints/naming.py`

**Choice**: `next_sprint_name(previous: str | None, project_code: str | None) -> str`,
módulo puro sin I/O. El servicio hace el fetch del último sprint y llama la función.
**Alternatives**: inline en `create_sprint` (no testeable aislado); en el repository
(mezcla persistencia con reglas de dominio).
**Rationale**: TDD directo del algoritmo (constraint `tdd-autoname-consecutive-non-conventional`)
sin fixtures de BD; el servicio orquesta, la función decide.

Algoritmo: última corrida de dígitos vía `re.finditer(r"\d+", previous)[-1]`; se
incrementa preservando ancho con `str(n+1).zfill(len(run))` y se conserva el prefijo
(incluye separador `-`). Sin dígitos → sufijo ` 2` (el existente cuenta como 1). Sin
`previous` → `f"{code} Sprint 1"`; sin `code` → `"Sprint 1"`. Sugerencia editable,
sin unicidad.

**Tabla de verdad** (RED tests):

| `previous` | `project_code` | resultado |
|---|---|---|
| `PANDORA 2026-1` | (cualquiera) | `PANDORA 2026-2` |
| `Sprint 9` | (cualquiera) | `Sprint 10` |
| `Velocidad` | (cualquiera) | `Velocidad 2` |
| `S-09` | (cualquiera) | `S-10` |
| `None` | `SDM` | `SDM Sprint 1` |
| `None` | `None` | `Sprint 1` |

### D2: API — reutilizar `POST /sprints`, `name` opcional + endpoint de sugerencia

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`name` opcional en `SprintCreate` (ausente/vacío → autonombre) + `GET /projects/{id}/sprints/next-name`** | Cero ruptura: clientes que mandan nombre+fechas siguen igual; la UI precarga el nombre sugerido | **Elegida** |
| Endpoint `/sprints:suggest` que devuelve todo el borrador | Más superficie; el POST igual necesita el fallback | Rechazada |

`next-name` es segmento estático (no colisiona con `{sprint_id}/burndown`). El
estado nace `active` si `start_date` y `end_date` vienen ambos, si no `draft`.

### D3: Transiciones — whitelist + `/start`, sin `cancelled`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`_ALLOWED_STATUSES = ("draft","active","closed")`; `POST /sprints/{id}/start` valida fechas** | Consistente con literales actuales; espeja `/close`; aditivo | **Elegida** |
| PATCH genérico de `status` para iniciar | No puede validar fechas ni dar 422 claro; frágil | Rechazada |
| Añadir `cancelled` para descartar draft | No existe hoy; amplía alcance sin pedido | Rechazada — futuro (30/31) |

`start_sprint`: 404 si no existe; 409 `sprint_already_started` si ya `active`; 422 si
`closed`; 422 `sprint_missing_dates` (español) si falta cualquier fecha; si no,
`draft→active`. `update_sprint` amplía el mensaje del whitelist a los tres estados.

### D4: Frontend — badge + acciones contextuales por estado

Un solo punto de decisión estado→acción en la pestaña sprints. Draft: "Añadir
fechas" (modal → `PATCH`) e "Iniciar sprint" (deshabilitado sin ambas fechas, con
tooltip). Active: "Cerrar" (existe). Closed: "Reactivar" (existe). La pestaña
precarga el nombre sugerido vía `next-name` (editable). Dates opcionales → draft.

### D5: Seams para el cambio 30 (backlog agrupado)

`SprintStatus` ya incluye `draft`; `sprintBadgeClass()` y el mapa estado→acción
quedan centralizados y reutilizables. 30 pinta grupos `draft` con el mismo badge y
menú contextual sin re-derivar estados.

## Data Flow

    POST /projects/{id}/sprints {name?, dates?}
        │  _require_sprints_enabled (strategy.sprints_enabled)
        ▼
    name vacío? ── sí → repo.last_by_created_at → next_sprint_name(prev, project.code)
        │ no (usa name)                              (función pura)
        ▼
    status = active si (start_date && end_date) else draft → persist

    POST /sprints/{id}/start → fechas presentes? ─ no → 422 español
        │ sí → draft→active

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/sprints/naming.py` | Create | `next_sprint_name` puro |
| `backend/app/modules/sprints/service.py` | Modify | `draft` en whitelist; estado derivado de fechas; `start_sprint`; usa `next_sprint_name` |
| `backend/app/modules/sprints/schemas.py` | Modify | `SprintCreate.name` opcional; `SprintNextName` |
| `backend/app/modules/sprints/router.py` | Modify | `GET .../sprints/next-name`; `POST /sprints/{id}/start` |
| `backend/app/modules/sprints/repository.py` | Modify | `last_for_project(by created_at)` |
| `backend/tests/**` | Create | tabla de verdad + iniciar sin fechas + retrocompat |
| `frontend/.../project-workspace.component.ts` | Modify | badge draft + acciones contextuales + prefill |
| `frontend/src/entities/workspace/workspace.service.ts` | Modify | `startSprint`, `nextSprintName` |
| `frontend/src/entities/workspace/workspace.model.ts` | Modify | `SprintStatus += 'draft'`; `name?` en payload |
| `frontend/src/assets/i18n/es-CO.json` | Modify | textos (tuteo) |

## Interfaces / Contracts

```python
def next_sprint_name(previous: str | None, project_code: str | None) -> str: ...

class SprintCreate(BaseModel):
    name: str | None = Field(default=None, max_length=160)  # vacío → autonombre
    ...

class SprintNextName(BaseModel):
    name: str
```

Endpoints (envelope `{data, meta}`):
- `GET /projects/{id}/sprints/next-name` — miembro; `{data: {name}}`.
- `POST /projects/{id}/sprints` — `name` opcional; 201.
- `POST /sprints/{id}/start` — `draft→active`; 422 español sin fechas; 409 si ya iniciado.
- `PATCH /sprints/{id}` — reutilizado para "Añadir fechas".

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `next_sprint_name`: los 6 casos de la tabla de verdad | función pura |
| Integration | Crear sin nombre → autonombre; sin fechas → `draft`; con fechas → `active` (retrocompat) | `client` |
| Integration | `/start` sin fechas → 422 español; con fechas → `active`; ya iniciado → 409; metodología sin sprints → 422 | `client` |
| Regresión | `sprints_enabled` gate; scoping multi-tenant; `/close` intacto | suite completa |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación
de ejecutables ni integración de procesos. Riesgo de dominio (regex de consecutivo,
inicio sin fechas) mitigado en D1/D3 y cubierto por TDD.

## Migration / Rollout

No migration required. Solo código: `draft` es valor libre del `String(20)`; el
default de columna sigue `active`. Revertir el commit restaura el comportamiento;
sprints creados `draft` se leen como abiertos (no `closed`) tras revertir.

## Open Questions

- [ ] Ninguna bloqueante. Descartar un draft (`cancelled`/DELETE) queda para 30/31.
