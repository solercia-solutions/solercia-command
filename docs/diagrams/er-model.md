# Modelo entidad-relación — Solercia Project Manager

**Propósito**: este es el **documento vivo** del esquema de base de datos. Refleja, tabla por
tabla, los modelos SQLAlchemy reales de `backend/app/modules/*/models.py`,
`backend/app/notify/models.py` y los mixins de `backend/app/shared/base_model.py`. La fuente
de verdad es el **código**; este documento es su espejo navegable.

**Fecha de línea base**: 2026-07-19 (estado del código en la rama `feat/consume-solercia-ui`,
migraciones Alembic hasta `0019_add_intake`).

> **Regla de actualización**: todo cambio de base de datos (modelo nuevo, columna nueva,
> enum nuevo, FK nueva o eliminada) debe actualizar este documento **en el mismo commit de la
> migración Alembic** que lo introduce. Un diagrama desactualizado es peor que ninguno.

> Nota: la imagen `docs/diagrams/erd.png` es una captura histórica anterior a esta línea base.
> Se conserva como referencia, pero **este archivo es la fuente viva** del diagrama.

**Total de tablas**: 41.

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
    subgraph AUTH["Auth / organizaciones / RBAC (9 tablas)"]
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

    subgraph GLPISYNC["Homologación GLPI (3 tablas)"]
        glpi_user_links
    end

    subgraph ORGTEMPLATES["Plantillas organizacionales (3 tablas)"]
        org_role_templates
    end

    subgraph INTAKE["Clasificador de insumos (4 tablas)"]
        intake_items
    end

    organizations -->|"organization_id en toda tabla tenant-scoped"| CORE
    organizations --> ALERTS
    organizations --> ASSETS
    organizations --> INTEGRATIONS
    organizations --> GLPISYNC
    organizations -->|"opcional en org_role_templates - NULL = sistema"| ORGTEMPLATES
    organizations --> INTAKE
    users -->|"assignee, author, actor, auditoría"| CORE
    users -->|"recipient, owner"| ALERTS
    users -->|"responsible_id"| ASSETS
    users -->|"connected_accounts.user_id"| INTEGRATIONS
    users -->|"glpi_user_links.user_id"| GLPISYNC
    users -->|"lead_user_id via instantiations"| ORGTEMPLATES
    users -->|"intake_rules.assignee_id"| INTAKE
    tasks -->|"reminders.task_id"| ALERTS
    tasks -->|"asset_tasks"| ASSETS
    tasks -->|"intake_items.created_task_id"| INTAKE
    connectors -->|"glpi_user_links.connector_id"| GLPISYNC
    connectors -->|"intake_items.connector_id"| INTAKE
    ORGTEMPLATES -->|"instantiation crea proyectos"| CORE
    INTAKE -->|"TaskService.create_task / proyecto por defecto"| CORE
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
    USERS         ||--o{ FEDERATED_IDENTITIES : "enlaza via SSO"

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
        string hashed_password "nullable desde 0016 - NULL en usuarios solo-SSO, nunca se expone"
        string numero_documento "nullable desde 0017 - unique parcial global (WHERE NOT NULL)"
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

    FEDERATED_IDENTITIES {
        uuid id PK
        uuid user_id FK "CASCADE, indexada"
        string provider "alias de config, ej keycloak - NO participa del anclaje"
        string issuer "anclaje: unique(issuer, subject)"
        string subject "sub del IdP - anclaje: unique(issuer, subject)"
        string email "nullable, informativo del enlace inicial"
    }
```

Notas del dominio:

- `users.full_name` **no es columna**: es una `hybrid_property` (`primer_nombre` +
  `primer_apellido`).
- `menus` es **global** (sin `organization_id`); lo que varía por organización es qué roles
  conceden cada menú.
- `roles` lleva `unique(organization_id, code)`.
- `federated_identities` (change 20-sso-keycloak, migración `0016`) enlaza un `user` a una
  identidad OIDC externa. El anclaje criptográfico es `UNIQUE(issuer, subject)` — `sub` solo es
  único por `issuer` (correctitud OIDC); `provider` es solo el alias de configuración que enruta
  qué proveedor usar, nunca participa del anclaje. Tras el primer enlace el `email` queda
  desactualizado a propósito (informativo, no se usa para resolver el usuario de nuevo). Mixins
  Pk/Timestamp/SoftDelete/Audit — **sin** `TenantMixin`: el aislamiento por organización llega
  transitivamente vía `user_id -> organization_members`.
- `users.hashed_password` es **nullable** desde la migración `0016`: un usuario creado o
  enlazado únicamente por SSO (auto-provisión, `SSO_AUTO_PROVISION=true`) nunca recibe
  contraseña local. El login por credenciales rechaza `hashed_password IS NULL` con el mismo
  mensaje genérico de credenciales inválidas (nunca revela el método de login de la cuenta). La
  migración `0016.downgrade()` se niega a restaurar `NOT NULL` si existe algún usuario
  solo-SSO, para no corromper esas cuentas.
- `users.numero_documento` (change 17-adapter-glpi, migración `0017`) es el documento de
  identidad, nullable, con índice **único parcial** `WHERE numero_documento IS NOT NULL`
  (`uq_users_numero_documento`, declarado también a nivel ORM en `Index(...)` para que
  `Base.metadata.create_all` lo respete en tests, no solo la migración). Alcance **global**
  (igual que `email`), no por organización — `User` no tiene `TenantMixin` en el código real.
  Segundo nivel determinístico de la cascada de homologación GLPI (correo -> documento ->
  nombre), ver Dominio 6.

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
    USERS         |o--o{ PROJECTS : "es responsable de (lead_user_id)"
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
        uuid lead_user_id FK "nullable, SET NULL - desde 0018, responsable del proyecto"
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
- `projects.lead_user_id` (change 23-org-role-templates, migración `0018`) es el
  responsable/cabeza del proyecto. Poblado SIEMPRE por la instanciación de una plantilla
  organizacional (Dominio 7); los proyectos creados por el flujo directo `POST /projects` lo
  mantienen `NULL` (compatibilidad, ver `specs/projects/spec.md` delta).

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

Configuración de conectores OAuth/api_token por organización (change 14-integration-ports,
delta `credential_kind`/`settings` en change 17-adapter-glpi): `connectors`
es la config del proveedor (p. ej. Microsoft 365, Google, GLPI, Jira — adaptadores reales en
los cambios 15-19). `connected_accounts`
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
        enum credential_kind "oauth, api_token - default oauth, desde 0017"
        jsonb settings "nullable, config no-secreta (ej. GLPI base_url/document_field)"
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
- `connectors.credential_kind` (change 17-adapter-glpi, migración `0017`) distingue `oauth`
  (`authorize`/`callback`, changes 15/16) de `api_token` (registro directo de credenciales,
  GLPI). Se fija al crear el conector y no cambia después sin recrearlo.
  `connectors.settings` (JSONB, nullable) es configuración no-secreta específica del
  proveedor (ej. `base_url`/`document_field` de GLPI) — el 17 es **dueño** de la columna;
  los cambios 18/19 solo la consumen con su propio namespace, nunca agregan columna nueva.
  Las credenciales `api_token` de GLPI reutilizan `connection_credentials` sin columna nueva:
  `access_token_enc`=user_token, `refresh_token_enc`=App-Token, `token_type="glpi"`,
  `expires_at=NULL` (la vida de la sesión GLPI la maneja Redis, no esta tabla).

---

## Dominio 6 — Homologación de usuarios GLPI

Change 17-adapter-glpi (user-homologation spec). Cada persona **asignada** de un caso GLPI se
homologa contra un `user` real de la plataforma mediante una cascada determinística
(correo -> `numero_documento` -> nombre). Los niveles 1 y 2 auto-confirman
(`glpi_user_links`); el nivel 3 (nombre) **nunca** auto-confirma — solo sugiere candidatos y
cae en la cola (`glpi_unmatched_assignees` + `glpi_unmatched_cases`). La sync dispara **por
caso**, pero la cola consolida **por persona GLPI**: un segundo caso sin homologar de la
misma persona se agrega al detalle de la cabecera existente, nunca duplica la persona.

```mermaid
erDiagram
    CONNECTORS             ||--o{ GLPI_USER_LINKS : "confirma mapeo via"
    USERS                  ||--o{ GLPI_USER_LINKS : "es mapeado a"
    CONNECTORS             ||--o{ GLPI_UNMATCHED_ASSIGNEES : "acumula cola via"
    USERS                  |o--o{ GLPI_UNMATCHED_ASSIGNEES : "resuelve (resolved_user_id)"
    GLPI_UNMATCHED_ASSIGNEES ||--o{ GLPI_UNMATCHED_CASES : "detalla casos via"

    GLPI_USER_LINKS {
        uuid id PK
        uuid organization_id FK
        uuid connector_id FK "CASCADE, unique(connector_id, glpi_user_id)"
        string glpi_user_id "unique(connector_id, glpi_user_id)"
        uuid user_id FK "CASCADE"
        enum match_method "email, document, name, manual"
        string glpi_username "nullable"
        string glpi_email "nullable"
    }

    GLPI_UNMATCHED_ASSIGNEES {
        uuid id PK
        uuid organization_id FK
        uuid connector_id FK "CASCADE, unique(connector_id, glpi_user_id)"
        string glpi_user_id "unique(connector_id, glpi_user_id) - cabecera por persona"
        string glpi_username "nullable"
        string glpi_email "nullable"
        string glpi_document "nullable"
        jsonb candidates "sugerencias [{user_id, score, reason}], nunca auto-confirma"
        enum status "pending, resolved, ignored"
        uuid resolved_user_id FK "nullable, SET NULL"
        timestamptz resolved_at "nullable"
    }

    GLPI_UNMATCHED_CASES {
        uuid id PK
        uuid unmatched_assignee_id FK "CASCADE, unique(unmatched_assignee_id, glpi_ticket_id)"
        string glpi_ticket_id "unique(unmatched_assignee_id, glpi_ticket_id) - idempotente"
        string glpi_ticket_title "nullable"
        string glpi_ticket_status "nullable"
    }
```

Notas del dominio:

- `glpi_user_links` — Pk+Timestamp+SoftDelete+Audit+Tenant. Mapeo **confirmado**; toda sync
  futura de ese `glpi_user_id` resuelve directo contra este link, sin repetir la cascada.
  Revocarlo (soft-delete) devuelve a esa persona a la cascada en la siguiente sync.
- `glpi_unmatched_assignees` (cabecera) — Pk+Timestamp+Audit+Tenant, **sin** `SoftDeleteMixin`:
  `status` (`pending|resolved|ignored`) ES el ciclo de vida de la fila; resolver/ignorar la
  cambia en el sitio en vez de borrarla lógicamente.
  `UNIQUE(connector_id, glpi_user_id)` — **una fila por persona GLPI sin homologar**, no por
  caso.
- `glpi_unmatched_cases` (detalle) — Pk+Timestamp únicamente (sin Audit/Tenant: el aislamiento
  llega transitivamente vía la cabecera -> `connector_id` -> organización). 1:N off la
  cabecera; `UNIQUE(unmatched_assignee_id, glpi_ticket_id)` hace idempotente un segundo caso de
  la misma persona (se agrega al detalle, nunca duplica la cabecera).
- Resolver una cabecera crea el `glpi_user_link` (`match_method=manual`), la cabecera pasa a
  `resolved` y el detalle queda como histórico. Ignorarla la retira de la vista activa sin
  crear ningún link.
- Todas las consultas están scoped por `organization_id` (directo en las tres tablas, vía
  `TenantMixin`) — una cola/link de la organización A nunca es visible ni resoluble desde B.

---

## Dominio 7 — Plantillas organizacionales de alto cargo

Change 23-org-role-templates (migración `0018`). Perfiles predefinidos que, al instanciarse,
generan de una sola vez el árbol de proyectos (Dominio 2) de un área con un responsable
(`lead_user_id`). `org_role_templates` es la cabecera (`organization_id` nullable = plantilla de
**sistema**, sembrada por `db_init.seed_default`); `org_role_template_nodes` es el árbol
(sombrilla/rama/equipo) de la plantilla; `org_role_template_instantiations` es el **ledger** de
idempotencia — la instanciación reconcilia contra esta tabla, nunca contra el nombre del proyecto
generado.

```mermaid
erDiagram
    ORGANIZATIONS |o--o{ ORG_ROLE_TEMPLATES : "opcional - NULL = plantilla de sistema"
    ORG_ROLE_TEMPLATES ||--o{ ORG_ROLE_TEMPLATE_NODES : "define árbol"
    ORG_ROLE_TEMPLATE_NODES |o--o{ ORG_ROLE_TEMPLATE_NODES : "es hijo de"
    ORG_ROLE_TEMPLATES ||--o{ ORG_ROLE_TEMPLATE_INSTANTIATIONS : "registra instanciación via"
    ORG_ROLE_TEMPLATE_NODES ||--o{ ORG_ROLE_TEMPLATE_INSTANTIATIONS : "genera"
    USERS         ||--o{ ORG_ROLE_TEMPLATE_INSTANTIATIONS : "es responsable via"
    PROJECTS      ||--o{ ORG_ROLE_TEMPLATE_INSTANTIATIONS : "referencia (project_id)"

    ORG_ROLE_TEMPLATES {
        uuid id PK
        uuid organization_id FK "nullable - NULL = plantilla de sistema"
        string name
        bool is_system
    }

    ORG_ROLE_TEMPLATE_NODES {
        uuid id PK
        uuid template_id FK "CASCADE"
        uuid parent_node_id FK "nullable, autoreferencia, CASCADE - NULL = sombrilla"
        string name
        enum default_methodology "planner, kanban, scrum, custom"
        int node_order
    }

    ORG_ROLE_TEMPLATE_INSTANTIATIONS {
        uuid id PK
        uuid organization_id FK "CASCADE"
        uuid template_id FK "CASCADE"
        uuid node_id FK "CASCADE"
        uuid lead_user_id FK "CASCADE"
        uuid project_id FK "CASCADE - proyecto generado/reconciliado"
    }
```

Notas del dominio:

- `org_role_templates`/`org_role_template_nodes` — Pk+Timestamp (la cabecera además
  Pk+Timestamp+SoftDelete+Audit); las 5 plantillas de sistema son sembradas idempotentemente
  (patrón `_ensure_*` de `db_init.py`), NUNCA en la migración (`bulk_insert = 0` en el repo).
- `org_role_template_instantiations` — Pk+Timestamp únicamente, sin `TenantMixin` directo aunque
  lleva `organization_id` explícito: es el **ledger** de idempotencia,
  `UNIQUE(organization_id, template_id, node_id, lead_user_id)`. La instanciación REUSA la fila
  cuando el `project_id` referenciado sigue `is_active=true`; si el proyecto fue soft-deleted, la
  fila se ACTUALIZA (nunca se inserta un duplicado) con el `project_id` del proyecto recreado.
- La instanciación recorre `org_role_template_nodes` padre→hijo y crea cada `Project` (Dominio 2)
  encadenando `parent_project_id` según la estructura del árbol, respetando
  `PROJECT_HIERARCHY_MAX_DEPTH` (Dominio 2, change 21-project-hierarchy) y fijando
  `lead_user_id = uuid del responsable` en TODOS los proyectos generados. Toda la operación corre
  en una única transacción (un solo `commit`).

---

## Dominio 8 — Clasificador de insumos

Change 22-intake-classifier: almacenamiento e idempotencia de insumos leídos vía los puertos
de solo lectura del 14 (correo, calendario, tareas externas, notas de reunión, tickets), motor
de reglas tema→respondiente puro (`app/modules/intake/classifier.py`, sin BD ni HTTP) y
conversión real a `Task` (Dominio 2) vía `TaskService.create_task`. `intake_items` es
idempotente por `UNIQUE(organization_id, connector_id, external_id)` — releer el mismo insumo
nunca duplica la fila ni la tarea ya creada. `intake_runs` es la bitácora por
cuenta/conector de cada `POST /intake/pull` (sin soft delete: un log se consulta, nunca se
"des-borra"). `intake_settings` guarda el proyecto por defecto de la organización, creado
perezosamente (`planner`, nombre configurable, por defecto "Tareas Outlook").

```mermaid
erDiagram
    ORGANIZATIONS   ||--o{ INTAKE_ITEMS : "almacena insumos de"
    CONNECTORS      ||--o{ INTAKE_ITEMS : "origina via"
    CONNECTED_ACCOUNTS |o--o{ INTAKE_ITEMS : "opcional - GLPI sin cuenta individual"
    INTAKE_RULES    |o--o{ INTAKE_ITEMS : "clasifica via (matched_rule_id)"
    TASKS           |o--o{ INTAKE_ITEMS : "genera (created_task_id)"
    ORGANIZATIONS   ||--o{ INTAKE_RULES : "configura reglas tema-respondiente"
    PROJECTS        |o--o{ INTAKE_RULES : "destino opcional (target_project_id)"
    USERS           |o--o{ INTAKE_RULES : "asignado opcional (assignee_id)"
    ORGANIZATIONS   ||--o{ INTAKE_RUNS : "bitacora por pull"
    CONNECTORS      ||--o{ INTAKE_RUNS : "procesa via"
    ORGANIZATIONS   ||--o| INTAKE_SETTINGS : "configura (unique 1:1)"
    PROJECTS        |o--o| INTAKE_SETTINGS : "proyecto por defecto (default_project_id)"

    INTAKE_ITEMS {
        uuid id PK
        uuid organization_id FK
        string source_provider
        uuid connector_id FK "CASCADE"
        uuid connected_account_id FK "SET NULL, nullable"
        enum item_type "email, calendar_event, external_task, meeting_note, ticket"
        string external_id "unique(organization_id, connector_id, external_id)"
        string title
        text snippet "nullable"
        string origin_actor
        timestamptz occurred_at
        jsonb raw_payload "payload original, trazabilidad"
        enum status "pending, converted, ignored, error"
        uuid matched_rule_id FK "SET NULL, nullable"
        uuid created_task_id FK "SET NULL, nullable"
        timestamptz classified_at "nullable"
    }

    INTAKE_RULES {
        uuid id PK
        uuid organization_id FK
        string name
        jsonb criteria "lista {field, operator, value}, AND intra-regla"
        bool convert_to_task
        uuid target_project_id FK "SET NULL, nullable - null = proyecto por defecto"
        enum task_priority "low, medium, high, critical"
        uuid assignee_id FK "SET NULL, nullable"
        int rule_order "precedencia ascendente"
    }

    INTAKE_RUNS {
        uuid id PK
        uuid organization_id FK
        uuid connector_id FK "CASCADE"
        uuid connected_account_id FK "SET NULL, nullable"
        int items_fetched
        int items_new
        int items_duplicated
        int items_converted
        enum status "running, completed, error"
        timestamptz started_at
        timestamptz finished_at "nullable"
    }

    INTAKE_SETTINGS {
        uuid id PK
        uuid organization_id FK "unique(organization_id)"
        uuid default_project_id FK "SET NULL, nullable"
        string default_project_name "nullable - fallback INTAKE_DEFAULT_PROJECT_NAME"
    }
```

Notas del dominio:

- `intake_rules.is_active` **no** redeclara un campo propio: es el `is_active` de
  `SoftDeleteMixin` — desactivar una regla (`PATCH is_active=false`) y eliminarla
  (`DELETE`, soft delete) comparten exactamente el mismo contrato de exclusión (evaluación
  del clasificador + listados), así que una sola columna sirve para ambos en vez de un
  segundo flag de negocio que colisionaría con el nombre del mixin.
- `intake_runs` **no** lleva `SoftDeleteMixin` (mismo criterio que `activity_log`/bitácoras):
  un log de ejecución se consulta, nunca se "des-borra".
- La primera regla activa por `rule_order` ascendente que casa GANA; ninguna regla posterior
  se evalúa para ese ítem (`app/modules/intake/classifier.py`, `RuleBasedClassifier` puro
  detrás de `ClassifierPort`, patrón Strategy — precedente `app/methodology/`).
- `intake_settings.default_project_id` se resuelve **perezosamente**: la primera vez que una
  regla sin `target_project_id` o una conversión manual lo necesita, el servicio crea un
  `Project` `planner` (Dominio 2) vía `ProjectService.create_project` y lo persiste aquí;
  usos posteriores reutilizan el mismo proyecto.
- Un asignado (`intake_rules.assignee_id`) que NO es miembro activo de la organización nunca
  bloquea con un error ni muta membresías: el `IntakeItem` simplemente permanece
  `status=pending` en la cola de triage (mismo criterio `_verify_assignee`/`is_org_member`
  que `TaskService.create_task`, Dominio 2).
- La conversión a `Task` (automática o manual) usa el **service real** `TaskService.
  create_task` — nunca INSERT directo — así la tarea nace normal, editable por los endpoints
  vigentes de `tasks` sin romper `created_task_id`/`matched_rule_id`.

---

## Módulos sin tablas propias

`dashboard` y `search` no definen modelos: operan sobre las tablas anteriores (vista ejecutiva y
búsqueda global sobre `projects`/`tasks`/`task_comments` con índices GIN de trigramas). `auth`
define un único modelo propio, `federated_identities` (change 20-sso-keycloak); el resto de su
lógica opera sobre `users`/`organization_members`.

## Referencias

- `backend/app/shared/base_model.py` — mixins.
- `backend/app/shared/enums.py` — todos los enums del dominio.
- `backend/alembic/versions/` — historia de migraciones (fuente de la evolución del esquema).
- `docs/DATA-MODEL.md` — documento narrativo anterior (parcialmente desactualizado; ver este
  archivo para el estado real).
- `docs/diagrams/c4-architecture.md` — arquitectura C4 del sistema.
- `backend/app/integrations/` — núcleo hexagonal de puertos de integración (ports, registro,
  OAuth genérico, cifrado, state store).
- `backend/app/modules/intake/` — módulo router→service→repository del clasificador de
  insumos, más `classifier.py` (motor de reglas puro, patrón Strategy).
