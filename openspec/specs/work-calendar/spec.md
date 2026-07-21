# work-calendar Specification

## Purpose

Fija el calendario laboral (horas por día y días laborables) que consumen la conversión de estimaciones (cambio 34) y el avance esperado (cambio 35). Se resuelve en cascada: proyecto → equipo (su proyecto RAÍZ, `parent_project_id = null`) → empresa → default global (8h, lunes-viernes). El override de equipo vive SOLO en la raíz; los hijos heredan sin excepción. Persiste como columnas, no como tabla dedicada. Festivos, husos horarios, jornadas partidas y calendarios por persona quedan fuera de alcance.

## Alcance propuesto

| Método | Ruta | Propósito |
|---|---|---|
| GET | /api/v1/organizations/me/work-calendar | Calendario de la empresa del solicitante (cualquier miembro) |
| PUT | /api/v1/organizations/me/work-calendar | Editar calendario de empresa (admin) |
| GET | /api/v1/projects/{id}/work-calendar | Override crudo del proyecto (cualquier miembro); `null` si no es raíz o no tiene override |
| PUT | /api/v1/projects/{id}/work-calendar | Setear u ocultar (`null` = heredar) el override de equipo; solo válido si `{id}` es proyecto raíz (admin/manager) |
| GET | /api/v1/projects/{id}/work-calendar/resolved | Calendario RESUELTO de cualquier proyecto (valores + fuente) |

`working_hours_per_day`: valor numérico entre 1 y 24 (admite medias jornadas, ej. `7.5`). `working_days`: array de enteros ISO 8601 (Lun=1..Dom=7), sin duplicados, con al menos un elemento. La organización se resuelve SIEMPRE desde la membresía activa del JWT (sin variante `/{organization_id}/...`, mismo patrón que `organizations/me/theme`); toda operación queda acotada por `organization_id`.

## Requirements

### Requirement: Calendario laboral de la empresa

`Organization` DEBE persistir `working_hours_per_day` (default 8) y `working_days` (default `[1,2,3,4,5]`), ambos no nulos, agregados por migración aditiva y reversible. `GET /organizations/me/work-calendar` DEBE estar disponible para cualquier miembro autenticado; `PUT /organizations/me/work-calendar` DEBE restringirse a rol `admin`. Toda edición DEBE validar 1-24 horas y días ISO 1-7 sin duplicados ni vacíos.

#### Scenario: Cualquier miembro lee el calendario por defecto
- DADO una organización recién creada sin edición previa
- CUANDO un miembro autenticado consulta `GET /organizations/me/work-calendar`
- ENTONCES recibe `working_hours_per_day=8`, `working_days=[1,2,3,4,5]`

#### Scenario: Admin edita el calendario de empresa
- DADO un admin autenticado
- CUANDO ejecuta `PUT /organizations/me/work-calendar` con `hours=10, days=[6,7]`
- ENTONCES el calendario de empresa queda persistido con esos valores

#### Scenario: Rol no admin no puede editar
- DADO un usuario `manager`, `member` o `viewer`
- CUANDO intenta `PUT /organizations/me/work-calendar`
- ENTONCES la petición se rechaza por autorización y el calendario no cambia

#### Scenario: Validación rechaza valores fuera de rango
- DADO un admin autenticado
- CUANDO envía `hours=0`, `hours=25`, `days=[]` o `days=[1,1,2]`
- ENTONCES cada caso se rechaza con error de validación (422) y nada se persiste

### Requirement: Override de calendario del equipo (proyecto raíz)

`Project` DEBE soportar `working_hours_per_day`/`working_days` nullable. `GET /projects/{id}/work-calendar` DEBE estar disponible para cualquier miembro y devolver el override crudo (`null` cuando el proyecto no es raíz o la raíz no tiene override configurado). `PUT /projects/{id}/work-calendar` DEBE estar restringido a rol `admin` o `manager`, DEBE aceptar `null` para volver a heredar, y SOLO es válido cuando el proyecto es RAÍZ (`parent_project_id = null`); sobre un proyecto NO raíz DEBE rechazarse con un error claro y distinguible. El override, cuando existe, se valida con las mismas reglas de horas/días.

#### Scenario: Manager sobreescribe el calendario de un equipo (raíz)
- DADO un proyecto raíz "Soporte" sin override previo
- CUANDO un manager ejecuta `PUT /projects/{id}/work-calendar` con `hours=8, days=[1,2,3,4,5,6,7]`
- ENTONCES el override queda persistido en ese proyecto raíz

#### Scenario: Override en proyecto no-raíz es rechazado
- DADO un proyecto hijo (con padre)
- CUANDO se intenta `PUT /projects/{id}/work-calendar`
- ENTONCES la operación se rechaza con un código específico ("solo la raíz define override") y no persiste nada

#### Scenario: Limpiar el override vuelve a heredar
- DADO un proyecto raíz con override activo
- CUANDO un admin/manager ejecuta `PUT /projects/{id}/work-calendar` con valores `null`
- ENTONCES el override se elimina y el proyecto vuelve a heredar el calendario de empresa (o el default global)

#### Scenario: Rol member no puede sobreescribir
- DADO un usuario `member` o `viewer`
- CUANDO intenta `PUT /projects/{id}/work-calendar` sobre un proyecto raíz
- ENTONCES la petición se rechaza por autorización

#### Scenario: Validación rechaza valores fuera de rango en el override
- DADO un manager sobre un proyecto raíz
- CUANDO envía `hours=25` o `days=[1,1,2]`
- ENTONCES se rechaza con error de validación (422) y no persiste

### Requirement: Resolución en cascada y calendario resuelto

`GET /api/v1/projects/{id}/work-calendar/resolved` DEBE devolver, para CUALQUIER proyecto en cualquier profundidad, el calendario efectivo junto con su fuente (`team` | `organization` | `default`): sube por `parent_project_id` hasta la raíz; si la raíz tiene override lo usa (`team`); si no, usa el calendario de la organización (`organization`); si ninguno estuviera disponible, aplica el default global explícito 8h/L-V (`default`) sin fallar. La resolución NO DEBE cruzar `organization_id`.

#### Scenario: Nieto hereda el override del equipo raíz
- DADO "Soporte" (raíz, override fin de semana) → "Atención" → "Turno noche" (nieto, sin override propio)
- CUANDO se consulta `GET /projects/{turno_noche_id}/work-calendar/resolved`
- ENTONCES responde con el override de "Soporte" y `source=team`

#### Scenario: Raíz sin override cae al calendario de empresa
- DADO una raíz sin `working_hours_per_day`/`working_days` propios
- CUANDO se consulta el calendario resuelto de un hijo suyo
- ENTONCES responde con el calendario de la organización y `source=organization`

#### Scenario: Sin datos resolubles, aplica el default global
- DADO un escenario donde ni la raíz ni la organización tienen valores resolubles
- CUANDO se consulta el calendario resuelto
- ENTONCES responde `hours=8, days=[1,2,3,4,5]` y `source=default`, sin error

#### Scenario: Aislamiento de tenant en la resolución
- DADO un proyecto que pertenece a la organización B
- CUANDO un usuario de la organización A consulta su calendario resuelto
- ENTONCES la API responde 404, igual que el resto de endpoints de detalle de `projects`

### Requirement: No regresión y prerrequisito de 34/35

La migración que agrega estas columnas DEBE ser aditiva y reversible; ningún endpoint existente de `organizations` o `projects` DEBE cambiar de comportamiento. La suite backend DEBE permanecer en verde. El resolver DEBE exponerse como interfaz reutilizable (sin caché en este cambio) para que los cambios 34 (conversión) y 35 (avance esperado) lo consuman sin recalcular la cascada por su cuenta.

#### Scenario: Suite completa en verde tras el cambio
- DADO la suite backend existente
- CUANDO se agregan las columnas y los endpoints de este cambio
- ENTONCES toda la suite previa sigue en verde, sin romper contratos de `organizations` ni `projects`

#### Scenario: Downgrade reversible sin pérdida de datos previos
- DADO el estado posterior a la migración de este cambio
- CUANDO se ejecuta `downgrade`
- ENTONCES las columnas nuevas se eliminan y el resto del modelo permanece intacto

## Limitaciones y deuda conocida

- Sin festivos, husos horarios, jornadas partidas ni calendarios por persona (futuro documentado en el proposal).
- Sin caché en este MVP; la interfaz del resolver queda abierta a cachear por `(organization_id, root_project_id)` cuando 34/35 lo requieran en caliente.
- `design.md` (ya escrito) usa literales internos `project_root_override`/`organization_default`/`global_default` para el enum `CalendarSource`; este contrato exige el valor de wire `team`/`organization`/`default`. Tasks/apply DEBEN mapear el enum interno al valor público exigido aquí (o renombrar el enum), sin romper ninguno de los dos documentos.

## Referencias

- `openspec/changes/28-calendario-laboral/proposal.md`
- `openspec/changes/28-calendario-laboral/specs/projects/spec.md` (delta de columnas en `Project`)
- `openspec/specs/project-hierarchy/spec.md` (definición de proyecto raíz y cascada de árbol)
- `backend/app/modules/organizations/router.py` (`/organizations/me/theme`, precedente de scoping por JWT sin `{organization_id}`)
