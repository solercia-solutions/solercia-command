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
    OAUTH_REDIRECT_ALLOWLIST: list[str] = ["http://localhost:4200/settings/connectors"]

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


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""

    return Settings()


settings = get_settings()
