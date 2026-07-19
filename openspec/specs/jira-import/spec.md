# jira-import Specification

> **Origen**: cambio [18-adapter-jira](../../proposal.md)

## Propósito

Adaptador Jira **solo-lectura** con dos vías convergentes (API REST de Jira Cloud y archivo CSV/Excel exportado) que normalizan issues al vocabulario del núcleo hexagonal del cambio 14 (`integration-ports`), con homologación de valores, fallback seguro y reporte de no homologados. La conversión a `Task` de la plataforma y la persistencia de insumos son del cambio 22 — fuera de alcance aquí.

## Ubicación

`backend/app/integrations/adapters/jira/` (cliente API, parser de archivo, normalizador, homologación) · `backend/app/modules/jira_import/` (superficie REST).

## Requisitos

### Requirement: Registro del adaptador Jira en el núcleo
El adaptador Jira DEBE registrarse en import-time con `provider="jira"` siguiendo el protocolo de adaptador del cambio 14, declarando la capacidad de lectura de tickets/issues. El núcleo DEBE resolverlo por `provider` sin condicionales `if provider == ...`.

#### Scenario: El adaptador se registra sin editar el núcleo
- GIVEN el módulo del adaptador Jira importado en el arranque
- WHEN el registro de adaptadores se puebla en import-time
- THEN `get_adapter("jira")` devuelve la instancia sin editar `ports.py` ni `registry.py`

#### Scenario: El adaptador queda excluido de puertos que no soporta
- GIVEN el adaptador Jira declarando solo la capacidad de tickets/issues
- WHEN el núcleo lo busca para otro puerto (ej. correo o calendario)
- THEN el adaptador no aparece disponible para ese puerto

### Requirement: Extracción de issues por proyecto vía API REST con paginación
La vía API DEBE consultar issues de un proyecto mediante JQL, paginar hasta agotar los resultados (`nextPageToken`/`isLast`, con `startAt`/`total` como respaldo) y SHOULD soportar import incremental por fecha de actualización.

#### Scenario: Paginación completa de un proyecto
- GIVEN un proyecto Jira con más issues que el tamaño de página
- WHEN se ejecuta la extracción vía API
- THEN el adaptador recorre todas las páginas hasta `isLast=true` y entrega el total de issues del proyecto

#### Scenario: Import incremental por fecha
- GIVEN una extracción previa con marca `updated >= :desde`
- WHEN se repite la extracción con esa marca
- THEN solo se traen los issues actualizados desde esa fecha

### Requirement: Manejo de rate limit 429 en la vía API
Ante `429 Too Many Requests`, el adaptador DEBE respetar `Retry-After`, reintentar con backoff exponencial acotado, y DEBE responder un error controlado si se agotan los reintentos.

#### Scenario: Reintento tras 429
- GIVEN Jira responde `429` con `Retry-After`
- WHEN el adaptador continúa la extracción
- THEN espera el tiempo indicado, reintenta y completa si Jira responde `2xx`

#### Scenario: Reintentos agotados
- GIVEN Jira responde `429` repetidamente hasta agotar el límite de reintentos
- WHEN el adaptador no logra completar la solicitud
- THEN devuelve un error controlado sin perder los issues ya extraídos en páginas previas

### Requirement: Resolución configurable de custom fields (story points y sprint)
Los IDs de custom field de story points y sprint DEBEN resolverse por nombre vía metadatos de campos de Jira, y DEBEN admitir override de configuración cuando el nombre no coincide con el estándar.

#### Scenario: Resolución por nombre
- GIVEN una instancia donde "Story Points" mapea a `customfield_10032`
- WHEN el adaptador resuelve campos antes de extraer
- THEN identifica ese ID sin que esté hardcodeado en el código

#### Scenario: Override cuando el nombre no calza
- GIVEN una instancia con el campo de story points renombrado
- WHEN la resolución automática por nombre no encuentra coincidencia
- THEN el adaptador usa el ID configurado explícitamente para esa organización/conector

### Requirement: Import por archivo CSV/Excel con las mismas garantías que la API
La vía archivo DEBE parsear `.csv` y `.xlsx`, tolerar BOM/encoding y columnas multivalor repetidas (labels, sprint), y DEBE producir el mismo `NormalizedJiraIssue` que la vía API para el mismo issue.

#### Scenario: Parseo de CSV con BOM y columnas repetidas
- GIVEN un CSV exportado de Jira con BOM UTF-8 y varias columnas "Labels"
- WHEN se procesa el archivo
- THEN todos los labels se agregan en el issue normalizado, sin perder filas ni truncar el archivo

#### Scenario: Convergencia entre vías
- GIVEN el mismo issue disponible por API REST y en el archivo exportado
- WHEN se normaliza por ambas vías
- THEN el `NormalizedJiraIssue` resultante es equivalente en ambos casos

### Requirement: Archivo malformado se rechaza con error controlado
Si el archivo carece de columnas requeridas o su estructura no es reconocible, el sistema DEBE responder un error controlado indicando las columnas faltantes/esperadas, sin procesar parcialmente el archivo.

#### Scenario: Columna requerida ausente
- GIVEN un archivo sin la columna "Issue key"
- WHEN se intenta importar
- THEN la API responde un error controlado listando la columna faltante y no se genera ningún issue normalizado

### Requirement: Homologación de tipo/estado/prioridad con fallback y reporte
Los valores de tipo, estado y prioridad DEBEN homologarse a los enums de la plataforma; un valor sin mapeo conocido DEBE usar un fallback seguro y DEBE quedar registrado en el reporte de no homologados. Ningún issue DEBE descartarse por falta de homologación.

| Campo Jira | Fallback | Reporte |
|---|---|---|
| `issue_type` desconocido | `task_type = task` | Sí |
| `status` sin coincidencia exacta | resuelto por `statusCategory` (To Do/In Progress/Done) | Sí |
| `priority` desconocida | `priority = medium` | Sí |

#### Scenario: Valor desconocido usa fallback y se reporta
- GIVEN un issue con un tipo de Jira sin mapeo conocido
- WHEN se normaliza
- THEN el issue usa `task_type=task` como fallback y el reporte del import incluye ese valor como no homologado

#### Scenario: Estado por categoría cuando el nombre no calza
- GIVEN un estado custom de un workflow de Jira sin coincidencia exacta
- WHEN se homologa
- THEN se usa la `statusCategory` para elegir el estado de la plataforma más cercano

### Requirement: Asignado y labels se conservan crudos
`assignee` y `labels` DEBEN preservarse tal como llegan de Jira (identificador crudo) en el `NormalizedJiraIssue`; su homologación contra usuarios/labels de la plataforma NO se resuelve en este cambio.

#### Scenario: Assignee crudo en el issue normalizado
- GIVEN un issue con un asignado en Jira
- WHEN se normaliza por cualquiera de las dos vías
- THEN el `NormalizedJiraIssue` conserva el identificador crudo del asignado sin intentar resolverlo contra un usuario de la plataforma

### Requirement: Credencial inválida se rechaza sin exponer el secreto
Si la credencial `api_token` es inválida, revocada o vencida, la vía API DEBE responder un error controlado y NO DEBE exponer el token en la respuesta ni en logs.

#### Scenario: Token inválido
- GIVEN una credencial `api_token` inválida asociada al conector
- WHEN se dispara un import vía API
- THEN la API responde un error controlado sin filtrar el valor del token en la respuesta ni en logs

### Requirement: Superficie REST de import solo-lectura, con permisos y multi-tenant
El sistema DEBE exponer una operación que dispara un import (por API o por archivo cargado) para un conector Jira de la organización del usuario, y DEBE devolver los issues normalizados junto con un resumen (conteos totales, conteo de no homologados). Un usuario de otra organización NO DEBE poder disparar el import sobre un conector ajeno.

#### Scenario: Import por API devuelve issues + resumen
- GIVEN un conector Jira activo con credencial `api_token` válida
- WHEN un usuario autenticado de la organización dispara el import
- THEN la respuesta incluye los issues normalizados y un resumen con el conteo de no homologados

#### Scenario: Import por archivo devuelve el mismo contrato
- GIVEN un archivo CSV/Excel válido cargado por un usuario de la organización
- WHEN se dispara el import por archivo
- THEN la respuesta sigue el mismo contrato (issues normalizados + resumen) que la vía API

#### Scenario: Conector ajeno
- GIVEN un conector Jira de la organización A
- WHEN un usuario de la organización B intenta disparar el import sobre ese conector
- THEN la API responde error sin ejecutar ningún import

### Requirement: Frontera solo-lectura estricta
El import DEBE ser de solo lectura hacia la plataforma: NO DEBE crear `Task`, sprints, labels ni proyectos, y NO DEBE persistir los issues normalizados como ítems de entrada (esa persistencia es del cambio 22).

#### Scenario: Ningún efecto secundario en la plataforma
- GIVEN un import completado por cualquiera de las dos vías
- WHEN se revisa el estado de la base de datos tras el import
- THEN no existen nuevos `Task`, `Sprint`, `Label` ni filas de insumos persistidos originados por ese import

## Referencias

- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md` (protocolo de adaptador, registro)
- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (modelo de credenciales, cifrado)
- `openspec/changes/18-adapter-jira/specs/connectors/spec.md` (delta de este cambio: provisión de credenciales por api_token)
- `openspec/changes/17-adapter-glpi/proposal.md` (dueño del contrato `credential_kind = api_token`)
- `openspec/changes/18-adapter-jira/proposal.md`
