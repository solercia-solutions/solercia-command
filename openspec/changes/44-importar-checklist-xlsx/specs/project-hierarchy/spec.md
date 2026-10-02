# Delta for project-hierarchy

> Base: `openspec/specs/project-hierarchy/spec.md`. Este delta MODIFICA el
> requisito «Avance consolidado por conteo de tareas (roll-up)» (`:111-125`
> de la línea base). El denominador deja de excluir el literal
> `Task.status != 'cancelled'` —que hoy no excluye nada, porque ninguna
> metodología de esta organización produce jamás ese estado— y pasa a
> excluir por la bandera `board_columns.excluded_from_progress` (ADDED en
> la capacidad `boards` de este mismo cambio) y por las tareas de contexto
> (`context_group IS NOT NULL`, ADDED en la capacidad `tasks` de este mismo
> cambio). Solo `Removida` y `Gestionada aparte` quedan marcadas
> `excluded_from_progress`; `Diferida` y `Recurrente` permanecen dentro del
> denominador, tal como lo comprometió `openspec/specs/data-maintenance/spec.md:142`.
> Este cambio nunca ADDED: el requisito ya está publicado, y `sdd-archive`
> DEBE fusionar este bloque completo reemplazando el requisito existente,
> no agregarlo como uno nuevo.
>
> **Nota para `sdd-archive`**: la sección «Limitaciones y deuda conocida» de
> la línea base (`openspec/specs/project-hierarchy/spec.md:195`) documenta
> que «el estado `cancelled` de `Task` aún NO está implementado… la
> exclusión de R6 es válida pero hoy no tiene efecto observable». Esa bala
> queda OBSOLETA con este delta —el denominador ya no depende de
> `cancelled` en absoluto— y DEBE eliminarse o reemplazarse al fusionar.

## MODIFIED Requirements

### Requirement: Avance consolidado por conteo de tareas (roll-up)

`GET /api/v1/projects/{id}/progress` DEBE calcular, para el proyecto solicitado y cada nodo de su subárbol, el avance por CONTEO de tareas: `done` son las tareas cuyo estado es el último estado permitido (`allowed_statuses()[-1]`) de la strategy de metodología de SU PROPIO proyecto, sobre `total` (todas las tareas del proyecto, EXCLUYENDO las tareas cuya `BoardColumn` asignada tiene `excluded_from_progress=true`, y EXCLUYENDO las tareas con `context_group IS NOT NULL`). La inclusión de tareas (incluidas subtareas, sin distinguir `parent_task_id`) sigue el mismo criterio que ya usa el cálculo de avance por proyecto existente del dashboard (`_build_projects_progress`: toda tarea cuyo `project_id` es el del nodo cuenta, salvo las dos exclusiones anteriores). El valor consolidado del proyecto raíz solicitado DEBE sumar `done` y `total` de él mismo más todos los proyectos activos de su subárbol.
(Previously: "`GET /api/v1/projects/{id}/progress` DEBE calcular, para el proyecto solicitado y cada nodo de su subárbol, el avance por CONTEO de tareas: `done` son las tareas cuyo estado es el último estado permitido (`allowed_statuses()[-1]`) de la strategy de metodología de SU PROPIO proyecto, sobre `total` (todas las tareas del proyecto, EXCLUYENDO las de estado `cancelled`). La inclusión de tareas (incluidas subtareas, sin distinguir `parent_task_id`) sigue el mismo criterio que ya usa el cálculo de avance por proyecto existente del dashboard (`_build_projects_progress`: toda tarea cuyo `project_id` es el del nodo cuenta). El valor consolidado del proyecto raíz solicitado DEBE sumar `done` y `total` de él mismo más todos los proyectos activos de su subárbol." — el denominador excluía un literal de estado que ninguna metodología de esta organización produce.)

#### Scenario: Roll-up reproduce el ejemplo de negocio

- DADO "Desarrollo" con 8 de 10 tareas done y "Seguridad" con 10 de 10 tareas done, ambos hijos de la sombrilla "Seguridad de la Información" (sin tareas propias)
- CUANDO se consulta `GET /projects/{sombrilla_id}/progress`
- ENTONCES el nodo consolidado de la sombrilla reporta `done=18`, `total=20`

#### Scenario: Tareas en columnas excluidas quedan fuera del denominador; Diferida y Recurrente permanecen dentro

- DADO un proyecto con 10 tareas totales, de las cuales 2 están asignadas a columnas `Removida` y `Gestionada aparte` (`excluded_from_progress=true`), 2 están asignadas a columnas `Diferida` y `Recurrente` (`excluded_from_progress=false`) y 5 están done
- CUANDO se consulta su avance
- ENTONCES `total=8` (10 menos las 2 de columnas excluidas; las 2 de `Diferida`/`Recurrente` permanecen en el denominador) y `done=5`

#### Scenario: Tareas de contexto excluidas del denominador

- DADO un proyecto con 6 tareas totales, de las cuales 1 tiene `context_group` no nulo
- CUANDO se consulta su avance
- ENTONCES `total=5` (la tarea de contexto queda fuera) y `done` se calcula solo entre las 5 restantes

#### Scenario: Metodologías mixtas en el subárbol

- DADO un padre scrum con un hijo kanban, cada uno con tareas propias
- CUANDO se consulta el avance consolidado del padre
- ENTONCES el `done` de cada nodo se calcula contra el último estado permitido de SU PROPIA strategy antes de sumarse al total consolidado

#### Scenario: Aislamiento de tenant en el roll-up

- DADO un subárbol con proyectos de la organización A y un proyecto sin relación de la organización B
- CUANDO un usuario de A consulta el avance consolidado de su sombrilla
- ENTONCES el resultado no incluye tareas ni proyectos de B

## Referencias

- `openspec/specs/project-hierarchy/spec.md` (línea base)
- `openspec/changes/44-importar-checklist-xlsx/specs/boards/spec.md` (bandera `excluded_from_progress`, ADDED en este mismo cambio)
- `openspec/changes/44-importar-checklist-xlsx/specs/tasks/spec.md` (columna `context_group`, ADDED en este mismo cambio)
- `openspec/specs/data-maintenance/spec.md:142` (deuda del denominador asignada a este cambio)
- `openspec/changes/44-importar-checklist-xlsx/{proposal,exploration}.md`
