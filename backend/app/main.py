"""Application entry point: FastAPI app, middleware, routers and lifespan."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.db_init import init_db, seed_default
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dependencies.router import router as dependencies_admin_router
from app.modules.menus.router import router as menus_admin_router
from app.modules.projects.router import router as projects_router
from app.modules.roles.router import router as roles_admin_router
from app.modules.sprints.router import router as sprints_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_admin_router
from app.shared.exceptions import register_exception_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("solercia")

API_PREFIX = "/api/v1"


async def _wait_for_db(max_attempts: int = 15, delay_seconds: float = 2.0) -> None:
    """Block until Postgres accepts connections, tolerating container warmup."""

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection established (attempt %s).", attempt)
            return
        except Exception as exc:  # noqa: BLE001 - retry on any connection error
            last_error = exc
            logger.warning(
                "Database not ready (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc,
            )
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(
        "No se pudo conectar a la base de datos tras varios intentos."
    ) from last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wait for the DB, create the schema and seed defaults on startup."""

    await _wait_for_db()
    await init_db()
    await seed_default()
    yield
    await engine.dispose()


app = FastAPI(
    title="Solercia PM",
    version="1.0.0",
    description="API del gestor de proyectos Solercia.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(tasks_router, prefix=API_PREFIX)
app.include_router(sprints_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)
# Admin / RBAC management endpoints (require the ADMIN role).
app.include_router(dependencies_admin_router, prefix=API_PREFIX)
app.include_router(roles_admin_router, prefix=API_PREFIX)
app.include_router(menus_admin_router, prefix=API_PREFIX)
app.include_router(users_admin_router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
async def root() -> dict:
    """Liveness probe."""

    return {"status": "ok"}


@app.get(f"{API_PREFIX}/health", tags=["health"])
async def health() -> dict:
    """Service health check."""

    return {"status": "ok", "service": "solercia-pm"}
