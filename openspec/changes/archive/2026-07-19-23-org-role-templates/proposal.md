# Proposal: 23 · Plantillas organizacionales de alto cargo

## Intent

OLA 2, ítem 5. Al vincular a un jefe o gerente con su área, hoy alguien debe crear a mano el proyecto sombrilla y cada subproyecto por equipo, uno por uno, y recordar quién queda a la cabeza. Es lento, propenso a omisiones y difícil de estandarizar entre entidades. Con la jerarquía del cambio **21** ya disponible (`parent_project_id`, validación de ciclos/profundidad, roll-up), se necesita que, a partir de un **perfil organizacional** predefinido, una sola acción genere la estructura jerárquica de proyectos del área y deje a la persona seleccionada **a la cabeza**. Lo generado son proyectos normales del 21: editables, reparentables y con roll-up.

## Scope

### In Scope
- Modelo de **plantilla como datos**: `org_role_template` (cabecera) + `org_role_template_node` (árbol de nodos: nombre, metodología por defecto, orden, padre).
- **Siembra (seed)** de 5 plantillas de sistema iniciales (tabla "Modelo").
- **Instanciación**: `POST /org-role-templates/{id}/instantiate` con `{ lead_user_id }` → crea el árbol de proyectos en la organización del solicitante, con esa persona como cabeza, reutilizando `ProjectService.create_project` + `parent_project_id` del 21.
- **Idempotencia**: reinstanciar la misma plantilla para la misma persona en la misma organización NO duplica el árbol.
- Lectura: `GET /org-role-templates`, `GET /org-role-templates/{id}` (con su árbol de nodos).
- `Project` gana `lead_user_id` (la "cabeza"), poblado por la instanciación y editable después.
- **Nota obligatoria**: hay tablas nuevas → el apply DEBE actualizar el documento ER (`docs/diagrams/er-model.md`; si no existe, `docs/DATA-MODEL.md`, misma discrepancia trazada en el 21).

### Out of Scope
- CRUD de plantillas propias por organización (extensibilidad futura; el modelo ya la soporta con `organization_id` nullable + `is_system`).
- Pantalla/UI de plantillas (`frontend-frozen`).
- Mover/fusionar tareas; PATCH/DELETE de proyectos (deuda del 21).
- Plantillas o roll-up entre tenants distintos.

## Modelo (plantilla → árbol de proyectos)

| Plantilla (perfil) | Sombrilla | Equipos (subproyectos) |
|--------------------|-----------|------------------------|
| Jefe OAP‑TI | OAP‑TI | Unión de Planeación + Tecnología (8 equipos) |
| Jefe de Planeación | Planeación | MIPG · PIGA · Políticas, planes y proyectos · Planeación presupuestal |
| Jefe de Tecnología | Tecnología | Infraestructura tecnológica · Desarrollo de software · Gobierno digital · Seguridad de la información |
| Gerente de Gestión Corporativa | Gestión Corporativa | Tesorería · Subdirección administrativa y financiera · Mantenimiento |
| Equipo de desarrollo | Desarrollo | Sistemas de información (sin más subniveles predefinidos) |

Cada `org_role_template_node` mapea 1:1 a un `Project`. La instanciación recorre el árbol en orden y crea cada proyecto encadenando `parent_project_id` al proyecto del nodo padre, respetando `PROJECT_HIERARCHY_MAX_DEPTH` (21). El `lead_user_id` de los proyectos generados = la persona seleccionada (miembro activo de la organización).

## Decisión: seed (datos) vs catálogo en código

**Elegido: plantillas como datos sembrados en BD.**

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Catálogo en código (estilo Strategy) | Cero migración y determinista; pero una organización NO puede crear sus propias plantillas sin desplegar código — choca de frente con el requisito explícito de extensibilidad | Rechazada |
| **Seed en BD** (`is_system=true`, `organization_id` nullable) | 2 tablas + seeder; habilita que cada organización cree/edite plantillas a futuro sin re-arquitectura; el árbol de un perfil es naturalmente dato | **Elegida** |

Las 5 plantillas se siembran como **plantillas de sistema** (`organization_id = NULL`, `is_system = true`): visibles e instanciables por cualquier organización; la instanciación siempre escribe proyectos en la organización del solicitante.

## Idempotencia

Clave de idempotencia: `(organization_id, template_id, lead_user_id)`. Reinstanciar con la misma clave **reconcilia**: crea solo los nodos faltantes (por nombre bajo el padre esperado) y nunca duplica la sombrilla ni un equipo ya creado. El mecanismo exacto (ledger `org_role_template_instantiation` vs marcador `generated_from_template_id` en `Project`) se fija en design. Toda la instanciación ocurre en una sola transacción (todo o nada).

## Capabilities

### New Capabilities
- `org-role-templates`: plantillas de perfil, sus nodos y la instanciación idempotente a árbol de proyectos con responsable.

### Modified Capabilities
- `projects`: `Project` gana `lead_user_id` (responsable/cabeza) nullable, poblado por la instanciación y editable después.

## Permisos

- Instanciar (`POST .../instantiate`): rol `admin` o `manager` (mutación estructural del área, coherente con `PATCH /projects/{id}/parent` del 21).
- Lecturas de plantillas: cualquier miembro autenticado.
- `lead_user_id` DEBE referir a un miembro activo de la organización del solicitante; en caso contrario, rechazo de validación.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/org_role_templates/` | New | models, repository, service, router, schemas, seeder |
| `backend/app/modules/projects/models.py` | Modified | `lead_user_id` nullable FK `users` (`SET NULL`) + índice |
| `backend/app/modules/projects/{service,schemas}.py` | Modified | `create_project` acepta `lead_user_id` |
| `backend/alembic/versions/00XX_*.py` | New | Tablas de plantillas + `projects.lead_user_id` (encadena tras `0014` del 21) |
| `docs/diagrams/er-model.md` (o `docs/DATA-MODEL.md`) | Modified (apply) | Nuevas tablas y la relación de cabeza |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Reinstanciar duplica el árbol | Med | Idempotencia por `(org, template, lead)` + ledger `org_role_template_instantiations` con `UNIQUE(org, template, node, lead)` (reconciliación por nodo, inmune a renombres) |
| Instanciación parcial ante fallo a mitad | Med | Transacción única (todo o nada) |
| `lead_user_id` de otra organización | Med | Validar membresía activa antes de crear |
| Cadena Alembic (debe ir tras `0014` del 21) | Med | `down_revision` lineal; apply serializado del repo |
| Plantillas de sistema compartidas entre tenants | Low | Solo lectura; la escritura siempre en la org del solicitante |

## Rollback Plan

Cambio aditivo. Revertir el merge; el `downgrade` Alembic elimina las tablas de plantillas y la columna `projects.lead_user_id`. Los proyectos ya generados NO se borran (quedan como proyectos normales del 21, solo pierden la marca de cabeza). Ninguna tarea se altera.

## Dependencies

- `depends_on: 21-project-hierarchy` — usa `parent_project_id`, la validación de ciclos/profundidad y `create_project` con padre.
- `depends_on: 02-contrato-api` (transitiva vía 21) — envelope/paginación estándar de los endpoints nuevos.

## Success Criteria

- [ ] Las 5 plantillas de sistema quedan sembradas y son consultables por cualquier organización.
- [ ] Instanciar una plantilla genera el árbol correcto en la organización del solicitante, con la persona a la cabeza.
- [ ] Reinstanciar la misma plantilla/persona/organización no duplica proyectos (reconciliación idempotente).
- [ ] La instanciación respeta `PROJECT_HIERARCHY_MAX_DEPTH` y el aislamiento de tenant.
- [ ] Solo `admin`/`manager` pueden instanciar; `lead_user_id` inválido se rechaza.
- [ ] Todo el código nace con prueba en rojo (TDD estricto): happy path + error + permisos.
- [ ] El apply actualiza el documento ER.

## Proposal question round

Preguntas de producto para afinar el PRD antes de spec/design (asunciones tomadas entre paréntesis; el usuario puede corregir o pedir otra ronda):

1. La sombrilla **OAP‑TI**, ¿debe agrupar los 8 equipos en dos ramas intermedias (Planeación / Tecnología) o colgarlos planos bajo "OAP‑TI"? (Asumido: plano; el agrupamiento sería refinamiento de design.)
2. La "cabeza" (`lead_user_id`), ¿se propaga a TODOS los subproyectos generados o solo a la sombrilla? (Asumido: a todos, editable después.)
3. Metodología por defecto de los proyectos generados, ¿cuál? (Asumido: `planner`, configurable por nodo de plantilla.)
4. La reinstanciación, ¿debe reconciliar nodos faltantes o ser no-op total si ya existe la sombrilla? (Asumido: reconcilia — crea solo los faltantes, nunca duplica.)
5. El CRUD de plantillas propias por organización, ¿entra en este slice o se difiere? (Asumido: diferido; el modelo lo soporta, pero este slice entrega seed + instanciación.)
