# estimation Specification

## Purpose

Normaliza la conversión de estimaciones expresadas en semanas/días/horas (`w/d/h`)
a horas persistidas, y el formateo inverso de horas a la unidad mayor alcanzada,
usando SIEMPRE el `ResolvedCalendar` del proyecto (cambio 28). Vive en
`app/modules/work_calendar/estimation.py` como funciones puras
(`estimate_to_hours`, `format_hours`), sin importar `tasks`, para que
`tasks` (delta de este cambio) y futuros consumidores (import Jira, cambios
40/41) lo reutilicen sin duplicar la tabla de conversión ni acoplarse entre sí.

## Requirements

### Requirement: Gramática del texto de estimación

El parser DEBE aceptar expresiones compuestas por tokens `Nw`, `Nd`, `Nh`
(semanas, días, horas), separados por uno o más espacios, en orden estricto
mayor→menor unidad (`w` antes de `d` antes de `h`), con unidades omitibles
pero NUNCA repetidas. `N` DEBE admitir enteros y decimales con punto (`1.5d`).
Cualquier expresión con unidad desconocida, unidad repetida, orden invertido,
número negativo o vacío DEBE rechazarse con un error de validación claro (422).

#### Scenario: Expresión completa válida
- DADO el texto `"2w 3d 4h"`
- CUANDO se parsea
- ENTONCES se acepta como 2 semanas + 3 días + 4 horas

#### Scenario: Expresión con decimales y una sola unidad
- DADO el texto `"1.5d"`
- CUANDO se parsea
- ENTONCES se acepta como 1.5 días

#### Scenario: Unidad repetida rechazada
- DADO el texto `"1d 2d"`
- CUANDO se parsea
- ENTONCES se rechaza con 422 y un mensaje claro

#### Scenario: Orden invertido rechazado
- DADO el texto `"4h 3d"`
- CUANDO se parsea
- ENTONCES se rechaza con 422 (el orden DEBE ser mayor→menor)

#### Scenario: Unidad desconocida o número inválido rechazado
- DADO el texto `"3x"` o `"-2h"`
- CUANDO se parsea
- ENTONCES se rechaza con 422 y no se persiste nada

### Requirement: Conversión a horas con el calendario del proyecto

`estimate_to_hours(expr, ResolvedCalendar) -> Decimal` DEBE convertir usando
`1d = working_hours_per_day` y `1w = len(working_days) × working_hours_per_day`
del `ResolvedCalendar` resuelto para el proyecto de la tarea. El resultado
SIEMPRE se expresa y persiste en horas, sin importar el calendario recibido.

#### Scenario: Conversión con calendario estándar (8h, L-V)
- DADO un `ResolvedCalendar` con `working_hours_per_day=8`, `working_days=[1,2,3,4,5]`
- CUANDO se convierte `"1w 2d 4h"`
- ENTONCES el resultado es `60` horas (`1×40 + 2×8 + 4`)

#### Scenario: Conversión con calendario de equipo con fin de semana
- DADO un `ResolvedCalendar` con `working_hours_per_day=10`, `working_days=[1,2,3,4,5,6]` (6 días)
- CUANDO se convierte `"1w"`
- ENTONCES el resultado es `60` horas (`6×10`), distinto del resultado con el calendario estándar

### Requirement: Formateo por unidad mayor alcanzada con resto

`format_hours(hours, ResolvedCalendar) -> str` DEBE expresar el valor en la
unidad mayor alcanzada según el mismo calendario, mostrando el resto en
unidades menores y omitiendo componentes en cero.

#### Scenario: Formateo solo en horas
- DADO un calendario de 8h/día y un valor de `6` horas
- CUANDO se formatea
- ENTONCES el resultado es `"6h"`

#### Scenario: Formateo en días con resto en horas
- DADO un calendario de 8h/día y un valor de `26` horas
- CUANDO se formatea
- ENTONCES el resultado es `"3d 2h"` (`24h = 3d`, resto `2h`)

#### Scenario: Formateo en semanas con resto en días y horas
- DADO un calendario de 8h/día, `working_days` de 5 días, y un valor de `60` horas
- CUANDO se formatea
- ENTONCES el resultado es `"1w 2d 4h"`

#### Scenario: Formateo exacto omite unidades en cero
- DADO un calendario de 8h/día y un valor de `40` horas (equivalente exacto a 1 semana)
- CUANDO se formatea
- ENTONCES el resultado es `"1w"`, sin `0d 0h`

### Requirement: Contrato de ida y vuelta estable entre calendarios distintos

Para cualquier `ResolvedCalendar` válido, encadenar `format_hours(estimate_to_hours(expr, cal), cal)`
DEBE preservar el valor en horas sin pérdida (mismo total, aunque el texto de
salida no reproduzca literalmente el texto de entrada cuando hay unidades
redundantes). El contrato DEBE verificarse con al menos dos calendarios
distintos: uno estándar (8h, L-V) y uno de equipo con fin de semana.

#### Scenario: Ida y vuelta estable con calendario estándar
- DADO el calendario A (8h/día, `working_days=[1,2,3,4,5]`)
- CUANDO se convierte `"1w 2d 4h"` a horas y se formatea de vuelta con el calendario A
- ENTONCES el total en horas se preserva (`60`) y el texto resultante es `"1w 2d 4h"`

#### Scenario: Ida y vuelta estable con calendario de equipo con fin de semana
- DADO el calendario B (10h/día, `working_days=[1,2,3,4,5,6,7]`, 7 días)
- CUANDO se convierte `"1w"` a horas y se formatea de vuelta con el calendario B
- ENTONCES el total en horas se preserva (`70`) y el texto resultante es `"1w"`, distinto del resultado que produciría el calendario A para el mismo total

### Requirement: Frontera de reutilización para consumidores futuros

`estimate_to_hours`/`format_hours` DEBEN ser funciones puras del módulo
`work_calendar`, sin importar `tasks` ni ningún módulo de dominio, para que
cualquier consumidor futuro (import Jira, cambios 40/41) las reutilice
pasando su propio `ResolvedCalendar` sin duplicar la tabla de conversión.
Este cambio NO implementa la integración concreta de Jira.

#### Scenario: El módulo estimation no depende de tasks
- DADO el módulo `app/modules/work_calendar/estimation.py`
- CUANDO se revisan sus imports
- ENTONCES no importa nada de `app.modules.tasks` (sin ciclo)

#### Scenario: Consumidor externo obtiene el mismo resultado que tasks
- DADO un módulo distinto de `tasks` que invoca `estimate_to_hours` con el mismo texto y el mismo `ResolvedCalendar` que usaría `tasks`
- CUANDO compara su resultado con el que `tasks` persistiría
- ENTONCES ambos resultados son idénticos

## Referencias

- `openspec/changes/34-estimacion-normalizada/proposal.md`
- `openspec/changes/28-calendario-laboral/specs/work-calendar/spec.md` (`ResolvedCalendar`, `WorkCalendarResolver.resolve`)
- `openspec/specs/tasks/spec.md` (delta modificado por este cambio)
