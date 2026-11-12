# Design: 34 · Estimación normalizada (w/d/h → horas con calendario laboral)

## Technical Approach

El backend se vuelve la ÚNICA fuente de conversión y formateo. Dos funciones puras
en el módulo dueño del calendario (`work_calendar`, cambio 28) reciben un
`ResolvedCalendar` y NO importan `tasks` (sin ciclo, Screaming): la unidad
horas/días la posee quien conoce el calendario. `TaskService` resuelve el
calendario del proyecto UNA vez por request (memo en memoria), convierte
`estimation_input` → horas al escribir y formatea `estimation_display` al leer. El
front deja de fijar 8h/5d: envía el string crudo y pinta el display del backend.

## Architecture Decisions

### D1: Punto de inyección en la escritura — service, no validator Pydantic

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Convertir en `TaskService.create/update`** | Ya resuelve `project`; la resolución del calendario es async y necesita `db` | **Elegida** |
| `field_validator` en el schema | Un validator Pydantic no tiene contexto async ni sesión para resolver el calendario | Rechazada |

### D2: `estimation_display` calculado en `_to_read`, calendario memoizado por request

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Resolver calendario 1 vez/request + memo por `project_id`; enriquecer en `_to_read`** | Listados single-project → una resolución; multi-proyecto (dashboard) cachea por proyecto, sin N+1 | **Elegida** |
| Resolver por fila | N+1 en backlog/board | Rechazada |
| Pipe Angular | Re-implementa la tabla de conversión → re-introduce el drift | Rechazada |

### D3: Contrato de las funciones puras (Decimal, sin floats)

`parse_estimation` valida contra gramática regex y hace aritmética `Decimal`
(`1d = hours_per_day`; `1w = len(working_days) × hours_per_day`). Empty lo maneja el
service (limpia). `format_estimation` hace rollup a la mayor unidad + resto decimal.

### D4: Precedencia input/numérico

`estimation_input` (str) manda sobre `estimation_hours`. Vacío/whitespace → `None`
(limpia). Inválido → `AppException` 422. En `update`, presente en `changes` gana.

### D5: Seam Jira (40/41) — segundos, NO gramática

Jira entrega `timeoriginalestimate` en segundos. `seconds_to_hours(sec) -> Decimal`
(= `sec / 3600`) vive junto al converter; NO usa la gramática w/d/h. Sólo se deja
la interfaz lista; 40/41 la consumen.

## Data Flow

    WRITE  input:str ─┐
                      ├─ TaskService._resolve_calendar(memo) ─→ parse_estimation ─→ Decimal hours ─→ estimation_hours (persist)
    numeric hours ────┘  (input gana; vacío→None; inválido→422)

    READ   estimation_hours ─→ _to_read(calendar) ─→ format_estimation ─→ estimation_display (respuesta)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/work_calendar/estimation.py` | Create | `parse_estimation`, `format_estimation`, `seconds_to_hours`, `InvalidEstimationError` (puras, sobre `ResolvedCalendar`) |
| `app/modules/tasks/schemas.py` | Modify | `estimation_input: str \| None` en `TaskCreate`/`TaskUpdate`; `estimation_display: str \| None` en `TaskRead` |
| `app/modules/tasks/service.py` | Modify | `_resolve_calendar` memoizado; convierte input→horas en create/update; `_to_read` recibe calendario y setea display |
| `frontend/src/widgets/task-modal/task-modal.component.ts` | Modify | Envía `estimation_input` (string "2d 3h"); pinta `estimation_display` del back; deja de pre-parsear a horas |
| `frontend/src/shared/lib/estimation.ts` | Modify | Quita el 8h/5d como fuente de verdad; queda como eco local de entrada |
| `frontend/src/entities/task/*` | Modify | Payload write: `estimation_input`; read model: `estimation_display` |
| `backend/tests/**` | Create | Contratos TDD ida y vuelta + precedencia + inválidos + no-N+1 |

## Interfaces / Contracts

```python
# app/modules/work_calendar/estimation.py
class InvalidEstimationError(ValueError): ...

def parse_estimation(text: str, calendar: ResolvedCalendar) -> Decimal:
    """'1w 2d 4h' → horas Decimal. 1d=hpd; 1w=len(days)*hpd.
    Acepta '2.5h'/'1.5d' (coma o punto). Inválido → InvalidEstimationError."""

def format_estimation(hours: Decimal, calendar: ResolvedCalendar) -> str:
    """Rollup a mayor unidad: 26h/8h → '3d 2h'; 60h/(8h,L-V) → '1w 2d 4h';
    2.5 → '2.5h'; 0 → '0h'; None → ''."""

def seconds_to_hours(seconds: int) -> Decimal:  # seam 40/41 (Jira)
    """Conversión directa (sec/3600); NO usa gramática w/d/h."""
```

`TaskService`: `WorkCalendarResolver(db).resolve(org_id, project_id)` memoizado en
`self._cal_cache: dict[UUID, ResolvedCalendar]` (vida = request).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Round-trip cal A (8h,L-V): `parse('1w 2d 4h')==60` y `format(60)=='1w 2d 4h'`; cal B (fin de semana, hpd distinto) estable; `2.5h`; `26h→'3d 2h'`; inválido → error | funciones puras |
| Unit | `seconds_to_hours(9000)==Decimal('2.5')` | pura |
| Integration | POST/PATCH: `estimation_input` gana sobre `estimation_hours`; vacío limpia; inválido → 422 | `client` |
| Integration | `estimation_display` en get/list/subtasks; listado single-project resuelve calendario 1 vez (no N+1) | `client` + spy resolver |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación
de ejecutables ni integración de procesos. El parseo del string es validación de
dominio (regex + Decimal), sin `eval`; inválido responde 422.

## Migration / Rollout

Sin migración. `estimation_hours` ya existe (`Numeric(7,2)`); `estimation_input` y
`estimation_display` son transitorios. Rollback = quitar los dos campos y
`estimation.py`; el front vuelve a convertir localmente; datos intactos.

## Open Questions

- [ ] Apply DEBE ir después de 28: el módulo `app/modules/work_calendar/` (resolver +
      `ResolvedCalendar`) aún no existe en disco. `depends_on: 28` ya lo declara.
- [ ] Dashboard (vista ejecutiva) agrega tareas multi-proyecto y tiene su propio
      `_to_read`; en MVP no puebla `estimation_display` (muestra horas numéricas). Si
      se enriquece luego, reusar el memo por `project_id` para no caer en N+1.
