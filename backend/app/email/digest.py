"""Digest job — one summary email per user with a due preference (D4).

Frontera de imports: this module — like every other module under
``app/email/`` — may import ``app.modules.notifications.models`` but NEVER
``app.modules.notifications.repository`` (the repository is the caller of
``app.email.outbox``, importing it back here would close a cycle).

Double idempotency (D4/R6): (1) a period gate (``_digest_due``) skips a
preference already digested for the current day/week; (2) even if that gate
were somehow bypassed, the ``emailed_at IS NULL`` filter finds nothing to
resend, and the outbox ``dedup_key`` is UNIQUE per ``(user_id, period)``.
"""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.email.models import EmailOutbox
from app.email.templates import render_digest
from app.modules.notifications.models import Notification, NotificationPreference
from app.modules.users.models import User
from app.shared.enums import DigestFrequency, EmailOutboxStatus, NotificationStatus

logger = logging.getLogger("solercia.email.digest")


def _period_key(pref: NotificationPreference, now_local: datetime) -> str:
    """A stable per-period string used in the outbox ``dedup_key`` (D4)."""

    if pref.digest_frequency == DigestFrequency.weekly:
        iso_year, iso_week, _iso_weekday = now_local.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return now_local.date().isoformat()


def _digest_due(pref: NotificationPreference, now_local: datetime) -> bool:
    """Whether ``pref``'s configured hour (and weekday, for weekly) has been
    reached in the CURRENT period and it has not already been digested."""

    if pref.digest_frequency == DigestFrequency.daily:
        if now_local.hour < pref.digest_hour:
            return False
        if pref.last_digest_at is None:
            return True
        last_local = pref.last_digest_at.astimezone(now_local.tzinfo)
        return last_local.date() < now_local.date()

    if pref.digest_frequency == DigestFrequency.weekly:
        weekday = pref.digest_weekday if pref.digest_weekday is not None else 0
        if now_local.weekday() != weekday or now_local.hour < pref.digest_hour:
            return False
        if pref.last_digest_at is None:
            return True
        last_local = pref.last_digest_at.astimezone(now_local.tzinfo)
        return last_local.isocalendar()[:2] < now_local.isocalendar()[:2]

    return False


async def dispatch_digest(db: AsyncSession) -> int:
    """Compose and enqueue one digest email per due preference.

    For every ``NotificationPreference`` with a non-``none`` frequency whose
    configured hour has been reached for the current period, aggregates the
    recipient's unread ``Notification`` rows with ``emailed_at IS NULL``,
    composes ONE outbox row, marks ``emailed_at`` on every included
    notification and updates ``last_digest_at`` — all committed once at the
    end. Returns the count of digests dispatched (0 if nothing was due, or
    due but with nothing to summarize).
    """

    tz = ZoneInfo(settings.EMAIL_DIGEST_TZ)
    now_local = datetime.now(tz)
    now_utc = datetime.now(UTC)

    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.digest_frequency != DigestFrequency.none
        )
    )
    preferences = result.scalars().all()

    dispatched = 0
    for pref in preferences:
        if not _digest_due(pref, now_local):
            continue

        notif_result = await db.execute(
            select(Notification).where(
                Notification.organization_id == pref.organization_id,
                Notification.recipient_user_id == pref.user_id,
                Notification.status == NotificationStatus.active,
                Notification.emailed_at.is_(None),
            )
        )
        notifications = list(notif_result.scalars().all())
        if not notifications:
            continue  # nothing pending: R6 guard — no empty digest is ever sent

        user_result = await db.execute(select(User).where(User.id == pref.user_id))
        recipient = user_result.scalar_one_or_none()
        if recipient is None:
            logger.warning(
                "No se pudo resolver el usuario %s para su digest; omitido.", pref.user_id
            )
            continue

        subject, text_body, html_body = render_digest(recipient, notifications)
        period = _period_key(pref, now_local)

        db.add(
            EmailOutbox(
                organization_id=pref.organization_id,
                notification_id=None,
                recipient_email=recipient.email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                dedup_key=f"digest:{pref.user_id}:{period}",
                status=EmailOutboxStatus.pending,
            )
        )
        for notification in notifications:
            notification.emailed_at = now_utc
            db.add(notification)

        pref.last_digest_at = now_utc
        db.add(pref)
        dispatched += 1

    await db.commit()
    return dispatched
