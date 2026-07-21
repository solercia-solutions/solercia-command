# Delta for Sprints

## Alcance propuesto (delta)

| Método | Ruta | Cambio |
|---|---|---|
| POST | /projects/{id}/sprints | `name` opcional; nace `draft` sin fechas |
| GET | /projects/{id}/sprints/suggested-name | NUEVO — autonombre sugerido, no persiste |
| POST | /sprints/{id}/start | NUEVO — `draft → active`; exige fechas |
| PATCH | /sprints/{id} | Sin cambio — sigue siendo el medio de "añadir fechas" |

`status` amplía su whitelist a `draft \| active \| closed` (sin migración; default de columna sigue `active`).

## ADDED Requirements

### Requirement: Creación en borrador sin fechas

`POST /projects/{id}/sprints` DEBE aceptar `name` vacío/omitido y usar el autonombre en ese caso; el sprint nace `draft` sin fechas. Sigue exigiendo `sprints_enabled` (422 si no aplica).

#### Scenario: Con o sin nombre; metodología no habilitada rechaza
- DADO un proyecto con `sprints_enabled` (o sin)
- CUANDO se crea con nombre, sin nombre, o sobre metodología no habilitada
- ENTONCES nace `draft` con el nombre o el autonombre; o responde 422 si no admite sprints

### Requirement: Autonombre sugerido del próximo sprint

`GET .../suggested-name` sugiere (sin persistir) el nombre del siguiente sprint según el último por `created_at`; es sugerencia editable, una colisión de nombre NO bloquea (sin unicidad).

| Último sprint | Autonombre sugerido |
|---|---|
| Termina en número (`PANDORA 2026-1`) | Incrementa la última corrida (mismo separador) → `PANDORA 2026-2` |
| Sin número final (`Sprint Kickoff`) | Sufija ` 2` → `Sprint Kickoff 2` |
| Sin previo, `code` presente | `<CODE> Sprint 1` |
| Sin previo, `code` nulo | `Sprint 1` |

#### Scenario: Consecutivo con separador y año
- DADO el último sprint "PANDORA 2026-1"
- CUANDO se pide el autonombre
- ENTONCES sugiere "PANDORA 2026-2"

### Requirement: Inicio de sprint exige fechas presentes

`POST /sprints/{id}/start` transiciona `draft → active` solo con ambas fechas presentes; si falta alguna, responde 422 ("El sprint necesita fecha de inicio y fin antes de iniciarse."). Ya `active`/`closed` responde 409. La misma guarda aplica si se fija `status=active` por `PATCH` directo; `PATCH` sigue permitiendo añadir fechas sin cambiar el estado.

#### Scenario: Sin fechas no inicia; con fechas sí; sin reinicio
- DADO un sprint `draft` sin fechas (o solo una), y otro ya `active`
- CUANDO se llama `POST .../start` o `PATCH status=active` en el primero, y de nuevo en el segundo
- ENTONCES el primero responde 422 y sigue `draft`; el segundo responde 409; con ambas fechas y `POST .../start` sí pasa a `active`

### Requirement: Permisos y aislamiento de tenant

`/start` y `suggested-name` exigen autenticación y membresía, con el mismo modelo que el resto de `sprints` (cualquier rol; sin restricción nueva). Otra organización responde 404; sin token, 401.

#### Scenario: Happy path, sin auth y tenant ajeno
- DADO un `member` con su sprint `draft` con fechas, una solicitud sin token, y un sprint ajeno
- CUANDO inicia el propio, repite sin token, y consulta el ajeno
- ENTONCES el propio pasa a `active`; sin token responde 401; el ajeno responde 404

### Requirement: UI del flujo de sprint borrador

La UI ofrece "Crear sprint" liviano (solo nombre, autonombre precargado editable, sin fechas); un `draft` muestra "Borrador" y "Añadir fechas"; "Iniciar sprint" está deshabilitado hasta tener ambas fechas.

#### Scenario: Creación liviana e inicio condicionado
- DADO el modal "Crear sprint" y un `draft` sin ambas fechas
- CUANDO se confirma solo el nombre, y luego se revisa la fila
- ENTONCES se crea sin pedir fechas; "Iniciar sprint" queda deshabilitado hasta completarlas

### Requirement: No regresión sobre sprints existentes

Sprints previos (`active`/`closed`) siguen listándose, editándose, cerrándose y calculando burndown/velocity sin cambios; sin migración.

#### Scenario: Suite en verde con sprints previos intactos
- DADO sprints previos `active`/`closed`
- CUANDO se agrega `draft`, autonombre y `/start`
- ENTONCES la suite sigue en verde; sprints previos no cambian

## Referencias

- `openspec/changes/29-sprint-borrador/proposal.md` (detalle de fuera de alcance)
- `openspec/specs/sprints/spec.md` (línea base) y `backend/app/modules/sprints/*.py`
