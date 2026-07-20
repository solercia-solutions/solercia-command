# Spec — Asistente de importación Jira (jira-import-wizard)

## Propósito

Asistente frontend de 3 pasos (elegir proyecto → previsualizar → importar) que trae un proyecto Jira completo a la plataforma, lanzado desde la acción `jira_import` de la tarjeta del conector (cambio 39). Consume los endpoints de `jira-import` (listar proyectos, preview, import-project) sin lógica de negocio propia; el asistente solo orquesta pasos y muestra estado.

## Ubicación

`frontend/src/pages|widgets/` (asistente) + `frontend/src/entities/jira-import/` (tipos y servicios).

## Requisitos

### Requirement: Paso 1 — Selección del proyecto Jira

El asistente DEBE listar, al abrirse, los proyectos Jira accesibles con el conector del usuario (`GET /connectors/{id}/jira/projects`), con estados de carga, lista vacía y error diferenciados. Seleccionar un proyecto avanza al paso de previsualización.

#### Scenario: Lista de proyectos disponible
- Dado un conector Jira conectado con proyectos accesibles
- Cuando el usuario abre el asistente
- Entonces ve la lista de proyectos Jira y puede seleccionar uno para continuar

#### Scenario: Conector sin conexión
- Dado un conector Jira sin cuenta conectada del usuario o con credenciales vencidas
- Cuando el usuario abre el asistente
- Entonces ve un mensaje de error claro en español colombiano formal y no puede avanzar

### Requirement: Paso 2 — Previsualización editable sin persistir

Al seleccionar un proyecto, el asistente DEBE mostrar el preview (`POST /connectors/{id}/jira/preview`): conteos por tipo (épicas/historias/subtareas/bugs), sprints detectados y el mapeo propuesto de estados/tipos/estimaciones. El nombre y el código del proyecto local a crear DEBEN prellenarse desde el proyecto Jira y ser editables antes de confirmar. Este paso NO DEBE crear ninguna fila en la base de datos.

#### Scenario: Preview muestra conteos y mapeo
- Dado un proyecto Jira con épicas, historias, subtareas y sprints
- Cuando el usuario llega al paso de previsualización
- Entonces ve los conteos por tipo, los sprints y el mapeo propuesto de estados, sin que se persista nada

#### Scenario: Nombre y código editables
- Dado el preview prellenado con el nombre/código derivados del proyecto Jira
- Cuando el usuario los edita antes de confirmar
- Entonces el paso de importación usa los valores editados

### Requirement: Paso 3 — Ejecución con resumen final

Al confirmar, el asistente DEBE ejecutar `POST /connectors/{id}/jira/import-project` y mostrar el resumen final devuelto (creados/actualizados/omitidos/errores), incluido el reporte de valores no homologados. Al reimportar el mismo proyecto Jira, el resumen DEBE reflejar la reconciliación (actualizados) sin indicar duplicados.

#### Scenario: Import inicial muestra creados
- Dado un proyecto Jira nunca importado
- Cuando el usuario confirma el paso 3
- Entonces ve el resumen con el conteo de elementos creados

#### Scenario: Reimportar el mismo proyecto muestra actualizados
- Dado un proyecto Jira ya importado previamente
- Cuando el usuario repite el asistente sobre el mismo proyecto
- Entonces el resumen muestra actualizados/omitidos, sin crear duplicados

### Requirement: Errores claros en cada paso

Ante un proyecto Jira inaccesible o una falla del conector durante cualquier paso, el asistente DEBE mostrar un mensaje de error específico en español colombiano formal (tuteo), sin tecnicismos ni excepciones crudas, y DEBE permitir reintentar o cerrar sin dejar el asistente en un estado inconsistente.

#### Scenario: Proyecto Jira inaccesible
- Dado un proyecto Jira que el conector ya no puede consultar
- Cuando el usuario lo selecciona
- Entonces ve un mensaje claro indicando que el proyecto no está disponible y puede volver a elegir otro

### Requirement: Permisos y punto de entrada

El asistente DEBE ser accesible solo desde la acción `jira_import` en estado `available` de la tarjeta del conector (rol admin/manager con cuenta Jira conectada); el proyecto local creado DEBE pertenecer a la organización activa del usuario.

#### Scenario: Acción no disponible no abre el asistente
- Dado un usuario sin rol admin/manager o sin cuenta Jira conectada
- Cuando intenta iniciar la importación
- Entonces la acción no está disponible y el asistente no se abre

## Referencias

- `openspec/changes/39-conector-capacidades/specs/connector-action-panel/spec.md` (punto de entrada)
- `openspec/changes/40-jira-import-usuario/specs/jira-import/spec.md` (contrato de los endpoints consumidos)
