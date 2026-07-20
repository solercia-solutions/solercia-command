# OLA 4 — Plan aprobado y guía de ejecución

> **Estado**: APROBADO por el usuario (2026-07-20) — decisiones 1 a 4 resueltas.
> **Rama base**: `preview` · **Ejecución**: vía briefing `openspec/OLA_4_BRIEFING.md`.
> Este documento es la fuente de verdad de la ola: fases, cambios SDD, reglas y criterios.

---

## 1. Decisiones resueltas

| № | Decisión | Resolución del usuario |
|---|----------|------------------------|
| 1 | Factor de conversión w/d/h | **Calendario laboral configurable por equipo** (equipo = proyecto raíz, ver decisión 3): horas por día y días laborales de la semana, porque desarrollo no trabaja igual que soporte y algunos equipos trabajan fin de semana. Valor por defecto de la empresa: 8h/día, lunes-viernes; cada equipo puede sobreescribirlo y los proyectos hijos lo heredan. |
| 2 | Nombre editable en proyectos de plantilla | **Sí** — editable desde la vista unificada Proyectos/Jerarquía, conservando trazabilidad del template de origen. |
| 3 | ¿Entidad Team o equipo = proyecto raíz? | **Mantener equipo = proyecto raíz** y distinguir por tipo con `project_kind` (`area` \| `proyecto`). La entidad Team queda condicionada a los disparadores del debate (capacidad por equipo, proyectos transversales, reorganizaciones, permisos de equipo). |
| 4 | Importación Jira con cuenta administradora | **Entra en esta ola.** Viabilidad PROBADA el 2026-07-20 contra `idartes-tecnologia.atlassian.net` con las credenciales de `AUTOMATINFORMES/.env`: `ADMINISTER: True`, 36 proyectos visibles, 31 tableros, sprints históricos e issues consultables por JQL. Ver sección 5. |
| 5 | Controles de metodología en sprint | Pendiente de confirmación explícita; se planifican como cambio opcional al final (Fase 4.5) con severidad "aviso". No bloquea la ola. |

**Prioridad confirmada por el usuario**: el multi-tenant backend va PRIMERO (cada empresa con sus proyectos, usuarios, métricas, dashboards y conectores por usuario).

---

## 2. Metodología de trabajo (obligatoria en toda la ola)

1. **SDD por cada cambio**: cada cambio listado en la sección 3 sigue el ciclo completo `explore → propose → spec → design → tasks → apply → verify → archive` en `openspec/changes/`. Verificar el consecutivo real disponible en `openspec/changes/archive/` antes de crear cada cambio (la numeración de abajo es tentativa desde 25).
2. **TDD estricto**: prueba primero (roja), implementación mínima (verde), refactor. Backend con pytest in-process (httpx.AsyncClient/ASGI, patrón de la suite actual); mínimo happy path + caso de error + caso de permisos por endpoint; tests de contrato para reglas de negocio (conversión de horas, scoping por empresa, idempotencia).
3. **Ramas**: una feature branch por cambio (`feat/...`, `fix/...`) partiendo de `preview`; merge a `preview` al cerrar su ciclo. **NUNCA tocar `main`.**
4. **Commits**: convencionales en español, sin atribución de IA, staging selectivo.
5. **Patrones del proyecto**: Repository pattern (el service nunca toca SQLAlchemy directo), Strategy para metodologías (prohibido `if methodology == ...` regado), soft delete, auditoría `created_by/updated_by`, multi-tenant por `organization_id`, respuestas envueltas `{data, message, meta}`.
6. **Textos de UI**: español colombiano formal (tuteo). Nunca voseo.
7. **Cierre de la ola**: `./gestion.sh restart`, verificar front y backend en 200, actualizar la guía de prueba y **reportar la URL del túnel** para revisión desde el celular.

---

## 3. Fases y cambios SDD

### Fase 4.1 — Multi-empresa backend (PRIMERO, decisión del usuario)

**Cambio 25 — `multiempresa-scoping`**
- Auditoría y endurecimiento del aislamiento por `organization_id` en TODAS las consultas: proyectos, usuarios, roles, actividades, dependencias, apariencia, plantillas/equipos, menús, búsqueda global, métricas y dashboards.
- Conectores y cuentas conectadas pasan a ser **por empresa y por usuario**.
- TDD: test de fuga cross-tenant por módulo (dos empresas sembradas; la consulta de una jamás devuelve datos de la otra).

**Cambio 26 — `admin-empresas`**
- CRUD de empresas; membresías multi-empresa (un usuario puede pertenecer a varias con roles distintos); selector de empresa activa en la UI (patrón boki: empresa → usuarios, roles, servicios).
- TDD: permisos por rol en cada endpoint; cambio de empresa activa refresca el contexto completo.

**Cambio 27 — `plantillas-idempotentes` (bug confirmado en prueba)**
- Instanciar una plantilla ya aplicada **reconcilia** (o rechaza con mensaje claro), nunca duplica. Incluye limpieza de los duplicados OAP-TI existentes.
- El generador marca los nodos con `project_kind` (`area` para contenedores del organigrama, `proyecto` para trabajo real) — implementa la decisión 3.
- TDD: doble instanciación → un solo árbol; listados filtran por `project_kind`.

**Cambio 28 — `calendario-laboral`**
- Nueva configuración: `working_hours_per_day` y `working_days` (días de la semana) a nivel empresa, con **override por equipo (proyecto raíz)** y herencia a los proyectos hijos — implementa la decisión 1.
- Es prerequisito de la estimación normalizada (cambio 34) y de la curva esperada (cambio 35).
- TDD: resolución en cascada hijo → raíz → empresa → default (8h, L-V).

### Fase 4.2 — Backlog estilo Jira (lo más pedido por el usuario)

**Cambio 29 — `sprint-borrador`**
- Sprint creable solo con nombre (estado `draft`, sin fechas). Autonombre: base del anterior + consecutivo (`PANDORA 2026-1` → `PANDORA 2026-2`; sin anterior: `<CLAVE> Sprint 1`). "Añadir fechas" habilita "Iniciar sprint".
- TDD: no se puede iniciar sin fechas; consecutivo correcto con nombres no convencionales.

**Cambio 30 — `backlog-sprints-agrupados`**
- Vista backlog con los sprints como secciones colapsables arriba (diseño compacto estilo Jira): nombre, fechas, conteo, suma de estimaciones, acción contextual (Iniciar/Completar).

**Cambio 31 — `backlog-drag-drop`**
- Arrastrar historias/tareas backlog ↔ sprint y entre sprints no iniciados; zona de drop visible.

**Cambio 32 — `jerarquia-subtareas`**
- Subtareas indentadas bajo su padre con clave, estado, estimación y avatar.
- **Regla de producto**: una subtarea asignada a un usuario SIEMPRE aparece al filtrar por ese usuario, aunque el padre esté asignado a otro (padre atenuado como contexto). Nada se oculta por posición jerárquica.
- TDD: filtro por asignado devuelve subtareas de padres ajenos.

**Cambio 33 — `busqueda-filtros`**
- En backlog Y cronograma (Gantt): búsqueda por `task_key` (ej. "SDM-7") y texto parcial (expande/resalta sprints colapsados con match); fila de avatares para filtrar por asignado (multi-selección, "+N"); filtros por épica, tipo y rango de fechas.
- Apoyarse en el módulo `search` existente. JQL queda fuera de alcance (visión futura).

**Cambio 34 — `estimacion-normalizada`**
- Blindar que TODO camino de escritura (formularios, import, API) convierta w/d/h → horas antes de persistir (la BD ya guarda horas: `tasks/models.py:113`).
- Formateador único de despliegue (mayor unidad alcanzada: `6h`, `Xd Yh`, `Xw Yd Zh`) usando el calendario laboral del cambio 28.
- TDD: contrato de conversión ida y vuelta con calendarios distintos (8h/L-V vs. equipo con fin de semana).

### Fase 4.3 — Vista de jefe y proyectos

**Cambio 35 — `avance-esperado-vs-real`**
- % esperado a la fecha por proyecto y rollup por subárbol/área (distribución por due dates sobre días laborales del calendario; lineal si faltan fechas).
- % real por completadas (ponderado por horas si existen). Tarjeta: esperado, real, desviación, tendencia 4 semanas.
- Semáforo (≤5% verde, ≤15% amarillo, >15% rojo; umbrales por empresa) + alerta de refuerzo accionable ("para cumplir el 31 de julio, esta semana el equipo debe completar N horas") integrada al motor de alertas.
- Corte mensual por área: qué llega, qué necesita refuerzo, qué va adelantado.

**Cambio 36 — `proyectos-jerarquia-unificada`**
- El árbol pasa a ser la vista principal de proyectos: clic en nodo → tareas de ese proyecto; editar nombre/descripción en el nodo (decisión 2); la grilla plana desaparece o queda como filtro "solo hojas"; distinción visual por `project_kind`.

**Cambio 37 — `cambio-metodologia`**
- Cambiar `methodology` de un proyecto existente con asistente de mapeo de estados/columnas origen → destino, vía Strategy pattern.
- TDD: ninguna tarea queda en estado inválido tras migrar.

### Fase 4.4 — Conexiones: de "conectado" a "útil"

**Cambio 38 — `oauth-ms-google`**
- Diagnóstico y reparación del OAuth de Microsoft 365 y Google, con prueba end-to-end desde la UI.

**Cambio 39 — `conector-capacidades`**
- Tarjeta de conector con panel de acciones post-conexión: importar proyectos / sprints / historias / sincronizar. Nada de "conectado" sin acciones.

**Cambio 40 — `jira-import-usuario`**
- Flujo: elegir proyecto(s) → previsualizar (conteos de épicas/historias/subtareas/sprints, mapeo de estados y estimaciones) → importar.
- Mapeo: épica→epic, historia→story, subtarea→subtask, bug→bug; sprints con fechas y estado; estimación original → horas (cambio 34); clave Jira original preservada como referencia.
- Cimientos existentes: módulo `jira_import` (parser + cliente HTTP).

**Cambio 41 — `jira-import-admin`**
- Modo administrador: con credenciales de admin del sitio se importa TODO (todos los proyectos, tableros y sprints). Viabilidad probada — ver sección 5.
- Selección múltiple de proyectos, importación por lotes con progreso, reanudable.

### Fase 4.5 — Opcional (pendiente confirmación del usuario)

**Cambio 42 — `controles-sprint`** (severidad "aviso" por defecto)
1. Iniciar sprint avisa si hay historias sin estimación o sin fechas.
2. Aviso al agregar historia con vencimiento posterior al fin del sprint (nunca bloqueo).
3. Snapshot de horas/puntos comprometidos al iniciar + registro de scope changes → burndown y velocity honestos.
4. Cierre de sprint con flujo guiado: mover incompletas a backlog o siguiente sprint; nunca extender fechas silenciosamente.

---

## 4. Verificaciones previas (hechos comprobados en código)

| Hecho | Evidencia |
|---|---|
| `estimation_hours` ya se guarda en horas (`Numeric(7,2)`) | `backend/app/modules/tasks/models.py:113` |
| `task_key` tipo "SDM-7" con contador atómico ya existe | `tasks/models.py:140-143` |
| Módulos `search` y `jira_import` (parser + cliente HTTP) ya existen | `backend/app/modules/` |
| Árbol de proyectos (`parent_project_id` indexado) + `lead_user_id` | `projects/models.py` |
| NO existe entidad Team; Equipos = generador desde `org_role_templates` | `backend/app/modules/` |
| Multi-tenancy row-level ya presente (`TenantMixin`) | modelos tenant-scoped |

## 5. Credenciales Jira admin — instrucciones y evidencia

**Prueba ejecutada el 2026-07-20** contra `https://idartes-tecnologia.atlassian.net` con el token de `/Users/camilocalderont/Proyectos/PERSONAL/AUTOMATINFORMES/.env` (usuario `cristian.calderontapia@idartes.gov.co`):

- Permiso `ADMINISTER` (administración del sitio): **True**.
- Proyectos visibles: **36** (AAC, BDBP, CM, CON, CP/PANDORA-IDARTES, EQ, FAQ, FOMENTO, GDU, HDC, LAV, LR, ...).
- Tableros: **31** (scrum y simples). Sprints históricos legibles (desde 2021) con fechas y estado. Issues consultables vía JQL.

**Conclusión**: con esas credenciales el modo admin (cambio 41) puede traer absolutamente todo el sitio. No se necesita nada adicional para IDARTES.

**Reglas de seguridad para la ejecución**:
- El token NUNCA se copia a archivos del repositorio ni a commits; se registra por la UI de Conexiones (o `.env` local del backend) y se persiste cifrado con `INTEGRATIONS_FERNET_KEY`, como ya hace el módulo de conectores.
- Requisito general para otros sitios: token de API de una cuenta con "Browse Projects" en todos los proyectos (idealmente admin del sitio), URL base y correo de la cuenta.

## 6. Fuera de alcance de la OLA 4

- Lenguaje de consulta tipo JQL (visión futura).
- Entidad Team (condicionada a los disparadores documentados en la decisión 3).
- Importación desde Microsoft Planner / Google (primero OAuth reparado; la importación llega en ola posterior).
- Etiquetas en filtros.

## 7. Definition of Done de la ola

1. Los cambios de las fases 4.1 a 4.4 archivados con su ciclo SDD completo y suite backend en verde.
2. Migraciones Alembic aplicadas y reversibles.
3. Guía de prueba de la ola actualizada.
4. `./gestion.sh restart` ejecutado, front y backend respondiendo 200, y **URL del túnel reportada al usuario** para prueba desde el celular.
