# Delta for projects

## ADDED Requirements

### Requirement: PATCH de proyecto no acepta metodología; la migración es la única vía

`PATCH /projects/{id}` DEBE seguir rechazando con 422
`methodology_not_editable` cualquier solicitud que incluya el campo
`methodology`, sin cambio de comportamiento respecto al contrato actual. El
ÚNICO camino para cambiar la metodología de un proyecto existente es la
capacidad `methodology-migration` (`GET .../preview` + `POST
.../methodology-migration`); ningún otro endpoint de `projects` acepta
modificarla.

#### Scenario: PATCH sigue rechazando methodology

- DADO un proyecto existente con metodología `scrum`
- CUANDO se hace `PATCH /projects/{id}` con `{ methodology: "planner" }`
- ENTONCES la API responde 422 `methodology_not_editable` y la metodología
  del proyecto no cambia

#### Scenario: La migración es la única vía para cambiar de metodología

- DADO un proyecto existente con metodología `scrum`
- CUANDO se ejecuta `POST /projects/{id}/methodology-migration` con un mapeo
  confirmado hacia `planner`
- ENTONCES `Project.methodology` queda en `planner`, a diferencia del PATCH
  normal que sigue bloqueado

## Referencias

- `openspec/specs/projects/spec.md` (línea base)
- `openspec/changes/37-cambio-metodologia/proposal.md`
- `openspec/changes/37-cambio-metodologia/specs/methodology-migration/spec.md`
- `backend/app/modules/projects/service.py:227` (`methodology_not_editable`)
