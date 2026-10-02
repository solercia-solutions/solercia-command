# Delta for boards

> Base: `openspec/specs/boards/spec.md`. Este delta AGREGA la bandera
> `excluded_from_progress` como propiedad configurable de `BoardColumn`
> (migración `0026`), el sembrado idempotente de las 7 columnas de PANDORA
> vía `ensure_board_columns` (nunca `add_column`, que slugifica —
> deuda ya reconocida en `openspec/specs/boards/spec.md:145`), y una
> invariante nueva que congela el orden de PANDORA (`_i4_seguridad_columns`
> solo protege a SEGURIDAD). El requisito «Configuración runtime de
> columnas» (`:83-103` de la línea base) NO cambia.

## ADDED Requirements

### Requirement: Bandera excluded_from_progress en BoardColumn

`BoardColumn` DEBE tener la columna `excluded_from_progress BOOLEAN NOT NULL DEFAULT false`, agregada por la migración Alembic aditiva `0026` (`down_revision="0025"`) y espejada en `BoardColumn.__table_args__`/modelo ORM, porque el harness de pruebas construye el esquema con `Base.metadata.create_all`. Cuando una columna tiene `excluded_from_progress=true`, toda tarea asignada a ella queda excluida del denominador del roll-up de avance de la capacidad `project-hierarchy` (ver delta MODIFIED de esa capacidad en este mismo cambio).

#### Scenario: Migración agrega la columna sin afectar filas existentes

- DADO un esquema con `BoardColumn` ya existentes antes de la migración `0026`
- CUANDO se aplica `alembic upgrade 0026`
- ENTONCES las columnas existentes conservan sus valores y `excluded_from_progress` queda en `false` para todas

#### Scenario: Downgrade elimina la columna sin pérdida de filas

- DADO el esquema en la revisión `0026` con columnas marcadas y sin marcar
- CUANDO se aplica `alembic downgrade -1`
- ENTONCES `excluded_from_progress` desaparece del esquema y ninguna fila de `board_columns` se pierde

#### Scenario: El esquema de create_all coincide con el de la migración

- DADO un motor de pruebas construido con `Base.metadata.create_all`
- CUANDO se compara su esquema contra el que resulta de `alembic upgrade head`
- ENTONCES ambos declaran la misma columna `excluded_from_progress` con el mismo tipo y default sobre `board_columns`

### Requirement: Sembrado idempotente de las 7 columnas de PANDORA

El sistema DEBE sembrar, vía `ensure_board_columns` (NUNCA `add_column`, que slugifica el `status_key`), exactamente las 7 columnas del tablero de PANDORA en este orden exacto: `Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done`, cada una con `status_key` idéntico y verbatim a su nombre visible. `Done` DEBE quedar obligatoriamente en la última posición. Sembrar sobre un board de PANDORA que ya tiene las 7 columnas DEBE ser un no-op.

#### Scenario: Primera siembra crea las 4 columnas faltantes preservando el orden

- DADO el board de PANDORA con únicamente `Backlog, Doing, Done` (estado previo a este cambio)
- CUANDO se ejecuta el sembrado de columnas
- ENTONCES el board queda con las 7 columnas en el orden `Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done`, con `Done` en la última posición

#### Scenario: Segunda siembra sobre un board completo es un no-op

- DADO el board de PANDORA ya con sus 7 columnas
- CUANDO se ejecuta el sembrado de nuevo
- ENTONCES no se crea ninguna columna adicional ni cambia el orden existente

#### Scenario: Los status_key de las columnas nuevas quedan verbatim

- DADO las 4 columnas nuevas sembradas en PANDORA
- CUANDO se inspecciona su `status_key`
- ENTONCES cada `status_key` coincide exactamente con su nombre visible (`"Diferida"`, no `"diferida"`)

### Requirement: Invariante de columnas y orden de PANDORA

DEBE existir una invariante propia — análoga a `_i4_seguridad_columns`, que solo protege a SEGURIDAD — que verifique: el board de PANDORA tiene exactamente 7 `BoardColumn` activas, en el orden `Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done`, con `status_key` verbatim, y `Done` en la posición final. Un fallo de esta invariante DEBE reportarse con código de salida distinto de cero en el script de mantenimiento que la evalúa.

#### Scenario: PANDORA con sus 7 columnas en el orden correcto pasa la invariante

- DADO el board de PANDORA con sus 7 columnas en el orden esperado
- CUANDO se evalúa la invariante
- ENTONCES la invariante se marca como cumplida

#### Scenario: Done fuera de la última posición falla la invariante

- DADO el board de PANDORA con `Done` en una posición distinta de la última, por un fallo inyectado en prueba
- CUANDO se evalúa la invariante
- ENTONCES el script termina con código de salida distinto de cero y el reporte señala la invariante rota

#### Scenario: Un status_key slugificado falla la invariante

- DADO el board de PANDORA con una columna cuyo `status_key` quedó slugificado (por ejemplo `"diferida"` en vez de `"Diferida"`, por un fallo inyectado en prueba)
- CUANDO se evalúa la invariante
- ENTONCES el script termina con código de salida distinto de cero

### Requirement: Banderas de exclusión en Removida y Gestionada aparte de ambos proyectos

Las columnas `Removida` y `Gestionada aparte` DEBEN quedar marcadas `excluded_from_progress=true` tanto en SEGURIDAD como en PANDORA; el resto de las columnas de ambos proyectos (incluidas `Diferida` y `Recurrente`) DEBEN quedar con `excluded_from_progress=false`.

#### Scenario: Removida y Gestionada aparte de SEGURIDAD quedan excluidas

- DADO SEGURIDAD con sus 7 columnas ya sembradas
- CUANDO se aplican las banderas de este cambio
- ENTONCES `Removida` y `Gestionada aparte` de SEGURIDAD quedan con `excluded_from_progress=true`

#### Scenario: Removida y Gestionada aparte de PANDORA quedan excluidas

- DADO PANDORA con sus 7 columnas ya sembradas
- CUANDO se aplican las banderas de este cambio
- ENTONCES `Removida` y `Gestionada aparte` de PANDORA quedan con `excluded_from_progress=true`

#### Scenario: Diferida y Recurrente permanecen dentro del denominador en ambos proyectos

- DADO SEGURIDAD y PANDORA con sus columnas ya marcadas
- CUANDO se inspeccionan `Diferida` y `Recurrente` de cada proyecto
- ENTONCES ambas quedan con `excluded_from_progress=false` en los dos proyectos

## Referencias

- `openspec/specs/boards/spec.md` (línea base, `:83-103` configuración runtime sin cambio, `:145` deuda de slugs vs. literales)
- `openspec/specs/data-maintenance/spec.md:100` (`SEGURIDAD_COLUMNS` literal, precedente de `ensure_board_columns`)
- `backend/app/maintenance/repository.py:392-419` (`ensure_board_columns`, idempotente, `status_key` verbatim)
- `backend/app/maintenance/invariants.py:37-49` (`_i4_seguridad_columns`, patrón de invariante a replicar)
- `openspec/changes/44-importar-checklist-xlsx/{proposal,exploration}.md`
