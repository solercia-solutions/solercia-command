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

    # Alert engine
    ALERT_SCHEDULER_INTERVAL_HOURS: int = 1


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""

    return Settings()


settings = get_settings()
