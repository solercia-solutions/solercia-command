# Proposal: 34 · Estimación normalizada (w/d/h → horas con calendario laboral)

## Intent

Hoy la conversión w/d/h → horas vive SOLO en el frontend con factores a fuego
(`8h/día`, `5d/semana` en `frontend/src/shared/lib/estimation.ts`). El backend
acepta únicamente `estimation_hours` numérico (`tasks/schemas.py`) y no convierte
nada: la API directa y la futura importación Jira (cambios 40/41) persisten lo que
reciban, sin blindaje. La BD ya guarda horas (`tasks/models.py:113`,
`Numeric(7,2)`), pero equipos con jornada distinta o que trabajan fin de semana
(soporte) ven despliegues errados porque el factor está clavado. Este cambio
centraliza conversión y formateo en el backend usando el calendario RESUELTO del
cambio 28.

## Scope

### In Scope
- Parser único backend de expresiones (`"2w 3d"`, `"6h"`, `"1.5d"`) → horas con el
  calendario resuelto del proyecto: `1d = hours_per_day`;
  `1w = len(working_days) × hours_per_day`.
- Formateador único de despliegue (mayor unidad alcanzada: `6h`, `Xd Yh`,
  `Xw Yd Zh`) con el mismo calendario.
- API: `estimation_input: str?` opcional en `TaskCreate`/`TaskUpdate` (cuando viene,
  el string manda y se convierte server-side); `estimation_hours` numérico sigue
  aceptado (retrocompat/API directa). Campo calculado `estimation_display` en
  `TaskRead`.
- Blindar POST/PATCH tasks y el front (envía string, deja de convertir a fuego). El
  converter queda listo para que Jira import (40/41) lo consuma.
- TDD: contrato de conversión ida y vuelta con calendarios distintos (8h/L-V vs.
  equipo con fin de semana).

### Out of Scope
- Migración / columna nueva: `estimation_hours` ya existe; `estimation_input` y
  `estimation_display` son transitorios (sin schema).
- Importación Jira real (cambios 40/41): solo se deja el converter compartido.
- Estimación en puntos (`estimation_points`): sin cambios.
- Edición del calendario laboral (cambio 28).

## Capabilities

### New Capabilities
- `estimation`: contrato de normalización — parser expr→horas con calendario,
  precedencia input/numérico, formateador único de despliegue y blindaje de los
  caminos de escritura.

### Modified Capabilities
- `tasks`: `TaskCreate`/`TaskUpdate` aceptan `estimation_input`; `TaskRead` expone
  `estimation_display` calculado.

## Approach

Funciones puras en el módulo `work_calendar` (dueño del calendario):
`estimate_to_hours(expr, ResolvedCalendar) -> Decimal` y
`format_hours(hours, ResolvedCalendar) -> str`, parametrizadas por
`ResolvedCalendar` (no importan `tasks`, sin ciclo; Screaming: la unidad de
horas/días la posee quien conoce el calendario). El service de tasks resuelve el
calendario del proyecto UNA vez por respuesta (batch en memoria, sin query por
fila), convierte al escribir y formatea al leer. El backend es la ÚNICA fuente de
conversión/formateo; el front envía el string crudo y pinta `estimation_display`.
`estimation.ts` queda como eco local de entrada (sin ser fuente de verdad).

Tradeoffs decididos: (1) converter en `work_calendar` sobre `shared/` o `tasks/`,
para que 34/35/40/41 importen un único punto sin acoplar a tasks; (2) display en
BACKEND sobre pipe Angular, porque un pipe cliente re-implementaría la tabla de
conversión y re-introduciría el drift actual; (3) `estimation_input` tiene
precedencia sobre `estimation_hours` cuando ambos llegan (regla documentada); input
vacío limpia, input inválido → 422.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `app/modules/work_calendar/estimation.py` | New | `estimate_to_hours` + `format_hours` (puras, sobre `ResolvedCalendar`) |
| `app/modules/tasks/{schemas,service}.py` | Modified | `estimation_input` in; `estimation_display` out; convierte/formatea vía resolver |
| `frontend/src/widgets/task-modal/*`, `shared/lib/estimation.ts` | Modified | Envía string; renderiza `estimation_display`; deja de fijar 8h/5d |
| `backend/tests/**` | New | Contratos TDD ida y vuelta con calendarios distintos + precedencia + inválidos |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Divergencia front/back de la conversión | Media | Backend fuente única; front solo pinta `estimation_display` |
| Resolver por fila degrada listados | Media | Resolver calendario 1 vez por proyecto/respuesta (batch en memoria) |
| Round-trip inexacto con horas no divisibles | Media | Rollup a mayor unidad + resto decimal; contrato TDD de ida y vuelta |
| Precedencia input/numérico ambigua | Baja | Regla explícita: input manda; vacío limpia; inválido 422 |
| 28 sin aplicar al iniciar 34 | Media | `depends_on: 28`; el converter recibe `ResolvedCalendar`, no resuelve solo |

## Rollback Plan

Sin migración: es cambio de código (campos transitorios + funciones puras).
Revertir = quitar `estimation_input`/`estimation_display` y el módulo
`estimation.py`; el front vuelve a convertir localmente. `estimation_hours`
persistido no se toca, así que no hay pérdida ni datos que restaurar.

## Dependencies

- `28-calendario-laboral`: aporta `ResolvedCalendar(working_hours_per_day,
  working_days, source)` vía `WorkCalendarResolver.resolve(org_id, project_id)`.
- Consumidores futuros: `40/41-jira-import` usarán el mismo converter.

## Success Criteria

- [ ] Todo camino de escritura (form, API, base para import) convierte w/d/h →
      horas ANTES de persistir, con el calendario del proyecto.
- [ ] Formateador único: `6h`, `Xd Yh`, `Xw Yd Zh` según la mayor unidad alcanzada.
- [ ] `estimation_input` manda sobre `estimation_hours`; vacío limpia; inválido 422.
- [ ] TDD ida y vuelta verde con 8h/L-V y con equipo de fin de semana.
- [ ] Suite backend en verde; sin migración nueva.

## Proposal question round

Supuestos a validar: (1) el converter vive en `work_calendar` como funciones puras
sobre `ResolvedCalendar` (no en `shared/` ni `tasks/`); (2) el despliegue es un campo
calculado en el BACKEND (`estimation_display`), no un pipe Angular, para eliminar el
drift; (3) cuando llegan `estimation_input` y `estimation_hours` juntos, el string
manda; input vacío limpia y un input inválido responde 422; (4) sin migración
(campos transitorios); (5) `estimation_points` queda fuera. Se puede correr una
segunda ronda si el usuario quiere revisar la precedencia o mover el converter a
`shared/`.
