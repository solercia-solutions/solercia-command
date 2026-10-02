# institutional-plans Specification

## Propósito

Planes institucionales del Decreto 612 (PSPI, PTR, PAI y, cuando exista fuente extraída, PTEP) como dimensión transversal de compromiso: modelo persistido con identificador legible derivado, reporte de autoevaluación por periodo, enlace actividad↔actividad con resolución trazable, enlace N:N tarea↔actividad con rol, doble avance (calculado desde las tareas vs. reportado por el responsable) con alcance de tenant transitivo, y una costura de escritura idempotente en el repositorio que consumirá el importador de una fase posterior. Vive en `backend/app/modules/plans/`. Command guarda únicamente el autorreporte de primera línea de la actividad; no modela monitoreo cualitativo, evaluación independiente ni observaciones-recomendaciones (frontera ADR 0009).

## Requirements

### Requirement: Modelo persistido de planes y actividades

El sistema DEBE persistir un plan institucional con: código único por organización, nombre, tipo de plan en el vocabulario cerrado `{pspi, ptr, pai, ptep}`, año del periodo, versión del documento fuente (opcional), referencia al documento fuente (opcional) y estado. DEBE persistir, para cada plan, sus actividades con: código único dentro del plan, código y nombre de grupo (opcionales), nombre, entregable (opcional), evidencia esperada (opcional), responsable (opcional), indicador booleano de si la actividad es propia de la entidad, fecha límite (opcional), meta inicial y meta final (opcionales), lista de controles ISO 27001:2022 asociados, lista de códigos externos asociados (una actividad PUEDE llevar más de un código externo), lista de periodos programados y un orden de presentación. Una actividad NUNCA DEBE llevar columna propia de organización: su alcance de tenant es transitivo por el plan al que pertenece. La migración que introduce este modelo DEBE ser estrictamente aditiva (tablas nuevas únicamente, ninguna tabla preexistente modificada) y reversible sin pérdida de las filas sembradas hasta el momento de revertir.

#### Scenario: Un plan con actividades queda persistido y es consultable
- DADO un plan `PSPI-2026` con seis grupos y actividades numeradas dentro de cada grupo
- CUANDO se consulta el detalle del plan
- ENTONCES la respuesta expone el código, el tipo, el año y el conteo de actividades por grupo

#### Scenario: Una actividad admite más de un código externo
- DADO una actividad cuyo control asociado en la fuente lleva dos códigos `OM-05` y `OM-08`
- CUANDO se consulta esa actividad
- ENTONCES ambos códigos aparecen en su lista de códigos externos, sin perder ninguno

#### Scenario: La migración no toca tablas existentes ni pierde datos al revertir
- DADO el esquema con el modelo de planes ya aplicado y filas sembradas en sus cinco tablas
- CUANDO se aplica la reversa de la migración
- ENTONCES las cinco tablas nuevas desaparecen, ninguna tabla previa al cambio pierde una columna o una fila, y un nuevo `upgrade` reconstruye un esquema equivalente

#### Scenario: El esquema migrado es equivalente al esquema construido en pruebas
- DADO un esquema construido con `alembic upgrade head`
- CUANDO se compara contra el esquema construido por el arnés de pruebas con `Base.metadata.create_all`
- ENTONCES ambos producen las mismas tablas, los mismos índices y las mismas restricciones, incluida la restricción de anti-autorreferencia de los enlaces entre actividades

### Requirement: Reporte de autoevaluación por periodo

El sistema DEBE permitir registrar, para cada actividad y cada periodo del vocabulario cerrado `{I, II, III, ANUAL}`, un único reporte con: porcentaje de avance reportado (opcional, entre 0 y 100), resumen cualitativo (opcional), referencias de evidencia (opcional), si la actividad se cumplió (opcional) y si se cumplió en la fecha programada (opcional). DEBE existir a lo sumo un reporte por combinación de actividad y periodo.

#### Scenario: Un periodo sin reporte no tiene fila
- DADO una actividad sin reporte del periodo `II`
- CUANDO se consulta el detalle de la actividad
- ENTONCES el periodo `II` no aparece entre sus reportes registrados

#### Scenario: Un segundo reporte del mismo periodo reemplaza al anterior, no lo duplica
- DADO una actividad con un reporte ya registrado del periodo `I`
- CUANDO el responsable registra un nuevo valor para el mismo periodo `I`
- ENTONCES la actividad conserva un único reporte para el periodo `I`, con el valor más reciente

### Requirement: Enlace actividad↔actividad con resolución trazable

El sistema DEBE permitir enlazar una actividad de plan con otra actividad de plan, registrando el tipo de enlace, el texto literal de la fuente que originó el enlace (opcional) y su resolución en el vocabulario cerrado `{exact, by_external_code, conflict, manual}`. Una actividad NUNCA DEBE enlazarse consigo misma. Un enlace con resolución `conflict` DEBE ser consultable pero NUNCA DEBE contarse como un enlace confirmado.

#### Scenario: Una actividad no puede enlazarse consigo misma
- DADO una actividad de plan existente
- CUANDO se intenta crear un enlace donde el origen y el destino son la misma actividad
- ENTONCES el sistema rechaza la operación

#### Scenario: Un enlace en conflicto es visible pero no confirmado
- DADO un enlace con `resolution = "conflict"` entre dos actividades
- CUANDO se consulta cualquiera de las dos actividades
- ENTONCES el enlace aparece en la respuesta con su resolución, y ningún cálculo de avance lo trata como confirmado

### Requirement: Enlace N:N entre tarea y actividad con rol

El sistema DEBE permitir enlazar una tarea con una actividad de plan, registrando un rol en el vocabulario cerrado `{primary, contributes}` y una nota opcional. Una misma tarea PUEDE ser `primary` de más de una actividad. Un mismo par tarea-actividad NUNCA DEBE repetirse.

#### Scenario: Una tarea aporta a varias actividades como primary
- DADO una tarea enlazada como `primary` a la actividad `PSPI-2026/2.5`
- CUANDO se enlaza la misma tarea como `primary` a la actividad `PSPI-2026/5.3`
- ENTONCES ambos enlaces coexisten y la tarea cuenta como `primary` en las dos actividades

#### Scenario: Un par tarea-actividad duplicado se rechaza
- DADO una tarea ya enlazada a una actividad con rol `contributes`
- CUANDO se intenta crear un segundo enlace entre la misma tarea y la misma actividad
- ENTONCES el sistema rechaza la operación por duplicado

### Requirement: Identificador legible derivado de la actividad

Toda respuesta que incluya una actividad de plan DEBE exponer una clave legible derivada con la forma `"{código del plan}/{código de la actividad}"` (por ejemplo `PSPI-2026/1.1`). Esta clave NUNCA DEBE persistirse como columna: se calcula en el momento de construir la respuesta a partir de los dos códigos únicos.

#### Scenario: La clave derivada se calcula, no se guarda
- DADO un plan `PAI-2026` con una actividad de código `12.4`
- CUANDO se consulta esa actividad
- ENTONCES la respuesta incluye `activity_key = "PAI-2026/12.4"` sin que exista una columna correspondiente en el modelo persistido

### Requirement: Doble avance por actividad, calculado y reportado

El sistema DEBE exponer, para cada actividad, un avance calculado y un avance reportado, sin combinarlos nunca en un único valor. El avance calculado DEBE resultar de la proporción entre las tareas enlazadas con rol `primary` que están activas, no excluidas del avance y cuyo estado coincide con la última columna activa del tablero DEL PROYECTO DE CADA TAREA, sobre el total de tareas `primary` activas y no excluidas. Cuando una actividad no tiene ningún enlace `primary`, el avance calculado DEBE responder como ausencia de dato, NUNCA como cero. Los enlaces `contributes` NUNCA DEBEN alterar esta proporción; DEBEN exponerse aparte como un conteo independiente de tareas contribuyentes. El avance reportado DEBE ser el valor registrado para el periodo consultado, o ausencia de dato si ese periodo no tiene reporte.

#### Scenario: Sin enlaces primary, el avance calculado es ausencia de dato, no cero
- DADO una actividad sin ningún enlace `primary`
- CUANDO se consulta su avance
- ENTONCES el avance calculado se reporta como ausencia de dato y NUNCA como `0`

#### Scenario: Avance calculado cruza proyectos distintos
- DADO una actividad con dos tareas `primary` en dos proyectos distintos, cada uno con su propio tablero y su propia última columna
- CUANDO se calcula el avance
- ENTONCES cada tarea se evalúa contra la última columna activa del tablero de SU PROPIO proyecto antes de sumarse a la proporción

#### Scenario: Los enlaces contributes no alteran la razón
- DADO una actividad con un enlace `primary` completo y tres enlaces `contributes` sin completar
- CUANDO se calcula el avance
- ENTONCES el avance calculado refleja solo el enlace `primary`, y los tres `contributes` aparecen únicamente en el conteo aparte

#### Scenario: Un periodo sin reporte no inventa un avance reportado
- DADO una actividad con reporte solo del periodo `I`
- CUANDO se consulta su avance del periodo `II`
- ENTONCES el avance reportado del periodo `II` es ausencia de dato

### Requirement: Aislamiento de tenant transitivo en toda lectura y escritura

Toda lectura y toda escritura sobre planes, actividades, reportes y enlaces DEBE resolver el alcance de tenant de forma transitiva hasta el plan propietario. Ninguna organización DEBE poder leer, enlazar ni reportar sobre una actividad de otra organización.

#### Scenario: Una actividad de otra organización responde como inexistente
- DADO una actividad que pertenece a la organización B
- CUANDO un usuario de la organización A la consulta por su identificador
- ENTONCES la API responde como recurso no encontrado, igual que el resto de detalles del sistema

#### Scenario: Un listado nunca mezcla organizaciones
- DADO planes y actividades de las organizaciones A y B
- CUANDO un usuario de A lista actividades sin filtros
- ENTONCES ninguna fila de B aparece en el resultado

#### Scenario: No se puede enlazar una tarea a una actividad de otra organización
- DADO una tarea de la organización A y una actividad de la organización B
- CUANDO se intenta enlazarlas
- ENTONCES el sistema rechaza la operación

### Requirement: Lectura de planes y actividades

El sistema DEBE exponer, para cualquier miembro autenticado de la organización: el listado de planes con filtros opcionales `plan_type`, `period_year` y `status`; el detalle de un plan con el conteo de actividades por grupo; el listado de actividades de todos los planes con filtros opcionales `plan_id`, `plan_type`, `is_mine`, `group_code`, `task_id` y `period`, donde cada fila expone su clave derivada, su avance calculado, su avance reportado del periodo consultado y el conteo de tareas contribuyentes; el detalle de una actividad con sus reportes por periodo y sus enlaces entrantes y salientes con su resolución y su referencia de origen; y las tareas enlazadas a una actividad, filtrables por rol. La ruta que lista actividades DEBE declararse antes que la ruta de detalle de un plan por identificador, para que el segmento fijo `activities` nunca se interprete como un identificador.

#### Scenario: Un miembro sin rol de escritura puede leer
- DADO un usuario con rol `member`
- CUANDO consulta el listado de planes, el detalle de una actividad o las tareas de una actividad
- ENTONCES recibe una respuesta exitosa con los datos correspondientes

#### Scenario: El lado de la tarea se consulta desde el módulo de planes, nunca desde tasks
- DADO una tarea enlazada como `primary` a dos actividades
- CUANDO se consulta el listado de actividades filtrado por esa tarea (`task_id`)
- ENTONCES ambas actividades aparecen en la respuesta, y el esquema de lectura de tareas (`TaskRead`) permanece sin cambios

#### Scenario: La ruta de actividades no colisiona con el detalle de un plan
- DADO el segmento fijo `activities` en la ruta de actividades
- CUANDO se consulta el listado de actividades
- ENTONCES el sistema devuelve la lista de actividades, no un error de identificador inválido

### Requirement: Escritura del reporte de periodo

El sistema DEBE permitir crear o actualizar, con una sola operación idempotente sobre el periodo indicado en el vocabulario cerrado `{I, II, III, ANUAL}`, el reporte de una actividad. El porcentaje de avance reportado, cuando se envía, DEBE estar entre 0 y 100. Repetir la misma operación con el mismo periodo NUNCA DEBE crear una segunda fila.

#### Scenario: Dos escrituras consecutivas del mismo periodo dejan una sola fila
- DADO un responsable que registra el avance del periodo `I` de una actividad
- CUANDO repite la operación con un valor distinto para el mismo periodo `I`
- ENTONCES la actividad conserva un único reporte del periodo `I`, con el valor de la segunda escritura

#### Scenario: Un porcentaje fuera de rango se rechaza
- DADO un intento de registrar un avance reportado de 150
- CUANDO se procesa la operación
- ENTONCES el sistema rechaza la operación sin persistir el valor

### Requirement: Escritura de enlaces por API

El sistema DEBE permitir crear y eliminar, por API, el enlace entre una tarea (identificada, con su rol y una nota opcional) y una actividad, y el enlace entre dos actividades (identificado por su tipo de enlace). Todo enlace actividad↔actividad creado por API DEBE quedar marcado con resolución `manual`, sin importar el valor que el cliente envíe: los valores `exact`, `by_external_code` y `conflict` son afirmaciones sobre la lectura de una fuente y la API NUNCA DEBE aceptarlos del cliente. Eliminar un enlace inexistente DEBE responder como recurso no encontrado.

#### Scenario: La API impone resolution manual sin importar lo que envíe el cliente
- DADO una petición de enlace actividad↔actividad que intenta enviar `resolution = "exact"`
- CUANDO el sistema procesa la petición
- ENTONCES el enlace creado queda con `resolution = "manual"`

#### Scenario: Un enlace tarea-actividad duplicado o inexistente falla de forma explícita
- DADO un enlace tarea↔actividad ya existente
- CUANDO se intenta crear el mismo enlace por segunda vez
- ENTONCES el sistema responde con un conflicto y un código de error estable, sin crear una segunda fila
- CUANDO se intenta eliminar un enlace que no existe
- ENTONCES el sistema responde como recurso no encontrado

### Requirement: Autorización de lectura y escritura

La lectura de planes, actividades, reportes y enlaces DEBE estar disponible para cualquier miembro autenticado de la organización, sin restricción adicional por rol. La escritura de reportes y de enlaces DEBE exigir rol `admin` o `manager` en la organización de la actividad.

#### Scenario: Un member no puede escribir
- DADO un usuario con rol `member`
- CUANDO intenta registrar un reporte de periodo o crear un enlace
- ENTONCES el sistema rechaza la operación por falta de autorización

#### Scenario: Un manager puede escribir
- DADO un usuario con rol `manager`
- CUANDO registra un reporte de periodo
- ENTONCES la operación se completa con éxito

### Requirement: Costura de escritura idempotente para importadores

El sistema DEBE ofrecer, fuera de la superficie HTTP, una operación de creación-o-actualización idempotente de planes por código, de actividades por código dentro de su plan, de reportes por actividad y periodo, de enlaces actividad↔actividad y de enlaces tarea↔actividad, para que un importador de una fase posterior sea su único consumidor. Ejecutar la misma operación dos veces con los mismos datos NUNCA DEBE producir una segunda fila ni un error. Esta operación NUNCA DEBE finalizar su propia transacción: quien la invoca controla cuándo se confirman los cambios. El sistema NUNCA DEBE exponer una ruta HTTP para crear planes o actividades: la autoridad de un plan del Decreto 612 es su documento fuente, no un formulario.

#### Scenario: Reejecutar la costura sin cambios no crea filas nuevas
- DADO un plan y una actividad ya creados por la costura de escritura
- CUANDO se reejecuta la misma operación con los mismos datos
- ENTONCES no se crea ninguna fila nueva

#### Scenario: No existe creación de planes por HTTP
- DADO el backend en ejecución
- CUANDO se inspeccionan las rutas registradas bajo `/api/v1/plans`
- ENTONCES ninguna ruta permite crear un plan o una actividad

### Requirement: Frontera con Solercia Security (ADR 0009)

El sistema DEBE persistir únicamente el autorreporte de primera línea de una actividad: porcentaje de avance del periodo, avance cualitativo, evidencia, si se cumplió la actividad y si se cumplió en la fecha. El sistema NUNCA DEBE modelar monitoreo cualitativo, evaluación independiente ni observaciones-recomendaciones: esa autoridad pertenece a Solercia Security.

#### Scenario: El reporte de periodo no admite campos de segunda o tercera línea de defensa
- DADO el esquema de escritura del reporte de periodo
- CUANDO se inspeccionan sus campos aceptados
- ENTONCES no existe ningún campo para monitoreo cualitativo, evaluación independiente ni observaciones-recomendaciones

### Requirement: Alcance excluido de este cambio

Este cambio NUNCA DEBE introducir importadores de documentos, un enlazador automático, un mapa semilla de enlaces, una interfaz de usuario para planes ni una entrada de menú «Planes». Estas piezas pertenecen a cambios posteriores que consumen el modelo y la API aquí definidos.

#### Scenario: No hay importadores ni CLI de planes en este cambio
- DADO el módulo `plans` del backend
- CUANDO se inspecciona su contenido
- ENTONCES no existe ningún lector de DOCX ni XLSX, ningún enlazador automático ni ninguna CLI de importación

#### Scenario: No hay entrada de menú ni vista de planes
- DADO el arranque de la aplicación con el modelo de planes ya aplicado
- CUANDO se inspecciona la semilla de menús y las rutas del frontend
- ENTONCES no existe ninguna entrada «Planes» en el menú ni ninguna ruta de frontend para planes
