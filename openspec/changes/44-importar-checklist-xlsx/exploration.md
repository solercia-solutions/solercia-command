# Exploration: 44 · Importador idempotente de `CHECKLIST_TAREAS.xlsx`

> Fase `sdd-explore`. Store híbrido: artefacto canónico en Engram (`sdd/44-importar-checklist-xlsx/explore`, #3735), volcado a disco por el orquestador el 2026-08-26.
> Fuente verificada en disco el 2026-08-26: volcado completo de la hoja `Checklist Tareas` (`scratchpad/fuentes/checklist-tareas.md`, 1639 líneas) y código de `backend/` leído directo. CodeGraph no operativo: la investigación se hizo con Read/Grep/Glob.

---

## 0. Corrección de partida: la fuente NO tiene 131 filas, tiene 135

La hoja declara `Dimensiones: A1:K136 | Filas: 136`. La fila 1 es encabezado; las filas 2..136 son datos, con `ID` = `T-(fila-1)`. Verificado en los extremos y en el medio: `[A2] T-01`, `[A40] T-39`, `[A100] T-99`, `[A136] T-135`. Conteo por patrón: **135 ocurrencias** de `[A<n>] T-<n>`.

Conteos de `Estado` medidos sobre el archivo (no estimados):

| Estado | Brief del orquestador | Verificado en disco |
|---|---|---|
| PENDIENTE | 71 | **72** |
| EN CURSO | 28 | 28 |
| COMPLETADA | 18 | **20** |
| REMOVIDA | 7 | **8** |
| RECURRENTE | 4 | 4 |
| DIFERIDA | 2 | 2 |
| GESTIONADA APARTE | 1 | 1 |
| **Total** | **131** | **135** |

El desfase no es una truncación simple: el archivo trae anotaciones `CORTE 26-ago-2026` que además movieron estados (p. ej. `T-121` «CERRADA el 24-ago» ya es COMPLETADA; `T-113` «REMOVIDA el 26-ago-2026 por duplicar T-128»). El análisis previo del orquestador corresponde a una versión anterior de la hoja y **no analizó T-132…T-135**, que existen y son las cuatro más recientes (todas PENDIENTE, dos CRÍTICAS):

- `T-132` Gestionar los análisis de vulnerabilidades por demanda fuera del cronograma regular
- `T-133` Diligenciar y devolver la matriz de seguimiento del Menú de Transparencia (CRÍTICA, vence 27-ago)
- `T-134` Ampliar y corregir el reporte financiero de PANDORA (ALTA, prioritario)
- `T-135` Rotar una credencial de servicio expuesta por correo (CRÍTICA, 26-ago)

**Regla derivada para el diseño**: el importador NO debe llevar ningún conteo esperado en el código ni en las pruebas de integración. La hoja es un documento vivo; el número de filas es un dato de entrada, nunca una constante.

Otras cifras verificadas:

- **72 valores distintos de `Categoría`** (el brief decía 68). El más largo es `Seguridad / Transparencia y clasificación de la información` (58 caracteres). **27 primeros segmentos distintos** (`MIPG`, `Seguridad`, `Pandora`, `DLP`, `Vulnerabilidades`, `Plan Seguridad D612`, …).
- **`Fecha Límite`**: 103 fechas ISO, 27 `Sin fecha (…)`, 4 literales `Recurrente` (`T-25`, `T-26`, `T-27`, `T-28`) y 1 `-` (`T-38`).
- El conjunto `Fecha Límite = "Recurrente"` **no coincide** con `Estado = RECURRENTE`: `T-25` es DIFERIDA con fecha `Recurrente`, y `T-39` es RECURRENTE con fecha ISO `2026-06-22`. La etiqueta `recurrente` debe derivarse de una regla explícita, no del cruce ingenuo.
- Recuento de `Solicitante`: **no verificado** (no es carga útil del diseño; `Solicitante` va a una línea de la descripción, nunca a una etiqueta).

---

## 1. Verificación del análisis de consolidación previo

Cada ítem se contrasta contra el texto literal del archivo. `Gxx`/`Kxx` son las celdas de `Detalle` y `Observaciones` de la fila `xx`.

### 1.1 Fusiones propuestas

| Propuesta | Veredicto | Evidencia |
|---|---|---|
| `T-81 → T-05` | **Confirmada** | `F82` «Terminar el formato de viabilidad definitivo» vs `F6` «Formato de viabilidad definitivo»; misma fecha `2026-05-28` en `H82` y `H6`. `G82`: «Tarea asignada en Planner, plan “OAP”, al 50 %». **Contradicción adicional a registrar**: `T-05` es COMPLETADA (`K6` «Formato de viabilidad ya aprobado, confirmado 19-jun-2026») mientras `T-81` sigue EN CURSO al 50 % — Planner está desactualizado, no es una discrepancia de alcance. |
| `T-113 → T-128` | **Confirmada, ya resuelta en la fuente** | `K114`: «REMOVIDA el 26-ago-2026 **por duplicar T-128**; la respuesta técnica fue entregada por José Leonardo el 19-ago». La fusión ya está aplicada en el archivo: `T-113` es REMOVIDA. El importador no debe «fusionar» otra vez, solo respetar el estado. |
| `T-114 → T-130` | **Confirmada** | `G115` «Correo del 13-ago-2026 con la remisión de las preguntas algorítmicas», `I115` «L. Silva». `G131` «**Laura Silva, de la Veeduría Distrital**, remitió el **13 de agosto** la revisión de preguntas algorítmicas». Mismo evento, misma fecha, misma persona. `T-130` es el registro completo; `T-114` el parcial. |
| `T-23 → T-77` | **Corregida — no es fusión, es dependencia/subtarea** | `F24` «**Confirmar** documentos AE pendientes de oficializar» (identificar) vs `F78` «**Formalizar y socializar** los procedimientos de arquitectura empresarial» (ejecutar). `K78` dice literalmente «**Relacionada** con T-23 … y con T-20», nunca «duplica». Fusionarlas perdería la solicitud nominal de Luz Ángela Andrade (`I24`). Recomendación: `subtask_of:T-77` para `T-23`, o dejarlas independientes con nota. |

### 1.2 Subtareas propuestas

| Propuesta | Veredicto | Evidencia |
|---|---|---|
| `T-129 → T-111` | **Confirmada** | `F112` «Atender la revisión MIPG - Tecnología convocada por la jefa» (el marco) y `F130` «Preparar la relación documental del proceso **para la revisión MIPG - Tecnología**» (el entregable concreto, CRÍTICA, `H130 = 2026-08-19`). |
| `T-127 → T-126` | **Confirmada** | `F127` «Manuales de usuario por rol …» y `F128` «**Solicitud formal a Jason Rizo y Santiago Carreño para elaborar los manuales por rol**». `K127` fija la estrategia: «no ejecutarla directamente sino **delegar la ejecución a Jason Rizo y Santiago Carreño** mediante un prompt replicable». `T-127` es el primer paso de `T-126`. |
| `T-76 → T-35` | **Confirmada con salvedad — la fuente misma la deja abierta** | `K77`: «Relacionada con T-35 … **Verificar si el informe de T-35 cubre este entregable o si son dos entregas distintas**». No hay evidencia de que sea la misma entrega. Es exactamente el tipo de decisión que el usuario pidió revisar en el CSV: debe salir **propuesta**, no aplicada. |
| `T-78 → T-36` (marcada dudosa) | **Rechazada** | `F79` «Incorporar en el Manual de Gestión Tecnológica el capítulo de **borrado lógico** y su trazabilidad» (vencida 27-mar). `K79`: «El Manual … v6 figura como completado … **verificar si el capítulo de borrado lógico quedó incluido en esa versión o si sigue faltando**». `T-36` está COMPLETADA. Colgar un pendiente abierto de un padre cerrado esconde el pendiente y rompe el cálculo de avance de subtareas (`TaskService._subtask_progress` cuenta `done/total` contra la última columna). Recomendación: dejar `T-78` independiente y registrar la contradicción como nota del CSV. |

### 1.3 Contradicciones señaladas

| Propuesta | Veredicto | Evidencia |
|---|---|---|
| `T-38` REMOVIDA vs `T-124` PENDIENTE (GT-MA-5) | **Confirmada, y con un tercer dato que la refuerza** | `F39` «GT-MA-5 Manual Gestión Riesgos Seguridad», `G39` «No es responsabilidad de Cristian». Pero `F125` «Atender los comentarios de la líder de riesgos **al GT-MA-5**» está PENDIENTE, y `K125` dice que el tercer comentario «no es un ajuste documental sino un hallazgo de cumplimiento: el seguimiento cuatrimestral está vencido y su responsable, según la tabla del propio manual, es el **Responsable de Seguridad de la Información**». **Tercer dato**: `G2` de `T-01` dice «GT-MA-5 excluido (no es responsabilidad de Cristian)», pero su propia `K2` lista «**GT-MA-5 v2**» entre los entregables cerrados. La exclusión de `T-38` está desmentida por dos filas distintas. |
| `T-34` vs `T-35` / `T-76` | **Confirmada** | `K35` (de `T-34`): «Cristian envió GT-FO-33 v6 … **Aplica también a T-35**». Además `T-34` (`F35`) es compuesta: «Actualización plan seguridad 2026 **+** informes vulns GROW/Kawak» — dos entregables en una fila. |
| `T-62` incluye «PAI 11.6» | **No verificable en la fuente** | `G63` enumera **cinco** actividades sin numeración alguna; no existe la cadena `11.6` en el archivo. Lo que sí es verificable y relevante: `T-62` es un **contenedor de 5 entregables distintos** con un único vencimiento (`H63 = 2026-08-31`) y `K63` ya reporta avance parcial desigual entre ellos. Recomendación: `T-62` como padre con 5 subtareas, o al menos marcado en el CSV. |
| `T-72` es regla de comportamiento | **Confirmada** | `F73` «Responder formalmente todas las convocatorias de reunión». `K73`: «**Regla a adoptar**: toda convocatoria se acepta o se declina con motivo escrito el mismo día». Su `Estado` es PENDIENTE (no RECURRENTE) y su `Fecha Límite` es ISO `2026-08-14`, así que la regla `recurrente` por estado/fecha **no la captura**. Es un recordatorio permanente disfrazado de tarea. |
| `T-40`/`T-41` REMOVIDA coexisten con `T-59` | **Rechazada como contradicción** | `K41` y `K42` dan la misma razón, y es de **titularidad**: «La validación … la realiza Paula Sosa; **no es responsabilidad de Cristian**». `T-59` (`F60`) es «Validación de la **documentación migrada** de Kawak a Pandora», que `K60` describe como coordinación de la migración por parte de Cristian. Son alcances adyacentes con dueños distintos, no estados incompatibles. Merece nota en el CSV, no una contradicción. |

### 1.4 Grupos de contexto

| Grupo propuesto | Veredicto | Corrección con evidencia |
|---|---|---|
| Operación DLP/SearchInform: `T-108,109,110,115–119` + `T-33`, espejo `T-94` | **Corregida — faltan dos** | Deben incluirse `T-07` (`F8` «Seguimiento proyecto DLP — reunión Innatel / SearchInform», COMPLETADA; `K8` remata «El seguimiento técnico continuo se registra como **T-94, T-115, T-117 y T-119**») y `T-107` (`F108` «Emitir concepto formal sobre el inicio de las fases 1 y 2 del DLP», COMPLETADA, `K108` con el informe de verificación). Ambas cerradas: son precisamente la historia cerrada del grupo. |
| Vulnerabilidades Wazuh: `T-120,121,123,125,131`, espejo `T-99` | **Corregida — falta `T-122`** | `E123 = Vulnerabilidades / GT-PR-18`, `F123` «Socializar el cronograma y plan de trabajo de gestión de vulnerabilidades», COMPLETADA; `K132` (de `T-131`) la referencia explícitamente: «Relacionada con **T-122** (socialización del cronograma) y con la actividad 4.8 del Plan de Seguridad (T-99)». |
| Pandora Presupuesto: `T-06,11,17,18,42,51` | **Confirmada, ampliable** | Candidatas adicionales por categoría/hilo: `T-05`/`T-81` (formato de viabilidad, `Pandora / Presupuesto`), `T-68` (`E69 = Pandora / Presupuesto`) y `T-133` (`E134 = Pandora / Reportes`, no analizada antes). |
| Migración Kawak → Pandora: `T-59` + `T-58,61,69,70` | **Confirmada, falta `T-71`** | `F72` «Llevar a mesa de trabajo con Gestión Documental la transferencia documental digital», mismo hilo del 13-ago con Paula Sosa y misma disyuntiva Pandora/Orfeo que `T-69`/`T-70`. |
| Continuidad y respaldos: `T-09,46,57,58,73`, espejos `T-95,97` | **Confirmada, con matiz sobre `T-95`** | `K96` (de `T-95`) dice literalmente «**T-09 solo cubre el procedimiento de prueba de recuperación; faltan las guías de contingencia con RTO y RPO por sistema crítico**». `T-95` no es espejo de `T-09`: es alcance residual distinto y no debe excluirse del conteo. |
| Revisión MIPG-Tecnología: `T-111,129,74` | **Corregida** | `T-111` y `T-129` confirmadas. La inclusión de `T-74` **no es verificable**: `F75` «Verificar el numeral afectado con Andrea Vela» y `K75` «**Falta precisar a qué numeral se refiere**». En cambio `T-54` sí pertenece: `K130` dice «Se apoya en el trabajo de **T-54** (cadena de valor), pero el entregable es distinto». |
| Manuales Pandora por rol: `T-126,127` | **Confirmada** | Ver 1.2. |
| Espejos del PSPI `T-82…T-106`, 1:1 con 25 actividades | **Estructura confirmada, clasificación RECHAZADA** | La estructura es exacta: `T-82 = [PSPI 1.1]`, `T-106 = [PSPI 6.3]`, y 3+5+2+8+4+3 = **25** actividades. Pero llamarlas «espejos» y excluirlas de los conteos **borraría trabajo que no existe en ningún otro sitio**. Cinco filas dicen literalmente «**Sin tarea operativa previa**»: `T-84` [1.3], `T-86` [2.2], `T-91` [3.2], `T-102` [5.3], `T-104` [6.1]. Y varias distinguen su alcance explícitamente: `K106` (de `T-105`, [6.2]) «T-49 cerró el concepto de confidencialidad, que **NO equivale** a las cláusulas de seguridad exigidas aquí»; `K91` (de `T-90`) «Relacionada con T-53 … **Alcance mayor**»; `K103` (de `T-102`) «Sin tarea operativa previa». Espejos/consolidaciones **reales** hay solo dos claros — `T-94` («**Cubierta por T-07**») y `T-99` («Es la actividad mejor respaldada del plan: T-35 y T-76») — más dos parciales: `T-82` («**Cubierta parcialmente** por T-33. **Faltan los informes** del grupo interdisciplinario») y `T-92` («Relacionada con T-61, T-62 y T-66»). Marcar el bloque completo como contexto ocultaría cuatro vencidas críticas: `T-91` [3.2] vence 31-ago, `T-93` [4.2] vence 30-ago, `T-98` [4.7] **vencida desde 31-mar**, `T-100` [5.1] **vencida desde 31-mar** y `T-105` [6.2] **vencida desde 30-jun**. |
| Espejos de Planner `T-74…T-81` | **Corregida** | Las ocho provienen del cruce con Planner (`I` = `Planner - …` en siete; `T-79` lleva `I79 = Yurieth Rojas` pero `G80` dice «Tarea asignada en Microsoft Planner, plan “Jueves de Pandora”»). Pero «provenir de Planner» ≠ «duplicar una tarea existente». Solo cuatro son candidatas a consolidación (`T-76→T-35`, `T-77↔T-23`, `T-78↔T-36`, `T-81→T-05`); `T-74`, `T-75`, `T-79` y `T-80` son **tareas nuevas descubiertas en Planner**, sin equivalente en el checklist. |

**Conclusión de la sección**: de 14 propuestas, **7 confirmadas**, **5 corregidas** y **2 rechazadas**. La consolidación no puede aplicarse automáticamente; el CSV revisable no es una comodidad, es el mecanismo correcto — y confirma la instrucción del usuario: «es fuente de verdad pero no quiere decir que sea un análisis correcto».

---

## 2. Estado actual del código (todo verificado con `ruta:línea`)

### 2.1 Lo que el 44 hereda del 42 (archivado) y del 43 (`apply: pending`)

- `backend/app/maintenance/bootstrap.py:25-33` — `SEGURIDAD_COLUMNS` son literales y en este orden: `Sin iniciar, En curso, Diferida, Recurrente, Gestionada aparte, Removida, **Completada**`. «Completada» es la **última** (comentario `:24`), lo que hace que `allowed_statuses()[-1]` sea exactamente el estado de cierre.
- `backend/app/maintenance/bootstrap.py:18-22` — `SDM` (area/planner) > `SEG` (proyecto/**custom**) y `PAN` (proyecto/**kanban**).
- `backend/app/maintenance/repository.py:392-419` — `ensure_board_columns(board_id, columns)`: idempotente, `status_key` **verbatim** («never slugified, in contrast to `BoardService.add_column`»), corrige `order` derivado, devuelve cuántas insertó.
- `backend/app/maintenance/runner.py:19-61` — el caso de uso es dueño de **la única** transacción: `purge -> bootstrap -> invariants`, y `commit()` **solo** si `execute and all(passed)`; todo lo demás termina en `rollback()`, por el mismo camino de código.
- `backend/scripts/purge_demo_data.py` — CLI delgada: `--dry-run` por defecto, `--execute`, `--database-url`, engine propio con `dispose()`, `redact_database_url` (`:112-116`), códigos de salida 0/1/2/3/4 (`:50-54`), `format_report` (`:151-184`).
- `backend/app/maintenance/invariants.py:37-49` — `I1..I8`; `_i4_seguridad_columns` congela las 7 columnas de SEGURIDAD; `_i3_hierarchy_shape` congela `PAN = Methodology.kanban` (`:29-33`).
- 43 (`state.yaml:10`, `apply: pending`) entrega `TaskService.create_task(..., *, external_origin=(source, external_key))`, `TaskRepository.get_by_external_key(organization_id, source, external_key)`, `KNOWN_TASK_SOURCES` con `checklist_xlsx`, y el único parcial `uq_tasks_source_external_key_project ... WHERE ... AND is_active`. **El 44 no puede empezar antes del apply del 43.**

### 2.2 Cinco hallazgos que cambian el diseño

**H1 — `is_context` ya existe y significa OTRA cosa.** `backend/app/modules/tasks/schemas.py:149-153`: «true **solo bajo `assignee_id`** — la fila es un padre ajeno devuelto como contexto (su subtarea coincidió con el filtro, el padre no)». Se calcula en `TaskService._to_read` (`service.py:968`) y su semántica de listado está en `service.py:100-106`. **Es un artefacto de paginación, no una propiedad de la tarea.** Convertir *ese* `is_context` en columna rompería su significado actual y el contrato del frontend (`workspace.model.ts`, `is_context?`). El 43 lo declaró «transitorio, el 44 lo vuelve columna» (`43/state.yaml:105`) sin advertir la colisión.

**H2 — `completed_at` no es escribible por ningún camino.** No está en `TaskCreate` (`schemas.py:13-43`) ni en `TaskUpdate` (`:62-82`). Se deriva solo en `TaskService._resolve_completed_at` (`service.py:854-864`), y `create_task` lo invoca con `current=None` (`service.py:328`), así que una tarea creada en la columna de cierre recibe **`datetime.now(UTC)`**, nunca una fecha histórica. La decisión del usuario («`completed_at` desde Observaciones cuando exista fecha de cierre, p. ej. “CERRADA el 2026-08-16”») **no es realizable con la API actual**.

**H3 — el denominador de avance excluye un literal que no existe en esta organización.** `backend/app/modules/projects/repository.py:330`: `not_cancelled = Task.status != "cancelled"`, usado en `:335` y `:337`. Ni SEGURIDAD (`Sin iniciar…Completada`) ni PANDORA (`Backlog/Doing/Done`) producen jamás `cancelled`: hoy el filtro **no excluye nada**. La spec lo fija en `openspec/specs/project-hierarchy/spec.md:113` («EXCLUYENDO las de estado `cancelled`») y el 42 dejó la deuda por escrito en `openspec/specs/data-maintenance/spec.md:142`: «Entre este cambio y el **cambio 44**, `Removida` y `Gestionada aparte` cuentan como pendientes en el denominador».

**H4 — el tablero de PANDORA es ampliable sin cambiar de metodología.** `BoardService.add_column` (`boards/service.py:184-223`) **no tiene ninguna guarda de metodología**, y `openspec/specs/boards/spec.md:85` lo exige literalmente: «renombrar, reordenar, agregar y quitar columnas de un board existente, **en cualquier metodología**». Además `BoardAwareStrategy.allowed_statuses()` (`methodology/board_aware.py:39-51`) devuelve los `status_key` **persistidos**, no los de la strategy base. Trampa asociada: `add_column` **slugifica** (`_slugify`, `:27-37` → `diferida`) mientras `ensure_board_columns` escribe **verbatim** (`Diferida`). La deuda ya está reconocida en `boards/spec.md:145`.

**H5 — usuarios sin credenciales ya son un caso soportado, sin esquema nuevo.** `backend/app/modules/users/models.py:65`: `hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)`, con el comentario `:59-64` («un usuario creado/vinculado SOLO vía SSO … nunca obtiene contraseña local»). `backend/app/modules/auth/service.py:27` rechaza `hashed_password is None` con el **mismo resultado genérico** que una contraseña errónea. `MemberRole.viewer` existe (`shared/enums.py:67-73`). Y `TaskRepository.is_org_member` (`tasks/repository.py:318-329`) solo consulta `OrganizationMember`, sin mirar `User.is_active`.

### 2.3 Otros datos verificados

| Dato | Evidencia |
|---|---|
| `openpyxl==3.1.5` disponible | `backend/requirements.txt:17`; `pyproject.toml:49` ya lo tiene en `mypy` overrides |
| Precedente real de lector XLSX | `backend/app/integrations/adapters/jira/file_parser.py:109-148` — `load_workbook(read_only=True, data_only=True)`, validación de encabezado, `_cell_text`, guarda antibomba, `except Exception → error tipado` |
| `Label` es **por proyecto** | `labels/models.py:30` `uq_labels_project_name`; `LabelService.assign_label` rechaza cruce con `label_project_mismatch` (`labels/service.py:114-119`) |
| `create_label` **no** es get-or-create | `labels/service.py:47` lanza 422 `duplicate_label_name`; el importador necesita su propio `ensure_label` |
| `assign_label` **sí** es idempotente | `labels/service.py:120-122` (`existing is not None: return`) |
| Anchos que el importador debe respetar | `Label.name String(80)` (categoría más larga: 58 ✓); `Task.title String(200)` (título más largo observado: `[PSPI 2.4] …` ≈133 ✓); `TaskCreate.description max_length=4000` |
| `Priority` calza 1:1 con `Urgencia` | `shared/enums.py:58-64`: `low/medium/high/critical` |
| El dashboard **no** conoce contexto ni exclusiones | `dashboard/service.py:85-91` (`_build_by_assignee`, `_build_at_risk`, `_build_workload`, `_build_projects_progress`, `_build_totals`) itera todas las tareas de la organización; `_bounds_for` (`:438-451`) solo saca primer/último estado |
| `task_dependencies` es una arista **«blocks»** | `task_links/models.py:1-12,23-38`; no expresa «fusionada en» |
| El harness construye el esquema con `create_all` | `tests/conftest.py:74-80`; toda restricción nueva debe espejarse en `__table_args__` |
| Línea base de pruebas **en deriva** | 1411 (43/design) → 1415 (43/tasks) → 1429 (48 s1). `43/tasks.md` tarea 0.6 ya obliga a re-medirla por rebanada en vez de congelarla |

---

## 3. Opciones y recomendaciones

### 3.1 Mapeo de los 7 estados a PANDORA

Tareas que rutean a PANDORA por la regla del usuario (categoría/título/detalle con `Pandora`, `HU-`, `Jueves de Pandora`, más `T-69/T-70/T-73`): ≈24-26 filas. Sus estados incluyen **DIFERIDA** (`T-22`), **RECURRENTE** (`T-28`) y **REMOVIDA** (`T-10`, `T-40`, `T-41`). Tres de los cuatro estados «extra» ocurren realmente en PANDORA: el problema no es teórico.

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **A. Colapsar a 3 columnas + etiqueta `estado-origen:*`** | Cero cambios de esquema y de tablero | Las 3 REMOVIDA caen en `Backlog`: inflan carga, riesgo y **denominador**. Pérdida semántica en la columna, que es lo que el usuario mira | Bajo |
| **B. Ampliar el board de PANDORA con las 4 columnas faltantes vía `ensure_board_columns`** | Sin migración, sin cambiar metodología (`_i3` sigue verde), `status_key` **verbatim** igual que SEGURIDAD, `BoardAwareStrategy` las toma solas, `Done` sigue último → `_resolve_completed_at` y el término `done` del roll-up intactos. Es exactamente el mecanismo que el 42 ya construyó | Columnas mixtas ES/EN (`Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done`); ninguna invariante cubre hoy las columnas de PANDORA | Bajo/Medio |
| **C. Pasar PANDORA a `custom` con 7 columnas propias** | Simetría total con SEGURIDAD | Rompe `_i3_hierarchy_shape` (`invariants.py:29-33`) y obliga a tocar `bootstrap.py`, `invariants.py` y la spec **archivada** `data-maintenance` | Alto |

**Recomendación: B.** Orden exacto a sembrar: `Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done` — `Done` obligatoriamente al final. El 44 debe además añadir una invariante propia («PANDORA tiene sus 7 columnas en este orden y `Done` es la última»), porque `_i4` solo protege a SEGURIDAD. Nota de UX opcional y no bloqueante: `BoardService.rename_column` (`boards/service.py:123-150`) permite castellanizar los rótulos **sin tocar `status_key`** (`Backlog → Sin iniciar`, `Doing → En curso`, `Done → Completada`).

### 3.2 `is_context` y `merge_into`

**`is_context` → NO reutilizar el nombre.** Colisiona con H1. Recomendación: **`tasks.context_group VARCHAR(80) NULL`**. Una sola columna que expresa las dos cosas: `NOT NULL` significa «es contexto» y el valor es el nombre del grupo, que es justo lo que el CSV ya necesita (`context_group:<nombre>`). Los denominadores excluyen `context_group IS NOT NULL`. Alternativa descartada: etiqueta `contexto:<grupo>` — no es consultable como exclusión en la CTE de roll-up sin un `JOIN` adicional a `task_labels` dentro de una consulta ya cara.

**`merge_into` → columna, pero con la fila fusionada creada, no omitida.** El error de omitir la fila fusionada es de **idempotencia**: si `T-81` no se crea, la siguiente corrida ve `get_by_external_key('checklist_xlsx','T-81') → None` y querrá crearla; la decisión viviría solo en el CSV. Recomendación:

1. La fila fusionada **sí** se crea, con su ancla `external_key='T-81'`, en la columna `Removida` del proyecto destino y con descripción «Consolidada en `SEG-N` (T-05)».
2. **`tasks.merge_into_task_id UUID NULL`**, auto-FK con la misma forma que `parent_task_id` (`tasks/models.py:72-76`, `ondelete="SET NULL"`).
3. Queda excluida del avance por el mismo mecanismo que `Removida` (§3.3), sin regla nueva.

Así la reejecución es idempotente por construcción, el rastro de auditoría se conserva y el puntero es consultable. Nombre `merge_into_task_id` y no `merge_into`, por convención con `parent_task_id`. `task_dependencies` queda descartada: es una arista `blocks`, otra semántica.

### 3.3 Exclusión del denominador de avance (deuda que el 42 asignó al 44)

| Opción | Pros | Contras |
|---|---|---|
| Añadir literales `Removida`/`Gestionada aparte` junto a `cancelled` en `repository.py:330` | 3 líneas | Mete el vocabulario de **un tenant** en SQL genérico de roll-up. Empeora el problema que H3 describe, no lo arregla |
| **`board_columns.excluded_from_progress BOOLEAN NOT NULL DEFAULT false`** | Agnóstico de metodología y de tenant; la CTE ya hace `DISTINCT ON (board.project_id)` sobre `BoardColumn` (`:309-328`), así que el `JOIN` ya está ahí; `cancelled` deja de ser literal y pasa a ser una bandera; sirve igual a SEGURIDAD y a PANDORA | Migración + espejo en `__table_args__` + delta de spec en `project-hierarchy` (hay que **modificar** el requisito de `:113`) y probablemente en `boards` |

**Recomendación: la bandera por columna.** Se marcan `Diferida`, `Recurrente`, `Gestionada aparte` y `Removida` en ambos proyectos. Consecuencia a decidir en `sdd-proposal`: `Diferida` y `Recurrente` ¿son «no cuentan» o «cuentan como pendientes»? Recomendación: **excluir solo `Removida` y `Gestionada aparte`** (es literalmente lo que el 42 dejó escrito) y dejar `Diferida`/`Recurrente` dentro del denominador, con la bandera disponible por si el usuario cambia de opinión sin migración.

### 3.4 Usuarios sin acceso (Jason Rizo, Santiago Carreño)

**Recomendación: cero esquema nuevo.** Crear `User` con `hashed_password=None`, `is_active=True`, y `OrganizationMember(role=MemberRole.viewer)`. Por H5 eso **ya es** «sin credenciales, login deshabilitado», con el mismo mensaje genérico que una contraseña errónea. `is_active=False` está descartado: aunque `is_org_member` no lo mira (`tasks/repository.py:318-329`), los desaparecería de `list_org_members` y de la vista ejecutiva, que es justo donde deben verse como responsables.

**Riesgo a documentar (no bloqueante)**: `auth/sso_service.py:159-173` autoaprovisiona/vincula por correo verificado cuando `SSO_AUTO_PROVISION` está activo. Si algún día se habilita Keycloak y esos correos existen en el IdP, esas cuentas podrían iniciar sesión. Es condicional y futuro; se registra, no se mitiga aquí.

### 3.5 `completed_at` histórico

Por H2 hace falta una costura. **Recomendación: replicar exactamente el patrón que el 43 acaba de establecer** — un segundo parámetro de palabra clave, ausente de `TaskCreate` y del router, por tanto inalcanzable por HTTP:

`create_task(..., *, actor_id=None, external_origin=None, completed_at_override: datetime | None = None)`

Se aplica **solo** cuando el estado resuelto es el de cierre; en cualquier otro caso se ignora, para no poder fabricar una tarea «cerrada» fuera de su columna. Descartado: `UPDATE` posterior (abre una ventana con la fila ya visible con `completed_at = now()`), y añadirlo a `TaskUpdate` (rompería la inmutabilidad que D-INM del 43 acaba de establecer para el ancla y expondría el campo por API).

### 3.6 Ubicación del importador

| Opción | Pros | Contras |
|---|---|---|
| `backend/app/maintenance/` | Reutiliza `runner`, `report`, `invariants`, `ensure_board_columns` | `maintenance` significa hoy «purga y bootstrap de la instalación»; un importador de datos de negocio no es eso. Su spec (`data-maintenance`) es de purga y está **archivada** |
| **`backend/app/importers/checklist/`** (paquete nuevo) | Screaming Architecture: el nombre dice qué hace; capacidad OpenSpec propia (`checklist-import`) sin tocar una spec archivada; puede importar `MaintenanceRepository.ensure_board_columns` sin heredar su alcance | Un paquete de primer nivel más |

**Recomendación: `backend/app/importers/checklist/`**, con `parser.py` (mecánica del XLSX, sin BD), `mapping.py` (funciones puras fila → intención), `consolidation.py` (escritura/lectura/validación del CSV), `importer.py` (caso de uso, dueño de la transacción al estilo `runner.py`) y `report.py`. CLI en `backend/scripts/import_checklist.py`, calcada de `purge_demo_data.py`.

Contrato de la CLI: `--file`, `--dry-run` (**por defecto**), `--csv-out` (por defecto `checklist_consolidation.csv`), `--execute --csv-in <ruta>`, `--database-url`, y los mismos códigos de salida 0/1/2/3/4.

### 3.7 Idempotencia y semántica de la reejecución

- Toda lectura por `('checklist_xlsx', 'T-xx')` pasa por `TaskRepository.get_by_external_key`; toda escritura por `create_task(..., external_origin=...)`. Sin excepciones (constraint del 43).
- **`--execute` DEBE exigir `--csv-in`.** Sin el CSV no hay decisiones y el importador no debe adivinarlas.
- **Recomendación sobre la reejecución**: por defecto `--execute` **solo crea lo que falta**; una segunda corrida con el mismo XLSX y el mismo CSV reporta `0 creadas, 0 actualizadas, 0 cambios`. La actualización de tareas existentes se habilita con `--update-existing` y se limita a una lista blanca explícita (`status`, `priority`, `due_date`, `completed_at`, etiquetas). Motivo: una vez importadas, esas tareas se editan en la aplicación; un `--execute` que sobrescriba en silencio destruiría el trabajo del usuario, que es exactamente el fallo del que se protege este cambio.
- Validación del CSV antes de escribir nada: toda fila decidida (`action` no vacía), todo `merge_into:`/`subtask_of:` apunta a un `ID` presente en el XLSX, y **sin ciclos** en el grafo de subtareas — con dos pasadas (crear todas las tareas, luego enlazar padres), porque `create_task` exige que el padre exista y esté en el mismo proyecto (`service.py:282-290`).

### 3.8 `plan_links` sin inventar las tablas del 45

Lo único con numeración explotable en la fuente es el PSPI: prefijo `[PSPI x.y]` en `F83..F107` y `I = Plan de Seguridad y Privacidad (D612)`. **No existe numeración de PAI en el archivo** (§1.3), así que `pai:12.1` no es derivable de esta fuente.

**Recomendación**: etiqueta `pspi:x.y` sobre las 25 filas del plan **y** sobre las operativas que el CSV declare vinculadas (columna `plan_links`). Es consultable hoy con `?label_id=`, no crea tablas y deja al 45 una migración trivial de etiqueta → relación. El control ISO ya viaja en el `Detalle`; no se convierte en etiqueta (sería duplicar 25 valores más de un vocabulario que ya crece).

### 3.9 Etiquetas: 72 categorías es inusable

Una etiqueta por `Categoría` completa da **72 nombres distintos** que, al ser `uq_labels_project_name` (por proyecto), se duplican en SEGURIDAD y PANDORA. Sumando `apoyo-ia:{total,parcial,no}` y `recurrente`, salen ~150 filas de `labels` para 135 tareas: un desplegable de filtro inservible.

**Recomendación**: dos niveles. `area:<primer segmento>` (**27** valores: `area:seguridad`, `area:pandora`, `area:mipg`, `area:dlp`, `area:vulnerabilidades`…) como etiqueta principal y filtrable, más la categoría completa normalizada solo cuando aporte (segundo segmento). El primer segmento debe normalizarse: la fuente ya trae inconsistencias de caja (`Seguridad / Datos Personales` vs `DLP / Datos personales`) y variantes (`Transparencia / ITA` vs `Cumplimiento / Transparencia (ITA)`).

---

## 4. Áreas afectadas

| Ruta | Impacto |
|---|---|
| `backend/alembic/versions/0026_*.py` y `0027_*.py` (tras el `0025` del 43; sin números reservados) | Nueva · `board_columns.excluded_from_progress` (`0026`), `tasks.context_group` y `tasks.merge_into_task_id` (`0027`) |
| `backend/app/modules/boards/models.py` | Modificar · columna + espejo en `__table_args__` si aplica |
| `backend/app/modules/tasks/models.py:43-58,72-76` | Modificar · dos columnas nuevas |
| `backend/app/modules/tasks/schemas.py:95-153` | Modificar · `context_group`, `merge_into_task_id` en `TaskRead` (**nunca** en `TaskCreate`/`TaskUpdate`) |
| `backend/app/modules/tasks/service.py:252-335,854-864` | Modificar · `completed_at_override` keyword-only |
| `backend/app/modules/projects/repository.py:290-350` | Modificar · CTE de `rollup_progress` con la bandera |
| `backend/app/maintenance/bootstrap.py`, `invariants.py` | Modificar · columnas de PANDORA + banderas + invariante nueva |
| `backend/app/importers/checklist/` | Nuevo · `parser.py`, `mapping.py`, `consolidation.py`, `importer.py`, `report.py` |
| `backend/scripts/import_checklist.py` | Nuevo · CLI |
| `frontend/src/entities/workspace/workspace.model.ts` | Modificar · dos campos opcionales + insignia de procedencia (D6 del 43 la difirió aquí) |
| `openspec/specs/{project-hierarchy,boards}/spec.md` | Deltas **MODIFIED** (el requisito de `:113` cambia de texto) |
| `openspec/changes/44-*/specs/checklist-import/spec.md` | Capacidad nueva |

**No se toca**: `sprints`, `checklists`, `comments`, `attachments`, `alerts`, `intake`, `connectors`, `backend/app/ai/`, `openspec/changes/48-puerto-llm/`.

---

## 5. Pruebas

- **Fixture**: XLSX pequeño (6-10 filas) generado con `openpyxl` en `tmp_path`, cubriendo los 7 estados, las 3 formas de `Fecha Límite`, una fusión, una subtarea, un grupo de contexto y una `Observaciones` con «CERRADA el YYYY-MM-DD». **Nunca** el archivo real: 135 filas de datos institucionales reales no deben entrar al repositorio.
- **Puras, sin BD y sin `@skip_no_db`** (patrón de las pruebas 10/24 del 43): `parser.py` y `mapping.py` completos — estados, prioridades, fechas, ruteo, normalización de categorías, extracción de `completed_at`, y el caso en que `openpyxl` devuelve `datetime` en vez de `str` para una celda con formato de fecha.
- **De integración (`@skip_no_db`)**: creación con ancla, idempotencia (segunda corrida = 0 creadas / 0 cambios), subtareas en dos pasadas, fusión que crea la fila con `merge_into_task_id`, grupo de contexto, `ensure_label` idempotente, usuarios `viewer` sin credenciales, `completed_at` histórico, exclusión del denominador, columnas de PANDORA, validación del CSV (fila sin decidir, referencia inexistente, ciclo).
- **De migración**: patrón `test_migration_project_kind.py:73-244` (base desechable, upgrade, `information_schema`, downgrade sin pérdida de filas).
- **Línea base**: re-medirla al iniciar **cada rebanada** (`43/tasks.md` tarea 0.6). Está en deriva: 1411 → 1415 → 1429, con el 48 escribiendo pruebas en paralelo.

---

## 6. Riesgos

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | El 43 está en `apply: pending`; sin él no existen `external_origin` ni `get_by_external_key` | Alta | Dependencia dura: el 44 no arranca hasta el archivado del 43 |
| R2 | Colisión de nombre `is_context` (H1): reutilizarlo rompe el filtro por `assignee_id` y el tipo del frontend | Alta | Columna nueva `context_group`; el `is_context` transitorio queda intacto |
| R3 | Importar 135 tareas —muchas vencidas desde marzo/abril/junio— distorsiona la vista ejecutiva de golpe: `_build_at_risk`, `_build_workload` y `_build_totals` no conocen contexto ni exclusiones (`dashboard/service.py:85-91`) | Alta | Decidir en `sdd-proposal` si el dashboard también excluye `context_group`; probarlo con el conjunto real antes de `--execute` |
| R4 | Marcar como contexto todo el bloque PSPI ocultaría 5 vencidas, 2 de ellas desde marzo | Alta | §1.4: solo `T-94` y `T-99` son consolidaciones reales; el resto entra al conteo |
| R5 | `add_column` slugifica y `ensure_board_columns` no: mezclar ambos deja `Diferida` y `diferida` en el mismo despliegue | Media | Usar **solo** `ensure_board_columns` para PANDORA; invariante que verifique los `status_key` verbatim |
| R6 | El orden de columnas de PANDORA determina `allowed_statuses()[-1]`: si `Done` deja de ser la última, `_resolve_completed_at` y el `done` del roll-up se rompen en silencio | Media | Invariante explícita de orden; `ensure_board_columns` ya corrige `order` |
| R7 | La descripción compuesta (Solicitante + Fecha límite + Detalle + Observaciones) puede pasar de 4000 caracteres | Media | Medir por fila y **fallar en esa fila con su `ID`**, nunca truncar en silencio |
| R8 | Sin el CSV, `--execute` recrearía las fusionadas | Media | `--execute` exige `--csv-in`; y la fila fusionada **se crea** con su ancla (§3.2) |
| R9 | Modificar un requisito de `project-hierarchy` ya publicado puede duplicarse al archivar | Media | Delta **MODIFIED** explícito sobre el requisito de `:113`, nunca ADDED |
| R10 | SSO podría vincular las cuentas sin credenciales si se habilita Keycloak (`auth/sso_service.py:159-173`) | Baja/futuro | Documentado; no se mitiga en este cambio |
| R11 | `data_only=True` puede devolver `datetime` en unas celdas y `str` en otras de la misma columna | Baja | El parser acepta ambos tipos; prueba pura dedicada |

---

## 7. Estimación y rebanadas

Estimado total **≈2300-2700 líneas** (`additions + deletions`), ~55 % pruebas. Muy por encima de 400.

`400-line budget risk: **High**` · `Chained PRs recommended: Yes` · `Decision needed before apply: Yes` (el pronóstico formal lo emite `sdd-tasks`).

| Rebanada | Contenido | ≈ líneas | Presupuesto (×1,2) |
|---|---|---|---|
| **A** | `board_columns.excluded_from_progress` (migración + espejo) · CTE de `rollup_progress` · columnas y banderas de PANDORA vía `ensure_board_columns` · invariante nueva · pruebas | 300-360 | **400** |
| **B** | `tasks.context_group` + `tasks.merge_into_task_id` (migración + espejo) · `TaskRead` · tipo e insignia del frontend · pruebas | 260-320 | **380** |
| **C** | `create_task(..., completed_at_override=...)` · pruebas | 100-140 | **170** |
| **D** | `parser.py` + `mapping.py` · pruebas puras sin BD | 400-460 | **550** |
| **E** | `consolidation.py`: escritura, lectura y validación del CSV (filas decididas, referencias, ciclos) · pruebas | 380-440 | **520** |
| **F** | `importer.py`: usuarios `viewer`, `ensure_label`, creación/reconciliación, dos pasadas de subtareas, fusiones, contexto, informe · pruebas de integración | 420-480 | **570** |
| **G** | `scripts/import_checklist.py` + prueba extremo a extremo de idempotencia con XLSX generado | 260-320 | **380** |

Cadena de ramas: `feat/44-importar-checklist-xlsx` (tracker) → A → B → C → D → E → F → G. A, B y C son las **costuras de esquema** y no dependen del XLSX: pueden entregarse y verificarse antes de que exista una sola línea de parser.

**Alternativa a evaluar en `sdd-proposal`**: siete rebanadas encadenadas son mucha carga de revisión. A/B/C forman un cambio coherente por sí solo («costuras de consolidación y avance para importadores») y D/E/F/G otro («importador del checklist»). Partirlos en dos cambios daría dos cadenas de 3-4 rebanadas cada una y permitiría verificar las costuras contra la base real antes de escribir el importador. Coste: un número de cambio nuevo y una dependencia más en el grafo.

---

## 8. Preguntas abiertas

Ninguna requiere al usuario para desbloquear `sdd-proposal`; las de consolidación se resuelven por diseño en el CSV que él mismo revisará. Quedan tres decisiones de alcance para el orquestador:

1. **¿El 44 se parte en dos cambios?** (§7). Recomendación: sí, si la carga de revisión pesa más que el número de cambio extra.
2. **¿`Diferida` y `Recurrente` salen del denominador de avance?** Recomendación: **no** — el 42 solo comprometió `Removida` y `Gestionada aparte` (`data-maintenance/spec.md:142`); la bandera por columna deja la puerta abierta sin migración.
3. **¿El dashboard ejecutivo también excluye `context_group`?** Recomendación: **sí** para `_build_workload` y `_build_totals`; **no** para `_build_at_risk` — una tarea de contexto vencida sigue siendo un riesgo real que el jefe debe ver.

### Decisiones del orquestador (2026-08-26, autonomía delegada por el usuario)

1. **Un solo cambio (44) con siete rebanadas encadenadas A → G** (no se parte en dos): el ciclo verify/archive se hace una sola vez y las costuras A/B/C se verifican contra la base real dentro de la misma cadena; el usuario ve su checklist real al cerrar el 44.
2. `Diferida` y `Recurrente` **permanecen** en el denominador; solo `Removida` y `Gestionada aparte` se marcan `excluded_from_progress` (más `merge_into_task_id` no nulo por vivir en `Removida`).
3. El dashboard ejecutivo **excluye `context_group`** en `_build_workload` y `_build_totals`; **no** en `_build_at_risk`.
4. Se adoptan íntegras las recomendaciones §3.1 (opción B: PANDORA a 7 columnas vía `ensure_board_columns`, `Done` última, invariante nueva), §3.2 (`context_group`, `merge_into_task_id` con fila fusionada creada en `Removida`), §3.3 (bandera por columna), §3.4 (usuarios sin login: `hashed_password=None`, `viewer`), §3.5 (`completed_at_override` keyword-only, solo en estado de cierre), §3.6 (`backend/app/importers/checklist/` + CLI), §3.7 (`--execute` exige `--csv-in`; por defecto solo crea faltantes; `--update-existing` con lista blanca), §3.8 (`pspi:x.y`), §3.9 (`area:<segmento>` normalizado; la categoría completa va a la descripción como línea `**Categoría:** …`, no como etiqueta).
5. Valores por defecto del CSV de consolidación = los veredictos de §1: fusiones confirmadas como `merge_into:`; `T-23` como `subtask_of:T-77`; `T-76→T-35` como `import` con nota «¿fusionar con T-35? la fuente lo deja abierto»; `T-78` independiente con nota; el bloque PSPI se importa como tareas reales (`T-94` y `T-99` marcadas como consolidaciones; `T-82`/`T-92` con nota de cobertura parcial); grupos de contexto corregidos (con `T-07`, `T-107`, `T-122`, `T-71`, `T-54`; sin `T-74`); `T-95` en el conteo; contradicciones (`T-38/T-124`, `T-34/T-35`, `T-62` contenedor, `T-72` regla) como notas; `T-40/T-41` sin nota de contradicción.
6. Ningún conteo esperado en código ni pruebas; la hoja es un documento vivo (135 filas hoy).
7. Descripciones > 4000 caracteres: fallo por fila con su `ID`; nunca truncar.
8. Migraciones `0026` (`board_columns`, `down_revision="0025"`) y `0027` (`tasks`, `down_revision="0026"`). El `0025` es del 43 y **no se reserva ningún número**: el 40 reanclado tomará el siguiente consecutivo libre en el momento de su propio `apply`.
9. La insignia de procedencia diferida por el 43 (D6) se entrega en la rebanada B como insignia de solo lectura junto al `task_key`, visible solo con `external_key` no nulo, con `aria-label` del sistema de origen; la revisión `ux-psicologia` es obligatoria antes de cerrar B.

---

## 9. Ready for Proposal

**Sí.** Con dos avisos que el orquestador traslada al usuario en el informe:

- La hoja tiene **135 filas (T-01…T-135)**, no 131, y **T-132…T-135 nunca se analizaron**. Todo artefacto que diga «131» —incluido `43/state.yaml:125`— está desactualizado.
- Del análisis de consolidación previo, **5 ítems se corrigieron y 2 se rechazaron**; el más relevante es que **el bloque PSPI no puede tratarse como contexto en bloque**, porque escondería cinco actividades vencidas, dos de ellas desde marzo de 2026.
