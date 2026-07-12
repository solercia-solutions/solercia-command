"""APScheduler jobs for the email engine — mirrors app/reminders/scheduler.py.

Registers its own job(s) onto the SAME ``AsyncIOScheduler`` instance returned
by ``app.alerts.scheduler.start_scheduler()``: one scheduler loop, isolated
jobs. Each job opens its own DB session and swallows its own exceptions — an
email failure never takes down the alert/reminder jobs or vice-versa.
Dependency direction is ``main -> email``, NEVER ``alerts -> email``.

``delivery_dispatch`` (renamed from ``email_dispatch``, change 12,
design.md D3/D4) drains ``notification_deliveries`` across EVERY registered
``durable`` channel via the GENERIC dispatcher
(``app.notify.dispatcher.dispatch_deliveries``) — it is the ONLY dispatcher
job in the system, no longer email-only. ``email_digest`` stays a
dedicated email-domain job (D4, "sigue siendo job de dominio email").
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.email.digest import dispatch_digest
from app.notify.dispatcher import dispatch_deliveries

logger = logging.getLogger("solercia.email.scheduler")


async def _run_dispatch() -> None:
    """Scheduler job wrapper: opens its own DB session and drains deliveries."""
    async with AsyncSessionLocal() as db:
        try:
            total = await dispatch_deliveries(db)
            logger.info("Scheduled delivery dispatch complete: %d row(s) processed.", total)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled delivery dispatch failed.")


async def _run_digest() -> None:
    """Scheduler job wrapper: opens its own DB session and runs the digest.

    Isolated from ``_run_dispatch``'s session/try-except (own job, own
    failure domain) — a digest failure never blocks the outbox dispatch job
    or vice-versa.
    """
    async with AsyncSessionLocal() as db:
        try:
            total = await dispatch_digest(db)
            logger.info("Scheduled email digest complete: %d digest(s) dispatched.", total)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled email digest failed.")


def register_delivery_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the ``delivery_dispatch`` and ``email_digest`` jobs onto an
    already-running scheduler."""
    dispatch_interval: int = getattr(settings, "EMAIL_DISPATCH_INTERVAL_MINUTES", 5)
    scheduler.add_job(
        _run_dispatch,
        trigger=IntervalTrigger(minutes=dispatch_interval),
        id="delivery_dispatch",
        name="Notification Delivery Dispatch",
        replace_existing=True,
    )
    logger.info("Delivery dispatch job registered (interval: %smin).", dispatch_interval)

    digest_interval: int = getattr(settings, "EMAIL_DIGEST_INTERVAL_MINUTES", 15)
    scheduler.add_job(
        _run_digest,
        trigger=IntervalTrigger(minutes=digest_interval),
        id="email_digest",
        name="Email Digest",
        replace_existing=True,
    )
    logger.info("Email digest job registered (interval: %smin).", digest_interval)
