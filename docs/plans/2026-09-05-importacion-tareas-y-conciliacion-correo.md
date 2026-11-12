# Plan: importación determinista de tareas y conciliación de correo con tareas

Fecha: 2026-09-05 · Estado: propuesta para revisión · Alcance: Solercia Command (backend + frontend), con lectura desde Solercia Connect ya operativa.

## 0. Punto de partida (verificado en código y en la fuente de verdad)

| Tema | Estado real |
|---|---|
| Fuente de verdad | `…/2026/VARIOS/TAREAS/CHECKLIST_TAREAS.csv` (UTF-8 con BOM, `;`, 139 filas T-01…T-139, 11 columnas). `CHECKLIST_TAREAS.xlsx` se regenera desde el CSV con la misma cabecera y validaciones de lista en Estado y Apoyo IA. |
| Cambio SDD 44 «importar-checklist-xlsx» | proposal/spec/design/tasks listos, `apply` pendiente, sin código. Su contrato exige la hoja «Checklist Tareas», **los 11 encabezados en orden exacto**, sin alias, sin JSON y sin proyecto por defecto (enruta a SEGURIDAD). Todo-o-nada, idempotente por `(source='checklist_xlsx', external_key=ID)`, CSV de decisiones (`import / merge_into / subtask_of / context_group / skip`). Reutiliza las guardas del parser XLSX de Jira. |
| Cambio SDD 45a «planes-modelo-api» | proposal/spec/design/tasks listos, sin código. Plan = transversal: `plans → plan_activities`, y **tarea ↔ actividad de plan M:N** (`task_plan_activities`, `role ∈ {primary, contributes}`). La tarea sigue perteneciendo a **un** proyecto. Sin `POST /plans` (los planes se cargan por repositorio/importador 45b) y sin UI (45c). |
| Modelo de tareas | `project_id NOT NULL`; `TaskCreate/TaskUpdate` **no aceptan `project_id`** → hoy no se puede mover una tarea de proyecto por API. Ancla externa `(source, external_key, project_id)` única entre filas activas; solo el caso de uso de creación puede fijarla. Un solo `assignee_id`. |
| Proyectos | Sin flag `is_default/is_system`; **no existe endpoint de borrado** (soft delete solo por mixin). El proyecto por defecto de intake se llama «Tareas Outlook» y hoy apunta a SEGURIDAD vía `maintenance/bootstrap`. |
| Intake | `IntakeItem` + `IntakeRule` deterministas (sin LLM). Único vínculo ítem→tarea: `created_task_id`. No existe «relacionar con tarea existente», «completar por correo» ni «reabrir». El puerto LLM (cambio 48) existe pero solo lo usa `/assistant/health`. |
| Frontend | Sin vista de planes, sin acción «mover de proyecto», sin bandeja de insumos. |

## 1. Decisiones de modelo que propongo

**D1 — Una tarea vive en UN proyecto; lo transversal se modela con planes.**
Proyecto = dónde se gestiona (tablero, metodología, columnas). Plan = a qué compromisos aporta (PSPI, PAI, D612…), muchos a la vez, con rol `primary` o `contributes`. Esto es exactamente el 45a y evita romper el ancla externa, los tableros y las métricas, que todas asumen un proyecto por tarea. «Asignar/desasignar» = mover de proyecto (D3) o vincular/desvincular actividades de plan (D4).

**D2 — Proyecto de sistema «Generales».**
Uno por organización, `code = GENERALES`, `is_system = true`, metodología `custom` con las 7 columnas del checklist (PENDIENTE, EN CURSO, COMPLETADA, DIFERIDA, RECURRENTE, GESTIONADA APARTE, REMOVIDA) para que la importación sea sin pérdida. Lo crea `maintenance/bootstrap` de forma idempotente; el servicio de proyectos rechaza borrarlo, archivarlo o cambiarle el código (aunque hoy no haya borrado, la guarda queda explícita y con invariante). Intake pasa a usarlo como proyecto por defecto (adiós «Tareas Outlook»). Es el destino de toda fila importada sin proyecto resoluble y de todo correo convertido sin regla.

**D3 — Mover una tarea de proyecto es una operación explícita.**
`POST /tasks/{id}/move` con `{project_id, status?}`. Traduce el estado por **estado canónico** (`backlog | to_do | in_progress | in_review | done | cancelled`): cada estrategia de metodología expone `canonical_state(status)` y `status_for(canonical)`, así PENDIENTE→Backlog en Kanban o →«Sin iniciar» en Planner sin `if` regados. Limpia `sprint_id` y `board_column_id` (pertenecen al proyecto origen), verifica que el ancla `(source, external_key)` no choque en el destino, escribe `task_history`. UI: selector «Proyecto» en el detalle de tarea y acción masiva «Mover a…» en la lista del proyecto; «Generales» es simplemente un proyecto más en la lista, así que ya tiene su vista.

**D4 — Planes: aplicar el 45a tal como está diseñado**, más chips «Planes» en el detalle de la tarea (agregar/quitar actividad, usa `POST|DELETE /plans/activities/{id}/tasks`). La columna opcional `Plan` de la importación usa el mismo formato del 45a: `PSPI-2026/1.1:primary;PAI-2026/12.4:contributes`.

**D5 — Después de importar, Command es la fuente de verdad.** La reimportación es un *upsert* con lista blanca (D6); no habrá escritura de vuelta al CSV/XLSX. El checklist queda como respaldo histórico.

## 2. Contrato de importación (XLSX, CSV y JSON)

### 2.1 Formatos aceptados

| Formato | Regla determinista |
|---|---|
| XLSX | Se usa la hoja llamada «Checklist Tareas» si existe; si no, la **primera hoja cuya fila 1 contenga todas las columnas obligatorias** tras normalizar. Lectura `read_only + data_only`, límites de filas/columnas del parser de Jira. |
| CSV | UTF-8 (BOM tolerado). Delimitador = el que produzca más columnas obligatorias reconocidas en la fila 1 entre `;` `,` `\t` `\|`. Comillas dobles estándar. |
| JSON | Un arreglo de objetos, o `{ "tasks": [ … ] }`. Las claves se normalizan igual que los encabezados. Fechas como `YYYY-MM-DD`. |

### 2.2 Detección de encabezados independiente del orden

Normalización de cada encabezado o clave: recortar, pasar a minúsculas, quitar tildes/diéresis, colapsar espacios, guiones y guiones bajos a uno solo. Luego se busca en la tabla de alias. Cada campo canónico puede aparecer **una sola vez**; dos columnas que resuelvan al mismo campo → error de estructura. Columnas no reconocidas → advertencia (se listan, no bloquean). El orden nunca importa.

| Campo canónico | Alias reconocidos (ya normalizados) | Obligatorio |
|---|---|---|
| `external_key` | `id`, `codigo`, `clave`, `key`, `external key` | **Sí** |
| `title` | `tarea`, `titulo`, `nombre`, `asunto`, `title` | **Sí** |
| `status` | `estado`, `status` | No → `PENDIENTE` |
| `priority` | `urgencia`, `prioridad`, `priority` | No → `MEDIA` |
| `category` | `categoria`, `area`, `tema` | No |
| `project` | `proyecto`, `project` | No → «Generales» (ver 2.4) |
| `description` | `detalle`, `descripcion`, `description` | No |
| `due_date` | `fecha limite`, `fecha de vencimiento`, `vence`, `due date`, `due` | No → sin fecha |
| `requester` | `solicitante`, `solicitado por`, `requester` | No |
| `assignee` | `responsable`, `asignado`, `asignado a`, `assignee` | No → quien importa |
| `ai_support` | `apoyo ia`, `apoyo` | No |
| `plan_links` | `plan`, `planes`, `plan links` | No |
| `notes` | `observaciones`, `notas`, `comentarios`, `notes` | No |
| *(ignorado)* | `vencido` | Se descarta: es un dato derivado; Command lo recalcula desde `due_date` y `status`. |

### 2.3 Dominios y normalización de valores

| Campo | Regla |
|---|---|
| `external_key` | Recortado, mayúsculas. Único dentro del archivo (repetido → error en ambas filas). Patrón libre; para el checklist es `T-\d{2,3}`. |
| `status` | Comparación sin tildes ni caja contra los 7 valores del checklist; además acepta los canónicos `backlog/to_do/in_progress/in_review/done/cancelled`. Desconocido → error. Se guarda traducido a la columna del proyecto destino vía estado canónico (D3). `COMPLETADA` fija `completed_at` = fecha de importación si no viene otra. |
| `priority` | `CRITICA→critical`, `ALTA→high`, `MEDIA→medium`, `BAJA→low`; `-`/vacío → `medium` (el 44 decía `low`; propongo `medium` porque «-» aparece solo en REMOVIDAS). Desconocido → error. |
| `due_date` | `YYYY-MM-DD`, `DD/MM/YYYY` o fecha nativa de Excel → `due_date`. Textos (`Sin fecha (…)`, `Recurrente`, `-`, vacío) → `due_date = NULL` y el texto se conserva en la descripción bajo **Fecha límite (texto):** (regla del 44). Fecha inválida → error. |
| `description` | Bloques en orden fijo: Solicitante → Categoría → Fecha límite (texto) → Detalle → `### Observaciones` (regla del 44). Más de 4000 caracteres → error nombrando el ID, nunca se trunca. |
| `ai_support` | `Total/Parcial/No` → etiqueta `apoyo-ia:total|parcial|no`; `-`/vacío → sin etiqueta. |
| `requester` | Se guarda en la descripción y en la tabla de contactos (sección 4.3) si trae correo entre paréntesis; si es solo nombre, se registra como contacto sin correo (no bloquea). |
| `assignee` | Correo → usuario de la organización (error si no existe); nombre → se resuelve **solo** por la tabla de contactos/miembros exacta, nunca por similitud; sin resolver → advertencia y queda quien importa. |
| `plan_links` | `CODIGO-PLAN/codigo-actividad[:primary|contributes]` separados por `;`. Actividad inexistente → error (es referencia a datos maestros). |

### 2.4 Resolución del proyecto (en este orden, determinista)

1. Columna `project` presente y con valor → debe coincidir con `code` o `name` de un proyecto activo de la organización (sin tildes ni caja); si no existe → **error** (no se inventan proyectos).
2. Sin `project` → reglas de ruteo por categoría/título/detalle declaradas en un archivo de configuración versionado del importador (`routing.yaml`): la del 44 para Pandora (`Pandora`, prefijo `HU-`, `Jueves de Pandora`, `T-69/T-70/T-73`) y las que se agreguen.
3. Sin regla que aplique → **«Generales»**.

### 2.5 Ejecución en dos fases, todo-o-nada

1. **Validar** (`validate_only = true`): parseo, estructura, dominios, unicidad, referencias (proyectos, planes, usuarios). Devuelve un informe por fila con `nivel ∈ {error, advertencia}`, código y mensaje, más el plan de acción por fila: `crear | actualizar(campos) | sin cambios`. Cero escrituras.
2. **Importar** solo si hay **cero errores** (las advertencias no bloquean). Una transacción; cualquier fallo → rollback total. Idempotente por `(source='checklist', external_key)`:
   - fila nueva → `create_task(..., external_origin=('checklist', ID))`;
   - fila existente y `update_existing = false` → sin cambios;
   - fila existente y `update_existing = true` → actualiza **solo** `status`, `priority`, `due_date`, `completed_at`, `notes`, etiquetas (lista blanca del 44); título, descripción y proyecto no se tocan (para mover se usa D3).
   - Tareas que están en Command y no vienen en el archivo → **no se tocan** (nunca se borra por omisión).
3. **Informe** final: creadas, actualizadas, sin cambios, advertencias, por proyecto y por estado; descargable como JSON y visible en pantalla. Se guarda una corrida (`task_import_runs`) con hash SHA-256 del archivo, usuario, fecha y el informe, para trazabilidad y para detectar «este archivo ya se importó».

`source` pasa a ser `checklist` (independiente del formato) y se registra en `KNOWN_TASK_SOURCES`; `checklist_xlsx` del 44 se sustituye.

### 2.6 Superficie

- API: `POST /api/v1/tasks/import` (`multipart` con archivo o `application/json`), query `validate_only`, `update_existing`, `default_project_id` (opcional, por defecto Generales). Rol admin/manager.
- UI: página `/tasks/import` con tres pasos: subir → revisar informe (tabla de filas con filtros por nivel) → importar. Nada arranca vacío: el paso 2 ya muestra el conteo de filas válidas y el destino de cada una.
- CLI del 44 (`scripts/import_checklist.py`) se conserva como envoltorio del mismo caso de uso (útil para la corrida inicial de 139 filas con el CSV de decisiones).

## 3. Relación con los cambios SDD existentes

- **44**: se enmienda, no se aplica tal cual. Deltas: encabezados por alias e independientes del orden; CSV y JSON; `source='checklist'`; proyecto por defecto «Generales» en lugar de SEGURIDAD; `-`→`medium`; `task_import_runs`; endpoint + UI. Se conservan: mapeos de estado/urgencia/fecha, bloques de descripción, todo-o-nada, idempotencia, CSV de decisiones para la corrida inicial.
- **45a**: se aplica como está (modelo + API). Se agrega al alcance de este plan solo los chips de planes en el detalle de tarea; la vista «Planes» sigue en 45c.
- **Nuevo cambio «Generales + mover tarea»** (D2 + D3): pequeño, sin dependencias, prerrequisito de los otros dos.
- **Nuevo cambio «Conciliación de correo»** (sección 4), dependiente de la importación y de la conexión Connect ya hecha.

## 4. Conciliación determinista de correos con tareas

### 4.1 Principio

Lo determinista es **enlazar** y **proponer**; **cambiar el estado** de una tarea solo ocurre (a) por una convención explícita escrita por vos en tus propios correos enviados, o (b) por tu confirmación en la bandeja de insumos. Ninguna inferencia semántica cambia estados por sí sola. Esto es coherente con la evidencia del corte 2026-08-31: 71 correos y **cero** anclas `T-xx` explícitas; sin convención, la conciliación automática no tiene de dónde agarrarse.

### 4.2 Señales disponibles (ya vienen de Connect)

Por correo: `id`, `internet_message_id`, `conversation_id`, `folder` (inbox/sent → dirección), `sender`, `to/cc`, `subject`, `body_text`, `received_at/sent_at`, `attachments`. Por tarea: `external_key` (T-xx), título, solicitante, responsable, `due_date`, estado, proyecto, hilos ya enlazados.

### 4.3 Modelo de datos nuevo

| Tabla | Para qué |
|---|---|
| `contacts` (org) | nombre normalizado, correo, área. Se siembra desde `Solicitante` del checklist y desde los encabezados de correo. Es la única forma de pasar de un nombre a un correo (sin similitud difusa). |
| `task_mail_links` | `task_id`, `intake_item_id`, `conversation_id`, `role ∈ {anchor, thread, probable, evidence, closure, origin}`, `rule_code`, `created_by`. Un correo puede enlazar varias tareas. |
| `intake_proposals` | `intake_item_id`, `task_id?`, `action ∈ {link, complete, reopen, create, comment}`, `rule_codes[]`, `evidence` (fragmento citado), `status ∈ {pending, accepted, rejected, auto_applied}`, `decided_by/at`. |
| `intake_items.direction` | `inbound | outbound`, derivado de la carpeta y del remitente = cuenta conectada. |

### 4.4 Nivel 0 — Enlace automático (sin cambiar estados)

| Regla | Condición | Efecto |
|---|---|---|
| E1 ancla | `\bT-\d{2,3}\b` en asunto o cuerpo y existe la tarea `(checklist, T-xx)` | enlace `anchor` (uno por cada ID citado) |
| E2 hilo | `conversation_id` ya enlazado a una tarea | enlace `thread` |
| E3 origen | el correo fue convertido en tarea por intake | enlace `origin` (hoy solo `created_task_id`) |
| E4 probable | remitente o destinatario = correo del solicitante/responsable de una tarea abierta **y** coincidencia de asunto ≥ 0,6 (Jaccard sobre tokens sin tildes, sin palabras vacías, tras quitar `RE:/RV:/FW:`) | enlace `probable` → siempre requiere confirmación |

### 4.5 Nivel 1 — Propuestas (requieren confirmación, salvo convención explícita)

| Regla | Dirección | Condición | Propuesta |
|---|---|---|---|
| P1 | saliente | hilo enlazado (E1/E2) y la tarea está abierta | `complete` si el correo lleva adjuntos o cierra explícitamente (marcadores léxicos cerrados: «adjunto», «remito», «queda atendido», «se envía»); si no, `comment` |
| P2 | saliente | sin enlace, asunto sin `RE:/RV:/FW:`, destinatarios internos, con verbo de solicitud («favor», «solicito», «agradezco», «requerimos») | `create` en «Generales» con tipo `seguimiento` (lo que le pediste a otros y debés perseguir) |
| P3 | entrante | hilo enlazado y la tarea está `done` | `reopen` si el último párrafo contiene pregunta (`¿`/`?`) o marcadores («pendiente», «falta», «no se recibió», «favor ajustar») |
| P4 | entrante | hilo enlazado y la tarea abierta | `comment` (evidencia); `complete` solo si el remitente es el solicitante y hay marcadores de recibido conforme («recibido», «gracias, quedamos», «aprobado», «se acepta») |
| P5 | entrante | sin enlace, vos en `To:` (no solo CC), remitente humano de un dominio permitido (`sdmujer.gov.co` y los que definás), no auto-respuesta (sin `Auto-Submitted`, sin «Respuesta automática») | `create` en «Generales», solicitante = remitente, fecha límite si el cuerpo trae una fecha explícita `DD/MM/YYYY` o «antes del …» |
| P6 | cualquiera | remitente en lista de exclusión (boletines, notificaciones de sistemas) | nada; el ítem queda `ignored` con la razón |

**Convención explícita (auto-aplicable, solo en tus correos enviados):** `[T-137]` identifica la tarea; `#cerrar`, `#reabrir`, `#nueva` en asunto o primera línea del cuerpo aplican la acción sin confirmación y quedan en `task_history` con el `internet_message_id` como evidencia. Es determinista porque solo vos podés escribir esos correos desde la cuenta conectada.

Cada propuesta guarda `rule_codes` y el fragmento de texto que la disparó, para que la decisión sea auditable.

### 4.6 Nivel 2 — LLM opcional, nunca decisor

Con `LLM_PROVIDER` distinto de `fake`, el puerto del cambio 48 puede **ordenar y etiquetar** las propuestas pendientes con esquema de salida estricto (`action_sugerida`, `cita`, `confianza`), pero no crea enlaces ni cambia estados. Apagado por defecto.

### 4.7 Bandeja de insumos (`/intake`)

Una pantalla, cinco estados: cargando, vacía («No hay insumos pendientes; sincroniza desde Conexiones»), sin resultados por filtro, error, éxito. Agrupa por acción propuesta (Completar / Reabrir / Crear / Comentar / Solo enlazar), muestra remitente, asunto, fragmento, tarea candidata y reglas que se dispararon; acciones «Aceptar», «Rechazar», «Cambiar tarea…», «Aceptar todo lo de convención». Aceptar escribe `task_mail_links` + `task_history` + (si aplica) el estado por estado canónico. El botón «Sincronizar ahora» de Conexiones enlaza al resultado en esta bandeja.

### 4.8 Flujo diario resultante

1. «Refrescar sesión» (si hace falta) y «Sincronizar ahora» en Conexiones.
2. Intake trae correos → Nivel 0 enlaza → Nivel 1 propone → convención explícita se auto-aplica.
3. En `/intake` confirmás el resto en minutos. Las tareas quedan al día y «Vencido» se recalcula solo.

## 5. Orden de ejecución propuesto

| Rebanada | Contenido | Tamaño relativo |
|---|---|---|
| 1 | Proyecto «Generales» de sistema + `POST /tasks/{id}/move` + estado canónico en estrategias + selector de proyecto en la UI | S |
| 2 | Importador (parsers XLSX/CSV/JSON, alias, dos fases, corrida trazable) + endpoint + página `/tasks/import` + corrida inicial de las 139 filas | M |
| 3 | 45a aplicado (planes) + chips de planes en el detalle + columna `plan_links` del importador | M |
| 4 | Conciliación: contactos, enlaces, propuestas, reglas E1–E4 y P1–P6, convención, bandeja `/intake` | L |
| 5 | LLM opcional para ordenar propuestas; exclusiones y dominios configurables en UI | S |

Cada rebanada se cierra con pruebas (happy path, error, permisos) y con la verificación en el navegador antes de pasar a la siguiente.

## 6. Supuestos y preguntas abiertas

- **Supuesto A**: tras la primera importación, el checklist deja de editarse y Command es la fuente de verdad (D5).
- **Supuesto B**: la cuenta de Catastro entra después; la conciliación arranca solo con SDMujer.
- **Pregunta 1 (bloqueante para las rebanadas 1 y 3)**: ¿confirmás D1, es decir, una tarea vive en un solo proyecto y lo transversal se modela con planes? Si preferís que una tarea pertenezca a varios proyectos, el modelo cambia (M:N tarea–proyecto) y hay que rediseñar tableros, ancla externa y métricas antes de importar.
- **Pregunta 2**: ¿adoptás la convención `[T-xx] #cerrar/#reabrir/#nueva` en tus correos enviados? Sin ella, todo pasa por confirmación manual.
