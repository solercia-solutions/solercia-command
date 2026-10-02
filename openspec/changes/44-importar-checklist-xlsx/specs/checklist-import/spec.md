# checklist-import Specification

> **Origen**: cambio [44-importar-checklist-xlsx](../../../changes/44-importar-checklist-xlsx/)

## Propósito

Importar de forma idempotente el checklist real de tareas de seguridad de la información (`CHECKLIST_TAREAS.xlsx`, hoja `Checklist Tareas`) hacia los proyectos SEGURIDAD y PANDORA de la organización SDMUJER, con una fase de consolidación revisable por CSV antes de escribir cualquier fila, usuarios sin credenciales para responsables sin acceso al sistema, etiquetado en dos niveles, y la garantía de que una segunda ejecución con el mismo archivo y el mismo CSV no produce ningún cambio.

## Alcance

Este cambio NO agrega endpoints HTTP. La importación es un proceso por lotes ejecutado desde la línea de comandos, dueño de su propia transacción, con dos modos de ejecución.

| Bandera | Obligatoria | Descripción |
|---|---|---|
| `--file` | Sí | Ruta al archivo `.xlsx` de origen |
| `--dry-run` | No (modo por defecto) | Analiza y propone sin escribir ninguna fila |
| `--csv-out` | No | Ruta de salida del CSV de consolidación propuesto (por defecto `checklist_consolidation.csv`) |
| `--execute` | No | Aplica las decisiones del CSV; EXIGE `--csv-in` |
| `--csv-in` | Solo con `--execute` | Ruta del CSV revisado por el usuario |
| `--update-existing` | No | Habilita la actualización de tareas ya ancladas, limitada a la lista blanca |
| `--database-url` | No | Cadena de conexión para ejecutar desde el host |

Módulo `backend/app/importers/checklist/`: `parser.py` (mecánica del XLSX, sin BD), `mapping.py` (funciones puras fila → intención), `consolidation.py` (escritura, lectura y validación del CSV), `importer.py` (caso de uso dueño de la única transacción) y `report.py` (reporte final). CLI en `backend/scripts/import_checklist.py`.

Sin modelo propio de persistencia: consume `Task.external_origin` / `TaskRepository.get_by_external_key` (capacidad `tasks`, publicada por el cambio 43), `context_group` / `merge_into_task_id` / `completed_at_override` (capacidad `tasks`, ADDED en este mismo cambio) y `BoardColumn.excluded_from_progress` (capacidad `boards`, ADDED en este mismo cambio).

## Requirements

### Requirement: Hoja y encabezados obligatorios del archivo de origen

El analizador DEBE leer la hoja llamada exactamente `Checklist Tareas` del archivo `.xlsx` indicado por `--file`, y DEBE validar que la fila 1 contiene, en orden, los encabezados `ID, Estado, Vencido, Urgencia, Categoría, Tarea, Detalle, Fecha Límite, Solicitante, Apoyo IA, Observaciones`. Cuando la hoja no existe o algún encabezado no coincide exactamente, el analizador DEBE fallar con un error tipado que identifique la causa, sin procesar ninguna fila.

#### Scenario: Lectura exitosa con encabezados exactos

- DADO un archivo `.xlsx` con la hoja `Checklist Tareas` y los 11 encabezados exactos en la fila 1
- CUANDO se analiza el archivo
- ENTONCES el analizador procesa las filas de datos sin error

#### Scenario: Hoja inexistente rechazada

- DADO un archivo `.xlsx` sin ninguna hoja llamada `Checklist Tareas`
- CUANDO se analiza el archivo
- ENTONCES el analizador falla con un error tipado que identifica la hoja faltante, sin procesar ninguna fila

#### Scenario: Encabezado faltante o reordenado rechazado

- DADO un archivo `.xlsx` cuya fila 1 omite el encabezado `Urgencia` o lo ubica en una posición distinta
- CUANDO se analiza el archivo
- ENTONCES el analizador falla con un error tipado que identifica el encabezado en conflicto, sin procesar ninguna fila

### Requirement: Guardas antibomba en la lectura del libro

El analizador DEBE abrir el libro con `load_workbook(read_only=True, data_only=True)` y DEBE aplicar límites explícitos de tamaño (filas y columnas máximas razonables) antes de iterar, replicando el patrón de guarda de `backend/app/integrations/adapters/jira/file_parser.py`. Cualquier excepción durante la apertura o la iteración DEBE convertirse en un error tipado del importador; NUNCA DEBE propagarse como una excepción cruda de `openpyxl`.

#### Scenario: Archivo corrupto o no XLSX rechazado

- DADO un archivo cuyo contenido no es un `.xlsx` válido
- CUANDO se intenta analizar
- ENTONCES el analizador falla con un error tipado del importador, sin exponer la excepción cruda de `openpyxl`

#### Scenario: Archivo que excede el límite de tamaño rechazado antes de terminar de iterar

- DADO un archivo cuyo número de filas o columnas excede el límite configurado de la guarda antibomba
- CUANDO se intenta analizar
- ENTONCES el analizador detiene la iteración y falla con un error tipado, sin cargar el archivo completo en memoria

### Requirement: Aceptación de celdas de fecha en datetime o texto

Para toda celda que `openpyxl` con `data_only=True` pueda devolver como `datetime.datetime`, `datetime.date` o `str`, el analizador DEBE aceptar ambos tipos indistintamente para la misma columna, sin asumir un tipo único por columna dentro del mismo archivo.

#### Scenario: Fecha Límite como datetime se interpreta igual que como texto ISO

- DADO dos filas con el mismo valor de `Fecha Límite`, una devuelta por `openpyxl` como `datetime.date` y otra como cadena ISO `"2026-08-16"`
- CUANDO se analizan ambas filas
- ENTONCES el mapeo produce el mismo `due_date` para las dos

#### Scenario: Columna con celdas mixtas dentro del mismo archivo se procesa sin error

- DADO un archivo donde unas celdas de `Fecha Límite` son `datetime.date` y otras son `str`
- CUANDO se analiza el archivo completo
- ENTONCES ninguna fila falla por el tipo de la celda

### Requirement: Ningún conteo de filas fijado en el analizador

El analizador NUNCA DEBE comparar el número de filas leídas contra una constante fija en el código ni en las pruebas de integración; DEBE procesar exactamente las filas de datos presentes en la hoja al momento de la ejecución, sea cual sea su cantidad.

#### Scenario: El analizador procesa exactamente las filas presentes

- DADO un archivo con N filas de datos (N variable, no fijado en el código)
- CUANDO se analiza el archivo
- ENTONCES se procesan exactamente esas N filas, sin error ni advertencia por no coincidir con un número esperado

#### Scenario: Dos archivos con distinto número de filas se procesan sin error de conteo

- DADO dos archivos válidos con un número distinto de filas de datos cada uno
- CUANDO se analiza cada uno por separado
- ENTONCES ninguno falla por su cantidad de filas

### Requirement: Mapeo de Estado a columna del tablero de destino

La función de mapeo puro DEBE convertir cada uno de los 7 valores de `Estado` (`PENDIENTE, EN CURSO, COMPLETADA, DIFERIDA, RECURRENTE, GESTIONADA APARTE, REMOVIDA`) en la columna del tablero del proyecto de destino: en SEGURIDAD, cada `Estado` mapea a su columna homónima literal (`Sin iniciar, En curso, Completada, Diferida, Recurrente, Gestionada aparte, Removida`); en PANDORA, `PENDIENTE→Backlog`, `EN CURSO→Doing`, `COMPLETADA→Done`, y `DIFERIDA/RECURRENTE/GESTIONADA APARTE/REMOVIDA` mapean a su columna homónima. La función DEBE ser pura: dado el mismo `Estado` y el mismo proyecto de destino, siempre devuelve el mismo `status_key`, sin acceso a base de datos.

#### Scenario: Mapeo completo de los 7 estados en SEGURIDAD

- DADO cada uno de los 7 valores de `Estado`, para una fila ruteada a SEGURIDAD
- CUANDO se mapea cada uno
- ENTONCES cada uno resuelve a su columna homónima literal de SEGURIDAD

#### Scenario: Mapeo completo de los 7 estados en PANDORA

- DADO cada uno de los 7 valores de `Estado`, para una fila ruteada a PANDORA
- CUANDO se mapea cada uno
- ENTONCES `PENDIENTE` resuelve a `Backlog`, `EN CURSO` a `Doing`, `COMPLETADA` a `Done`, y `DIFERIDA`/`RECURRENTE`/`GESTIONADA APARTE`/`REMOVIDA` a su columna homónima

#### Scenario: La función de mapeo es pura y determinista

- DADO el mismo `Estado` y el mismo proyecto de destino, invocado dos veces
- CUANDO se compara el resultado de ambas invocaciones
- ENTONCES el resultado es idéntico y la función no realiza ninguna consulta a base de datos

### Requirement: Mapeo de Urgencia a prioridad

La función de mapeo puro DEBE convertir `Urgencia` en `Priority`: `CRÍTICA→critical`, `ALTA→high`, `MEDIA→medium`, `BAJA→low`; el literal `-` o una celda vacía DEBEN mapear a `low`.

#### Scenario: Mapeo de las 4 urgencias nombradas

- DADO cada uno de los valores `CRÍTICA`, `ALTA`, `MEDIA`, `BAJA`
- CUANDO se mapea cada uno
- ENTONCES cada uno resuelve a `critical`, `high`, `medium` y `low` respectivamente

#### Scenario: Urgencia vacía o "-" mapea a low

- DADO una fila con `Urgencia = "-"` y otra con la celda vacía
- CUANDO se mapea cada una
- ENTONCES ambas resuelven a `low`

### Requirement: Mapeo de Fecha Límite a due_date o a texto libre en la descripción

Cuando `Fecha Límite` es una fecha ISO (o un `datetime`/`date` devuelto por `openpyxl`), la función de mapeo DEBE asignarla a `due_date`. Cuando es el literal `Recurrente`, un literal `Sin fecha (…)` o el literal `-`, la función NO DEBE asignar `due_date` (queda `NULL`) y en su lugar DEBE agregar la línea `**Fecha límite (texto):** <valor literal>` a la descripción compuesta de la tarea.

#### Scenario: Fecha ISO mapea a due_date

- DADO una fila con `Fecha Límite = "2026-08-16"`
- CUANDO se mapea la fila
- ENTONCES `due_date` queda en `2026-08-16` y la descripción no incluye la línea de texto libre

#### Scenario: Literal "Recurrente" no mapea a due_date

- DADO una fila con `Fecha Límite = "Recurrente"`
- CUANDO se mapea la fila
- ENTONCES `due_date` queda `NULL` y la descripción incluye la línea `**Fecha límite (texto):** Recurrente`

#### Scenario: Literal "Sin fecha (…)" no mapea a due_date

- DADO una fila con `Fecha Límite = "Sin fecha (pendiente de definir)"`
- CUANDO se mapea la fila
- ENTONCES `due_date` queda `NULL` y la descripción incluye la línea de texto libre con ese valor literal

#### Scenario: Literal "-" no mapea a due_date

- DADO una fila con `Fecha Límite = "-"`
- CUANDO se mapea la fila
- ENTONCES `due_date` queda `NULL` y la descripción incluye la línea `**Fecha límite (texto):** -`

### Requirement: Etiqueta recurrente por regla explícita

La etiqueta `recurrente` DEBE asignarse ÚNICAMENTE cuando `Estado = RECURRENTE` O `Fecha Límite` es el literal `Recurrente`, y en ningún otro caso; NUNCA por el cruce implícito de otros campos ni por inferencia sobre el título o el detalle.

#### Scenario: Estado RECURRENTE con fecha ISO obtiene la etiqueta

- DADO una fila con `Estado = RECURRENTE` y `Fecha Límite` en formato ISO
- CUANDO se mapea la fila
- ENTONCES la tarea recibe la etiqueta `recurrente`

#### Scenario: Fecha Límite literal "Recurrente" con otro estado obtiene la etiqueta

- DADO una fila con `Estado = DIFERIDA` y `Fecha Límite = "Recurrente"`
- CUANDO se mapea la fila
- ENTONCES la tarea recibe la etiqueta `recurrente`

#### Scenario: Ninguna de las dos condiciones no obtiene la etiqueta aunque el contenido sugiera periodicidad

- DADO una fila con `Estado = PENDIENTE`, `Fecha Límite` en formato ISO, y un título que describe una acción recurrente en su texto
- CUANDO se mapea la fila
- ENTONCES la tarea NO recibe la etiqueta `recurrente`

### Requirement: Etiquetas area: y apoyo-ia:

`area:<primer segmento normalizado>` DEBE derivarse del primer segmento de `Categoría` (el texto antes del primer separador `/`), normalizado para tratar como equivalentes las variantes de mayúsculas/minúsculas y de espaciado del mismo segmento. La `Categoría` completa NUNCA DEBE convertirse en el nombre de una etiqueta; DEBE aparecer únicamente como la línea `**Categoría:** …` en la descripción. `apoyo-ia:{total|parcial|no}` DEBE derivarse de la columna `Apoyo IA`; cuando su valor es el literal `-`, NO DEBE asignarse ninguna etiqueta `apoyo-ia:*`.

#### Scenario: Variantes de mayúsculas y espacio en el primer segmento producen la misma etiqueta area:

- DADO dos filas cuya `Categoría` comienza con `"Seguridad / Transparencia"` y `"seguridad / Otro tema"` respectivamente (mismo primer segmento, distinta caja)
- CUANDO se calcula la etiqueta `area:` de cada una
- ENTONCES ambas obtienen exactamente `area:seguridad`

#### Scenario: La Categoría completa nunca aparece como nombre de etiqueta

- DADO una fila con `Categoría = "Seguridad / Transparencia y clasificación de la información"`
- CUANDO se mapea la fila
- ENTONCES ninguna etiqueta creada tiene ese texto completo como nombre; el texto completo aparece únicamente en la descripción

#### Scenario: Apoyo IA = "-" no genera ninguna etiqueta apoyo-ia:*

- DADO una fila con `Apoyo IA = "-"`
- CUANDO se mapea la fila
- ENTONCES la tarea no recibe ninguna etiqueta `apoyo-ia:*`

#### Scenario: Apoyo IA con valor nombrado genera la etiqueta correspondiente

- DADO tres filas con `Apoyo IA` igual a `Total`, `Parcial` y `No` respectivamente
- CUANDO se mapea cada una
- ENTONCES cada una recibe `apoyo-ia:total`, `apoyo-ia:parcial` y `apoyo-ia:no` respectivamente

### Requirement: Etiqueta pspi:x.y

La etiqueta `pspi:x.y` DEBE asignarse sobre toda fila cuyo título o categoría lleve el prefijo `[PSPI x.y]`, extrayendo `x.y` literal, y sobre toda fila que el CSV de consolidación declare vinculada mediante su columna `plan_links`. Ninguna otra fila DEBE recibir esta etiqueta.

#### Scenario: Fila con prefijo [PSPI x.y] recibe la etiqueta correspondiente

- DADO una fila con `[PSPI 1.1]` como prefijo de su título
- CUANDO se mapea la fila
- ENTONCES la tarea recibe la etiqueta `pspi:1.1`

#### Scenario: Fila declarada en plan_links del CSV recibe la etiqueta pspi correspondiente

- DADO una fila sin prefijo `[PSPI x.y]` cuyo CSV de consolidación declara `plan_links=3.2` para su `id`
- CUANDO se aplica la consolidación
- ENTONCES la tarea recibe la etiqueta `pspi:3.2`

#### Scenario: Fila sin prefijo y sin plan_links no recibe ninguna etiqueta pspi

- DADO una fila sin prefijo `[PSPI x.y]` y sin valor en `plan_links`
- CUANDO se mapea la fila
- ENTONCES la tarea no recibe ninguna etiqueta `pspi:*`

### Requirement: Ruteo a SEGURIDAD o PANDORA

Toda fila DEBE rutear al proyecto PANDORA cuando su `Categoría`, `Tarea` o `Detalle` contiene "Pandora", el prefijo "HU-", o la frase "Jueves de Pandora", o cuando su `ID` es `T-69`, `T-70` o `T-73` (ruteo forzado); en cualquier otro caso DEBE rutear a SEGURIDAD. Las filas `T-69`, `T-70` y `T-73`, además de rutear a PANDORA, DEBEN recibir una etiqueta cruzada de área (`area:gestion-documental` o `area:continuidad`, según corresponda) que preserva su origen temático de SEGURIDAD.

#### Scenario: Fila con "Pandora" en la Categoría rutea a PANDORA

- DADO una fila cuya `Categoría` contiene "Pandora"
- CUANDO se rutea la fila
- ENTONCES la tarea se crea en el proyecto PANDORA

#### Scenario: Fila con prefijo "HU-" en el título rutea a PANDORA

- DADO una fila cuyo título comienza con "HU-"
- CUANDO se rutea la fila
- ENTONCES la tarea se crea en el proyecto PANDORA

#### Scenario: T-69/T-70/T-73 rutean a PANDORA con su etiqueta cruzada de área

- DADO las filas `T-69`, `T-70` y `T-73`
- CUANDO se rutean
- ENTONCES las tres se crean en PANDORA y cada una recibe además su etiqueta cruzada de área (`area:gestion-documental` o `area:continuidad`)

#### Scenario: Fila sin ninguna coincidencia rutea a SEGURIDAD por defecto

- DADO una fila cuya `Categoría`, `Tarea` y `Detalle` no contienen ninguna de las señales de PANDORA, y cuyo `ID` no es `T-69`, `T-70` ni `T-73`
- CUANDO se rutea la fila
- ENTONCES la tarea se crea en el proyecto SEGURIDAD

### Requirement: Composición de la descripción de la tarea

La descripción DEBE componerse, en este orden, de la línea `**Solicitante:** …`, la línea `**Categoría:** …`, la línea `**Fecha límite (texto):** …` cuando aplique, el texto de `Detalle`, y una sección `### Observaciones` con el texto de `Observaciones` cuando esa celda no esté vacía. Cuando la descripción compuesta supere 4000 caracteres, el importador DEBE fallar por esa fila identificando su `ID`, y NUNCA DEBE truncar la descripción en silencio.

#### Scenario: Composición completa en el orden especificado

- DADO una fila con `Solicitante`, `Categoría`, `Fecha Límite` literal, `Detalle` y `Observaciones` no vacíos
- CUANDO se compone la descripción
- ENTONCES el texto resultante contiene las cuatro partes exactamente en el orden `Solicitante → Categoría → Fecha límite (texto) → Detalle → ### Observaciones`

#### Scenario: Fila sin Observaciones omite la sección sin dejar un encabezado vacío

- DADO una fila con `Observaciones` vacía
- CUANDO se compone la descripción
- ENTONCES el texto resultante no incluye el encabezado `### Observaciones`

#### Scenario: Descripción que supera 4000 caracteres falla nombrando el ID de la fila

- DADO una fila cuya descripción compuesta supera 4000 caracteres
- CUANDO se procesa esa fila
- ENTONCES el importador falla identificando el `ID` de la fila, sin truncar el texto y sin crear la tarea

### Requirement: Extracción de completed_at desde Observaciones

Cuando `Observaciones` contiene el patrón «CERRADA el YYYY-MM-DD», el importador DEBE extraer esa fecha e invocar la creación de la tarea con `completed_at_override` fijado a esa fecha, ÚNICAMENTE cuando el estado resuelto de la fila (Requirement «Mapeo de Estado a columna del tablero de destino») es el estado de cierre del proyecto de destino. Cuando el patrón no está presente, o el estado resuelto no es el de cierre, `completed_at_override` NO DEBE informarse.

#### Scenario: Observaciones con el patrón en una fila cerrada fija la fecha exacta

- DADO una fila COMPLETADA cuyas `Observaciones` contienen «CERRADA el 2026-08-16»
- CUANDO se crea la tarea
- ENTONCES `completed_at` queda fijado en `2026-08-16`, no en la fecha de creación

#### Scenario: El mismo patrón en una fila no cerrada no se aplica

- DADO una fila EN CURSO cuyas `Observaciones` contienen «CERRADA el 2026-08-16» (anotación heredada de un estado anterior)
- CUANDO se crea la tarea
- ENTONCES `completed_at_override` no se informa a la creación

#### Scenario: Observaciones sin el patrón no fija completed_at

- DADO una fila COMPLETADA cuyas `Observaciones` no contienen el patrón «CERRADA el YYYY-MM-DD»
- CUANDO se crea la tarea
- ENTONCES la tarea recibe la fecha de creación por defecto del caso de uso, sin `completed_at_override`

### Requirement: Formato del CSV de consolidación

El CSV de consolidación DEBE tener las columnas `id, action, project, status, labels, plan_links, notes`, con una fila por cada `ID` presente en el XLSX de origen. `action` DEBE pertenecer al vocabulario cerrado `import`, `merge_into:T-xx`, `subtask_of:T-xx`, `context_group:<nombre>`, `skip`.

#### Scenario: El CSV generado por --dry-run tiene una fila por cada fila del origen

- DADO un archivo XLSX con N filas de datos
- CUANDO se ejecuta `--dry-run --csv-out`
- ENTONCES el CSV resultante tiene exactamente N filas de datos, con las 7 columnas exactas

#### Scenario: Una action fuera del vocabulario cerrado es inválida

- DADO un CSV con una fila cuya `action` no pertenece al vocabulario cerrado
- CUANDO se valida el CSV
- ENTONCES esa fila se rechaza como inválida

### Requirement: Valores por defecto del CSV según los veredictos verificados

El `--csv-out` generado por defecto DEBE reflejar los veredictos verificados contra el archivo real, y NUNCA las propuestas originales no confirmadas: las fusiones confirmadas (entre otras, `T-81→merge_into:T-05`, `T-114→merge_into:T-130`) como `merge_into:`; `T-23` como `subtask_of:T-77`; `T-76` como `import` con una nota indicando que la fuente deja abierta la relación con `T-35`; `T-78` como `import` independiente con una nota sobre la contradicción con su posible padre `T-36`; las 25 filas del bloque PSPI (`T-82`…`T-106`) como `import`, salvo `T-94` y `T-99` que se proponen como `merge_into:` por ser consolidaciones reales verificadas; los grupos de contexto corregidos (incluyendo `T-07`, `T-107`, `T-122`, `T-71`, `T-54`; excluyendo `T-74`, cuya pertenencia no es verificable) como `context_group:<nombre>`; y las contradicciones detectadas (`T-38`/`T-124`, `T-34`/`T-35`, `T-62` como contenedor de 5 entregables, `T-72` como regla de comportamiento) registradas en `notes`, NUNCA aplicadas automáticamente como fusión o contexto.

#### Scenario: T-81 se propone por defecto como merge_into:T-05

- DADO el `--csv-out` generado sobre el archivo real
- CUANDO se inspecciona la fila de `T-81`
- ENTONCES su `action` propuesta es `merge_into:T-05`

#### Scenario: T-23 se propone como subtask_of, no como fusión

- DADO el `--csv-out` generado sobre el archivo real
- CUANDO se inspecciona la fila de `T-23`
- ENTONCES su `action` propuesta es `subtask_of:T-77`, no `merge_into:`

#### Scenario: T-94 y T-99 se proponen como merge_into; el resto del bloque PSPI como import

- DADO el `--csv-out` generado sobre el archivo real
- CUANDO se inspeccionan las filas `T-82`…`T-106`
- ENTONCES `T-94` y `T-99` proponen `merge_into:`, y las 23 filas restantes del bloque proponen `import`

#### Scenario: T-74 no aparece en ningún grupo de contexto propuesto

- DADO el `--csv-out` generado sobre el archivo real
- CUANDO se inspecciona la fila de `T-74`
- ENTONCES su `action` propuesta NO es `context_group:*`

#### Scenario: Las contradicciones detectadas quedan como notas, sin acción automática

- DADO el `--csv-out` generado sobre el archivo real
- CUANDO se inspeccionan las filas `T-38`, `T-124`, `T-34`, `T-35`, `T-62` y `T-72`
- ENTONCES cada una lleva una nota describiendo la contradicción o particularidad detectada, sin que el importador les aplique fusión ni contexto por sí solo

### Requirement: Validación del CSV antes de escribir cualquier fila

Antes de crear o modificar una sola tarea, el importador DEBE validar el CSV completo: toda fila DEBE tener una `action` no vacía (decidida); toda referencia `merge_into:` o `subtask_of:` DEBE apuntar a un `ID` presente en el XLSX de origen; y el grafo de relaciones `subtask_of:` NO DEBE contener ciclos. Cualquier violación DEBE abortar la ejecución completa sin escribir ninguna fila, identificando la fila y la causa del rechazo.

#### Scenario: Fila sin decidir aborta antes de cualquier escritura

- DADO un CSV con al menos una fila cuya `action` está vacía
- CUANDO se ejecuta `--execute --csv-in`
- ENTONCES la ejecución aborta antes de crear o modificar ninguna tarea, identificando la fila sin decidir

#### Scenario: Referencia a un ID inexistente aborta antes de cualquier escritura

- DADO un CSV con una fila `merge_into:T-999`, donde `T-999` no existe en el XLSX de origen
- CUANDO se ejecuta `--execute --csv-in`
- ENTONCES la ejecución aborta antes de escribir, identificando la referencia inválida

#### Scenario: Ciclo en el grafo de subtareas aborta antes de cualquier escritura

- DADO un CSV donde la fila `A` declara `subtask_of:B` y la fila `B` declara `subtask_of:A`
- CUANDO se ejecuta `--execute --csv-in`
- ENTONCES la ejecución aborta antes de escribir, identificando el ciclo

### Requirement: --execute exige --csv-in

`--execute` sin `--csv-in` DEBE terminar con error y un código de salida distinto de cero, sin leer ni escribir ninguna tarea. El importador NUNCA DEBE inferir las decisiones de consolidación por sí mismo en modo `--execute`.

#### Scenario: --execute sin --csv-in termina con error

- DADO una invocación `--execute` sin la bandera `--csv-in`
- CUANDO se ejecuta la CLI
- ENTONCES el proceso termina con un código de salida distinto de cero, sin tocar la base de datos

#### Scenario: --execute con --csv-in válido procede

- DADO una invocación `--execute --csv-in <ruta válida>`
- CUANDO se ejecuta la CLI
- ENTONCES el proceso aplica las decisiones del CSV validado

### Requirement: Idempotencia por ancla de procedencia externa

Toda lectura de una tarea ya importada DEBE hacerse mediante `TaskRepository.get_by_external_key(organization_id, 'checklist_xlsx', external_key)`; toda escritura de una tarea nueva DEBE hacerse mediante `TaskService.create_task(..., external_origin=('checklist_xlsx', external_key))`, sin ningún camino alterno. Ejecutar `--execute --csv-in` dos veces seguidas con el mismo XLSX y el mismo CSV DEBE reportar `0 creadas, 0 actualizadas, 0 cambios` en la segunda corrida.

#### Scenario: Primera corrida crea las tareas ancladas por external_key

- DADO un XLSX y un CSV validados, sobre una base sin ninguna tarea con `source='checklist_xlsx'`
- CUANDO se ejecuta `--execute --csv-in` por primera vez
- ENTONCES cada fila decidida crea su tarea con `external_key` igual a su `ID` del XLSX

#### Scenario: Segunda corrida idéntica reporta cero cambios

- DADO el mismo XLSX y el mismo CSV ya aplicados en una corrida previa
- CUANDO se ejecuta `--execute --csv-in` por segunda vez
- ENTONCES el reporte final indica `0 creadas, 0 actualizadas, 0 cambios`

### Requirement: Por defecto --execute solo crea lo que falta

Sin `--update-existing`, una tarea cuya ancla ya existe (`get_by_external_key` la encuentra) NUNCA DEBE modificarse, sea cual sea la diferencia entre el XLSX y el estado actual de la tarea.

#### Scenario: Tarea ya importada permanece sin modificar

- DADO una tarea ya importada cuyo `status` en el XLSX cambió desde la última corrida
- CUANDO se ejecuta `--execute --csv-in` sin `--update-existing`
- ENTONCES la tarea existente permanece sin modificar

### Requirement: --update-existing con lista blanca explícita

`--update-existing` DEBE limitar la actualización de una tarea ya anclada EXCLUSIVAMENTE a los campos `status`, `priority`, `due_date`, `completed_at` y las etiquetas derivadas; NINGÚN otro campo (incluidos `title`, `description`, `assignee_id`) DEBE modificarse por esta vía, aunque difiera del XLSX.

#### Scenario: Un título editado manualmente se conserva

- DADO una tarea importada cuyo `title` fue editado manualmente en la aplicación, mientras el XLSX conserva el título original
- CUANDO se ejecuta `--execute --csv-in --update-existing`
- ENTONCES el `title` editado manualmente se conserva sin cambios

#### Scenario: Un status distinto se actualiza con --update-existing

- DADO una tarea importada cuyo `status` en el XLSX cambió desde la última corrida
- CUANDO se ejecuta `--execute --csv-in --update-existing`
- ENTONCES el `status` de la tarea existente se actualiza al nuevo valor

#### Scenario: Las etiquetas cambiadas se reconcilian con --update-existing

- DADO una tarea importada cuyas etiquetas derivadas del XLSX cambiaron desde la última corrida
- CUANDO se ejecuta `--execute --csv-in --update-existing`
- ENTONCES las etiquetas de la tarea existente se reconcilian con las nuevas

### Requirement: Fila fusionada creada, nunca omitida

Toda fila cuya `action` sea `merge_into:T-xx` DEBE crearse igual que cualquier otra, con su propio `external_key`, en la columna `Removida` del proyecto de destino, con `merge_into_task_id` apuntando a la tarea superviviente y una descripción que indique la consolidación. NUNCA DEBE omitirse su creación.

#### Scenario: Fila con merge_into se crea con su propio ancla

- DADO una fila con `action=merge_into:T-05`
- CUANDO se ejecuta `--execute --csv-in`
- ENTONCES esa fila se crea como tarea con su propio `external_key`, en la columna `Removida` del proyecto de destino, con `merge_into_task_id` apuntando a la tarea `T-05`

#### Scenario: Una segunda corrida no recrea la fila fusionada

- DADO la fila fusionada ya creada en una corrida previa
- CUANDO se ejecuta `--execute --csv-in` de nuevo con el mismo CSV
- ENTONCES esa fila no se crea de nuevo; el reporte la cuenta entre las `0 creadas`

### Requirement: Enlace de subtareas en dos pasadas

El importador DEBE crear primero TODAS las tareas del CSV (incluidas las declaradas `subtask_of:`), y solo después, en una segunda pasada, enlazar cada una a su `parent_task_id` dentro del mismo proyecto. Ninguna creación DEBE fallar por referenciar un padre que aún no existe en la base de datos.

#### Scenario: Una fila subtask_of se crea aunque su padre aparezca después

- DADO una fila `subtask_of:T-77` que precede a `T-77` en el orden del XLSX
- CUANDO se ejecuta `--execute --csv-in`
- ENTONCES ambas tareas se crean sin error de referencia

#### Scenario: El enlace padre-hijo se completa en la segunda pasada

- DADO todas las tareas del CSV ya creadas en la primera pasada
- CUANDO corre la segunda pasada de enlace
- ENTONCES toda fila `subtask_of:T-xx` queda con `parent_task_id` apuntando a la tarea `T-xx`, dentro del mismo proyecto

### Requirement: Usuarios sin acceso creados como viewer sin contraseña

Cuando `Solicitante` referencia a un miembro declarado en la invocación con `--member "Nombre=correo"` y ese usuario no existe aún en la organización, el importador DEBE crearlo con `hashed_password=NULL`, `is_active=true`, y vincularlo mediante `OrganizationMember(role=viewer)`, reconciliándolo por correo. Los correos de esos miembros NUNCA DEBEN estar codificados en el repositorio: la única fuente DEBE ser `--member`. Si el CSV o el XLSX asigna una fila a un nombre sin correo mapeado, el importador DEBE terminar con código de salida `1` nombrando ese nombre, sin escribir nada y sin derivar un correo ni caer al responsable por defecto. Ningún intento de inicio de sesión con esas cuentas DEBE tener éxito; DEBE recibir el mismo mensaje genérico de rechazo que una contraseña errónea.

#### Scenario: Primera importación crea a Jason Rizo y Santiago Carreño

- DADO una base sin esos usuarios y una invocación con `--member` para cada uno de ellos
- CUANDO se ejecuta la importación y alguna fila los referencia como `Solicitante`
- ENTONCES ambos quedan creados con el correo declarado en `--member`, `hashed_password=NULL`, `is_active=true` y `role=viewer`

#### Scenario: Una segunda corrida no duplica esos usuarios

- DADO Jason Rizo y Santiago Carreño ya creados por una corrida previa
- CUANDO se ejecuta la importación de nuevo
- ENTONCES no se crea ningún usuario duplicado; la reconciliación los encuentra por correo

#### Scenario: Un intento de login con esas cuentas es rechazado genéricamente

- DADO la cuenta de Jason Rizo, sin contraseña local
- CUANDO se intenta iniciar sesión con cualquier contraseña
- ENTONCES el sistema rechaza el intento con el mismo mensaje genérico que una contraseña errónea

### Requirement: admin@solercia.com como responsable por defecto

Toda tarea del checklist cuyo `Solicitante` no se resuelva a un usuario existente o creado por este importador DEBE asignarse por defecto a `admin@solercia.com`.

#### Scenario: Solicitante no reconocible se asigna al administrador

- DADO una fila cuyo `Solicitante` no corresponde a ningún usuario existente ni a Jason Rizo ni a Santiago Carreño
- CUANDO se crea la tarea
- ENTONCES su `assignee_id` corresponde a `admin@solercia.com`

### Requirement: ensure_label idempotente por proyecto

El importador DEBE exponer su propia función `ensure_label` que obtiene o crea la etiqueta por `(project_id, name)`, sin depender de `LabelService.create_label` (que no es get-or-create y lanza `duplicate_label_name`). Asignar una etiqueta ya vinculada a una tarea mediante `assign_label` NUNCA DEBE duplicar el vínculo.

#### Scenario: Dos filas con la misma etiqueta reutilizan la misma fila de Label

- DADO dos filas del mismo proyecto cuyo primer segmento de `Categoría` normaliza a `area:seguridad`
- CUANDO se procesan ambas
- ENTONCES ambas tareas quedan vinculadas a la misma fila de `Label`, sin duplicado

#### Scenario: Reejecutar la asignación no crea un segundo vínculo

- DADO una tarea ya vinculada a una etiqueta
- CUANDO el importador vuelve a intentar asignar esa misma etiqueta a esa misma tarea
- ENTONCES no se crea un segundo `TaskLabel`

### Requirement: Contrato de la CLI import_checklist.py

`backend/scripts/import_checklist.py` DEBE aceptar `--file` (obligatorio), `--dry-run` (modo por defecto), `--csv-out` (por defecto `checklist_consolidation.csv`), `--execute` (requiere `--csv-in`), `--csv-in`, `--update-existing`, `--member "Nombre=correo"` (repetible) y `--database-url`. DEBE terminar con código de salida `0` en éxito, y con `1`, `2`, `3` o `4` distinguiendo la causa de fallo (uso o argumentos —incluidos un `--file` inexistente y un XLSX no analizable—; validación del CSV —incluida una codificación no decodificable—; error de conexión/BD; y fallo de una fila individual o excepción inesperada), replicando el contrato de `backend/scripts/purge_demo_data.py`.

#### Scenario: Invocación mínima corre en dry-run

- DADO `python import_checklist.py --file X.xlsx` sin ninguna otra bandera
- CUANDO se ejecuta
- ENTONCES corre en modo `--dry-run`, genera `checklist_consolidation.csv` y no escribe ninguna tarea

#### Scenario: Códigos de salida distinguen la causa del fallo

- DADO una corrida que falla por validación del CSV y otra que falla por error de conexión a la base de datos
- CUANDO se ejecuta cada una por separado
- ENTONCES cada una termina con un código de salida distinto de cero, y los dos códigos son distinguibles entre sí

### Requirement: Reporte final con conteos y advertencias

Al finalizar cualquier ejecución (`--dry-run` o `--execute`), el importador DEBE imprimir un reporte con conteos por proyecto, por estado y por acción del CSV (creadas, actualizadas, fusionadas, contexto, omitidas), más cualquier advertencia registrada durante el mapeo.

#### Scenario: Reporte de --dry-run muestra los conteos previstos

- DADO una corrida `--dry-run`
- CUANDO finaliza
- ENTONCES el reporte muestra los conteos previstos por proyecto, por estado y por acción propuesta del CSV

#### Scenario: Reporte de --execute muestra los conteos reales aplicados

- DADO una corrida `--execute --csv-in` cuyo CSV revisado difiere del `--dry-run` original
- CUANDO finaliza
- ENTONCES el reporte muestra los conteos realmente aplicados, no los previstos originalmente

### Requirement: Transacción única propiedad del caso de uso

`importer.py` DEBE ser dueño de una única transacción para toda la corrida: solo comitea si TODAS las validaciones y todas las creaciones/actualizaciones se completan sin error; cualquier fallo DEBE producir un `rollback()` completo, sin dejar tareas, usuarios ni etiquetas parcialmente creados. Ningún `commit` de un repositorio DEBE cerrar la transacción externa del importador (`join_transaction_mode="create_savepoint"`). Un `--dry-run` DEBE ejecutar el mismo camino de código que `--execute` hasta el punto de decisión final —incluidas las escrituras dentro de la transacción, de modo que sus conteos sean los que realmente se habrían aplicado—, y DEBE terminar siempre con `rollback()`, nunca con `commit()`.

#### Scenario: Un fallo a mitad de la corrida revierte toda la transacción

- DADO una corrida `--execute` que falla al procesar una fila intermedia
- CUANDO ocurre el fallo
- ENTONCES ninguna tarea, usuario ni etiqueta de esa corrida queda creado; una consulta posterior confirma el rollback completo

#### Scenario: --dry-run nunca comitea

- DADO una corrida `--dry-run` completa sin errores
- CUANDO finaliza
- ENTONCES una consulta posterior a la base de datos no muestra ninguna fila nueva

### Requirement: El archivo real nunca es fixture de pruebas

Las pruebas del importador NUNCA DEBEN usar el archivo `CHECKLIST_TAREAS.xlsx` real como fixture; DEBEN generar un XLSX sintético con `openpyxl` en un directorio temporal (`tmp_path`), con un número reducido de filas que cubra los casos relevantes (los 7 estados, una fusión, una subtarea, un grupo de contexto y una fila con «CERRADA el YYYY-MM-DD»).

#### Scenario: La suite de pruebas no referencia el archivo institucional real

- DADO la suite de pruebas completa del importador
- CUANDO se inspeccionan sus fixtures
- ENTONCES ninguna referencia una ruta al archivo `CHECKLIST_TAREAS.xlsx` real; todas usan un XLSX generado en `tmp_path`

#### Scenario: El fixture sintético cubre los casos relevantes en pocas filas

- DADO el fixture generado por la suite de integración
- CUANDO se inspecciona su contenido
- ENTONCES cubre los 7 estados, una fusión, una subtarea, un grupo de contexto y una fila con «CERRADA el YYYY-MM-DD» en un total de 6 a 10 filas

## Referencias

- `openspec/changes/44-importar-checklist-xlsx/{proposal,exploration}.md`
- `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` (`external_origin`, `get_by_external_key`, `KNOWN_TASK_SOURCES`)
- `openspec/specs/data-maintenance/spec.md` (patrón de CLI delgada, transacción única, respaldo verificado)
- `openspec/specs/labels/spec.md` (contrato de `Label`/`TaskLabel` por proyecto)
- `backend/app/integrations/adapters/jira/file_parser.py` (precedente de lector XLSX con guardas antibomba)
- `backend/app/maintenance/{bootstrap,repository,runner,invariants}.py`, `backend/scripts/purge_demo_data.py` (patrones reutilizados)
- `agents/rules/solercia-persistence.md` — repositorios sin commit, transacción única en el caso de uso
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` §5.5 (idempotencia obligatoria en la ingestión)
