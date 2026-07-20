# Proposal: 28 · Calendario laboral configurable (empresa → equipo → proyecto)

## Intent

Las estimaciones w/d/h y la curva de avance esperado necesitan saber cuántas horas rinde un día y qué días de la semana se trabaja. Hoy no existe: ni `Organization` (`app/modules/organizations/models.py`) ni `Project` (`app/modules/projects/models.py`) guardan `working_hours_per_day` ni `working_days`. Sin este dato, la conversión (cambio 34) y la distribución por días laborales (cambio 35) tendrían que asumir 8h/L-V a fuego, y equipos como soporte (fin de semana) o desarrollo quedarían mal medidos. Este cambio introduce el calendario laboral con default de empresa y override por equipo (decisión 1 de OLA 4), reutilizando "equipo = proyecto raíz" (`project_kind`, cambio 27).

## Scope

### In Scope
- Config de calendario a nivel EMPRESA: `working_hours_per_day` (default 8) y `working_days` (default L-V) en `organizations`.
- Override por EQUIPO = proyecto RAÍZ: columnas nullable en `projects`; solo la raíz las usa; los hijos heredan.
- Servicio de resolución en cascada `WorkCalendarResolver`: proyecto → sube por `parent_project_id` hasta la raíz → override de la raíz → default de empresa → default global (8h, L-V). Resuelve por query (árbol poco profundo), con interfaz que permita cachear luego para 34/35.
- API: leer/editar calendario de la empresa (admin) y de la raíz/equipo (admin/manager); exponer el calendario RESUELTO de CUALQUIER proyecto (fuente + valores) para el front y los cambios 34/35.
- `working_days` como array de enteros ISO 8601 (Lun=1..Dom=7). Validaciones: `1 ≤ hours ≤ 24`, ≥1 día, días 1-7 sin duplicados.
- TDD: cascada hijo→raíz→empresa→default; override de equipo con fin de semana; validaciones; resuelto en cualquier profundidad.

### Out of Scope
- Festivos/calendario de excepciones, husos horarios, jornadas partidas, calendarios por persona (documentados como futuro).
- El cálculo de conversión (34) y de avance esperado (35): este cambio solo aporta el dato.
- Frontend de edición (llega con las vistas de las fases 4.2/4.3).

## Capabilities

### New Capabilities
- `work-calendar`: config de horas/días laborales (empresa + override de equipo raíz), resolución en cascada y API de lectura/edición + calendario resuelto.

### Modified Capabilities
- `projects`: columnas nullable de override de calendario en el proyecto raíz; el calendario resuelto se expone en el ámbito del proyecto.

## Approach

Persistir como COLUMNAS (no tabla aparte): `organizations` recibe los dos campos con default; `projects` recibe los dos campos nullable (solo la raíz los rellena). Tradeoff: dos campos escalares encajan en el patrón aditivo-nullable ya usado (`code`, `theme`) y evitan joins en la cascada; una tabla `work_calendar` dedicada solo se justifica cuando entren festivos/husos (futuro) — se deja como vía de extensión explícita. La cascada se resuelve en un service con un CTE recursivo (raíz + override) más el default de empresa; sin caché en el MVP (profundidad acotada), con la puerta abierta a cachear por `(org_id, root_project_id)` cuando 34/35 lo llamen en caliente.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/organizations/{models,schemas,router,repository}.py` | Modified | Campos + endpoint calendario empresa |
| `backend/app/modules/projects/{models,schemas,router,repository}.py` | Modified | Override nullable en raíz + calendario resuelto |
| `backend/app/modules/work_calendar/*` (o dentro de projects) | New | `WorkCalendarResolver`, schemas, router |
| `backend/app/shared/enums.py` | Modified | Weekday ISO (si se enumera) |
| `backend/alembic/versions/` | New | 1 migración aditiva (columnas empresa + proyecto) |
| `backend/tests/**` | New | Contratos TDD de cascada y validación |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Override aplicado en nodo no-raíz | Media | Validar que solo la raíz guarda override; hijos leen resuelto |
| Cascada lenta en árboles profundos | Baja | CTE recursivo en una query; interfaz cacheable para 34/35 |
| Representación de `working_days` inconsistente | Media | Estándar único ISO Lun=1..Dom=7 + validación central |
| Migración choca con cadena 25→26→27 | Media | Encadenar tras el head real (esperado 0024); verificar en design/apply |
| 34/35 asumen 8h/L-V si el resolver falla | Media | Default global explícito y probado como último eslabón |

## Rollback Plan

Migración aditiva y reversible: el downgrade elimina las columnas de `organizations` y `projects`. No hay borrado de datos preexistentes (columnas nuevas), así que revertir es seguro; el default global 8h/L-V mantiene el comportamiento previo si se desactiva la lectura.

## Dependencies

- `27-plantillas-idempotentes`: aporta `project_kind`/árbol para definir "equipo = proyecto raíz". Applies secuenciales 25 → 26 → 27 → 28.
- `25-multiempresa-scoping`: el calendario se lee/escribe siempre scoped por `organization_id`.

## Success Criteria

- [ ] Empresa guarda default de calendario; equipo raíz puede sobreescribirlo; hijos heredan.
- [ ] `WorkCalendarResolver` resuelve hijo→raíz→empresa→default (8h, L-V) en cualquier profundidad.
- [ ] API expone el calendario RESUELTO de cualquier proyecto con su fuente, consumible por 34/35.
- [ ] Validaciones: 1-24h, ≥1 día, días ISO 1-7 sin duplicados.
- [ ] Migración aditiva y reversible; suite backend en verde.

## Proposal question round

Supuestos a validar con el usuario: (1) el override vive SOLO en el proyecto raíz (`project_kind=area`/equipo) y los hijos nunca guardan calendario propio, solo heredan; (2) `working_days` se modela como array de enteros ISO (Lun=1..Dom=7) y el default global es 8h/L-V; (3) editar el calendario de empresa es rol ADMIN y el del equipo raíz ADMIN/MANAGER; (4) persistimos como columnas (no tabla `work_calendar`) y aplazamos festivos/husos/jornadas partidas a un cambio futuro; (5) sin caché en el MVP, resolviendo por query. Se puede correr una segunda ronda si el usuario quiere revisar la representación de días o la política de caché para 34/35.
