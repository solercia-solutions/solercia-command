# Spec — Importación Jira modo administrador (jira-import-admin)

## Propósito

Descubrimiento masivo del sitio Jira y orquestación de import por lotes, reanudable
y con progreso consultable, sobre credenciales de administrador del sitio. Reutiliza
el pipeline de persistencia e idempotencia por clave Jira del cambio 40
(`importar_proyecto`); este spec cubre solo la orquestación por lotes.

## Ubicación

`backend/app/modules/jira_import/{router,service,models}.py` ·
`backend/app/integrations/adapters/jira/client.py`
(`list_projects/list_boards/list_sprints`) ·
`frontend/src/features/.../connectors`.

## Requisitos

### Requirement: Descubrimiento masivo con conteos
El sistema DEBE listar todos los proyectos del conector Jira de la organización
activa, con conteos por entidad (épicas/historias/subtareas, sprints, tableros) y
marcando los ya importados. Los archivados de Jira NO DEBEN listarse por defecto;
DEBE existir un filtro opcional para incluirlos.

#### Scenario: Listado con estado de importación
- Dado un conector con credenciales de administrador
- Cuando el admin solicita el descubrimiento
- Entonces recibe todos los proyectos con conteos y marca de importados

#### Scenario: Archivados excluidos por defecto
- Dado proyectos activos y archivados en el sitio
- Cuando el admin descubre sin activar el filtro
- Entonces solo ve los proyectos activos

### Requirement: Selección múltiple con "seleccionar todo"
La UI DEBE permitir seleccionar uno o varios proyectos descubiertos, con una opción
"seleccionar todo" que marca todos los listados para el job.

#### Scenario: Seleccionar todo encola el sitio completo
- Dado el listado de descubrimiento con N proyectos
- Cuando el admin activa "seleccionar todo" y confirma
- Entonces el job se crea con los N proyectos

### Requirement: Creación de job por lotes
El sistema DEBE persistir el job en `import_jobs` y un detalle por proyecto en
`import_job_projects`, con estado (`pending/running/done/failed`) y contadores
por entidad importada.

#### Scenario: Job creado con detalle por proyecto
- Dado una selección válida de proyectos
- Cuando el admin crea el job
- Entonces se persiste `import_jobs` con un `import_job_projects` `pending` por
  proyecto

### Requirement: Un solo job activo por conector
El sistema NO DEBE permitir crear un job para un conector que ya tiene otro en
`pending`/`running`; DEBE responder `409` señalando el job activo.

#### Scenario: Job duplicado rechazado
- Dado un job `running` de un conector
- Cuando el admin intenta crear otro job para ese conector
- Entonces la API responde `409` sin crear uno nuevo

### Requirement: Ejecución secuencial con throttling
El runner DEBE procesar los proyectos del job uno a la vez (sin concurrencia),
invocando `importar_proyecto` del cambio 40 por proyecto, reutilizando el backoff
ante `429` del `JiraClient`.

#### Scenario: Sin solapamiento entre proyectos
- Dado un job con varios proyectos `pending`
- Cuando el runner lo ejecuta
- Entonces procesa un proyecto a la vez, respetando el backoff `429`

### Requirement: Progreso consultable por polling
El sistema DEBE exponer `GET .../import-jobs/{id}` con el estado agregado y el
detalle por proyecto; la UI DEBE consultarlo por polling, sin WebSocket.

#### Scenario: Consulta de progreso durante la ejecución
- Dado un job `running` con proyectos `done` y `pending`
- Cuando el admin consulta el progreso
- Entonces ve el estado agregado y el detalle actualizado por proyecto

### Requirement: Reanudación idempotente sin duplicar
Reintentar un job `failed` o parcial DEBE reprocesar solo los proyectos
`pending`/`failed`; los `done` NO DEBEN reprocesarse ni duplicarse, por la
idempotencia por clave Jira del cambio 40.

#### Scenario: Reanudar sin duplicar
- Dado un job con proyectos `done` y `failed` tras una interrupción
- Cuando el admin lo reintenta
- Entonces solo se reprocesa el `failed`, sin duplicar el `done`

### Requirement: Truncamiento honesto por límite de páginas
Si un proyecto excede el tope de páginas configurado, el sistema DEBE marcarlo
`truncated`, registrando lo omitido, y NO DEBE presentarlo como completo.

#### Scenario: Proyecto truncado
- Dado un proyecto con más issues que el tope de páginas
- Cuando el runner lo procesa
- Entonces queda `truncated=true` con el conteo de importado y omitido

### Requirement: Permisos de administrador y aislamiento organizacional
Solo el rol `admin` de la organización DEBE poder descubrir el sitio, crear jobs,
consultar progreso y reanudar; un job de otra organización NO DEBE ser accesible.

#### Scenario: Rol no-admin rechazado
- Dado un usuario `manager` o `member`
- Cuando intenta crear o consultar un job
- Entonces la API responde `403` sin ejecutar ninguna acción

#### Scenario: Aislamiento entre organizaciones
- Dado un job creado por la organización A
- Cuando un admin de la organización B intenta consultarlo
- Entonces la API responde error sin exponer datos del job

### Requirement: El token de Jira nunca se expone
El token del sitio NO DEBE aparecer en el repositorio, en commits, en logs ni en
ninguna respuesta de la API; DEBE registrarse por la UI de Conexiones o `.env`
local, persistido cifrado con `INTEGRATIONS_FERNET_KEY`.

#### Scenario: Token ausente de logs y respuestas
- Dado un job en ejecución con credenciales válidas
- Cuando se generan logs y respuestas de progreso
- Entonces ninguno contiene el token, solo su estado cifrado

## Referencias

- `openspec/changes/40-jira-import-usuario/design.md` (seam `importar_proyecto`,
  idempotencia por clave Jira)
- `openspec/changes/40-jira-import-usuario/specs/jira-import/spec.md` (contrato de
  persistencia reutilizado)
- `openspec/specs/connectors/spec.md` (cifrado Fernet, `settings.base_url`)
