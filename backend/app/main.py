"""Application entry point: FastAPI app, middleware, routers and lifespan."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.alerts.router import router as alerts_admin_router
from app.alerts.scheduler import start_scheduler, stop_scheduler
from app.config import settings
from app.database import engine
from app.db_init import seed_default
from app.email.scheduler import register_delivery_jobs
from app.integrations import crypto as integrations_crypto
from app.modules.activity.router import router as activity_router
from app.modules.ai_settings.router import router as ai_settings_router
from app.modules.alert_rules.router import router as alert_rules_router
from app.modules.assets.router import router as assets_router
from app.modules.assistant.router import router as assistant_router
from app.modules.attachments.router import router as attachments_router
from app.modules.auth.router import router as auth_router
from app.modules.boards.router import router as boards_router
from app.modules.checklists.router import router as checklists_router
from app.modules.comments.router import router as comments_router
from app.modules.connectors.router import router as connectors_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dependencies.router import router as dependencies_admin_router
from app.modules.gitlab_integration.router import router as gitlab_router
from app.modules.glpi_sync.router import router as glpi_sync_router
from app.modules.intake.router import router as intake_router
from app.modules.jira_import.router import router as jira_import_router
from app.modules.labels.router import router as labels_router
from app.modules.menus.router import router as menus_admin_router
from app.modules.notifications.router import preferences_router as notifications_prefs_router
from app.modules.notifications.router import router as notifications_router
from app.modules.org_role_templates.router import router as org_role_templates_router
from app.modules.organizations.router import router as organizations_router
from app.modules.plans.router import router as plans_router
from app.modules.projects.router import router as projects_router
from app.modules.reconciliation.router import router as reconciliation_router
from app.modules.reminders.router import router as reminders_router
from app.modules.roles.router import router as roles_admin_router
from app.modules.scheduled_sync.router import router as scheduled_sync_router
from app.modules.scheduled_sync.scheduler import start_sync_scheduler, stop_sync_scheduler
from app.modules.search.router import router as search_router
from app.modules.sprints.router import router as sprints_router
from app.modules.task_import.router import router as task_import_router
from app.modules.task_links.router import router as task_links_router
from app.modules.tasks.router import router as tasks_router
from app.modules.time_logs.router import router as time_logs_router
from app.modules.users.router import router as users_admin_router
from app.modules.work_calendar.router import (
    organization_calendar_router,
)
from app.modules.work_calendar.router import (
    project_calendar_router as work_calendar_project_router,
)
from app.notify.dispatcher import has_active_durable_channel
from app.realtime.router import router as realtime_router
from app.reminders.scheduler import register_reminders_job
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
    """Wait for the DB and seed defaults on startup.

    The schema itself is no longer created here: the container entrypoint
    (``docker/entrypoint.sh``) runs ``alembic upgrade head`` before uvicorn
    starts, so by the time the lifespan runs the migrated schema already
    exists (see ADR 0003 and design.md Decision 1 of change 01-fundacion-tdd).
    """

    scheduler_attempted = False
    sync_scheduler_attempted = False
    lifespan_failed = False
    try:
        # Settings validates the closed profile set before importing resources.
        # Encryption validation remains mandatory in every profile.
        integrations_crypto.validate_key(settings.INTEGRATIONS_FERNET_KEY)
        await _wait_for_db()
        if settings.STARTUP_PROFILE == "default":
            await seed_default()
            scheduler = None
            # Best effort, including cleanup if creation/start fails partway.
            scheduler_attempted = True
            try:
                scheduler = start_scheduler()
            except Exception:  # noqa: BLE001
                logger.exception("No se pudo iniciar el programador de alertas; se continúa sin él.")
            # All jobs share the same scheduler; each registration is isolated.
            if scheduler is not None:
                try:
                    register_reminders_job(scheduler)
                except Exception:  # noqa: BLE001
                    logger.exception("No se pudo registrar el trabajo de recordatorios; se continúa sin él.")
                if has_active_durable_channel():
                    try:
                        register_delivery_jobs(scheduler)
                    except Exception:  # noqa: BLE001
                        logger.exception("No se pudieron registrar los trabajos de entrega; se continúa sin ellos.")
        # Scheduled sync (C02): its own flag, independent of the profile and
        # of EMAIL_ENABLED; in local_restricted these are the only jobs.
        if settings.SCHEDULED_SYNC_ENABLED:
            sync_scheduler_attempted = True
            try:
                start_sync_scheduler()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "No se pudo iniciar la sincronización programada; se continúa sin ella."
                )
        yield
    except BaseException:
        # Observe, never replace, the original failure (including cancellation).
        lifespan_failed = True
        raise
    finally:
        if sync_scheduler_attempted:
            try:
                stop_sync_scheduler()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "No se pudo detener correctamente la sincronización programada.",
                    exc_info=True,
                )
        try:
            if scheduler_attempted:
                try:
                    stop_scheduler()
                except Exception:  # noqa: BLE001
                    logger.warning("No se pudo detener correctamente el programador de alertas.", exc_info=True)
        finally:
            try:
                await engine.dispose()
            except (Exception, asyncio.CancelledError):
                if not lifespan_failed:
                    raise
                # Preserve the pending exception and its traceback; never log
                # exception details, which may contain connection credentials.
                logger.warning("No se pudo liberar el motor de base de datos tras un fallo previo.")


app = FastAPI(
    title="Solercia Command",
    version="1.0.0",
    description="API del centro operativo de trabajo Solercia Command.",
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
app.include_router(organizations_router, prefix=API_PREFIX)
app.include_router(organization_calendar_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(work_calendar_project_router, prefix=API_PREFIX)
app.include_router(org_role_templates_router, prefix=API_PREFIX)
app.include_router(boards_router, prefix=API_PREFIX)
app.include_router(tasks_router, prefix=API_PREFIX)
app.include_router(task_import_router, prefix=API_PREFIX)
app.include_router(comments_router, prefix=API_PREFIX)
app.include_router(attachments_router, prefix=API_PREFIX)
app.include_router(sprints_router, prefix=API_PREFIX)
app.include_router(labels_router, prefix=API_PREFIX)
app.include_router(checklists_router, prefix=API_PREFIX)
app.include_router(task_links_router, prefix=API_PREFIX)
app.include_router(time_logs_router, prefix=API_PREFIX)
app.include_router(activity_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(search_router, prefix=API_PREFIX)
# Admin / RBAC management endpoints (require the ADMIN role).
app.include_router(dependencies_admin_router, prefix=API_PREFIX)
app.include_router(roles_admin_router, prefix=API_PREFIX)
app.include_router(menus_admin_router, prefix=API_PREFIX)
app.include_router(users_admin_router, prefix=API_PREFIX)
app.include_router(alerts_admin_router, prefix=API_PREFIX)
app.include_router(alert_rules_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(notifications_prefs_router, prefix=API_PREFIX)
app.include_router(reminders_router, prefix=API_PREFIX)
app.include_router(assets_router, prefix=API_PREFIX)
app.include_router(connectors_router, prefix=API_PREFIX)
app.include_router(glpi_sync_router, prefix=API_PREFIX)
app.include_router(gitlab_router, prefix=API_PREFIX)
app.include_router(jira_import_router, prefix=API_PREFIX)
app.include_router(intake_router, prefix=API_PREFIX)
app.include_router(reconciliation_router, prefix=API_PREFIX)
app.include_router(assistant_router, prefix=API_PREFIX)
app.include_router(ai_settings_router, prefix=API_PREFIX)
app.include_router(plans_router, prefix=API_PREFIX)
app.include_router(scheduled_sync_router, prefix=API_PREFIX)
# Realtime push (WebSocket) is a best-effort channel: off does not affect
# REST, which stays authoritative regardless (design.md, Migration / Rollout).
if settings.WS_ENABLED:
    app.include_router(realtime_router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
async def root() -> dict:
    """Liveness probe."""

    return {"status": "ok"}


@app.get(f"{API_PREFIX}/health", tags=["health"])
async def health() -> dict:
    """Service health check."""

    return {"status": "ok", "service": "solercia-pm"}
