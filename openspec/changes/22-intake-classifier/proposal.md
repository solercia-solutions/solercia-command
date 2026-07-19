# Proposal: 22 · Clasificador de insumos (almacenamiento + reglas tema→respondiente + correo→tarea)

## Intent

El núcleo del 14 lee insumos externos (correo, calendario, tareas, notas, tickets) pero los DEVUELVE sin persistirlos; los adaptadores 17/18 disparan import por REST y tampoco almacenan. Hoy un jefe de planeación y tecnología que recibe insumos de todos sus equipos (correos, reuniones, casos GLPI, historias de Jira) no tiene dónde se acumulen, ni forma de que el sistema los convierta en tareas asignadas al respondiente correcto dentro del árbol de proyectos del 21 (sus equipos SON proyectos). Este cambio construye ese eslabón: **almacena** los insumos, **evalúa reglas** configurables tema→respondiente y **convierte** los que corresponda en `Task` sobre el árbol del 21, con proyecto, prioridad y asignado según la regla. Es el ítem 4b de OLA 2 y el corazón del caso de uso.

## Scope

### In Scope
- **Almacenamiento de insumos (`IntakeItem`)**: persistir cada DTO leído por los puertos del 14 (`MailMessage`, `CalendarEvent`, `ExternalTask`, `MeetingNote`, `Ticket`) con vínculo al origen (conector, cuenta, proveedor, `external_id`) para trazabilidad. Tenant-scoped, soft delete, auditoría.
- **Idempotencia**: `UNIQUE(organization_id, connector_id, external_id)`; re-leer el mismo correo no duplica ítem ni tarea (dos conectores del mismo proveedor no colisionan).
- **Reglas configurables (`IntakeRule`)**: CRUD tema→respondiente por organización, con criterios evaluables (remitente, dominio, palabras clave en asunto/cuerpo, proveedor/conector de origen) y acción (convertir sí/no, `target_project_id`, prioridad, `assignee_id`).
- **Clasificador determinístico**: evalúa reglas activas (por orden, primera coincidencia) sobre ítems pendientes; si una regla convierte, crea la `Task` en el proyecto de la regla o en el proyecto por defecto, con prioridad y asignado. Interfaz `ClassifierPort` (Strategy) para habilitar un clasificador LLM futuro sin reescribir.
- **Proyecto por defecto "Tareas Outlook"**: get-or-create perezoso por organización (metodología `planner`), recordado en `IntakeSettings`.
- **Bitácora de ejecución (`IntakeRun`)**: registro de cada pull manual (conector/cuenta, ítems leídos/nuevos/duplicados/convertidos, estado, tiempos).
- **Ingesta pull manual por REST** (`POST /intake/pull`), leyendo a través de la abstracción de puertos del 14 (funciona contra el `fake` en pruebas y contra 15–19 al aterrizar, sin acoplarse a un adaptador).
- **Cola de triage + conversión manual**: ítems sin regla coincidente quedan pendientes y visibles; un usuario puede convertirlos a tarea a mano (proyecto por defecto).
- **Sink de tokens rotados**: al leer, si el token expiró se refresca (`adapter.refresh`) y se **persisten** las credenciales rotadas en `connection_credentials` (Fernet). El 22 **materializa** la persistencia: la Open Question genérica de renovación es del 14 y la expectativa específica del sink (`on_tokens_refreshed`) la declaró el 15 como contrato sin confirmar; el 14 NO lo garantiza (ver Risks).
- **Migración Alembic aditiva** con `downgrade`; **actualización obligatoria de `docs/diagrams/er-model.md` y `docs/diagrams/c4-architecture.md`** en el mismo commit.

### Out of Scope
- Clasificador LLM (interfaz lista; implementación diferida y documentada como extensión futura).
- Pull programado por scheduler (APScheduler) y en tiempo real; esta ola es pull manual disparado por REST.
- Escritura hacia el proveedor (frontera solo-lectura del 14 intacta).
- Reglas basadas en calendario/tickets más allá del contrato de criterios genérico; homologación fina de assignee externo→usuario (se toma el `assignee_id` de la regla, no del proveedor).
- Mover/reasignar/repriorizar la tarea tras crearla: es CRUD de `Task` existente (la tarea creada es una `Task` normal, editable por los endpoints vigentes). Frontend (frozen).

## Modelo de datos propuesto

| Tabla | Mixins | Campos clave | Unicidad |
|-------|--------|--------------|----------|
| `intake_items` | Pk+Timestamp+SoftDelete+Audit+Tenant | `source_provider String`, `connector_id FK`, `connected_account_id FK?`, `item_type` (email/calendar_event/external_task/meeting_note/ticket), `external_id String`, `title`, `snippet Text`, `origin_actor` (remitente/organizador/solicitante), `occurred_at`, `raw_payload JSONB`, `status` (pending/converted/ignored/error), `matched_rule_id FK?`, `created_task_id FK?`, `classified_at?` | `UNIQUE(organization_id, connector_id, external_id)` |
| `intake_rules` | Pk+Timestamp+SoftDelete+Audit+Tenant | `name`, `criteria JSONB` (lista de condiciones evaluables `field/operator/value`, AND), `convert_to_task Bool`, `target_project_id FK?`, `task_priority Priority`, `assignee_id FK?`, `rule_order Int`, `is_active Bool` | — |
| `intake_runs` | Pk+Timestamp+Audit+Tenant | `connector_id FK`, `connected_account_id FK?`, `items_fetched`, `items_new`, `items_duplicated`, `items_converted`, `status` (running/completed/error), `started_at`, `finished_at?` | — |
| `intake_settings` | Pk+Timestamp+Tenant | `default_project_id FK?`, `default_project_name` (por defecto "Tareas Outlook") | `UNIQUE(organization_id)` |

## Flujo (ingesta → clasificación → tarea)

```
POST /intake/pull (admin|manager) → abre IntakeRun
  → por cuenta conectada: si expires_at vencido → adapter.refresh → persiste credenciales rotadas (sink)
  → adapter.port_for(capability).list_*(ctx) → DTOs
  → repo.upsert IntakeItem (idempotente por org+conector+external_id) → cuenta nuevos/duplicados
  → clasificador: por cada IntakeItem pending, primera IntakeRule activa que casa (orden asc)
      · convert_to_task=true → asegura proyecto (regla.target o default get-or-create) →
        crea Task(project_id, title, description=snippet+enlace origen, priority, assignee_id) →
        item.status=converted, item.created_task_id, item.matched_rule_id
      · sin coincidencia → item.status=pending (cola de triage; conversión manual posterior)
  → cierra IntakeRun con conteos
```

## Decisiones clave (con criterio)

- **Determinístico por reglas en el MVP, LLM como extensión futura.** Argumento: (1) TDD estricto exige resultados reproducibles — un motor de reglas es determinista y testeable, un LLM no; (2) sin costo/latencia ni dependencia de un proveedor externo; (3) **gobernanza y privacidad**: no se envían cuerpos de correo a un tercero; (4) **trazabilidad auditable** — "por qué este correo se volvió tarea" = qué regla coincidió (`matched_rule_id`), no una caja negra. La interfaz `ClassifierPort` (Strategy, mismo precedente que `app/methodology/`) deja la puerta abierta a `LLMClassifier` sin tocar el resto.
- **Pull manual por REST**, coherente con 17/18 (disparan import y no persisten): 22 es quien persiste y clasifica. Scheduler = futuro.
- **Proyecto default perezoso** (get-or-create por organización, `planner`), NO sembrado en toda organización: evita ensuciar tenants que nunca usan intake; el nombre "Tareas Outlook" es configurable en `intake_settings`.
- **Ítems sin regla → cola de triage manual** (espejo de la cola "sin homologar" del 17): no auto-crear ruido; el usuario convierte a mano.
- **Desacople del adaptador**: 22 lee por los puertos del 14, así opera contra el `fake` en pruebas (TDD estricto ahora) y contra 15–19 sin cambios.

## Capabilities

### New Capabilities
- `intake-items`: almacenamiento de insumos + ingesta pull + idempotencia + bitácora `IntakeRun`.
- `intake-rules`: reglas tema→respondiente con criterios evaluables, CRUD tenant-scoped y RBAC.
- `intake-classifier`: motor determinístico ítem→`Task` (proyecto/prioridad/asignado), proyecto por defecto y cola de triage manual.

### Modified Capabilities
- `connectors`: persistencia de credenciales rotadas tras refresh-on-read (sink que cierra la Open Question de renovación del 14). Sin cambios en el CRUD ni en la frontera solo-lectura.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/intake/` | New | `IntakeItem/IntakeRule/IntakeRun/IntakeSettings`: models, router, service, repository, schemas |
| `backend/app/modules/intake/classifier.py` | New | `ClassifierPort` (Strategy) + `RuleBasedClassifier`; puerta a `LLMClassifier` futuro |
| `backend/app/modules/connectors/repository.py` | Modified | Persistir credenciales rotadas (Fernet) tras refresh en lectura |
| `backend/app/main.py`, `backend/app/db_init.py` | Modified | Incluir router + registrar modelos |
| `backend/app/config.py` | Modified | Nombre por defecto del proyecto de intake ("Tareas Outlook") |
| `backend/alembic/versions/` | New | Migración aditiva (revisión al final de la cadena vigente, posterior a 14 y 21) con `downgrade` |
| `docs/diagrams/er-model.md`, `docs/diagrams/c4-architecture.md` | Modified | **Obligatorio en el apply, mismo commit que la migración** |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Sobre-construir con LLM | Med | Reglas determinísticas en el MVP; `ClassifierPort` deja el LLM como extensión sin reescritura |
| Tareas duplicadas por re-pull | Med | `UNIQUE(org, connector_id, external_id)` + guardia `created_task_id`; re-clasificar salta ítems ya convertidos |
| Ambigüedad de reglas (varias casan) | Med | Precedencia determinista por `rule_order` + primera coincidencia, documentada |
| Proliferación de proyectos default | Low | get-or-create perezoso + `intake_settings` (uno por organización) |
| Adaptadores reales aún no existen | Low | 22 lee por los puertos del 14; validación contra `fake` (TDD estricto); 15–19 conectan sin cambios |
| PII de cuerpos de correo en BD | Med | Tenant-scoped + soft delete; cifrado de `raw_payload` fuera de alcance, documentado como deuda |
| Colisión de cadena Alembic (14 y 21 reclaman 0014) | Med | La revisión de 22 se ancla al head aplicado; apply serializado por repositorio |
| Sink `on_tokens_refreshed` NO garantizado por el 14 | Med | El `AccessContext` del 14 no define el sink (su design no lo declara; el 15 lo enunció como expectativa sin confirmar). Si al aplicar el 22 el campo no existe, el 22 DEBE extender `app/integrations/` primero (delta aditivo propio) para exponer el sink antes de cablearlo |

## Rollback Plan

Cambio aditivo. Revertir el merge y aplicar `downgrade` de la migración (elimina `intake_items`, `intake_rules`, `intake_runs`, `intake_settings` en orden inverso). Las tareas ya creadas permanecen como `Task` normales (no se borran) y siguen siendo editables; el `created_task_id` queda huérfano pero la tarea es autónoma. El sink de tokens rotados se retira quitando la llamada de persistencia en el repositorio de connectors, sin afectar el CRUD del 14.

## Dependencies

- `depends_on: 14-integration-ports` (puertos de lectura, DTOs, modelo de conectores/credenciales cifradas), `21-project-hierarchy` (árbol de proyectos donde caen las tareas creadas).
- Usa `15-adapter-microsoft365` como adaptador de referencia (no es dependencia dura: 22 opera por la abstracción de puertos y el `fake`).
- Reutiliza as-built: módulo `tasks` (creación de `Task`) y `projects` (proyecto por defecto). No son dependencias SDD.

## Success Criteria

- [ ] `IntakeItem` almacenado con vínculo al origen; re-pull idempotente (sin duplicar ítem ni tarea); tests happy path + error + permisos.
- [ ] CRUD de `IntakeRule` con criterios evaluables, tenant-scoped y RBAC (config `admin|manager`).
- [ ] El clasificador convierte ítems que casan en `Task` sobre el proyecto de la regla o el default, con prioridad y asignado correctos.
- [ ] Proyecto "Tareas Outlook" creado perezosamente una sola vez por organización (`planner`).
- [ ] Ítems sin regla quedan en cola de triage; la conversión manual crea la tarea en el proyecto por defecto.
- [ ] La tarea creada es una `Task` normal, movible/reasignable/repriorizable por los endpoints vigentes.
- [ ] `IntakeRun` registra conteos; la ingesta funciona contra el adaptador `fake` (TDD estricto).
- [ ] Credenciales rotadas persistidas tras refresh-on-read.
- [ ] Migración aditiva con `downgrade` probado; ER + C4 actualizados en el mismo commit; suite completa verde.

## Proposal question round (decisiones a ratificar antes de spec)

Al ser un ejecutor delegado no puedo preguntar en vivo; dejo las incógnitas de producto que conviene ratificar (asumo el default indicado si no hay corrección):

1. **Ítems sin regla coincidente**: ¿cola de triage manual (asumido) o regla catch-all opcional que convierta con defaults? Asumo triage manual, espejo del 17.
2. **RBAC del pull** (`POST /intake/pull`): ¿`admin|manager` (asumido, consume conectores) o cualquier miembro?
3. **Nombre del proyecto default**: ¿configurable por organización en `intake_settings` (asumido) o constante "Tareas Outlook"?
4. **Alcance de tipos convertibles en el MVP**: ¿todos los `item_type` o priorizar correo (`mail`) primero? Asumo el contrato genérico para todos, con correo como caso guía probado.
5. **Sink de tokens rotados**: ¿lo asume 22 (asumido, cierra la Open Question del 14) o se espera que 15 lo aterrice primero y 22 solo lo consuma?
