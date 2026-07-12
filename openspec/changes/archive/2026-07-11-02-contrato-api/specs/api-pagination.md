# Delta for api-conventions — Paginación estándar

## MODIFIED Requirements

### Requirement: Envelope de lista con paginación estándar

Toda respuesta de un endpoint de lista DEBE usar el envelope `{"data": [...], "meta": {...}}`. El campo `meta` DEBE incluir siempre `total`. Cuando la petición incluye al menos uno de los parámetros de paginación (`page`, `size`, `sort`, `order`), la respuesta DEBE aplicar paginación offset-based sobre el resultado, y `meta` DEBE incluir además `page` y `size`. Cuando la petición NO incluye ningún parámetro de paginación, el endpoint DEBE conservar el comportamiento actual: devuelve la colección completa y `meta` contiene únicamente `total` — esto es un requisito duro de compatibilidad retro con el frontend Angular congelado, no una opción de diseño.

(Previously: el envelope de lista solo exponía `data` + `meta.total`, sin soporte de paginación.)

Aplica a los 11 endpoints de lista en scope del cambio: tasks, notifications, users, roles, menus, dependencies, projects, sprints, comments, attachments, alert-rules.

#### Scenario: Envelope de lista sin parámetros (comportamiento por defecto)

- GIVEN un cliente autenticado consumiendo un endpoint de lista
- WHEN hace `GET` sin ningún parámetro de paginación
- THEN la API responde `{"data": [...], "meta": {"total": n}}` con la colección completa
- AND el comportamiento es idéntico al existente antes de este cambio

#### Scenario: Error tipado (heredado, sin cambios)

- GIVEN una petición por un recurso inexistente
- WHEN el servicio lanza la excepción de dominio
- THEN el cliente recibe `{"detail": "...", "code": "...", "status": 404}`

#### Scenario: Lista con page y size — slice correcto

- GIVEN un endpoint de lista con 25 registros existentes
- WHEN el cliente solicita `?page=2&size=10`
- THEN la respuesta contiene los registros 11 a 20
- AND `meta` es `{"page": 2, "size": 10, "total": 25}`

## ADDED Requirements

### Requirement: Validación de límites de page y size

La API DEBE validar `page` (entero ≥ 1) y `size` (entero entre 1 y un máximo configurado por endpoint). Valores fuera de rango o no numéricos DEBEN responder `422` con el envelope de error estándar.

#### Scenario: page o size fuera de rango

- GIVEN un endpoint de lista paginable
- WHEN el cliente solicita `?page=0` o `?size` por encima del máximo permitido
- THEN la API responde `422` con `{"detail", "code", "status", "errors"}`
- AND no se ejecuta la consulta contra la base de datos

### Requirement: Whitelist de campos ordenables por endpoint

Cada endpoint de lista paginable DEBE definir una whitelist explícita de campos válidos para `sort`. Un valor de `sort` fuera de la whitelist DEBE rechazarse con `422`; `order` solo acepta `asc` o `desc`.

#### Scenario: sort con campo no permitido

- GIVEN un endpoint de lista con una whitelist de sort definida (ej. `{title, created_at, priority}`)
- WHEN el cliente solicita `?sort=password_hash` u otro campo fuera de la whitelist
- THEN la API responde `422` sin ejecutar el ordenamiento
- AND el detalle del error identifica `sort` como el campo inválido

#### Scenario: sort y order válidos

- GIVEN un endpoint de lista con `created_at` en su whitelist de sort
- WHEN el cliente solicita `?sort=created_at&order=desc`
- THEN la API responde `200` con los registros ordenados descendentemente por `created_at`
