"""APScheduler setup for periodic alert evaluation.

Uses AsyncIOScheduler with an interval job. The scheduler is started inside
FastAPI's lifespan so it shares the event loop.

NOTE (multi-worker): When running multiple uvicorn workers or replicas,
every worker starts its own scheduler and evaluations may overlap. To prevent
duplicate work, wrap evaluate_all_organizations() in a Redis distributed lock.
This is documented but not implemented here — see evaluator.py TODO.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.alerts.evaluator import evaluate_all_organizations
from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger("solercia.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_evaluation() -> None:
    """Scheduler job wrapper: opens a DB session and runs evaluation."""
    async with AsyncSessionLocal() as db:
        try:
            total = await evaluate_all_organizations(db)
            logger.info(
                "Scheduled alert evaluation complete: %d new notifications.", total
            )
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled alert evaluation failed.")


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the alert scheduler. Call once from lifespan."""
    global _scheduler
    interval_hours: int = getattr(settings, "ALERT_SCHEDULER_INTERVAL_HOURS", 1)
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_evaluation,
        trigger=IntervalTrigger(hours=interval_hours),
        id="alert_evaluation",
        name="Alert Engine Evaluation",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Alert scheduler started (interval: %sh).", interval_hours)
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully. Call from lifespan teardown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Alert scheduler stopped.")
    _scheduler = None
