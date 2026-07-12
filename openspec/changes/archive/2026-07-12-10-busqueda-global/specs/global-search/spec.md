# global-search Specification

## Purpose

Búsqueda transversal por organización sobre **tasks**, **projects** y **comments**: una sola caja de búsqueda que resuelve título/clave/descripción de tareas, nombre/código/descripción de proyectos y cuerpo de comentarios, agrupando resultados por tipo de entidad con scope estricto de tenant.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/search | Búsqueda multi-entidad (`q`, `types`, `page`, `size`, `sort`, `order`) |

Sin modelo propio: consulta `Task` (scope vía join a `Project.organization_id`), `Project` y `TaskComment` (scope directo por `organization_id`, `TenantMixin`), excluyendo siempre registros con soft delete activo.

## Requirements

### Requirement: Contrato del endpoint de búsqueda global

`GET /api/v1/search` DEBE aceptar `q` (texto, obligatorio), `types` (opcional, lista separada por comas entre `task`, `project`, `comment`; por defecto los tres) y los parámetros de paginación estándar `page`/`size`/`sort`/`order` (02-contrato-api), con `size` por defecto 20 y máximo 100. La respuesta DEBE usar el envelope `{data, message, meta}`, con `meta` incluyendo `page`, `size`, `total`. Cada elemento de `data` DEBE incluir `entity_type` (`task`|`project`|`comment`), `id`, `snippet` (fragmento con la coincidencia) y contexto de proyecto (`project_id`, `project_name`); los resultados `comment` DEBEN incluir además `task_id` como contexto adicional.

#### Scenario: Búsqueda multi-entidad agrupada por tipo

- DADO una organización con una tarea, un proyecto y un comentario que contienen la palabra "factura"
- CUANDO un miembro consulta `GET /search?q=factura`
- ENTONCES la respuesta incluye los tres resultados, cada uno con su `entity_type` correspondiente

#### Scenario: Filtro de tipos limita el resultado

- DADO coincidencias de "factura" en tareas y en proyectos
- CUANDO se consulta `GET /search?q=factura&types=task`
- ENTONCES solo se devuelven resultados con `entity_type=task`

### Requirement: Longitud mínima de la consulta

El sistema DEBE rechazar con `422` toda consulta `q` cuya longitud, tras recortar espacios, sea menor a 2 caracteres.

#### Scenario: Consulta demasiado corta rechazada

- DADO un miembro autenticado
- CUANDO consulta `GET /search?q=a`
- ENTONCES la API responde `422` sin ejecutar la búsqueda

#### Scenario: Consulta vacía o solo espacios rechazada

- DADO un miembro autenticado
- CUANDO consulta `GET /search?q=` o `GET /search?q=%20%20`
- ENTONCES la API responde `422`

### Requirement: Validación del filtro de tipos

El sistema DEBE rechazar con `422` cualquier valor de `types` fuera del catálogo `task`, `project`, `comment`.

#### Scenario: Tipo de entidad inválido

- DADO un miembro autenticado
- CUANDO consulta `GET /search?q=factura&types=asset`
- ENTONCES la API responde `422`

### Requirement: Scope estricto por organización en cada rama de entidad

Ninguna rama de búsqueda DEBE devolver resultados de una organización distinta a la del usuario autenticado: `task` se filtra vía join a `Project.organization_id`; `project` y `comment` se filtran por su `organization_id` directo.

#### Scenario: Aislamiento en tareas entre dos organizaciones

- DADO la organización A con una tarea que contiene "factura" y la organización B sin ninguna tarea así
- CUANDO un miembro de B consulta `GET /search?q=factura&types=task`
- ENTONCES la respuesta no incluye la tarea de A

#### Scenario: Aislamiento en proyectos entre dos organizaciones

- DADO la organización A con un proyecto llamado "Facturación" y la organización B sin proyecto homónimo
- CUANDO un miembro de B consulta `GET /search?q=facturación&types=project`
- ENTONCES la respuesta no incluye el proyecto de A

#### Scenario: Aislamiento en comentarios entre dos organizaciones

- DADO la organización A con un comentario que contiene "factura" y la organización B sin comentarios así
- CUANDO un miembro de B consulta `GET /search?q=factura&types=comment`
- ENTONCES la respuesta no incluye el comentario de A

### Requirement: Exclusión de registros con borrado suave

El sistema DEBE excluir de los resultados toda tarea, proyecto o comentario con soft delete activo (`is_active=false`).

#### Scenario: Tarea borrada excluida

- DADO una tarea con "factura" en el título marcada con borrado suave
- CUANDO se consulta `GET /search?q=factura`
- ENTONCES esa tarea no aparece en los resultados

#### Scenario: Proyecto o comentario borrado excluido

- DADO un proyecto y un comentario con "factura" en su texto, ambos con borrado suave activo
- CUANDO se consulta `GET /search?q=factura`
- ENTONCES ninguno de los dos aparece en los resultados

### Requirement: Permisos de acceso a la búsqueda

Cualquier miembro autenticado de la organización, sin importar su rol (`admin`, `manager`, `member`, `viewer`), DEBE poder usar `GET /search`; no PUEDE existir restricción adicional por rol.

#### Scenario: Miembro sin rol de supervisión puede buscar

- DADO un usuario con rol `member` en su organización
- CUANDO consulta `GET /search?q=factura`
- ENTONCES la API responde `200` con los resultados de su organización
