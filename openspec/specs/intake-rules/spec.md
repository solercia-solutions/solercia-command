# intake-rules Specification

> **Origen**: cambio [22-intake-classifier](../../changes/22-intake-classifier/proposal.md)

## Propósito

Reglas configurables tema→respondiente por organización que el motor de `intake-classifier` evalúa sobre los `IntakeItem` pendientes, para decidir si un insumo se convierte en `Task` y en qué proyecto, con qué prioridad y qué asignado.

## Alcance propuesto

| Método | Ruta | Propósito | Rol requerido |
|--------|------|-----------|----------------|
| POST | /api/v1/intake/rules | Crea una regla | admin\|manager |
| GET | /api/v1/intake/rules | Lista reglas de la organización | cualquier miembro |
| GET | /api/v1/intake/rules/{id} | Detalle de una regla | cualquier miembro |
| PATCH | /api/v1/intake/rules/{id} | Edita una regla (incluye `rule_order`, `is_active`) | admin\|manager |
| DELETE | /api/v1/intake/rules/{id} | Borrado suave de una regla | admin\|manager |

Modelo (Pk+Timestamp+SoftDelete+Audit+Tenant): `IntakeRule`: `name`, `criteria JSONB` (lista de condiciones `field/operator/value`, combinadas con AND), `convert_to_task Bool`, `target_project_id FK?`, `task_priority` (`Priority`), `assignee_id FK?`, `rule_order Int`, `is_active Bool`.

## Requisitos

### Requirement: CRUD de reglas con permisos por rol

`POST`/`PATCH`/`DELETE /api/v1/intake/rules` DEBEN estar restringidos a `admin` o `manager` (`require_role`). `GET /intake/rules` y `GET /intake/rules/{id}` DEBEN ser accesibles a cualquier miembro autenticado de la organización. `DELETE` DEBE ser borrado suave y la regla eliminada DEBE excluirse de la evaluación del clasificador.

#### Scenario: Manager crea una regla

- Dado un manager autenticado
- Cuando envía `POST /intake/rules` con `name`, `criteria` y `rule_order`
- Entonces la regla se crea activa (`is_active=true`) por defecto

#### Scenario: Member no puede crear reglas

- Dado un usuario `member`
- Cuando llama `POST /intake/rules`
- Entonces la API responde `403`

### Requirement: Criterios evaluables combinados con AND

`criteria` DEBE aceptar condiciones sobre remitente/organizador (`origin_actor`), dominio del remitente, palabras clave en el título o el fragmento (`snippet`), y `source_provider`/`connector_id` de origen. Todas las condiciones de una regla DEBEN combinarse con AND: una regla solo casa si TODAS sus condiciones se cumplen.

#### Scenario: Regla por dominio de remitente

- Dado una regla con criterio `origin_actor domain contains "proveedor-x.com"`
- Cuando un `IntakeItem` con ese dominio se evalúa
- Entonces la regla casa

#### Scenario: Regla con dos condiciones — solo casa si ambas se cumplen

- Dado una regla con criterios `source_provider = microsoft365` AND `title contains "incidente"`
- Cuando un ítem cumple solo una de las dos condiciones
- Entonces la regla NO casa

### Requirement: Precedencia determinista por orden de regla

El clasificador DEBE evaluar las reglas activas de la organización en orden ascendente de `rule_order`. La PRIMERA regla activa cuyos criterios casan con el `IntakeItem` GANA; ninguna regla posterior se evalúa para ese ítem.

#### Scenario: Dos reglas casan, gana la de menor rule_order

- Dado dos reglas activas que casan con el mismo ítem, con `rule_order=1` y `rule_order=2`
- Cuando se clasifica el ítem
- Entonces se aplica la regla con `rule_order=1`; `matched_rule_id` apunta a ella

### Requirement: Reglas inactivas excluidas de la evaluación

Una regla con `is_active=false` NUNCA DEBE participar en la evaluación del clasificador, sin importar su `rule_order` o si sus criterios coincidirían.

#### Scenario: Regla inactiva no compite

- Dado una regla inactiva cuyos criterios coincidirían con un ítem
- Cuando se clasifica ese ítem
- Entonces esa regla se omite; se evalúa la siguiente regla activa por `rule_order`

### Requirement: Acción de conversión de la regla

Una regla con `convert_to_task=true` DEBE declarar `task_priority`; `target_project_id` y `assignee_id` SON opcionales. Si `target_project_id` es nulo, el ítem que casa DEBE convertirse en el proyecto por defecto de la organización (ver `intake-classifier`).

#### Scenario: Regla sin target_project_id usa el proyecto por defecto

- Dado una regla activa con `target_project_id` nulo que casa con un ítem
- Cuando se clasifica el ítem
- Entonces la `Task` creada queda en el proyecto por defecto de la organización

## Referencias

- `openspec/changes/22-intake-classifier/proposal.md`
- `openspec/changes/22-intake-classifier/specs/intake-classifier/spec.md`
