# intake-items Specification

> **Origen**: cambio [22-intake-classifier](../../proposal.md)

## Propósito

Almacenamiento persistente de los insumos leídos por los puertos de solo lectura del cambio 14 (correo, calendario, tareas externas, notas de reunión, tickets), con vínculo trazable al origen, idempotencia ante re-lecturas y bitácora de cada ejecución de ingesta (`IntakeRun`). Es la capa de almacenamiento que consume `intake-classifier` para evaluar reglas.

## Alcance propuesto

| Método | Ruta | Propósito | Rol requerido |
|--------|------|-----------|----------------|
| POST | /api/v1/intake/pull | Dispara ingesta manual on-demand contra las cuentas conectadas de la organización | admin\|manager |
| GET | /api/v1/intake/items | Lista insumos almacenados, con filtros | cualquier miembro |
| GET | /api/v1/intake/items/{id} | Detalle de un insumo | cualquier miembro |
| GET | /api/v1/intake/runs | Bitácora de ejecuciones de ingesta | cualquier miembro |

Modelos (Pk+Timestamp+SoftDelete+Audit+Tenant salvo donde se indique):

- `IntakeItem`: `source_provider`, `connector_id FK`, `connected_account_id FK?`, `item_type` (`email|calendar_event|external_task|meeting_note|ticket`), `external_id`, `title`, `snippet`, `origin_actor`, `occurred_at`, `raw_payload JSONB`, `status` (`pending|converted|ignored|error`), `matched_rule_id FK?`, `created_task_id FK?`, `classified_at?`.
- `IntakeRun` (Pk+Timestamp+Audit+Tenant, sin soft delete): `connector_id FK`, `connected_account_id FK?`, `items_fetched`, `items_new`, `items_duplicated`, `items_converted`, `status` (`running|completed|error`), `started_at`, `finished_at?`.

## Requisitos

### Requirement: Almacenamiento de insumos con vínculo al origen

El sistema DEBE persistir cada insumo leído a través de los puertos del 14 como un `IntakeItem`, con `item_type` perteneciente a la taxonomía `email|calendar_event|external_task|meeting_note|ticket` (mapeo 1:1 con las 5 capacidades de puerto del 14; los proveedores de tipo issue-tracker como Jira o GLPI entran como `ticket`), y vínculo trazable a `connector_id`, `connected_account_id` (nulo permitido para conectores sin cuenta individual, ej. GLPI a nivel de servicio), `source_provider`, `external_id`, `origin_actor` y `occurred_at`. El `raw_payload` original DEBE conservarse en JSONB para trazabilidad y reclasificación futura.

#### Scenario: Ingesta pull almacena un correo nuevo

- Dado un `MailMessage` devuelto por el puerto de correo del 14 para una cuenta conectada
- Cuando `POST /intake/pull` procesa esa cuenta
- Entonces se crea un `IntakeItem` con `item_type=email`, `status=pending`, `raw_payload` con el contenido original

#### Scenario: Insumo de conector sin cuenta individual

- Dado un conector de tickets (ej. GLPI) sin `connected_account_id` asociado
- Cuando se ingesta un ticket vía ese conector
- Entonces el `IntakeItem` se crea con `connected_account_id` nulo, sin error

### Requirement: Idempotencia por organización, conector e identificador externo

La unicidad de `IntakeItem` DEBE evaluarse por (`organization_id`, `connector_id`, `external_id`). Re-ejecutar la ingesta sobre un insumo ya almacenado NO DEBE crear un segundo `IntakeItem` ni una segunda `Task`, incluso si el insumo ya fue convertido.

#### Scenario: Re-pull del mismo correo no duplica el ítem

- Dado un `IntakeItem` ya almacenado con un `external_id` dado
- Cuando se repite `POST /intake/pull` y el puerto devuelve el mismo insumo
- Entonces no se crea una fila nueva; el conteo `items_duplicated` del `IntakeRun` aumenta

#### Scenario: Re-pull de un ítem ya convertido no crea una segunda tarea

- Dado un `IntakeItem` con `status=converted` y `created_task_id` asignado
- Cuando se repite la ingesta y el mismo insumo vuelve a leerse
- Entonces no se crea una `Task` adicional ni se reclasifica el ítem

### Requirement: Ingesta manual on-demand con bitácora de ejecución

`POST /api/v1/intake/pull` DEBE estar restringido a roles `admin` o `manager`. Cada ejecución DEBE abrir un `IntakeRun` por conector/cuenta procesada, registrar `items_fetched`, `items_new`, `items_duplicated`, `items_converted`, y cerrarlo con `status=completed` o `status=error`. Un error en una cuenta NO DEBE impedir que se registren los ítems ya almacenados de otras cuentas procesadas en la misma ejecución.

#### Scenario: Admin dispara un pull exitoso

- Dado un admin autenticado con cuentas conectadas activas
- Cuando llama `POST /intake/pull`
- Entonces se crea un `IntakeRun` por cuenta con `status=completed` y los conteos correctos

#### Scenario: Member no puede disparar el pull

- Dado un usuario con rol `member`
- Cuando llama `POST /intake/pull`
- Entonces la API responde `403` y no se abre ningún `IntakeRun`

#### Scenario: Error en una cuenta no bloquea las demás

- Dado dos cuentas conectadas, una con token irrecuperable
- Cuando se ejecuta `POST /intake/pull`
- Entonces la cuenta fallida cierra su `IntakeRun` con `status=error`, y la cuenta sana cierra el suyo con `status=completed` e ítems almacenados

### Requirement: Consulta y filtrado de insumos

`GET /api/v1/intake/items` DEBE soportar filtros por `status`, `item_type` y `connector_id`, incluida la vista de triage (`status=pending`) usada por `intake-classifier` para la reclasificación manual. `GET /api/v1/intake/runs` DEBE listar las ejecuciones con sus conteos.

#### Scenario: Filtrar la cola de triage

- Dado insumos con distintos `status`
- Cuando se consulta `GET /intake/items?status=pending`
- Entonces la respuesta solo incluye los ítems sin regla coincidente aún no convertidos

### Requirement: Aislamiento multi-tenant

Ningún `IntakeItem` ni `IntakeRun` DEBE ser visible ni editable por un usuario de otra organización, sin importar su rol.

#### Scenario: Insumo de otra organización no es visible

- Dado un `IntakeItem` de la organización A
- Cuando un usuario de la organización B llama `GET /intake/items/{id}`
- Entonces la API responde `404`

## Referencias

- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md`
- `openspec/changes/22-intake-classifier/proposal.md`
