# OLA 2 — Plan orquestado de especificaciones

> Documento de orquestación para agentes LLM. Cada funcionalidad de la OLA 2 se atiende como un
> cambio SDD independiente en `openspec/changes/<id>-<nombre>/`, con ciclo completo
> `proposal → specs → design → tasks → apply (TDD estricto) → verify → archive`.
> Este documento define el orden, las dependencias y qué se puede ejecutar en paralelo.

## Cómo usar este documento (instrucciones para el orquestador)

1. **Persistencia**: modo `hybrid` — artefactos en `openspec/changes/<id>-<nombre>/` (proposal.md,
   specs/, design.md, tasks.md, state.yaml) + espejo en Engram con topic keys `sdd/<id>-<nombre>/<fase>`.
2. **TDD estricto obligatorio** en todo apply de backend. Test runner:
   `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v`.
3. **Paralelización**:
   - Las fases de planeación (proposal, specs, design, tasks) de specs SIN dependencia entre sí
     pueden ejecutarse en paralelo con agentes independientes.
   - La fase **apply es serializada por repositorio** (un solo escritor a la vez). Los cambios con
     migración Alembic NUNCA se aplican en paralelo: la cadena de revisiones es lineal
     (`down_revision` apunta a la migración anterior).
   - Un spec no inicia su planeación hasta que sus dependencias tengan al menos `design` aprobado,
     y no inicia su apply hasta que sus dependencias estén archivadas.
4. **Diagramas obligatorios**:
   - Todo apply que modifique el modelo de datos DEBE actualizar `docs/diagrams/er-model.md`
     (mermaid `erDiagram`) en el mismo commit de la migración.
   - Todo apply que agregue contenedores, módulos o integraciones externas DEBE actualizar
     `docs/diagrams/c4-architecture.md` (mermaid, niveles C1 contexto, C2 contenedores, C3 componentes).
5. **Convenciones del repo**: conventional commits, arquitectura router → service → repository,
   soft delete, multi-tenant por `organization_id`, Repository pattern, respuestas envueltas
   `{data, message, meta}`. Frontend: FSD, señales, lazy loading, componentes de `@solercia/ui` antes
   que componentes nuevos.
6. **Estado**: al terminar cada fase de cada spec, actualizar la tabla de estado al final de este
   documento y el `state.yaml` del cambio.

## Specs de la OLA 2

| ID | Cambio | Origen | Alcance | Depende de |
|----|--------|--------|---------|------------|
| 13 | `13-ui-component-audit` | Ítem 1 | Auditoría 1:1 de componentes del frontend; reemplazo de componentes manuales o de librerías externas por `@solercia/ui` ≥ 0.3.0; aportar a la librería los componentes faltantes | — |
| 14 | `14-integration-ports` | Ítem 2 (núcleo) | Puertos hexagonales de integración (lectura de correo, calendario, tareas, transcripciones, tickets), entidad Conector, sección de conectores, flujo OAuth genérico (botón → autorización → callback → tokens cifrados) | — |
| 15 | `15-adapter-microsoft365` | Ítem 2a | Adaptador Microsoft Graph solo-lectura: correo Outlook, calendario, tareas Planner, notas/transcripciones de reuniones | 14 |
| 16 | `16-adapter-google` | Ítem 2b | Adaptador Google solo-lectura: Gmail, Google Calendar, transcripciones de Meet | 14 |
| 17 | `17-adapter-glpi` | Ítem 2c | Adaptador GLPI: casos/soportes + homologación de usuarios por nombre, cédula o correo + cola de casos sin homologar | 14 |
| 18 | `18-adapter-jira` | Ítem 2d | Importador Jira: API REST con permisos y alternativa por archivo Excel/CSV | 14 |
| 19 | `19-mcp-connector` | Ítem 2e | Conector genérico vía MCP para servicios adicionales | 14 |
| 20 | `20-sso-keycloak` | Ítem 3 | Segundo método de login: SSO OIDC con Keycloak (redirección, callback, validación, emisión del JWT local); los permisos siguen gestionados por la plataforma | — |
| 21 | `21-project-hierarchy` | Ítem 4a | Proyectos dentro de proyectos: `parent_project_id`, árbol jerárquico, roll-up de avance hacia arriba (8/10 + 10/10 = 18/20), API de agregación | — |
| 22 | `22-intake-classifier` | Ítem 4b | Almacenamiento de ítems importados (correos, eventos, casos), reglas tema → respondiente, clasificación correo → tarea, proyecto por defecto "Tareas Outlook", reasignación posterior de proyecto/prioridad/usuario | 14, 21 |
| 23 | `23-org-role-templates` | Ítem 5 | Perfiles organizacionales que generan árboles de proyectos: Jefe OAP‑TI, Jefe de Planeación (MIPG, PIGA, Políticas/Planes/Proyectos, Planeación presupuestal), Jefe de Tecnología (Infraestructura, Desarrollo, Gobierno digital, Seguridad de la información), Gerente de Gestión Corporativa (Tesorería, Subdirección administrativa y financiera, Mantenimiento), Equipo de desarrollo | 21 |
| 24 | `24-hierarchy-tree-view` | Ítem 6 | Vista jerárquica visual del árbol de proyectos de arriba hacia abajo, con avance roll-up, limpia y navegable | 13, 21 |

## Grafo de dependencias

```mermaid
graph TD
    subgraph "Ola 1 — sin dependencias (paralelo)"
        C13[13-ui-component-audit]
        C14[14-integration-ports]
        C20[20-sso-keycloak]
        C21[21-project-hierarchy]
    end
    subgraph "Ola 2 — tras sus dependencias (paralelo)"
        C15[15-adapter-microsoft365]
        C16[16-adapter-google]
        C17[17-adapter-glpi]
        C18[18-adapter-jira]
        C19[19-mcp-connector]
        C23[23-org-role-templates]
        C24[24-hierarchy-tree-view]
    end
    subgraph "Ola 3"
        C22[22-intake-classifier]
    end
    C14 --> C15
    C14 --> C16
    C14 --> C17
    C14 --> C18
    C14 --> C19
    C21 --> C23
    C21 --> C24
    C13 --> C24
    C14 --> C22
    C15 --> C22
    C21 --> C22
```

## Olas de ejecución

| Ola | Specs | Regla |
|-----|-------|-------|
| 0 | Línea base de diagramas (`docs/diagrams/er-model.md`, `docs/diagrams/c4-architecture.md`) | Prerequisito documental; no requiere SDD |
| 1 | 13, 14, 20, 21 | Planeación en paralelo (4 agentes); applies serializados. 14 y 21 llevan migración: definir el orden de la cadena Alembic antes del apply |
| 2 | 15, 16, 17, 18, 19, 23, 24 | Cada spec arranca cuando su dependencia de la Ola 1 esté archivada; planeación en paralelo entre sí |
| 3 | 22 | Requiere 14 y 21 archivados; usa 15 como adaptador de referencia |

## Detalle por spec

### 13 · Auditoría de componentes UI (`13-ui-component-audit`)

Revisar uno a uno los componentes del frontend (`frontend/src/`) y verificar cuáles están hechos a
mano o con librerías externas pudiendo usar `@solercia/ui` ≥ 0.3.0. Reemplazarlos por los de la
librería. Si un componente necesario no existe en la librería, primero aportarlo allí
(repositorio de la librería) o documentarlo como pendiente de librería. Contexto: la rama
`feat/consume-solercia-ui` ya consumió 0.1.1 → 0.2.0 → 0.3.0; este spec cierra la auditoría
exhaustiva y los reemplazos restantes. Ver `docs/PLAN_MIGRACION_SOLERCIA_UI.md`.

**Terminado cuando**: inventario auditado documentado, cero componentes duplicados con equivalente
en la librería, build y pruebas del frontend en verde.

### 14 · Puertos de integración (`14-integration-ports`)

Arquitectura hexagonal (puertos y adaptadores) para consumir servicios externos SOLO LECTURA desde
la capa de negocio. Puertos mínimos: lectura de correo, calendario, tareas externas,
notas/transcripciones de reuniones y tickets/casos. Modelo de datos: conectores por organización,
cuentas conectadas por usuario, tokens cifrados. Flujo de autorización tipo botón: el usuario pulsa
"Conectar", se lanza la autorización del proveedor (OAuth/OIDC), y el callback registra la cuenta.
Sección de conectores en la API (`/api/v1/connectors`). Los puertos deben ser extensibles: Outlook y
Gmail comparten interfaces si la semántica lo permite.

**Terminado cuando**: puertos definidos e implementados con un adaptador fake de pruebas, CRUD de
conectores con permisos, migración aplicada, ER y C4 actualizados.

### 15 · Adaptador Microsoft 365 (`15-adapter-microsoft365`)

Adaptador de los puertos del 14 contra Microsoft Graph: correo Outlook, calendario, tareas de
Planner y, si el tenant lo expone, notas/transcripciones de reuniones (Teams/OneDrive). Solo
lectura. Autorización delegada con el flujo del 14.

### 16 · Adaptador Google (`16-adapter-google`)

Igual que el 15 pero contra Google: Gmail, Google Calendar y transcripciones de Meet (Drive).
Reutiliza las mismas interfaces que Outlook cuando la semántica coincida; documentar divergencias.

### 17 · Adaptador GLPI (`17-adapter-glpi`)

Extraer casos/soportes de GLPI. Homologar la persona asignada contra los usuarios de la plataforma
por nombre, número de cédula o correo (cualquiera de los tres). Los casos que no se logren homologar
quedan en una cola visible de "sin homologar" para resolución manual.

### 18 · Adaptador Jira (`18-adapter-jira`)

Importar la configuración y los issues de Jira: vía API REST cuando haya permisos, o vía el reporte
Excel/CSV exportado de Jira como alternativa. Misma filosofía de interfaces del 14.

### 19 · Conector MCP (`19-mcp-connector`)

Habilitar la opción de conectar servicios adicionales vía MCP (Model Context Protocol), como
mecanismo genérico para reemplazar eventualmente otros servicios que use la entidad.

### 20 · SSO con Keycloak (`20-sso-keycloak`)

Mantener el login actual (usuario/contraseña contra BD + JWT) y agregar un segundo método: SSO
OIDC contra Keycloak. Botón de SSO → redirección al IdP → callback → validación del token → emisión
del JWT propio de la plataforma. Los permisos y roles se siguen manejando desde esta plataforma;
Keycloak solo autentica.

**Terminado cuando**: ambos métodos conviven, usuarios SSO se aprovisionan/enlazan por correo,
pruebas de happy path + error + permisos.

### 21 · Jerarquía de proyectos (`21-project-hierarchy`)

Proyectos dentro de proyectos: un proyecto "sombrilla" (p. ej. Seguridad de la Información) contiene
subproyectos, y el avance reporta hacia arriba. La suma de actividades de los subproyectos compone
el total del padre: si Desarrollo lleva 8/10 y Seguridad 10/10, la sombrilla va 18/20. Cambio
estructural: `parent_project_id` en Project, validación de ciclos, queries de agregación
recursiva (CTE), endpoints de árbol y de avance consolidado.

**Terminado cuando**: migración aplicada, roll-up correcto en todos los niveles, ER actualizado.

### 22 · Clasificador de insumos (`22-intake-classifier`)

Los datos leídos por los conectores no solo se consultan: se ALMACENAN como ítems de entrada
(correos, eventos, casos) para clasificar, organizar y priorizar. Reglas configurables
tema → respondiente (p. ej. "todo lo de seguridad → Camilo Calderón"). Un analizador decide si un
correo se convierte en tarea; si sí, la crea en un proyecto por defecto ("Tareas Outlook") desde el
cual se puede mover a otro proyecto, cambiar prioridad y asignar usuarios. Caso de uso guía: jefe de
planeación y tecnología que recibe insumos de todos sus equipos y necesita que el sistema los
convierta en tareas asignadas al respondiente correcto.

### 23 · Plantillas organizacionales (`23-org-role-templates`)

Perfiles de alto cargo que, al asignarse, generan la estructura jerárquica de proyectos del área:

- **Jefe OAP‑TI** (planeación + tecnología): todos los equipos de ambos.
- **Jefe de Planeación**: MIPG, PIGA, Políticas/Planes/Proyectos, Planeación presupuestal.
- **Jefe de Tecnología**: Infraestructura tecnológica, Desarrollo de software, Gobierno digital, Seguridad de la información.
- **Gerente de Gestión Corporativa**: Tesorería, Subdirección administrativa y financiera, Mantenimiento.
- **Equipo de desarrollo**: un proyecto grande y debajo los sistemas de información.

La creación de proyectos iniciales es jerárquica: quedan a la cabeza de la persona con el perfil y
de ahí hacia abajo se pueden crear más proyectos.

### 24 · Vista de árbol jerárquico (`24-hierarchy-tree-view`)

Visual "muy linda" del árbol completo de arriba hacia abajo: estructura jerárquica de proyectos y
actividades, con el avance roll-up del 21, navegable y limpia. Usa componentes de `@solercia/ui`.

## Tabla de estado

| Spec | proposal | specs | design | tasks | apply | verify | archive |
|------|----------|-------|--------|-------|-------|--------|---------|
| 13-ui-component-audit | ☑ | ☑ | ☑ | ☑ | ☐ | ☐ | ☐ |
| 14-integration-ports | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 15-adapter-microsoft365 | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 16-adapter-google | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 17-adapter-glpi | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 18-adapter-jira | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 19-mcp-connector | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 20-sso-keycloak | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 21-project-hierarchy | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 22-intake-classifier | ☑ | ☑ | ☑ | ☑ | ☐ | ☐ | ☐ |
| 23-org-role-templates | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |
| 24-hierarchy-tree-view | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ | ☑ |

> Nota de revisión (2026-07-18): la revisión 4R post-apply del 21 confirmó un hallazgo CRITICAL
> (carrera en reparent + CTEs descendentes sin guarda de ciclo) corregido como seguimiento en la
> misma rama, más 2 WARNINGs de confiabilidad (orden de hermanos sin ORDER BY — corregido;
> invariante de soft-delete de padre con hijos sin implementación — deuda trazada en el spec del 21).
