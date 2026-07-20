"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration sourced from the environment.

    Defaults match the Docker Compose topology so the service boots without
    an explicit ``.env`` file in development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database / cache
    DATABASE_URL: str = "postgresql+asyncpg://app:app@postgres:5432/solercia"
    REDIS_URL: str = "redis://redis:6379/0"

    # Authentication
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Refresh-token cookie. ``COOKIE_SECURE`` defaults to False for local dev
    # (HTTP); set it True behind HTTPS. ``SameSite=lax`` keeps the cookie on
    # same-site navigations while blocking cross-site POSTs.
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]
    # Allow VS Code dev tunnels (https://<id>-<port>.<region>.devtunnels.ms) and similar.
    CORS_ORIGIN_REGEX: str = r"https://.*\.devtunnels\.(ms|com)"

    # File uploads — directory where uploaded files are stored on disk.
    # Use an absolute path in production (e.g. /data/uploads).
    # Relative paths resolve from the process working directory (inside /app in Docker).
    UPLOAD_DIR: str = "./uploads"

    # Project hierarchy — maximum nesting depth (root = depth 1), configurable
    # per change 21-project-hierarchy design.md Decision 3.
    PROJECT_HIERARCHY_MAX_DEPTH: int = 5

    # Alert engine
    ALERT_SCHEDULER_INTERVAL_HOURS: int = 1

    # Reminder engine — separate interval from the alert engine's own job
    # (both run on the same AsyncIOScheduler instance, see app/reminders/scheduler.py).
    REMINDER_SCHEDULER_INTERVAL_MINUTES: int = 5

    # Realtime engine (WebSocket push) — best-effort channel, off does not
    # affect REST (see openspec/changes/09-websocket-realtime/design.md).
    # Default True: the frozen frontend does not consume it yet, so there is
    # no client-facing risk in shipping it enabled.
    WS_ENABLED: bool = True
    WS_HEARTBEAT_SECONDS: int = 30
    WS_IDLE_TIMEOUT_SECONDS: int = 90

    # Email engine — master switch off by default (aditivo, see
    # openspec/changes/08-email-notifications/design.md). ``EMAIL_BACKEND``
    # defaults to "console" so the test suite never touches the network even
    # if a test forgets to stub the sender explicitly; "smtp" only activates
    # by explicit configuration.
    EMAIL_ENABLED: bool = False
    EMAIL_BACKEND: str = "console"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "no-reply@solercia.com"
    FROM_NAME: str = "Solercia"
    SMTP_USE_TLS: bool = True
    EMAIL_MAX_ATTEMPTS: int = 5
    EMAIL_DIGEST_TZ: str = "America/Bogota"
    EMAIL_DISPATCH_INTERVAL_MINUTES: int = 5
    EMAIL_DIGEST_INTERVAL_MINUTES: int = 15

    # Integrations engine (OAuth connectors, change 14-integration-ports).
    # ``INTEGRATIONS_FERNET_KEY`` MUST be a urlsafe-base64 32-byte key (same
    # shape ``cryptography.fernet.Fernet.generate_key()`` produces); this dev
    # default is a valid key so the suite boots without a ``.env`` file —
    # production overrides it via the environment, same convention as
    # ``JWT_SECRET``.
    INTEGRATIONS_FERNET_KEY: str = "GVraOHsbm9EGeG8TDBNGc8TRZZEzPeSVIkytJ7jZGd8="
    OAUTH_STATE_TTL_SECONDS: int = 600
    # Allowlist of redirect_uri values a caller may request for the OAuth
    # authorize step (anti-SSRF/open-redirect, specs/connectors/spec.md).
    # The same list gates the OPTIONAL `redirect_to` browser-return
    # destination of `GET /connectors/{id}/authorize` (Conexiones page):
    # /connections is listed for every local frontend port — 4200
    # (docker-compose), 4242 and 4243 (local dev servers).
    OAUTH_REDIRECT_ALLOWLIST: list[str] = [
        "http://localhost:4200/settings/connectors",
        "http://localhost:4200/connections",
        "http://localhost:4242/connections",
        "http://localhost:4243/connections",
    ]

    # SSO (OIDC) — second login method, change 20-sso-keycloak. Master switch
    # off by default: with it False every /auth/sso/* route stays inert
    # (sso-oidc R6). ``SSO_AUTO_PROVISION`` off by default: no local account
    # is EVER created from an unrecognized SSO email unless explicitly
    # opted in (sso-oidc R4). ``SSO_POST_LOGIN_REDIRECT`` is the ONE
    # allowlisted SPA landing the callback 302s to after issuing the refresh
    # cookie — the access token never travels in the URL (sso-oidc R7).
    #
    # Per-provider ``OIDC_{PROVIDER}_ISSUER/CLIENT_ID/CLIENT_SECRET/
    # REDIRECT_URI`` are DELIBERATELY NOT declared as fixed Settings fields
    # here: they are read directly from the environment by provider name in
    # ``app/modules/auth/oidc/config.py`` (``load_provider_config(provider)``)
    # so a second IdP is wired by adding new env vars alone, zero code
    # changes (sso-oidc R6, "agregar un segundo proveedor OIDC NO DEBE
    # requerir cambios de código").
    SSO_ENABLED: bool = False
    SSO_AUTO_PROVISION: bool = False
    SSO_POST_LOGIN_REDIRECT: str = "http://localhost:4200/auth/callback"

    # Microsoft 365 adapter (change 15-adapter-microsoft365) — first REAL
    # provider over the 14's read-only ports, delegated OAuth (Entra ID).
    # ``M365_TENANT`` defaults to the multi-tenant "organizations" endpoint;
    # a fixed tenant ID overrides it per-deployment. Both base URLs MUST be
    # ``https://`` — ``GraphClient`` fails fast otherwise (anti-SSRF/TLS
    # obligatorio, design.md Threat Matrix).
    M365_CLIENT_ID: str = ""
    M365_CLIENT_SECRET: str = ""
    M365_TENANT: str = "organizations"
    M365_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    M365_LOGIN_BASE_URL: str = "https://login.microsoftonline.com"
    M365_TIMEOUT_SECONDS: float = 10.0
    M365_MAX_RETRIES: int = 3
    # Techo del backoff ante 429: `_retry_after_seconds` NUNCA duerme más
    # que esto, sin importar el `Retry-After` que devuelva Graph.
    M365_MAX_BACKOFF_SECONDS: float = 30.0
    M365_DEFAULT_SINCE_DAYS: int = 30
    M365_CALENDAR_FUTURE_DAYS: int = 90
    M365_MAX_PAGES: int = 20
    M365_MAX_LIMIT: int = 200

    # Google adapter (change 16-adapter-google) — the second real provider
    # over the 14's read-only ports, Gmail/Calendar/Drive via a plain OAuth
    # 2.0 authorization-code flow (not delegated-tenant like Entra ID).
    # Every *_BASE_URL below MUST be ``https://`` — ``GoogleClient`` fails
    # fast otherwise (anti-SSRF/TLS obligatorio, same guard as M365's
    # `_require_https`). ``GOOGLE_OAUTH_REDIRECT_URI`` documents the
    # expected callback for operators; the adapter itself always uses the
    # explicit ``redirect_uri`` the 14's `IntegrationAdapter.authorize_url`
    # protocol passes in, never this setting.
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:4200/settings/connectors"
    GOOGLE_GMAIL_BASE_URL: str = "https://gmail.googleapis.com/gmail/v1"
    GOOGLE_CALENDAR_BASE_URL: str = "https://www.googleapis.com/calendar/v3"
    GOOGLE_DRIVE_BASE_URL: str = "https://www.googleapis.com/drive/v3"
    GOOGLE_AUTHZ_BASE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_BASE_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_BASE_URL: str = "https://openidconnect.googleapis.com/v1/userinfo"
    GOOGLE_TIMEOUT_SECONDS: float = 10.0
    GOOGLE_MAX_RETRIES: int = 3
    # Techo del backoff ante 429/403 rateLimitExceeded — mismo criterio que
    # `M365_MAX_BACKOFF_SECONDS`.
    GOOGLE_MAX_BACKOFF_SECONDS: float = 30.0
    GOOGLE_DEFAULT_SINCE_DAYS: int = 30
    # Límite efectivo que `_GooglePortBase._bounded_limit` usa cuando el
    # caller NO pasa `limit` (los tres puertos Google resuelven este
    # default adentro, sin tocar la firma del `Protocol`).
    GOOGLE_DEFAULT_LIMIT: int = 50
    GOOGLE_MAX_PAGES: int = 20
    GOOGLE_MAX_LIMIT: int = 200

    # GLPI adapter (change 17-adapter-glpi) — read-only tickets over GLPI's
    # `apirest.php`, `credential_kind=api_token` (App-Token + user_token ->
    # `initSession`). Unlike M365/Google, `base_url` is PER-CONNECTOR
    # (`connectors.settings.base_url`, admin-configured) rather than a
    # single fixed provider host — `GLPI_BASE_URL_ALLOWLIST` is the
    # anti-SSRF guard (analogous to `OAUTH_REDIRECT_ALLOWLIST`): a
    # connector's `base_url` MUST be a member of this list, checked BEFORE
    # any request (`GlpiClient.__init__`, Threat Matrix).
    GLPI_BASE_URL_ALLOWLIST: list[str] = ["http://localhost:8080/glpi/apirest.php"]
    GLPI_TIMEOUT_SECONDS: float = 10.0
    # `session_token` Redis TTL — MUST stay below GLPI's own server-side
    # session lifetime (design.md Open Questions: confirmar contra la
    # instancia destino); 3300s (55min) is a conservative default under
    # GLPI's common 1h default.
    GLPI_SESSION_TTL_SECONDS: int = 3300
    GLPI_PAGE_SIZE: int = 100
    GLPI_MAX_PAGES: int = 20
    GLPI_MAX_RETRIES: int = 3
    # Techo del backoff — mismo criterio que `M365_MAX_BACKOFF_SECONDS`/
    # `GOOGLE_MAX_BACKOFF_SECONDS`, aplicado por `client.py`'s resilience
    # boundary ante un 5xx transitorio de GLPI.
    GLPI_MAX_BACKOFF_SECONDS: float = 30.0
    # Campo GLPI portador del documento de identidad del asignado, usado
    # por defecto cuando `connectors.settings.document_field` no lo
    # especifica explícitamente (mapper.py, change 17 Lote 6).
    GLPI_DEFAULT_DOCUMENT_FIELD: str = "registration_number"

    # Jira adapter (change 18-adapter-jira) — read-only issue import over
    # Jira Cloud's REST API v3 and CSV/XLSX export, `credential_kind=
    # api_token` (email + API token, HTTP Basic, validated via `GET
    # /rest/api/3/myself`). Solo-lectura; no persiste (design.md, "el
    # storage y la conversión a Task son del 22").
    #
    # Guarda antibomba del parser de archivo (Lote 4): un CSV/XLSX que
    # exceda CUALQUIERA de estos dos límites se rechaza con un error
    # controlado ANTES de terminar de leerlo — nunca se procesa
    # parcialmente (Threat Matrix, "Bomba de descompresión XLSX").
    JIRA_FILE_MAX_ROWS: int = 50_000
    JIRA_FILE_MAX_CELLS: int = 500_000
    # Techo de bytes del upload crudo, rechazado (413) ANTES de parsear —
    # mismo criterio que `attachments/service.py`'s `_MAX_UPLOAD_BYTES`.
    JIRA_FILE_MAX_BYTES: int = 10 * 1024 * 1024
    # Cliente HTTP de la vía API (Lote 5). A diferencia de GLPI
    # (`GLPI_BASE_URL_ALLOWLIST`, una lista cerrada de instancias
    # conocidas), un sitio Jira Cloud es por-tenant y prácticamente
    # ilimitado (`https://<site>.atlassian.net`) — la frontera anti-SSRF
    # aquí es un SUFIJO obligatorio en vez de una allowlist cerrada
    # (design.md Threat Matrix, "host fuera de *.atlassian.net ->
    # rechazado").
    JIRA_BASE_URL_ALLOWED_SUFFIX: str = ".atlassian.net"
    JIRA_TIMEOUT_SECONDS: float = 10.0
    JIRA_PAGE_SIZE: int = 100
    JIRA_MAX_PAGES: int = 20
    JIRA_MAX_RETRIES: int = 3
    # Techo del backoff ante 429 — mismo criterio que
    # `GLPI_MAX_BACKOFF_SECONDS`/`M365_MAX_BACKOFF_SECONDS`.
    JIRA_MAX_BACKOFF_SECONDS: float = 30.0

    # MCP adapter (change 19-mcp-connector) — read-only client over the
    # Model Context Protocol's Streamable HTTP transport, `credential_kind
    # ∈ {api_token, none}` (a per-CONNECTOR choice, not fixed per-adapter
    # like GLPI/Jira — see `IntegrationAdapter.credential_kinds`).
    #
    # Anti-SSRF (`adapters/mcp/ssrf.py`, MC-R7) is DEFAULT-DENY: unlike
    # GLPI's `GLPI_BASE_URL_ALLOWLIST` (full base URLs), `MCP_HOST_ALLOWLIST`
    # holds bare HOSTS — ANY host not literally present here is rejected,
    # private range or not, BEFORE any DNS lookup is attempted. A host that
    # IS present is explicitly trusted by the admin and may resolve to a
    # private/reserved range on purpose (e.g. a local test server).
    # `MCP_BLOCK_PRIVATE_NETWORKS` is kept for `Settings` shape/backward
    # compatibility but is presently a no-op — see `ssrf.py`'s docstring.
    MCP_HOST_ALLOWLIST: list[str] = ["localhost", "127.0.0.1"]
    # Off by default (dev/test convenience) — production deployments MUST
    # override this to False, same convention as `COOKIE_SECURE`.
    MCP_ALLOW_HTTP: bool = True
    MCP_BLOCK_PRIVATE_NETWORKS: bool = True
    # `MCP_CONNECT_TIMEOUT_SECONDS` bounds ONLY the transport handshake +
    # `initialize` (`session.open_session`); `MCP_TOTAL_TIMEOUT_SECONDS`
    # bounds every SUBSEQUENT request on the same session
    # (`ClientSession(..., read_timeout_seconds=...)`) — mirrors
    # `GLPI_TIMEOUT_SECONDS`'s single-timeout shape, split in two because an
    # ephemeral MCP session's `initialize` handshake and a `read_resource`
    # call are separate round-trips with different failure semantics
    # (MC-R3 vs MC-R6).
    MCP_CONNECT_TIMEOUT_SECONDS: float = 10.0
    MCP_TOTAL_TIMEOUT_SECONDS: float = 30.0
    # Bounds ONLY the `getaddrinfo` lookup `validate_mcp_url` performs for an
    # ALLOWLISTED host (`ssrf.py`) — a non-allowlisted host is rejected
    # BEFORE any lookup, so this only guards against a hanging/malicious
    # resolver for a host the admin already trusts.
    MCP_DNS_TIMEOUT_SECONDS: float = 5.0
    # `resources/list`/`tools/list` results are truncated to this many
    # items — mirrors `GOOGLE_DEFAULT_LIMIT`/`GLPI_PAGE_SIZE`'s antibomba
    # intent, applied client-side since MCP's list operations do not accept
    # a caller-supplied page size (MC-R6).
    MCP_MAX_LIST_ITEMS: int = 100
    # `read_resource`/`call_tool` results exceeding this many bytes are
    # rejected — the oversized content is NEVER mapped into the returned
    # DTO (MC-R4; see `reader.py`'s docstring for the SDK's synchronous
    # `resources/read` shape this tope is enforced against).
    MCP_MAX_RESOURCE_BYTES: int = 1_048_576  # 1 MiB

    # Intake classifier (change 22-intake-classifier) — storage + rules engine
    # over the 14's read-only ports. ``INTAKE_DEFAULT_PROJECT_NAME`` seeds
    # ``IntakeSettings.default_project_name`` the FIRST time an organization
    # needs its lazy default project (design.md "Proyecto por defecto");
    # `PATCH /intake/settings` overrides it per-organization afterwards.
    # ``INTAKE_PULL_MAX_ITEMS`` bounds every `list_*` call a `POST
    # /intake/pull` makes per account (same antibomba intent as
    # `M365_MAX_PAGES`/`GLPI_PAGE_SIZE`) — pull is synchronous in the
    # request, never a background job (design.md Architecture Decisions).
    INTAKE_DEFAULT_PROJECT_NAME: str = "Tareas Outlook"
    INTAKE_PULL_MAX_ITEMS: int = 50


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""

    return Settings()


settings = get_settings()
