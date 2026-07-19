# Arquitectura C4 — Solercia Project Manager

**Propósito**: este es el **documento vivo** de la arquitectura del sistema en tres niveles
del modelo C4 (contexto, contenedores, componentes). Refleja el código **actual** —verificado
contra `docker-compose.yml`, `backend/app/main.py` y la estructura de `backend/app/`—, no la
arquitectura aspiracional.

**Fecha de línea base**: 2026-07-18 (rama `feat/consume-solercia-ui`).

> **Regla de actualización**: todo cambio que agregue o retire contenedores, módulos del
> backend, engines, integraciones externas o canales de entrega debe actualizar este
> documento **en el mismo commit** que introduce el cambio.

---

## C1 — Contexto del sistema

Tres perfiles de personas usan el sistema. El **servidor SMTP** participa solo cuando
`EMAIL_ENABLED=true` con `EMAIL_BACKEND=smtp` (por defecto el backend de correo es
`console`, que solo registra en log). **Microsoft 365 (Graph + Entra ID)** es la primera
integración externa real sobre el motor de conectores del cambio 14 (change
15-adapter-microsoft365): solo participa cuando una organización conecta un conector
`provider=microsoft365`, y únicamente en modo lectura (correo, calendario, tareas Planner,
transcripciones de reuniones).

```mermaid
C4Context
    title C1 - Contexto: Solercia Project Manager

    Person(jefe, "Jefe / Ejecutivo", "Consulta la vista ejecutiva: quien hace que, riesgos, carga de trabajo y alertas.")
    Person(miembro, "Miembro de equipo", "Gestiona sus tareas, tableros, sprints, comentarios y registro de horas.")
    Person(admin, "Administrador", "Administra usuarios, roles RBAC, menús, dependencias y reglas de alerta.")

    System(spm, "Solercia Project Manager", "Gestión de proyectos multi-tenant con metodología configurable (planner, kanban, scrum, custom), alertas, recordatorios y activos de información.")

    System_Ext(smtp, "Servidor SMTP", "Entrega de correos (inmediatos y digest). Solo activo con EMAIL_ENABLED=true y EMAIL_BACKEND=smtp.")
    System_Ext(m365, "Microsoft 365 (Graph + Entra ID)", "Correo, calendario, tareas Planner y transcripciones de reuniones vía Graph API, solo lectura; autorización delegada OAuth vía Entra ID. Activo solo si la organización conecta un conector provider=microsoft365 (change 15).")

    Rel(jefe, spm, "Usa", "HTTPS")
    Rel(miembro, spm, "Usa", "HTTPS")
    Rel(admin, spm, "Administra", "HTTPS")
    Rel(spm, smtp, "Envía correos vía", "SMTP/TLS")
    Rel(spm, m365, "Lee correo/calendario/tareas/transcripciones vía", "HTTPS + OAuth delegado")
```

---

## C2 — Contenedores

Verificado contra `docker-compose.yml` (4 servicios) y `backend/app/main.py`. Punto clave:
**el scheduler no es un contenedor aparte** — es un `AsyncIOScheduler` (APScheduler) que
arranca dentro del proceso uvicorn del backend durante el `lifespan`, y sobre esa misma
instancia se registran los jobs de alertas, recordatorios y entregas de correo.

```mermaid
C4Container
    title C2 - Contenedores: Solercia Project Manager

    Person(usuario, "Usuario", "Jefe, miembro de equipo o administrador.")

    System_Boundary(spm, "Solercia Project Manager (docker compose)") {
        Container(frontend, "Frontend Angular", "Angular 20, @solercia/ui, puerto 4200", "SPA con Feature-Sliced Design. Consume la API REST y el WebSocket de notificaciones.")
        Container(backend, "Backend FastAPI", "Python 3.12, uvicorn, puerto 8000", "API REST /api/v1 + WebSocket /api/v1/ws/notifications. Incluye in-process el AsyncIOScheduler con los jobs de alertas (1 h), recordatorios (5 min) y entregas de correo (5/15 min).")
        ContainerDb(postgres, "PostgreSQL 16", "postgres:16-alpine, puerto 5432", "Datos multi-tenant por fila (organization_id). Esquema gestionado con Alembic (entrypoint ejecuta alembic upgrade head).")
        ContainerDb(redis, "Redis 7", "redis:7-alpine, puerto 6379", "Store del state OAuth (CSRF, single-use, TTL) del motor de integraciones (change 14). Primer uso real: antes solo era un TODO de lock en el evaluador de alertas.")
    }

    System_Ext(smtp, "Servidor SMTP", "Solo con EMAIL_ENABLED=true y EMAIL_BACKEND=smtp.")

    Rel(usuario, frontend, "Usa", "HTTPS")
    Rel(frontend, backend, "Consume", "JSON/HTTPS /api/v1 y WebSocket")
    Rel(backend, postgres, "Lee y escribe", "SQLAlchemy 2 async (asyncpg)")
    Rel(backend, redis, "Lee y escribe el state OAuth", "app/shared/redis.py, REDIS_URL")
    Rel(backend, smtp, "Envía correos", "SMTP/TLS")
```

Notas de contenedores:

- Los adjuntos se guardan en **disco local** del contenedor backend (`UPLOAD_DIR`,
  `./uploads`), no en un almacenamiento externo.
- El WebSocket es un canal *best-effort* controlado por `WS_ENABLED` (default `true`); REST
  sigue siendo autoritativo con o sin él.
- `EMAIL_ENABLED` es `false` por defecto: sin ese flag no se registran los jobs de entrega
  y no se contacta ningún SMTP.

---

## C3 — Componentes del backend

Por la cantidad de componentes, este nivel usa `flowchart` con subgrafos (más legible que
`C4Component` con ~30 nodos). Regla transversal: **router → service → repository**; el
service nunca toca SQLAlchemy directamente y las queries viven en el repository. No hay
middleware propio de auth/tenant: la autenticación y el scoping de tenant se resuelven con
**dependencias de FastAPI** (`app/dependencies.py`), no con la carpeta `middleware/` que
describe `CLAUDE.md` (no existe en el código).

```mermaid
flowchart TB
    subgraph http["Capa HTTP (routers /api/v1)"]
        direction LR
        r_negocio["Modulos de negocio:<br/>auth, projects, boards, tasks,<br/>comments, attachments, sprints,<br/>labels, checklists, task_links,<br/>time_logs, activity, dashboard, search"]
        r_admin["Modulos admin (rol ADMIN):<br/>dependencies, roles, menus, users,<br/>alerts (admin), alert_rules"]
        r_notif["Notificaciones y activos:<br/>notifications (+preferences),<br/>reminders, assets"]
        r_conn["connectors<br/>CRUD + authorize/callback OAuth<br/>+ cuentas conectadas<br/>(RBAC require_role admin|manager)"]
        r_ws["realtime.router<br/>WS /ws/notifications<br/>(si WS_ENABLED)"]
    end

    subgraph deps["app/dependencies.py (auth + tenant via Depends, sin middleware)"]
        d_auth["get_current_user /<br/>authenticate_access_token (JWT)"]
        d_tenant["get_current_membership<br/>(resuelve organization_id)"]
        d_rbac["require_role (rol de tenant)<br/>require_admin (RBAC ADMIN)<br/>get_actor_id (auditoría)"]
    end

    subgraph capas["Patrón por módulo (app/modules/*)"]
        service["service.py<br/>(reglas de negocio, valida<br/>status contra la Strategy)"]
        repo["repository.py<br/>(unico que toca SQLAlchemy)"]
        models["models.py + schemas.py<br/>(ORM + Pydantic v2)"]
    end

    subgraph metodo["app/methodology (Strategy)"]
        factory["factory.py"]
        strategies["planner / kanban /<br/>scrum / custom"]
        board_aware["board_aware.py<br/>(columnas reales del tablero<br/>como allowed_statuses)"]
    end

    subgraph engines["Engines top-level (in-process)"]
        subgraph alerts_e["app/alerts"]
            a_sched["scheduler (APScheduler, 1 h)"]
            a_eval["evaluator + registry"]
            a_strat["7 estrategias: task_overdue,<br/>task_at_risk, sprint_at_risk,<br/>workload_imbalance, blocked_task,<br/>license_expiring, license_expired"]
        end
        subgraph rem_e["app/reminders"]
            rm_sched["job cada 5 min<br/>(mismo scheduler)"]
            rm_disp["dispatcher + registry<br/>estrategia task_due_soon"]
        end
        subgraph notify_e["app/notify"]
            n_disp["dispatcher de canales<br/>(delivery_dispatch)"]
            n_model["NotificationDelivery<br/>(outbox agnostico de canal)"]
        end
        subgraph email_e["app/email"]
            e_sender["sender (smtp o console)"]
            e_digest["digest + templates + policy"]
            e_sched["jobs entrega 5 min / digest 15 min<br/>(si EMAIL_ENABLED)"]
        end
        subgraph rt_e["app/realtime"]
            rt_mgr["manager (conexiones WS)"]
            rt_pub["publisher (push best-effort)"]
        end
        subgraph integrations_e["app/integrations (change 14)"]
            i_ports["ports.py: 5 protocolos read-only<br/>+ IntegrationAdapter + AccessContext"]
            i_registry["registry.py: adaptadores por<br/>provider (import-time, sin tocar el nucleo)"]
            i_oauth["oauth.py: build_authorize /<br/>handle_callback generico"]
            i_crypto["crypto.py: Fernet<br/>(tokens cifrados en reposo)"]
            i_state["state_store.py: state OAuth<br/>en Redis (SETEX + GETDEL single-use)"]
            i_fake["adapters/fake.py: adaptador en<br/>memoria"]
            i_ms365["adapters/microsoft365/ (change 15):<br/>GraphClient httpx inyectable + OAuth<br/>Entra ID delegado + correo/calendario/<br/>Planner/notas de reunión, solo lectura"]
        end
    end

    subgraph shared["app/shared"]
        sh["base_model (mixins), enums,<br/>exceptions, pagination, security (JWT),<br/>redis (get_redis_client)"]
    end

    db[("PostgreSQL")]
    redis_ext[("Redis")]
    smtp_ext[["Servidor SMTP"]]
    graph_ext[["Microsoft 365<br/>(Graph + Entra ID)"]]

    http --> deps
    deps --> capas
    service --> repo
    repo --> models
    repo --> db
    service --> metodo
    a_eval --> a_strat
    a_sched --> a_eval
    a_eval -->|"crea Notification via service"| capas
    rm_disp -->|"crea Notification"| capas
    capas -->|"al crear Notification"| n_disp
    n_disp --> n_model
    n_disp --> e_sender
    e_sched --> n_disp
    e_sender --> smtp_ext
    capas -->|"publica eventos"| rt_pub
    rt_pub --> rt_mgr
    rt_mgr --> r_ws
    capas --> shared
    engines --> db
    r_conn --> capas
    r_conn -->|"authorize/callback"| i_oauth
    i_oauth --> i_state
    i_oauth --> i_registry
    i_registry --> i_fake
    i_registry --> i_ms365
    i_ms365 -->|"solo lectura: GET correo/calendario/<br/>Planner/transcripciones"| graph_ext
    i_ms365 -->|"OAuth Entra ID (authorize/token/refresh)"| graph_ext
    r_conn -->|"cifra/descifra tokens"| i_crypto
    i_state --> redis_ext
```

Notas de componentes:

- **Metodología (Strategy)**: la API lee el comportamiento (columnas por defecto, estados
  permitidos, sprints, modo de estimación) desde la strategy del proyecto; `board_aware`
  hace que, con tablero configurado, los `status_key` de las columnas reales sean la fuente
  de `allowed_statuses` — nunca hay `if methodology == ...` regado por el código.
- **Scheduler único**: `app/alerts/scheduler.py` crea el `AsyncIOScheduler`; los jobs de
  recordatorios y de entregas se registran sobre **esa misma instancia** en el `lifespan`.
  Cada registro tiene su `try/except` aislado: un fallo no tumba el arranque de la API.
- **Outbox de entregas**: `notification_deliveries` desacopla la creación de la notificación
  del envío por canal; `dedup_key` único evita el doble encolado y `delivery_dispatch` es el
  único despachador.
- **Módulos sin modelos**: `auth`, `dashboard` y `search` solo exponen router/service sobre
  tablas de otros módulos.
- **Seed**: `app/db_init.py` puebla datos por defecto al arrancar (después de que el
  entrypoint ejecute `alembic upgrade head`).
- **Integraciones (change 14-integration-ports)**: `app/integrations/` es un motor
  hermano de `notify`/`alerts`/`email`/`realtime` — puertos de lectura por capacidad
  (correo, calendario, tareas externas, notas, tickets), registro de adaptadores por
  `provider` en import-time (sin `if provider == ...` regado por el código) y handshake
  OAuth genérico (`authorize`/`callback`) que delega el canje de tokens al adaptador. El
  módulo `app/modules/connectors` (router→service→repository, mismo patrón que `assets`)
  expone el CRUD y el flujo OAuth vía REST, con RBAC `require_role(admin, manager)` para
  configurar conectores. Es el **primer consumidor real** de `require_role`
  (`app/dependencies.py`, ya existía sin uso) y del cliente Redis (`app/shared/redis.py`,
  nuevo — el state OAuth es el primer dato que realmente pasa por Redis).
- **Adaptador Microsoft 365 (change 15-adapter-microsoft365)**: primer adaptador REAL
  sobre el núcleo del 14, `app/integrations/adapters/microsoft365/` (7 módulos:
  `__init__`/`adapter`/`oauth`/`client`/`mappers`/`ports`/`errors`), auto-registrado en
  import-time (mismo precedente que `adapters/fake.py`, cero ediciones a `ports.py`/
  `oauth.py`/`registry.py` del 14). `GraphClient` (httpx inyectable, cero red en tests)
  centraliza paginación `@odata.nextLink`, TLS obligatorio + anti-SSRF (host fijo desde
  `M365_GRAPH_BASE_URL`), refresco 401→reintento único y backoff 429 con `Retry-After`.
  Implementa `MailReaderPort`, `CalendarReaderPort`, `ExternalTaskReaderPort` (solo
  Planner, sin Microsoft To Do) y `MeetingNotesReaderPort` (degrada a
  `capability_unavailable` sin red cuando el conector no tiene el scope
  `OnlineMeetingTranscript.Read.All`, o ante un `403` en runtime); **nunca** declara la
  capacidad `tickets`. Frontera solo-lectura estricta: ninguna llamada del paquete usa
  `POST`/`PATCH`/`PUT`/`DELETE` hacia Graph — la única escritura HTTP es el `POST` de
  `oauth.py` contra el endpoint de token de Entra ID (login.microsoftonline.com), que no
  es una escritura hacia Graph.

## Referencias

- `backend/app/main.py` — registro de routers, lifespan y schedulers.
- `backend/app/config.py` — flags (`WS_ENABLED`, `EMAIL_ENABLED`, intervalos de jobs).
- `docs/diagrams/er-model.md` — modelo entidad-relación vivo.
- `docs/ARCHITECTURE.md` — narrativa extendida de la arquitectura.
