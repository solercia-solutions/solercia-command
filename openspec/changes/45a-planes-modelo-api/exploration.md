# Exploration: 45 · Planes institucionales (Decreto 612) como dimensión transversal de compromiso

> Exploración compartida por los tres cambios en que se parte el 45: **45a** (`45a-planes-modelo-api`, este directorio), **45b** (`45b-planes-importadores`) y **45c** (`45c-planes-vista`). Artefacto canónico en Engram (`sdd/45-planes-actividades/explore`, #3738), volcado a disco por el orquestador el 2026-08-26 con la sección final «Decisiones del orquestador».
> Idioma: español neutro/profesional (convención del repositorio). Identificadores, nombres de tabla, columna, índice y ruta en inglés. Fuentes extraídas a texto en `scratchpad/fuentes/{pspi-2026,ptr-2026,pai-2026,reporte-cruce-2026-08-14,checklist-tareas}.md`.

## 1. Estado actual del sistema

### 1.1 Persistencia y migraciones

- **Cabeza real de Alembic en disco: `0024`** — `backend/alembic/versions/0024_add_work_calendar.py:38-39` (`revision="0024"`, `down_revision="0023"`). Cadena lineal `0001`→`0024`, 24 archivos, sin bifurcaciones ni merges.
- **Números ya reclamados por cambios pendientes**: `0025` por el 43 (`openspec/changes/43-tareas-origen-externo/proposal.md:152`) y `0026` + `0027` por el 44 (`board_columns` y `tasks`, dos rebanadas con reversa independiente). **No se reserva ningún número al cambio 40**: tomará el siguiente consecutivo libre en el momento de su propio `apply`, verificado con `alembic heads` y con los cambios pendientes de esa fecha.
- **Convención de nombre**: `00NN_verbo_sustantivo.py` con docstring de cabecera que cita el cambio SDD, el apartado del `design.md` y la verificación en vivo del head (`0024_add_work_calendar.py:1-29` es el modelo a copiar).
- **Patrón de migración aditiva**: `op.add_column` / `op.create_table` sin `batch_alter_table` (PostgreSQL exclusivo, cero apariciones en las 24 migraciones). `downgrade()` en orden inverso.
- **JSONB**: precedente sólido — `postgresql.JSONB(astext_type=sa.Text())` en migraciones (`0019_add_intake.py:71,141`, `0020:37`, `0017:83,156`, `0015:40,173`, `0013:62`) y `from sqlalchemy.dialects.postgresql import JSONB` + `mapped_column(JSONB, nullable=...)` en modelos (`app/modules/intake/models.py:21,71,108`, `app/modules/connectors/models.py:54,73`). No requiere extensión; válido en el Postgres real de pruebas y en `Base.metadata.create_all`.
- **Regla dura**: `agents/rules/solercia-persistence.md:41-45` — los repositorios nunca hacen commit/rollback, `organization_id` obligatorio en lecturas/escrituras/borrados, JSONB/ARRAY y SQL textual confinados al adaptador, servicios con fakes y adaptadores contra PostgreSQL real.

### 1.2 Identificador público legible — **`public_id` NO existe en el repositorio**

Búsqueda exhaustiva en `backend/`: cero apariciones de `public_id`. Lo que sí existe:

| Mecanismo | Dónde | Forma |
|---|---|---|
| `organizations.slug` | `0001_baseline.py:44,52` | `String(120)`, único global |
| `projects.code` | `app/modules/projects/models.py:69` | `String(10)` nulable + `UniqueConstraint("organization_id","code", name="uq_project_code_per_org")` (`models.py:38`) |
| `tasks.task_number` | `app/modules/tasks/models.py:143` | `Integer` nulable, asignado atómicamente vía `UPDATE ... RETURNING` sobre `projects.task_counter` |
| `task_key` | `app/modules/tasks/schemas.py:127` + `service.py:967` | **Campo transitorio de Pydantic**, no columna: `read.task_key = f"{project_code}-{task.task_number}"` |
| `board_columns.status_key` | `app/modules/boards/service.py:27-37,203-207` | slug derivado del nombre, único por board |

**Conclusión**: introducir `public_id` crearía una convención nueva sin precedente. La forma canónica del repositorio es *columna `code` legible con unicidad de alcance* + *clave compuesta derivada y expuesta solo en la respuesta*.

### 1.3 Roll-up de avance existente

`app/modules/projects/repository.py:290-350` (`rollup_progress`):

- `done` = tareas cuyo `status` coincide con el `status_key` de la **última columna del board del mismo proyecto**, resuelto con un CTE `DISTINCT ON (board.project_id) ... ORDER BY column_order DESC, created_at DESC` (`repository.py:295-300`), replicando `DashboardService._bounds_for`.
- `total` = todas las tareas del nodo **excluyendo `status == 'cancelled'`** en ambos términos (`repository.py:330,335-338`). (El 44 sustituye ese literal por la bandera `board_columns.excluded_from_progress`; el 45 debe usar el mismo criterio vigente al momento de su apply.)
- Alcance de tenant transitivo vía `_subtree_ids_select`.
- La suma de la jerarquía la hace la capa de servicio, no el repositorio.

**Matiz importante frente al enunciado del plan**: `is_context` **no es criterio de exclusión del roll-up**. Es un campo transitorio de respuesta (`app/modules/tasks/schemas.py:153`) que solo marca padres arrastrados por el filtro de `assignee` en `GET /tasks` (`app/modules/tasks/service.py:104-106,152`); nunca llega a la base ni a `rollup_progress`. El 44 introduce `tasks.context_group` como columna real para ese fin. Tampoco existen los estados «Removida» ni «Gestionada aparte» en el modelo de Command: son valores del `Estado` del checklist XLSX (`checklist-tareas.md:4`) que el 44 homologa a columnas de tablero antes de persistir.

**Restricción real**: `rollup_progress` está modelado sobre *un subárbol de un proyecto*. Una actividad de plan agrupa tareas de **proyectos distintos**, así que la «última columna» varía por tarea. La consulta del 45 no es reutilizable tal cual: hay que generalizarla a «para cada tarea, la última columna del board de *su* proyecto», con el CTE unido por `board.project_id` en lugar de filtrado a un único proyecto. Es SQL nuevo, no una reutilización.

### 1.4 Precedentes de módulo con tabla + API (+ frontend)

Estructura fija por módulo: `__init__.py`, `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py` (ver `assets/`, `glpi_sync/`, `intake/`, `connectors/`). Cableado en tres puntos:

1. `app/main.py:18-46` (import del router) y `:158-188` (`include_router(..., prefix=API_PREFIX)`).
2. `app/db_init.py:43-96` — import de los modelos con `# noqa: F401` para que las `relationship()` por cadena resuelvan.
3. `app/db_init.py:133-163` — `_MENU_SEED` y `_ROLE_MENU_SEED`. Comentario explícito en `:129-132`: se ejecutan en cada arranque e insertan solo lo faltante, así que **una entrada de menú nueva no necesita migración de datos**.

- **RBAC**: `require_role(MemberRole.admin, MemberRole.manager)` declarado como singleton a nivel de módulo para esquivar `ruff B008` (`app/modules/intake/router.py:32-34`, `glpi_sync/router.py:26`, `jira_import/router.py:27`, `projects/router.py:31-34`).
- **Paginación**: `app/shared/pagination.py` — opt-in (`page`/`sort` la activan), `DEFAULT_PAGE_SIZE=20`, `MAX_PAGE_SIZE=100`, `paginate(...)` + `build_list_meta(...)`, mapa `sortable` cuyo primer campo es el orden por defecto.
- **Sobre**: `{ "data": ..., "message": ..., "meta": ... }` y errores `AppException(msg, code=..., status_code=...)`.

### 1.5 Importadores y CLI

- **XLSX**: `app/integrations/adapters/jira/file_parser.py` — `openpyxl` (ya en `requirements.txt:17`, `openpyxl==3.1.5`), guarda antibomba por filas y celdas antes de terminar de leer (`config.py:249-250`: `JIRA_FILE_MAX_ROWS=50_000`, `JIRA_FILE_MAX_CELLS=500_000`), tolerancia a BOM y a cabeceras repetidas.
- **DOCX**: `python-docx` **no está** en `requirements.txt`. El archivo documenta el nivel de rigor exigido para agregar una dependencia (`requirements.txt:18-29`: verificación en vivo contra PyPI, justificación del pin, impacto en los techos transitivos).
- **CLI**: `backend/scripts/purge_demo_data.py` (cambio 42) — `python -m scripts.X` desde `backend/`, `--dry-run` por defecto y `--execute` explícito, engine propio con `dispose()`, códigos de salida tipados (`:50-54`), redacción de la contraseña de la URL (`:56`).
- **Fixtures**: `backend/tests/fixtures/jira/{export.csv,export.xlsx,export_bomba.xlsx}` — archivos sintéticos mínimos versionados, nunca documentos reales.

### 1.6 Frontend

- Angular **22** (`frontend/package.json:17`), TypeScript 6.0.3, `@solercia/ui@^0.5.0` (`:22`).
- Rutas planas y lazy en `frontend/src/app/app.routes.ts` (10 rutas + `admin.routes.ts`).
- FSD real hoy: `pages/` (12 componentes), `widgets/`, `features/`, `entities/` (servicio + modelo por entidad), `shared/ui/index.ts` = re-export puro de `@solercia/ui`.
- **`@solercia/ui@0.5.0` ya expone todo lo que la vista «Planes» necesita** — verificado en `frontend/node_modules/@solercia/ui/types/solercia-ui.d.ts`: `SolDataTableComponent:1606`, `SolProgressBarComponent:920` (`variant: primary|success|warning|danger`, `mode: continuous|segmented`, accesible con `role="progressbar"`), `SolBadgeComponent:286`, `SolCardComponent:301`, `SolTreeComponent:3963`, `SolTabsComponent:334`, `SolEmptyStateComponent:778`, `SolSkeletonComponent:527`, `SolSpinnerComponent:313`, `SolPaginationComponent:352`, `SolChipComponent:2767`, `SolModalComponent:203`, `SolDrawerComponent:246`, `SolFormFieldComponent:344`, `SolSelectComponent:78`, `SolNumberInputComponent:2977`, `SolTextareaComponent:133`, `SolPageHeaderComponent:1514`, `SolTimelineComponent:2138`. **Cero componentes nuevos.**
- `SolEmptyState` exige claves i18n (`titleKey`/`descriptionKey`, `.d.ts:781-785`): todo el texto de la vista pasa por `frontend/src/assets/i18n/es-CO.json`, nunca literales en plantilla.
- Un ícono de menú nuevo necesita alias en `frontend/src/widgets/sidebar/ui/sidebar-icons.ts:17-28` si no coincide con `SolIconName`.
- **No hay runner de pruebas de frontend**: `package.json:5-11` solo tiene `ng`, `start`, `build`, `lint`, `watch`. La rebanada de frontend se verifica con `ng build` + `eslint`.

### 1.7 Contratos vecinos

- **43 (`0025`, no aplicado)**: `TaskRepository.get_by_external_key(organization_id, source, external_key)` como único camino de lectura (`43/design.md:160-173`) y `TaskService.create_task(..., external_origin=(source, external_key))` como único camino de escritura (`43/design.md:25-26,235,246`). Único parcial `uq_tasks_source_external_key_project (source, external_key, project_id) WHERE source IS NOT NULL AND external_key IS NOT NULL AND is_active` + `ck_tasks_external_key_requires_source` (`43/design.md:48-50`). **Consecuencia para el 45**: `get_by_external_key` filtra por `(source, external_key)` **sin conocer el proyecto** (`43/design.md:56`), y la unicidad es *por proyecto*; un mismo `T-82` puede existir en dos proyectos de la misma organización. El enlazador debe tratar el resultado múltiple como ambigüedad reportable, nunca elegir uno.
- **ADR 0009 (`docs/adr/0009-solercia-command-connect-data-conventions.md:78-80,238-240`)**: Command es la única autoridad sobre el estado operativo del trabajo; **Security es la única autoridad sobre cumplimiento, validación y cierre de evidencia**. Esto acota qué puede guardar `plan_activity_reports` (ver D5).

---

## 2. Verificación de las fuentes (conteos reales, no supuestos)

### 2.1 PSPI 2026 — `pspi-2026.md`

- **25 actividades** en la Tabla 2 (`pspi-2026.md:91-123`), distribuidas en **6 grupos**: `1.` Datos personales (3: 1.1-1.3), `2.` Información documentada (5: 2.1-2.5), `3.` Activos (2: 3.1-3.2), `4.` Riesgos y continuidad (8: 4.1-4.8), `5.` Formación (4: 5.1-5.4), `6.` Terceros (3: 6.1-6.3). **Coincide con lo anunciado.**
- Las filas de grupo repiten el mismo texto en las 7 columnas (`:93,97,103,106,115,120`) — huella de una celda con `gridSpan` que abarca toda la rejilla. Detección determinista: fila cuyas celdas son todas idénticas.
- `META 2026` sigue siempre el patrón `N% → M%` con flecha U+2192 (5 variantes observadas: `0% → 100%`, `95% → 100%`, `75% → 90%`, `60% → 100%`, `0% → 50%`). Regex determinista.
- `FECHA FIN` en formato `DD-mmm-AAAA` con mes abreviado en español (`ene…dic`). Mapa fijo.
- `CONTROL ISO 27001:2022` es **multivaluado** separado por coma: `5.2, 5.3` (`:99`), `8.10, 8.15` (`:101`), `5.9, 5.10` (`:105`), `5.19, 5.20` (`:121`).
- **Códigos `OM-xx` en el PSPI** (dentro del texto de la actividad): `2.4 → OM-05 **y** OM-08` (`:101`), `2.5 → OM-09` (`:102`), `4.2 → OM-02` (`:108`), `4.4 → OM-03` (`:110`), `4.5 → OM-06` (`:111`), `5.2 → OM-04` (`:117`). **`2.4` lleva DOS códigos** → `external_code` en singular no representa la fuente.
- Documento fuente y versión confirmados por el reporte de cruce (`reporte-cruce-2026-08-14.md:4`): `2623_PLAN_DE_SEGURIDAD_Y_PRIVACIDAD_DE_LA_INFORMACIÓN_v2_20260120.docx` → `version = "v2_20260120"`.

### 2.2 PTR 2026 — `ptr-2026.md`

- **Matriz de riesgos (Tabla 6, `:95-125`): 29 filas** — R13-R30, R32, R34-R43. El propio documento afirma «28» en `:92` y en la Tabla 7 (`:136`). **Inconsistencia de la fuente**, no del análisis.
- **Acciones de tratamiento: 26** — Tabla 8 riesgo extremo (1: R32, `:145`), Tabla 9 riesgos altos (14, `:153-166`), Tabla 10 moderados (11, `:174-184`). **Coincide con lo anunciado.**
- **Riesgos aceptados: 2** (R30, R42; Tabla 11, `:192-193`). **Coincide.**
- **Remediaciones CVE por materialización de R34: 4** (`:202-205`). **Coincide.** La tabla está rotulada «Tabla 8» por segunda vez (`:198`) — número duplicado en la fuente.
- **Huecos de la fuente detectados**: **R31 tiene acción (`:161`) pero no fila en la matriz** (es la 26.ª acción); **R40 y R43 están en la matriz como MODERADO pero no tienen acción** en la Tabla 10; R32 aparece con `Nivel Res. = "Catastrófico"` (`:115`), que es un nivel de *impacto*, no de riesgo.
- **Columna «Actividad Plan Seguridad»**: 14 de las 26 acciones traen referencia; 12 traen `-`. Expandiendo los multivalor son **17 enlaces PTR→PSPI**.

#### Conflictos `OM-xx` encontrados (evidencia exacta)

| Riesgo | Texto en el PTR | Código OM | Actividad PSPI que lleva ese OM | Veredicto |
|---|---|---|---|---|
| R17 | `4.5 (OM-03)` (`:153`) | OM-03 | **4.4** (`pspi:110`) | **Conflicto duro** |
| R19 | `4.5 (OM-03)` (`:155`) | OM-03 | **4.4** | **Conflicto duro** |
| R20 | `4.5 (OM-03)` (`:156`) | OM-03 | **4.4** | **Conflicto duro** |
| R26 | `4.4` (`:180`) | — | — | **Conflicto semántico sin OM**: R26 es DLP/ISO 8.12; PSPI 4.4 es contingencia/ISO 5.30; el DLP es PSPI **4.3** |
| R32 | `4.3` (`:145`) | — | — | **Sospechoso sin OM**: R32 es XDR/antimalware ISO 8.7; PSPI 4.3 es DLP ISO 8.12 |
| R18, R31, R34 | `2.5 (OM-09)` | OM-09 | 2.5 | ✅ |
| R21 | `5.2 (OM-04)` | OM-04 | 5.2 | ✅ |
| R23, R37 | `2.4 (OM-08)` | OM-08 | 2.4 | ✅ |
| R41 | `4.2 (OM-02)` | OM-02 | 4.2 | ✅ |
| R22 | `4.8` | — | — | ✅ (ambos ISO 8.8) |
| R34 | `2.5 (OM-09), 5.3` (`:162`) | — | 2.5 + 5.3 | ✅ multivalor |
| R39 | `1.1, 1.2, 1.3` (`:165`) | — | 1.1+1.2+1.3 | ✅ multivalor |

**El desfase no es uniforme**: `4.5(OM-03)→4.4` y `4.4→4.3` sugieren un corrimiento de +1 en el grupo 4, pero `4.2(OM-02)` y `4.8` son correctos. **No hay regla aritmética válida**: solo el código `OM-xx` desambigua, y donde no lo hay (R26, R32) el importador **no puede resolver**.

**Corrección al enunciado del cambio**: el plan afirma «R26 ≡ 4.3». El documento dice literalmente `4.4` (`ptr-2026.md:180`). La *intención* muy probablemente sea 4.3 (ambos son DLP con ISO 8.12), pero eso es interpretación, no lectura.

### 2.3 PAI 2026 — `pai-2026.md`

- Hoja `PlandeacciónInstitucional`, dimensiones `A1:FD420`, 420 filas × 160 columnas (`:2`).
- **La estructura no es una tabla plana.** Cada actividad ocupa **dos filas**: `Programado` y `Ejecutado` (columna `PROGRAMADO / EJECUTADO`). Confirmado en `:20-24` (actividad 1), `:25-27` (actividad 2), `:285-292` (actividad 12.1).
- **Datos en `A9:AE229`** (221 filas). Columnas por cabecera (`:16-19`): `A` Visión … `G` Dimensiones MIPG, `H` **Políticas MIPG**, `I` Responsable, `J` **Código actividad No.**, `K` Actividad de gestión, `L` Producto, `M` Evidencia, `N` Índice, `O` Programado/Ejecutado, `P` Seg. I, `Q` Seg. II, `R` Seg. III, `S` Total programado vs ejecutado, `T` Fuentes de verificación, `U` Observaciones, `V` % de avance cuatrimestral, `W` Avance cualitativo, `X` Evidencia, `Y` Se cumplió la actividad, `Z` Se cumplió en la fecha, `AA` Monitoreo cualitativo, `AB` Evaluación independiente, `AC` Observaciones-recomendaciones, `AD` No. actividades programadas, `AE` No. actividades ejecutadas.
- **20 políticas MIPG**, legibles como los 20 bloques de celdas fusionadas de la columna `H` (`:3`): `H9:H24, H25:H36, H37:H44, H45:H52, H53:H66, H67:H78, H79:H92, H93:H104, H105:H124, H125:H132, H133:H140, H141:H152, H153:H162, H163:H166, H167:H174, H175:H186, H187:H202, H203:H214, H215:H226, H227:H229`. Siete bloques en `G` = las 7 dimensiones MIPG.
- **≈110 actividades**, no 223. `221 filas ÷ 2 = 110,5`; el último bloque `H227:H229` tiene 3 filas (anomalía de la fuente). **El «223» del enunciado cuenta filas, no actividades.**
- **Las 11 actividades propias, verificadas fila por fila**: `H141:H152` = 12 filas = **6 actividades** → política **`11.Gobierno digital`** (`:249`): `11.1` sensibilización Gobierno Digital (`:250`, periodo II), `11.2` actualizar documentación de Gestión Tecnológica en el SIG (`:258`, II), `11.3` estrategia integral de gobierno digital / tecnologías emergentes (`:269`, III), `11.4` seguimiento al PETI (`:271`, III), `11.5` formalizar y socializar procedimientos de arquitectura empresarial (`:273`, I), `11.6` actualización del Plan de Contingencia de TI (`:276`, II). `H153:H162` = 10 filas = **5 actividades** → política **`12. Seguridad digital`** (`:284`): `12.1` tres sensibilizaciones de seguridad digital (`:285`, I+II+III), `12.2` marco institucional de intercambio seguro de información (`:293`, I), `12.3` tres capacitaciones a administradores de SI (`:295`, I+II+III), `12.4` revisión/monitoreo/actualización de riesgos de SI (`:297`, II), `12.5` gestión de vulnerabilidades y seguridad en SI (`:300`, I+II+III). **Total 6 + 5 = 11.** ✅
- **El filtro por responsable rinde exactamente esas 11 filas**: `"Equipo Arquitectura Empresarial TI"` aparece 3 veces en la columna `I` (`:250,258,269`) y `"Equipo Tecnología de Información"` 8 veces (`:271,273,276,285,293,295,297,300`). **Pero es frágil**: la hoja contiene al menos una errata (`"Ofcina Asesora de Planeación"`, `:245`). El filtro debe normalizar (minúsculas, sin tildes, subcadena), no comparar cadenas exactas.
- **`scheduled_periods`** se lee de la fila `Programado` con `x` en `P/Q/R`; los `x` de la fila `Ejecutado` son *periodos ejecutados*, dato distinto. Ej.: `12.1` programada I+II+III y ejecutada I+II con `S = 0.66` (`:285,292`).
- **Ya hay seguimiento real cargado** en `11.1`, `11.2`, `11.6` y `12.1` (columnas `T`-`X`; ver `:250-256`, `:258-267`, `:276-282`, `:285-291`). Las cabeceras dicen «SEGUIMIENTO 2025» y «Total Programado Vs Ejecutado 2025» (`:9,19`) sobre un plan con fecha 31/01/2026 y versión 02 del 09/06/2026 (`:7,10`) — arrastre de plantilla. Ambigüedad a documentar (P2).
- **`CÓDIGO ACTIVIDAD No.` es un entero por política** (1,2,3…, ver `:20,25,28,32,38,40`), no un código global. La clave compuesta `{política}.{código}` del enunciado es correcta y necesaria.

### 2.4 Checklist de tareas — `checklist-tareas.md`

- 136 filas, 11 columnas (`:2`). `Fila N ↔ T-(N-1)` (verificado en `:20` `A2=T-01`, `:32` `A3=T-02`, `:752` `A63=T-62`, `:1004` `A84=T-83`, `:1556` `A130=T-129`).
- **Los 25 enlaces PSPI son deterministas y triplemente redundantes**, no heurísticos: (1) prefijo `[PSPI x.y]` en la columna `F` — **filas 83 a 107 = T-82 a T-106**, en orden `1.1 → 6.3`, exactamente 25 (`:997-1285`); (2) columna `E` = `Plan Seguridad D612` (`:996`); (3) columna `K` con el marcador `[ORIGEN: Plan de Seguridad y Privacidad de la Información v2 del 20-ene-2026, actividad 1.1. Cargada al checklist el 2026-08-14 09:53.]` (`:1002,1014,1230`). **Coincide con lo anunciado** (`T-82…T-106 → PSPI 1.1…6.3`, rol `primary`).
- **Los enlaces PAI NO son deterministas.** `T-62` (`:752-762`) tiene categoría `Plan de Acción Institucional` y su detalle (`:758`) enumera en prosa las cinco actividades: sensibilización de seguridad digital (12.1), capacitación a administradores (12.3), revisión de riesgos (12.4), gestión de vulnerabilidades (12.5) y Plan de Contingencia de TI (11.6). **Coincide con lo anunciado**, pero solo un humano lo deriva de ese texto.
- **Hallazgo no previsto**: `T-63` (`:768-769`) también es categoría `Plan de Acción Institucional` («Reportar acciones y evidencias del Plan de Acción — julio 2026») y no está en el mapa del enunciado. Debe entrar en la tabla semilla.
- El reporte de cruce (`reporte-cruce-2026-08-14.md`) es **análisis del usuario sobre 81 tareas (T-01..T-81)**, anterior a la carga de T-82..T-106 que él mismo recomienda (`:90`). Es insumo de contexto, no fuente oficial ni fuente de enlaces.

---

## 3. Áreas afectadas

| Ruta | Por qué |
|---|---|
| `backend/alembic/versions/00NN_add_institutional_plans.py` | 5 tablas nuevas, FKs, únicos, JSONB |
| `backend/app/modules/plans/{__init__,models,schemas,repository,service,router}.py` | Módulo nuevo, patrón router→service→repository |
| `backend/app/modules/plans/importers/{docx_reader,pspi,ptr,pai,common}.py` | Lectura de las tres fuentes (45b) |
| `backend/app/modules/plans/linker.py` + `seeds/task_activity_links.py` | Resolución de enlaces + mapa semilla versionado (45b) |
| `backend/scripts/import_plans.py` | CLI delgada con `--dry-run` (patrón `purge_demo_data.py`) (45b) |
| `backend/app/main.py:18-46,158-188` | Import + `include_router` |
| `backend/app/db_init.py:43-96` | Import de modelos `# noqa: F401` |
| `backend/app/db_init.py:133-163` | `_MENU_SEED` + `_ROLE_MENU_SEED` (sin migración) |
| `backend/app/config.py` | Guardas antibomba propias para los archivos de plan (45b) |
| `backend/tests/test_plans_*.py`, `backend/tests/fixtures/plans/*` | TDD estricto obligatorio |
| `frontend/src/entities/plan/{plan.model.ts,plans.service.ts}` | Modelo + servicio (45c) |
| `frontend/src/pages/plans/plans.component.ts` | Página lazy (45c) |
| `frontend/src/app/app.routes.ts:96` | Ruta antes del comodín (45c) |
| `frontend/src/widgets/sidebar/ui/sidebar-icons.ts:17-28` | Alias del ícono del menú (45c) |
| `frontend/src/assets/i18n/es-CO.json` | Todo el texto visible (45c) |
| `openspec/specs/institutional-plans/spec.md` (nueva) + deltas en `tasks`, `project-hierarchy` | Requisitos |

---

## 4. Decisiones recomendadas

### D1 — Identificador público: `code` + clave derivada, **sin `public_id`**

Descartar `public_id`. Adoptar la convención existente (§1.2):

- `plans.code String(20)` con `UniqueConstraint("organization_id","code")` → `PSPI-2026`, `PTR-2026`, `PAI-2026`, `PTEP-2026`.
- `plan_activities.code String(20)` con `UniqueConstraint("plan_id","code")` → `1.1`, `R34`, `12.1`.
- **Clave legible derivada, transitoria en el esquema Pydantic**, calculada en el servicio igual que `task_key` (`app/modules/tasks/service.py:967`): `read.activity_key = f"{plan.code}/{activity.code}"` → `PSPI-2026/1.1`, `PAI-2026/12.4`. Nunca se persiste; se expone en toda respuesta que lleve una actividad y es el token que consume el CSV del 44 y el enlazador.

**Justificación**: cero convenciones nuevas, cero columnas redundantes, y una clave que sobrevive a un cambio de `id` porque se reconstruye de dos columnas con unicidad garantizada.

### D2 — Modelo final

```
plans                       (TenantMixin, PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin)
  code             String(20)   NOT NULL
  name             String(255)  NOT NULL
  plan_type        String(20)   NOT NULL      -- 'pspi' | 'ptr' | 'pai' | 'ptep'
  period_year      Integer      NOT NULL
  version          String(50)   NULL          -- 'v2_20260120'
  source_document  String(500)  NULL
  status           String(20)   NOT NULL default 'active'
  UNIQUE (organization_id, code)              -> uq_plans_org_code
  INDEX  (organization_id, plan_type, period_year) -> ix_plans_org_type_year

plan_activities             (PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin)
  plan_id            UUID FK plans ON DELETE CASCADE, index
  code               String(20)   NOT NULL
  group_code         String(20)   NULL        -- '1' | 'ALTO' | '12'
  group_name         String(255)  NULL        -- 'DATOS PERSONALES' | '12. Seguridad digital'
  name               Text         NOT NULL
  deliverable        Text         NULL        -- PRODUCTO
  evidence_expected  Text         NULL        -- EVIDENCIA
  responsible        String(255)  NULL
  is_mine            Boolean      NOT NULL default false
  due_date           Date         NULL
  target_from        Numeric(5,2) NULL
  target_to          Numeric(5,2) NULL
  iso_controls       JSONB        NULL        -- ["8.10","8.15"]
  external_codes     JSONB        NULL        -- ["OM-05","OM-08"]   <- PLURAL
  scheduled_periods  JSONB        NULL        -- ["I","II","III"]
  sort_order         Integer      NOT NULL default 0
  UNIQUE (plan_id, code)                      -> uq_plan_activities_plan_code
  INDEX  (plan_id, is_mine)                   -> ix_plan_activities_plan_is_mine

plan_activity_reports       (PkMixin, TimestampMixin, AuditMixin)
  plan_activity_id    UUID FK plan_activities ON DELETE CASCADE, index
  period              String(10)   NOT NULL   -- 'I' | 'II' | 'III' | 'ANUAL'
  reported_progress   Numeric(5,2) NULL
  qualitative_summary Text         NULL
  evidence_refs       JSONB        NULL
  is_met              Boolean      NULL
  met_on_time         Boolean      NULL
  UNIQUE (plan_activity_id, period)           -> uq_plan_activity_reports_activity_period

plan_activity_links         (PkMixin, TimestampMixin, AuditMixin)
  from_activity_id  UUID FK plan_activities ON DELETE CASCADE, index
  to_activity_id    UUID FK plan_activities ON DELETE CASCADE, index
  link_type         String(20)  NOT NULL default 'contributes_to'
  source_reference  String(50)  NULL          -- '4.5 (OM-03)' literal de la fuente
  resolution        String(20)  NOT NULL      -- 'exact'|'by_external_code'|'conflict'|'manual'
  UNIQUE (from_activity_id, to_activity_id, link_type) -> uq_plan_activity_links_from_to_type
  CHECK  (from_activity_id <> to_activity_id)          -> ck_plan_activity_links_no_self

task_plan_activities        (PkMixin, TimestampMixin, AuditMixin)
  task_id           UUID FK tasks ON DELETE CASCADE, index
  plan_activity_id  UUID FK plan_activities ON DELETE CASCADE, index
  role              String(20) NOT NULL       -- 'primary' | 'contributes'
  note              Text       NULL
  UNIQUE (task_id, plan_activity_id)          -> uq_task_plan_activities_task_activity
```

Cambios frente al modelo del plan aprobado, con su razón:

1. **`external_code` → `external_codes JSONB`**: la fuente tiene una actividad con dos códigos (`PSPI 2.4 = OM-05/OM-08`, `pspi-2026.md:101`).
2. **Se elimina `plan_activities.reported_progress`**: duplicaría el dato que ya vive en `plan_activity_reports`. El avance reportado «vigente» se calcula como el último periodo con reporte.
3. **Se eliminan `reported_at`/`reported_by`** de `plan_activity_reports`: `TimestampMixin` + `AuditMixin` ya aportan `created_at`/`updated_at`/`created_by`/`updated_by`.
4. **`plan_activity_links` gana `source_reference` + `resolution`**: el conflicto `OM-xx` queda **persistido y consultable**. Un enlace con `resolution='conflict'` se muestra en la UI con `SolBadge` de advertencia y jamás se cuenta como enlace confirmado.
5. **`CHECK` anti-autorreferencia** en los enlaces.
6. **`plan_activities` no lleva `organization_id`**: el alcance de tenant llega transitivamente por `plan_id → plans.organization_id`, y toda consulta del repositorio hace el `JOIN` explícito, como `rollup_progress` (`projects/repository.py:302-303`).
7. **Longitud de identificadores**: el más largo es `uq_plan_activity_reports_activity_period` (40 caracteres), muy por debajo del límite de 63 de PostgreSQL.

### D3 — Doble avance por actividad

- **Calculado** (`calculated_progress`): sobre las tareas enlazadas con `role='primary'`. Denominador: enlaces `primary` cuya tarea está activa y no excluida del avance (criterio vigente de `projects/repository.py:330,335`, que el 44 convierte en bandera por columna). Numerador: esas tareas cuyo `status` coincide con el `status_key` de la **última columna del board del proyecto de cada tarea** — el CTE `DISTINCT ON (board.project_id) ... ORDER BY column_order DESC, created_at DESC` de `projects/repository.py:308-327` se conserva, unido por `board.project_id = task.project_id`. **Cero enlaces `primary` ⇒ `calculated_progress = null`, nunca `0`.** Los enlaces `contributes` **no entran en la razón**: se exponen aparte como `contributing_task_count`.
- **Reportado** (`reported_progress`): el valor del periodo consultado en `plan_activity_reports`, o `null` si ese periodo aún no tiene reporte. La UI muestra las dos barras (`SolProgressBar variant="primary"` calculado, `variant="success"` reportado) y **nunca** rellena una con la otra.

### D4 — Lectura de DOCX: **`zipfile` + `xml.etree` de la biblioteca estándar**, sin dependencia nueva

| Opción | Ventajas | Desventajas | Esfuerzo |
|---|---|---|---|
| **A. `python-docx`** | API conocida; celdas fusionadas resueltas por la librería | Dependencia nueva + `lxml` (extensión en C) en la imagen; exige el rigor de `requirements.txt:18-29`; **oculta `gridSpan`, que es justo la señal que usamos para detectar filas de grupo** | Baja |
| **B. `zipfile` + `xml.etree` (stdlib)** | Cero dependencias; acceso directo a `w:gridSpan`/`w:vMerge`; ~70 líneas en `docx_reader.py` | Código propio que mantener; hay que probar el lector aparte | Media-baja |
| **C. Exigir texto/CSV preextraído** | El importador no toca DOCX | Traslada el trabajo frágil a un paso manual; rompe la idempotencia reproducible | Baja |

**Recomendación: B.** Si la compuerta de Fase 0 sobre los archivos reales demuestra que el lector crudo no basta, se cae a A **documentando la decisión con el rigor de `requirements.txt:18-29`**. Para XLSX: `openpyxl==3.1.5` ya está y `app/integrations/adapters/jira/file_parser.py` es el patrón a copiar, guardas antibomba incluidas (`config.py:249-250`).

### D5 — Frontera con Solercia Security (ADR 0009)

`docs/adr/0009-...:80,238-240`: Security es la única autoridad sobre cumplimiento, validación y cierre de evidencia; Command no toma decisiones de SGSI. **Command guarda solo el autorreporte de primera línea** — `% de avance cuatrimestral` (`V`), `avance cualitativo` (`W`), `evidencia` (`X`), `se cumplió la actividad` (`Y`) y `se cumplió en la fecha programada` (`Z`). **Command NO modela** las columnas de segunda y tercera línea de defensa del PAI — `Monitoreo Cualitativo` (`AA`), `Evaluación independiente` (`AB`) y `Observaciones - recomendaciones` (`AC`). Debe quedar escrito en el `design.md` como frontera, no como omisión.

### D6 — Política del importador ante conflictos: **registrar, nunca resolver en silencio**

1. Resolver por `OM-xx` cuando el texto lo traiga → `resolution='by_external_code'`.
2. Si además el número coincide → `resolution='exact'`.
3. Si el número **no** coincide con el que lleva ese `OM-xx` (R17, R19, R20) → crear el enlace hacia la actividad que lleva el `OM-xx`, marcarlo `resolution='conflict'`, guardar el texto literal en `source_reference` y emitirlo en el CSV de revisión.
4. Si **no hay `OM-xx`** y el número es semánticamente sospechoso (R26 `4.4`, R32 `4.3`) → **no crear enlace**. Emitir la fila en el CSV de revisión con el motivo. Un enlace inventado es peor que un enlace ausente.
5. `T-xx` que resuelva a **más de una tarea** por `get_by_external_key` → ambigüedad reportada, sin enlace.
6. Riesgos con acción pero sin fila en la matriz (R31) → se importan igual, con advertencia. Riesgos en la matriz sin acción (R40, R43) → se importan como actividad sin producto, con advertencia.

Idempotencia por `(plan.code, activity.code)` para actividades y por `(task.id, plan_activity.id)` para enlaces; `--dry-run` por defecto, `--execute` explícito, códigos de salida tipados.

### D7 — Formato de `plan_links` para el CSV del 44

`PSPI-2026/1.1:primary;PAI-2026/12.4:contributes` — separador de enlaces `;`, de campos `:`, sin espacios; cadena vacía cuando no hay enlaces. La clave es **exactamente** `activity_key` de D1. El 44 la emite como columna informativa; el 45b la consume como una entrada más del enlazador, sujeta a D6.

### D8 — Numeración de migración

Compuerta de Fase 0: `alembic heads` en vivo + inventario de `backend/alembic/versions/` + revisión de los cambios pendientes.

---

## 5. Rebanado y estimación

| Pieza | Líneas | ×1,2 |
|---|---:|---:|
| Migración 5 tablas + índices + docstring | 200 | 240 |
| `models.py` (5 modelos) | 180 | 216 |
| `schemas.py` | 140 | 168 |
| `repository.py` (roll-up cruzado + CRUD + enlaces) | 220 | 264 |
| `service.py` | 200 | 240 |
| `router.py` (8 endpoints) | 180 | 216 |
| Cableado `main.py` + `db_init.py` + menú | 15 | 18 |
| Prueba de migración | 230 | 276 |
| Prueba de repositorio / roll-up | 200 | 240 |
| Pruebas de endpoints | 320 | 384 |
| **Subtotal modelo + API (45a)** | **1 885** | **2 262** |
| `docx_reader.py` (stdlib) | 70 | 84 |
| `common.py` (fechas, metas, ISO, normalización) | 140 | 168 |
| `pspi.py` | 200 | 240 |
| `ptr.py` (incluye reporte de conflictos) | 220 | 264 |
| `pai.py` (dos filas por actividad, bloques fusionados) | 230 | 276 |
| `linker.py` + `seeds/task_activity_links.py` | 200 | 240 |
| `scripts/import_plans.py` | 180 | 216 |
| Pruebas de importadores + enlazador | 740 | 888 |
| Fixtures sintéticos (constructores DOCX/XLSX) | 120 | 144 |
| **Subtotal importadores (45b)** | **2 100** | **2 520** |
| `entities/plan/*` | 140 | 168 |
| `pages/plans/plans.component.ts` | 300 | 360 |
| Tabla de actividades (compone `SolDataTable`) | 180 | 216 |
| Formulario de seguimiento (modal) | 200 | 240 |
| Rutas + ícono + i18n | 120 | 144 |
| **Subtotal frontend (45c)** | **940** | **1 128** |
| Specs delta + documentación | 350 | 420 |
| **TOTAL** | **≈ 5 275** | **≈ 6 330** |

### Tres cambios SDD, no uno con muchas rebanadas

| Cambio | Alcance | Líneas ×1,2 | Rebanadas | Depende de |
|---|---|---:|---:|---|
| **45a — modelo y API de planes** | Migración, 5 modelos, esquemas, repositorio con roll-up cruzado, servicio, router, RBAC, menú, pruebas | ≈ 2 262 | 6 | nada (puede arrancar ya) |
| **45b — importadores y enlazador** | Lector DOCX, 3 importadores, `common.py`, enlazador, mapa semilla, CLI, CSV de revisión, fixtures, pruebas | ≈ 2 520 | 6 | **45a** + **43 aplicado** |
| **45c — vista «Planes»** | Entidad, servicio, página, tabla, formulario de seguimiento, rutas, i18n, ícono | ≈ 1 128 | 3 | **45a** |

Rebanadas propuestas para **45a** (todas ≤ 400 antes de sumar las marcas de `tasks.md`):

| # | Rama | Contenido | Líneas |
|---|---|---|---:|
| A | `feat/45a-migracion` | Migración + espejo en `__table_args__` + prueba de migración | ~390 |
| B | `feat/45a-modelos` | 5 modelos + `db_init` + esquemas | ~330 |
| C | `feat/45a-repositorio` | Repositorio + roll-up cruzado + pruebas de repositorio | ~380 |
| D | `feat/45a-servicio` | Servicio + `activity_key` derivado + pruebas con fakes | ~330 |
| E | `feat/45a-api-lectura` | `GET` de planes/actividades/tareas + pruebas de endpoints | ~390 |
| F | `feat/45a-api-escritura` | `POST` de reportes y enlaces + RBAC + menú + pruebas | ~380 |

---

## 6. Riesgos

1. **Tamaño**: ≈ 6 300 líneas → tres cambios, 15 rebanadas.
2. **Colisión de numeración de migración**: 43→`0025`, 44→`0026`+`0027` → 45a→`0028` (compuerta en vivo en Fase 0). Sin números reservados: el 40 toma el siguiente consecutivo libre en su propio `apply`.
3. **45b bloqueado por el 43** (y por el 44 para `plan_links` y `context_group`).
4. **Conflictos de la fuente PTR**: 3 duros `OM-03` (R17/R19/R20) y 2 referencias sin `OM` sospechosas (R26→`4.4`, R32→`4.3`) → D6 + `resolution`/`source_reference` persistidos.
5. **Frontera ADR 0009** → D5 explícita.
6. **Confidencialidad**: el PTR declara reservado el detalle de riesgos (`ptr-2026.md:78`) → **los documentos reales no se versionan como fixtures**; sintéticos mínimos en `backend/tests/fixtures/plans/`.
7. **Estructura del PAI**: dos filas por actividad y 20 bloques fusionados → lector por bloque + prueba dedicada.
8. **Filtro por responsable frágil** (`"Ofcina"`) → normalización + aserción de 11 filas.
9. **El roll-up no se reutiliza tal cual** → SQL nuevo probado contra PostgreSQL real.
10. **Ambigüedad de `get_by_external_key`** → D6.5.
11. **Sin pruebas de frontend** → `ng build` + `eslint` + lista de comprobación de los 5 estados.
12. **Los archivos fuente viven fuera del repositorio** → rutas explícitas en la CLI.
13. **Inconsistencias internas del PTR** → advertencias, nunca error duro.

---

## 7. Preguntas abiertas (con recomendación)

| # | Pregunta | Recomendación |
|---|---|---|
| **P1** | ¿El 45 cubre también el PTEP-2026? No hay fuente extraída. | Modelar `plan_type` con los cuatro valores; importar solo PSPI/PTR/PAI. |
| **P2** | El PAI trae seguimiento ya diligenciado en 11.1, 11.2, 11.6 y 12.1 con cabeceras «2025» sobre un plan de 2026. | Importarlos como `plan_activity_reports` del periodo marcado, dejando constancia de la ambigüedad en `qualitative_summary`. **Confirmar con el usuario** (no bloquea). |
| **P3** | ¿Quién escribe un reporte de seguimiento? | `require_role(admin, manager)`; lectura para cualquier miembro. |
| **P4** | ¿Qué números reclama el cambio 44? | `0026` y `0027` (decidido): 45a → `0028`. |
| **P5** | Los enlaces PAI son juicio del usuario, no dato de la fuente. | Tabla semilla versionada en `app/modules/plans/seeds/task_activity_links.py`, cada fila con `note`. **Añadir `T-63`.** |
| **P6** | «R26 ≡ 4.3» vs el documento (`4.4`); R32→`4.3` sospechoso. | Se aplica D6.4: sin enlace, fila de revisión con el motivo; el usuario decide en el CSV. |
| **P7** | ¿`plan_activities` denormaliza `organization_id`? | No (D2.6); ratificar en diseño con prueba de aislamiento de tenant. |

### Decisiones del orquestador (2026-08-26, autonomía delegada por el usuario)

1. **El 45 se parte en tres cambios SDD**: `45a-planes-modelo-api` (sin dependencias; arranca ya en planificación), `45b-planes-importadores` (depende de 45a, 43 aplicado y 44 aplicado para `plan_links`/`context_group`), `45c-planes-vista` (depende de 45a; checklist `ux-psicologia` obligatorio).
2. **Sin `public_id`**: se adopta D1 (`code` + `activity_key` derivado `PSPI-2026/1.1`). Es una desviación de la redacción literal de la decisión del usuario («N:N con public_id»), no de su intención (identificador público estable y legible); se informa en el reporte matutino.
3. D2 (modelo con `external_codes` JSONB, sin `reported_progress` redundante, `resolution`/`source_reference` en enlaces, `CHECK` anti-autorreferencia, sin denormalizar `organization_id`), D3 (doble avance; `null` ≠ `0`), D4 (DOCX por stdlib), D5 (frontera ADR 0009), D6 (conflictos registrados, nunca resueltos en silencio; R26/R32 sin enlace y a revisión), D7 (formato `plan_links`), P1 (cuatro `plan_type`, tres importados), P3 (admin+manager escriben), P5 (tabla semilla + `T-63`), P7 (sin denormalizar) — **adoptadas**.
4. Migración del 45a: **`0028`** con `down_revision="0027"` (43→`0025`; 44→`0026` y `0027`, porque partió su migración en dos rebanadas con reversa independiente), confirmada por compuerta en vivo en Fase 0. **Sin reservas**: el cambio 40 toma el siguiente consecutivo libre en el momento de su propio `apply`.
5. P2 (seguimiento 2025/2026 del PAI): se importa con constancia de la ambigüedad; el usuario confirma después (no bloquea 45a).
6. Fixtures sintéticos únicamente; los documentos reales nunca entran al repositorio.

## 8. ¿Listo para propuesta?

**Sí** para 45a con las decisiones anteriores; 45b y 45c se proponen cuando 45a tenga spec y diseño.
