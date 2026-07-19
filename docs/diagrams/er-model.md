# Modelo entidad-relación — Solercia Project Manager

**Propósito**: este es el **documento vivo** del esquema de base de datos. Refleja, tabla por
tabla, los modelos SQLAlchemy reales de `backend/app/modules/*/models.py`,
`backend/app/notify/models.py` y los mixins de `backend/app/shared/base_model.py`. La fuente
de verdad es el **código**; este documento es su espejo navegable.

**Fecha de línea base**: 2026-07-18 (estado del código en la rama `feat/consume-solercia-ui`,
migraciones Alembic hasta `0015_add_connectors`).

> **Regla de actualización**: todo cambio de base de datos (modelo nuevo, columna nueva,
> enum nuevo, FK nueva o eliminada) debe actualizar este documento **en el mismo commit de la
> migración Alembic** que lo introduce. Un diagrama desactualizado es peor que ninguno.

> Nota: la imagen `docs/diagrams/erd.png` es una captura histórica anterior a esta línea base.
> Se conserva como referencia, pero **este archivo es la fuente viva** del diagrama.

**Total de tablas**: 34.

---

## Convenciones y mixins

Los modelos componen mixins de `app/shared/base_model.py`. Para no repetir columnas triviales
en cada bloque del diagrama, se omiten y se documentan aquí una sola vez:

| Mixin | Columnas que aporta | Notas |
|-------|---------------------|-------|
| `PkMixin` | `id uuid PK` | UUID generado en la aplicación. Todas las tablas lo usan. |
| `TimestampMixin` | `created_at`, `updated_at` (timestamptz) | Todas las tablas **excepto** `task_history` (append-only, define su propio `created_at`). |
| `SoftDeleteMixin` | `is_active bool`, `deleted_at timestamptz?` | Borrado lógico. No lo llevan las tablas pivote de borrado físico (`user_roles`, `role_menus`, `task_labels`, `asset_tasks`, `organization_members`) ni `notifications`, `notification_preferences`, `notification_deliveries`, `task_history`. |
| `TenantMixin` | `organization_id uuid FK → organizations` | Aislamiento multi-tenant por fila (`ondelete=CASCADE`). |
| `AuditMixin` | `created_by uuid? FK → users`, `updated_by uuid? FK → users` | `ondelete=SET NULL`; lo estampa el service desde el actor autenticado. Estas dos FK hacia `users` **no se dibujan** como aristas para no saturar el diagrama. |

Otras convenciones del esquema:

- Los enums se persisten como `VARCHAR` con `CHECK` (`native_enum=False`); en los diagramas
  se anotan como `enum` con sus valores.
- La columna lógica `order` se mapea a nombres físicos no reservados: `tasks.task_order`,
  `board_columns.column_order`, `task_checklists.checklist_order`, `checklist_items.item_order`,
  `menus.menu_order`.
- `tasks.status` es texto libre validado contra la metodología del proyecto (columnas del
  tablero), **no** un enum global.
- Las relaciones punteadas (`..`) indican vínculos lógicos sin FK física (validados en el
  service), como los destinos polimórficos de `attachments`.

---

## Vista general por dominios

Relaciones entre dominios (cada caja se detalla en su propia sección):

```mermaid
flowchart LR
    subgraph AUTH["Auth / organizaciones / RBAC (8 tablas)"]
        organizations
        users
    end

    subgraph CORE["Núcleo proyectos / tareas (14 tablas)"]
        projects
        tasks
    end

    subgraph ALERTS["Alertas / notificaciones / recordatorios (6 tablas)"]
        alert_rules
        notifications
        reminders
    end

    subgraph ASSETS["Activos de información (3 tablas)"]
        assets
    end

    subgraph INTEGRATIONS["Conectores e integraciones (3 tablas)"]
        connectors
    end

    organizations -->|"organization_id en toda tabla tenant-scoped"| CORE
    organizations --> ALERTS
    organizations --> ASSETS
    organizations --> INTEGRATIONS
    users -->|"assignee, author, actor, auditoría"| CORE
    users -->|"recipient, owner"| ALERTS
    users -->|"responsible_id"| ASSETS
    users -->|"connected_accounts.user_id"| INTEGRATIONS
    tasks -->|"reminders.task_id"| ALERTS
    tasks -->|"asset_tasks"| ASSETS
```

---

## Dominio 1 — Auth, organizaciones y RBAC

`organizations` es el tenant. `organization_members` da el **rol de tenant**
(`admin|manager|member|viewer`) que gobierna `require_role`. Aparte, `roles` + `user_roles` +
`role_menus` + `menus` forman el RBAC de navegación (el rol `ADMIN` habilita los endpoints
`/admin/*`). `dependencies` son áreas organizacionales (concepto distinto de
`task_dependencies` del dominio 2).

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERS : "agrupa miembros"
    USERS         ||--o{ ORGANIZATION_MEMBERS : "pertenece via"
    ORGANIZATIONS ||--o{ DEPENDENCIES : "define"
    DEPENDENCIES  |o--o{ USERS : "agrupa"
    ORGANIZATIONS ||--o{ ROLES : "define"
    USERS         ||--o{ USER_ROLES : "tiene"
    ROLES         ||--o{ USER_ROLES : "se asigna en"
    ROLES         ||--o{ ROLE_MENUS : "concede"
    MENUS         ||--o{ ROLE_MENUS : "se incluye en"
    MENUS         |o--o{ MENUS : "es hijo de"

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
    }

    USERS {
        uuid id PK
        string email UK
        string primer_nombre
        string segundo_nombre "nullable"
        string primer_apellido
        string segundo_apellido "nullable"
        uuid dependency_id FK "nullable, SET NULL"
        string hashed_password "nunca se expone"
    }

    ORGANIZATION_MEMBERS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        enum role "admin, manager, member, viewer"
    }

    DEPENDENCIES {
        uuid id PK
        uuid organization_id FK
        string name
        string code "nullable, no unico"
    }

    ROLES {
        uuid id PK
        uuid organization_id FK
        string code "unico por organizacion"
        string name
    }

    USER_ROLES {
        uuid id PK
        uuid user_id FK
        uuid role_id FK "unique(user_id, role_id)"
    }

    MENUS {
        uuid id PK
        string name
        string icon "nullable"
        string path "nullable"
        uuid parent_id FK "nullable, autoreferencia"
        int menu_order
    }

    ROLE_MENUS {
        uuid id PK
        uuid role_id FK
        uuid menu_id FK "unique(role_id, menu_id)"
    }
```

Notas del dominio:

- `users.full_name` **no es columna**: es una `hybrid_property` (`primer_nombre` +
  `primer_apellido`).
- `menus` es **global** (sin `organization_id`); lo que varía por organización es qué roles
  conceden cada menú.
- `roles` lleva `unique(organization_id, code)`.

---

## Dominio 2 — Núcleo de proyectos y tareas

`projects` se configura con una `methodology` (patrón Strategy). Cada proyecto tiene a lo sumo
**un** tablero (`boards.project_id` es `unique`) cuyas `board_columns` definen el `status`
que adopta la tarea al entrar en la columna (`status_key`). `tasks.status` sigue siendo el
campo validado; `board_column_id` es la fuente en runtime cuando hay tablero configurado.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ PROJECTS : "posee"
    PROJECTS      |o--o{ PROJECTS : "es hijo de"
    PROJECTS      ||--o| BOARDS : "tiene tablero"
    BOARDS        ||--o{ BOARD_COLUMNS : "ordena"
    PROJECTS      ||--o{ SPRINTS : "contiene"
    PROJECTS      ||--o{ TASKS : "contiene"
    SPRINTS       |o--o{ TASKS : "agrupa"
    BOARD_COLUMNS |o--o{ TASKS : "ubica"
    TASKS         |o--o{ TASKS : "es subtarea de"
    USERS         |o--o{ TASKS : "es responsable de"
    PROJECTS      ||--o{ LABELS : "define"
    TASKS         ||--o{ TASK_LABELS : "se etiqueta en"
    LABELS        ||--o{ TASK_LABELS : "clasifica via"
    TASKS         ||--o{ TASK_COMMENTS : "recibe"
    USERS         ||--o{ TASK_COMMENTS : "escribe"
    TASKS         ||--o{ TASK_CHECKLISTS : "desglosa en"
    TASK_CHECKLISTS ||--o{ CHECKLIST_ITEMS : "contiene"
    TASKS         ||--o{ TASK_DEPENDENCIES : "bloquea via"
    TASKS         ||--o{ TASK_TIME_LOGS : "registra horas en"
    USERS         ||--o{ TASK_TIME_LOGS : "reporta"
    TASKS         ||--o{ TASK_HISTORY : "audita en"
    USERS         |o--o{ TASK_HISTORY : "actua en"
    TASKS         ||..o{ ATTACHMENTS : "adjunta (sin FK)"
    TASK_COMMENTS ||..o{ ATTACHMENTS : "adjunta (sin FK)"

    PROJECTS {
        uuid id PK
        uuid organization_id FK
        string name
        text description "nullable"
        enum methodology "planner, kanban, scrum, custom"
        enum status "active, archived"
        string code "nullable, unique(organization_id, code)"
        int task_counter "asigna task_number atomicamente"
        uuid parent_project_id FK "nullable, autoreferencia, SET NULL"
    }

    BOARDS {
        uuid id PK
        uuid project_id FK "UK - un tablero por proyecto"
    }

    BOARD_COLUMNS {
        uuid id PK
        uuid board_id FK
        string name "renombrable"
        string status_key "inmutable, unique(board_id, status_key)"
        int column_order
        int wip_limit "nullable = sin limite WIP"
    }

    SPRINTS {
        uuid id PK
        uuid project_id FK
        string name
        text goal "nullable"
        timestamptz start_date "nullable"
        timestamptz end_date "nullable"
        string status "active, closed - validado en service"
        int completed_points "puntos Done al cerrar"
        timestamptz closed_at "nullable"
    }

    TASKS {
        uuid id PK
        uuid project_id FK
        uuid sprint_id FK "nullable = backlog, SET NULL"
        uuid parent_task_id FK "nullable, autoreferencia"
        uuid board_column_id FK "nullable, SET NULL"
        uuid assignee_id FK "nullable, SET NULL"
        string title
        text description "nullable"
        string task_type "task, bug, story, epic"
        string status "columna del tablero, no enum global"
        enum priority "low, medium, high, critical"
        int estimation_points "nullable"
        numeric estimation_hours "nullable"
        timestamptz due_date "nullable"
        timestamptz start_date "nullable"
        timestamptz completed_at "nullable, marca entrada a done"
        int task_order
        bool risk_flag
        text risk_reason "nullable"
        int task_number "nullable, secuencial por proyecto"
    }

    LABELS {
        uuid id PK
        uuid organization_id FK
        uuid project_id FK "unique(project_id, name)"
        string name
        string color
    }

    TASK_LABELS {
        uuid id PK
        uuid task_id FK
        uuid label_id FK "unique(task_id, label_id)"
    }

    TASK_COMMENTS {
        uuid id PK
        uuid organization_id FK
        uuid task_id FK
        uuid author_id FK "SET NULL"
        text body
        json mentioned_user_ids "menciones para notificar"
    }

    TASK_CHECKLISTS {
        uuid id PK
        uuid organization_id FK
        uuid task_id FK
        string title
        int checklist_order
    }

    CHECKLIST_ITEMS {
        uuid id PK
        uuid organization_id FK
        uuid checklist_id FK
        string text
        bool is_done
        int item_order
    }

    TASK_DEPENDENCIES {
        uuid id PK
        uuid organization_id FK
        uuid blocker_task_id FK "unique(blocker, blocked)"
        uuid blocked_task_id FK
    }

    ATTACHMENTS {
        uuid id PK
        uuid organization_id FK
        string target_type "task o comment - discriminador"
        uuid target_id "sin FK, integridad en service"
        string original_name
        string stored_name UK "nombre UUID en disco"
        string content_type
        int size_bytes
        uuid uploaded_by FK "SET NULL"
    }

    TASK_TIME_LOGS {
        uuid id PK
        uuid organization_id FK
        uuid task_id FK
        uuid user_id FK "SET NULL"
        date work_date
        numeric hours
        text note "nullable"
    }

    TASK_HISTORY {
        uuid id PK
        uuid organization_id FK
        uuid task_id FK
        uuid actor_id FK "nullable = accion del sistema"
        string actor_type
        string field
        text old_value "nullable"
        text new_value "nullable"
        timestamptz created_at "append-only, sin updated_at"
    }
```

Notas del dominio:

- `projects.parent_project_id` (change 21-project-hierarchy, migración `0014`) modela una
  jerarquía padre-hijo entre proyectos de la MISMA organización, mismo patrón de
  autoreferencia que `tasks.parent_task_id` (`SET NULL`, indexada). Cada subproyecto conserva
  su propia `methodology` (Strategy intacto); la jerarquía es puramente estructural. Validación
  de ciclos/profundidad máxima (`PROJECT_HIERARCHY_MAX_DEPTH`, por defecto 5) vive en el
  service, no en la base de datos.
- `task_dependencies` modela la arista dirigida canónica «`blocker` bloquea a `blocked`»;
  la vista inversa `is_blocked_by` se calcula, nunca es una segunda fila. Desvincular hace
  `is_active=false`, **nunca** DELETE físico (el DFS anti-ciclos filtra por `is_active`).
- `attachments` es polimórfica (`target_type` + `target_id`), por eso las aristas punteadas.
- `task_history` es append-only: sin `TimestampMixin`, sin soft delete; la fila **es** el
  registro de auditoría.
- `tasks.task_number` + `projects.code` forman la llave visible `task_key` (p. ej. `SDM-7`),
  asignada atómicamente vía `UPDATE ... RETURNING` sobre `projects.task_counter`.

---

## Dominio 3 — Alertas, notificaciones y recordatorios

`alert_rules` configura el motor de alertas por organización; el evaluador genera
`notifications` (in-app) con `dedup_key` anti-duplicados. `notification_preferences` guarda
la cadencia de digest de correo por usuario. `notification_deliveries` es el **outbox**
agnóstico de canal (hoy solo canal `email`). `reminders`/`reminder_rules` son recursos
estrictamente personales (ni un admin ve los de otra persona).

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ALERT_RULES : "configura"
    ORGANIZATIONS ||--o{ NOTIFICATIONS : "genera"
    USERS         ||--o{ NOTIFICATIONS : "recibe"
    USERS         ||--o{ NOTIFICATION_PREFERENCES : "configura digest"
    NOTIFICATIONS |o--o{ NOTIFICATION_DELIVERIES : "se entrega via"
    USERS         ||--o{ REMINDERS : "posee"
    TASKS         |o--o{ REMINDERS : "referencia"
    USERS         ||--o{ REMINDER_RULES : "configura"

    ALERT_RULES {
        uuid id PK
        uuid organization_id FK
        string rule_type "task_overdue, license_expiring, etc"
        bool enabled
        json threshold_params "ej days_before, max_active_tasks"
    }

    NOTIFICATIONS {
        uuid id PK
        uuid organization_id FK
        uuid recipient_user_id FK
        string rule_type
        string title
        text body
        string target_type "nullable"
        uuid target_id "nullable, sin FK"
        string dedup_key "anti-duplicados"
        enum status "active, read, resolved, silenced"
        timestamptz emailed_at "nullable, ya enviada por correo"
    }

    NOTIFICATION_PREFERENCES {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK "unique(organization_id, user_id)"
        enum digest_frequency "none, daily, weekly"
        int digest_hour
        int digest_weekday "nullable"
        timestamptz last_digest_at "nullable"
    }

    NOTIFICATION_DELIVERIES {
        uuid id PK
        uuid organization_id FK
        uuid notification_id FK "nullable, SET NULL"
        string channel "default email"
        string dedup_key UK "anti doble-encolado"
        enum status "pending, sending, sent, failed"
        int attempts
        text last_error "nullable"
        jsonb payload "datos del canal (destinatario, asunto...)"
        timestamptz sent_at "nullable"
    }

    REMINDERS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK "propietario, SET NULL"
        uuid task_id FK "nullable, SET NULL"
        timestamptz remind_at
        text message
        enum status "scheduled, fired, skipped, cancelled"
        timestamptz fired_at "nullable"
    }

    REMINDER_RULES {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK "propietario, SET NULL"
        string rule_type "ej task_due_soon"
        bool enabled
        json params "ej lead_days = 3"
    }
```

Notas del dominio:

- `notifications`, `notification_preferences` y `notification_deliveries` **no** llevan
  `SoftDeleteMixin`; las preferencias se *upsertean* en sitio (una fila por org+usuario).
- El `CHECK` del enum de `notification_deliveries.status` conserva el nombre histórico
  `email_outbox_status` (renombre de `email_outbox` en la migración `0013`).

---

## Dominio 4 — Activos de información (SDMujer)

Inventario de activos con licencias (composición: la licencia no sobrevive al activo) y
vínculo M:N a tareas existentes.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ASSETS : "inventaria"
    USERS         |o--o{ ASSETS : "es responsable de"
    ASSETS        ||--o{ ASSET_LICENSES : "licencia (CASCADE)"
    ASSETS        ||--o{ ASSET_TASKS : "se vincula via"
    TASKS         ||--o{ ASSET_TASKS : "atiende activo via"

    ASSETS {
        uuid id PK
        uuid organization_id FK
        string name
        text description "nullable"
        enum asset_type "hardware, software, saas_subscription, information, service, certificate"
        string category "nullable, segundo eje de taxonomia"
        enum status "active, inactive, retired, under_review"
        enum criticality "critical, high, medium, low"
        uuid responsible_id FK "nullable, SET NULL"
        date acquisition_date "nullable"
        string location "nullable"
        string vendor "nullable"
    }

    ASSET_LICENSES {
        uuid id PK
        uuid organization_id FK
        uuid asset_id FK "CASCADE"
        enum license_type "perpetual, subscription, trial"
        string license_key "nullable"
        date start_date
        date expiration_date "dispara alertas de vencimiento"
        int seats "nullable"
        numeric cost "nullable"
        bool auto_renew
    }

    ASSET_TASKS {
        uuid id PK
        uuid organization_id FK
        uuid asset_id FK "unique(asset_id, task_id)"
        uuid task_id FK
    }
```

Notas del dominio:

- `asset_criticality` es un enum propio, deliberadamente **no** reutiliza `Priority` de
  tareas aunque los valores coincidan.
- `asset_tasks` diverge del precedente `task_labels`: lleva `organization_id` directo para
  filtrar por tenant sin join extra. Sin soft delete: desvincular borra la fila.

---

## Dominio 5 — Conectores e integraciones

Configuración de conectores OAuth por organización (change 14-integration-ports): `connectors`
es la config del proveedor (p. ej. Microsoft 365, Google, GLPI, Jira — adaptadores reales en
los cambios 15-19; esta ola solo registra un adaptador `fake` en memoria). `connected_accounts`
es la cuenta que un usuario conectó bajo ese proveedor — la unicidad es por
`external_account_id` **dentro del conector**, nunca por `(user_id, provider)`: un usuario
puede conectar varias cuentas del mismo proveedor (ej. dos buzones de correo). Los tokens
viven **aislados** en `connection_credentials` (1:1 con la cuenta, cifrados con Fernet),
nunca junto a los campos que la API expone directamente sobre `connected_accounts`. El
`state` OAuth (CSRF, single-use) vive en Redis con TTL, no en una tabla.

```mermaid
erDiagram
    ORGANIZATIONS      ||--o{ CONNECTORS : "configura"
    CONNECTORS         ||--o{ CONNECTED_ACCOUNTS : "agrupa cuentas via"
    USERS              ||--o{ CONNECTED_ACCOUNTS : "conecta"
    CONNECTED_ACCOUNTS ||--o| CONNECTION_CREDENTIALS : "cifra tokens via (1:1)"

    CONNECTORS {
        uuid id PK
        uuid organization_id FK
        string provider "String(50), no enum PG - extensible 15-19"
        jsonb scopes "nullable"
        enum status "active, inactive, error"
    }

    CONNECTED_ACCOUNTS {
        uuid id PK
        uuid organization_id FK
        uuid connector_id FK "CASCADE"
        uuid user_id FK "CASCADE"
        string external_account_id "unique(connector_id, external_account_id)"
        string display_name "nullable"
        enum status "active, expired, revoked, error"
    }

    CONNECTION_CREDENTIALS {
        uuid id PK
        uuid organization_id FK
        uuid connected_account_id FK "CASCADE, unique - 1:1"
        text access_token_enc "cifrado Fernet"
        text refresh_token_enc "nullable, cifrado Fernet"
        timestamptz expires_at "nullable"
        string token_type "nullable"
        jsonb scopes "nullable"
    }
```

Notas del dominio:

- `connection_credentials` **no** lleva `SoftDeleteMixin`: es un hijo estrictamente
  1:1 (`ondelete=CASCADE`) de `connected_accounts` — desconectar una cuenta hace soft-delete
  de `ConnectedAccount` (respeta auditoría vía `SoftDeleteMixin`) y **DELETE físico (purga)** de
  `ConnectionCredentials` (postura conservadora de seguridad: los tokens cifrados no permanecen
  en la base tras la desconexión, incluso como borrados lógicos). Reconectar la misma cuenta
  externa reactiva la fila soft-deleted de la cuenta y guarda credenciales nuevas.
- El `state` OAuth (CSRF, anti-replay) NO es una tabla: vive en Redis
  (`oauth:state:{state}`, `SETEX`+`GETDEL` single-use) — decisión ratificada, TTL nativo sin
  necesidad de limpieza.
- `AccessContext` (contrato de `app/integrations/ports.py`, no persistido) transporta el
  token descifrado + `scopes` + un sink opcional `on_tokens_refreshed` para que un adaptador
  que rota tokens en una lectura los devuelva sin conocer la persistencia — lo consumen los
  adaptadores de los cambios 15/16 y el cambio 22.

---

## Módulos sin tablas propias

`auth`, `dashboard` y `search` no definen modelos: operan sobre las tablas anteriores
(autenticación sobre `users`/`organization_members`, vista ejecutiva y búsqueda global sobre
`projects`/`tasks`/`task_comments` con índices GIN de trigramas).

## Referencias

- `backend/app/shared/base_model.py` — mixins.
- `backend/app/shared/enums.py` — todos los enums del dominio.
- `backend/alembic/versions/` — historia de migraciones (fuente de la evolución del esquema).
- `docs/DATA-MODEL.md` — documento narrativo anterior (parcialmente desactualizado; ver este
  archivo para el estado real).
- `docs/diagrams/c4-architecture.md` — arquitectura C4 del sistema.
- `backend/app/integrations/` — núcleo hexagonal de puertos de integración (ports, registro,
  OAuth genérico, cifrado, state store).
