# Delta for projects

## ADDED Requirements

### Requirement: Campo project_kind en Project

`Project` DEBE tener una columna `project_kind` (enum `area | proyecto`, no nulo, default `proyecto`) agregada mediante una migración aditiva y reversible. Todo proyecto creado por `POST /projects` sin pasar por instanciación de plantilla DEBE quedar con `project_kind = proyecto`. La instanciación de plantillas (`org-role-templates`) lo asigna según la regla del nodo (contenedor con hijos = `area`, hoja = `proyecto`).

#### Scenario: Creación directa con POST /projects es siempre proyecto
- DADO un usuario con membresía activa
- CUANDO crea un proyecto vía `POST /projects` sin pasar por una plantilla
- ENTONCES el proyecto queda creado con `project_kind = proyecto`

#### Scenario: Migración es aditiva y reversible
- DADO proyectos existentes antes de la migración
- CUANDO se ejecuta `upgrade`
- ENTONCES todos quedan con `project_kind = proyecto` sin perder datos
- Y CUANDO se ejecuta `downgrade`
- ENTONCES la columna se elimina sin afectar el resto del modelo

### Requirement: Filtro opcional project_kind en el listado

`GET /projects` DEBE aceptar un parámetro de consulta opcional `project_kind` (`area` o `proyecto`); cuando se envía, la lista DEBE incluir únicamente proyectos de ese tipo dentro de la organización del solicitante; cuando se omite, el comportamiento DEBE ser idéntico al actual (todos los tipos, sin romper clientes existentes).

#### Scenario: Filtro por area devuelve solo contenedores
- DADO una organización con proyectos `area` y `proyecto` mezclados
- CUANDO consulta `GET /projects?project_kind=area`
- ENTONCES la respuesta incluye únicamente los proyectos `area`

#### Scenario: Filtro por proyecto devuelve solo trabajo real
- DADO la misma organización
- CUANDO consulta `GET /projects?project_kind=proyecto`
- ENTONCES la respuesta incluye únicamente los proyectos `proyecto`

#### Scenario: Sin parámetro el comportamiento no cambia
- DADO la misma organización
- CUANDO consulta `GET /projects` sin `project_kind`
- ENTONCES recibe todos los proyectos de la organización, igual que antes de este cambio

#### Scenario: Valor inválido de project_kind se rechaza
- DADO un usuario autenticado
- CUANDO consulta `GET /projects?project_kind=invalido`
- ENTONCES la API responde con un error de validación (422) y no ejecuta el listado

## Referencias

- `openspec/specs/projects/spec.md` (línea base)
- `openspec/specs/org-role-templates/spec.md` y su delta en este mismo cambio (generador que asigna `project_kind`)
- `openspec/changes/27-plantillas-idempotentes/proposal.md`
