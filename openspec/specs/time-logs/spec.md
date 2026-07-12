# time-logs Specification

## Purpose

Registro de horas trabajadas por tarea y usuario ("trabajo realizado"). Es la fuente de datos que compara lo asignado con lo efectivamente ejecutado en la vista ejecutiva. Cada colaborador registra su propio tiempo; los roles de supervisión (`admin`, `manager` en `OrganizationMember`) consultan el de cualquier persona de su organización.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/tasks/{task_id}/time-logs | Lista de entradas de una tarea (paginada) |
| POST | /api/v1/tasks/{task_id}/time-logs | Registra tiempo propio (201) |
| PATCH | /api/v1/time-logs/{id} | Edita una entrada propia |
| DELETE | /api/v1/time-logs/{id} | Borra (suave) una entrada propia |
| GET | /api/v1/users/{user_id}/time-logs | Entradas de un usuario; filtros `date_from`/`date_to` (paginada) |
| GET | /api/v1/users/{user_id}/time-logs/summary | Agregación diaria y semanal de horas |

Modelo `TaskTimeLog` (Pk + Timestamp + SoftDelete; scope de tenant vía join a Task→Project): `task_id`, `user_id`, `date` (Date), `hours` (Decimal > 0), `note?`, `created_by`/`updated_by`.

## Requirements

### Requirement: Registro propio de tiempo

Cualquier colaborador autenticado con acceso al proyecto de la tarea MUST poder crear una entrada de tiempo para sí mismo con `task_id`, `date`, `hours` (Decimal) y `note` opcional. El sistema MUST rechazar `hours <= 0` con 422.

#### Scenario: Registro válido

- GIVEN un colaborador con acceso a la tarea T
- WHEN envía `POST /tasks/{T}/time-logs` con `hours=2.5`, `date=hoy`
- THEN la entrada se crea con `user_id` = el colaborador autenticado y responde 201

#### Scenario: Horas inválidas

- GIVEN un colaborador autenticado
- WHEN envía `hours=0` o `hours=-1`
- THEN la API responde 422 y no crea la entrada

### Requirement: Edición y borrado limitados al dueño

El sistema MUST permitir editar (`PATCH`) o borrar (`DELETE`, borrado suave) una entrada de tiempo únicamente al usuario que la creó (`user_id` == usuario autenticado). Cualquier otro usuario, incluidos `admin`/`manager`, MUST recibir 403.

#### Scenario: Edición propia permitida

- GIVEN una entrada creada por el usuario U
- WHEN U envía `PATCH /time-logs/{id}` con nuevas `hours`
- THEN la entrada se actualiza y responde 200

#### Scenario: Edición ajena rechazada

- GIVEN una entrada creada por el usuario U
- WHEN otro usuario (incluido uno con rol `manager`) envía `PATCH /time-logs/{id}` o `DELETE /time-logs/{id}`
- THEN la API responde 403 y la entrada no cambia

### Requirement: Visibilidad propia vs. supervisión

Un colaborador con rol `member`/`viewer` MUST poder listar únicamente sus propias entradas; consultar `GET /users/{user_id}/time-logs` de otro usuario MUST responder 403. Un usuario con rol `admin` o `manager` MUST poder consultar las entradas de cualquier usuario de su organización.

#### Scenario: Consulta ajena por miembro regular rechazada

- GIVEN un usuario con rol `member`
- WHEN consulta `GET /users/{otro_id}/time-logs` de otro usuario
- THEN la API responde 403

#### Scenario: Consulta de supervisión permitida

- GIVEN un usuario con rol `manager`
- WHEN consulta `GET /users/{otro_id}/time-logs` de cualquier colaborador de su organización
- THEN la API responde 200 con las entradas de ese usuario

### Requirement: Listados paginados por tarea y por usuario

`GET /tasks/{id}/time-logs` y `GET /users/{id}/time-logs` MUST aceptar `?page&size&sort&order` y responder `meta {page, size, total}` (contrato de `02-contrato-api`). `GET /users/{id}/time-logs` MUST soportar filtro de rango de fechas (`date_from`, `date_to`).

#### Scenario: Filtro por rango de fechas

- GIVEN un usuario con entradas en enero y en febrero
- WHEN consulta `GET /users/{id}/time-logs?date_from=2026-02-01&date_to=2026-02-28`
- THEN solo devuelve las entradas de febrero

### Requirement: Agregación diaria y semanal

El sistema MUST exponer la suma de horas por usuario agrupada por día y por semana. Si un usuario tiene más de una entrada el mismo día (misma o distinta tarea), la agregación diaria MUST sumarlas.

#### Scenario: Suma de dos entradas del mismo día

- GIVEN el usuario U con dos entradas el mismo día: 3 horas en la tarea A y 2 horas en la tarea B
- WHEN consulta la agregación diaria de ese día
- THEN el total reportado es 5 horas

#### Scenario: Agregación semanal

- GIVEN el usuario U con entradas en distintos días de la misma semana ISO
- WHEN consulta la agregación semanal
- THEN el total de la semana es la suma de todas sus entradas dentro de esa semana

## Limitaciones y deuda conocida

- Ninguna en este momento.

## Referencias

- backend/app/modules/time_logs/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/alembic/versions/ (migración xxxx_add_time_logs_and_task_history.py)
