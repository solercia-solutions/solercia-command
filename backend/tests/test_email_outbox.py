"""Tests for the email outbox hook at ``NotificationRepository.create()``
(change 08, Fase B).

R2 Interruptor maestro `EMAIL_ENABLED` · R3 Envío inmediato de tipos urgentes ·
R5 Alcance y marcado del digest · R10 Encolado de entrega email en la
creación (specs/email-notifications/spec.md, specs/notifications-inapp/spec.md).

Exercises ``NotificationRepository.create()`` directly (the single point
where a ``Notification`` is born, design.md D2) — never the dispatch job
itself (that is ``test_email_dispatch.py``). Uses the SAVEPOINT ``session``
fixture, mirroring ``test_reminder_dispatch.py``.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_urgent_notification_enqueues_outbox_row_and_marks_emailed_at(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """license_expired -> a pending email_outbox row + notification.emailed_at,
    both written in the SAME transaction as the notification itself."""

    from app.email.models import EmailOutbox
    from app.modules.notifications.repository import NotificationRepository
    from app.shared.enums import EmailOutboxStatus

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    owner, _ = user
    repo = NotificationRepository(session)
    notification = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="license_expired",
        title="Licencia vencida",
        body='La licencia de "Antivirus Corporativo" venció el 2026-07-01.',
        dedup_key=f"license_expired:outbox-test-1:{owner.id}",
    )

    assert notification.emailed_at is not None

    result = await session.execute(
        select(EmailOutbox).where(EmailOutbox.notification_id == notification.id)
    )
    outbox_row = result.scalar_one()
    assert outbox_row.status == EmailOutboxStatus.pending
    assert outbox_row.recipient_email == owner.email
    assert outbox_row.dedup_key == f"immediate:{notification.id}"
    assert outbox_row.organization_id == tenant.id
    assert outbox_row.subject
    assert notification.body in outbox_row.text_body


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_two_urgent_notifications_get_two_distinct_outbox_rows(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Triangulation: a SECOND urgent notification enqueues a SECOND row with a
    DIFFERENT dedup_key — proves the key is derived per-notification, not hardcoded."""

    from app.email.models import EmailOutbox
    from app.modules.notifications.repository import NotificationRepository

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    owner, _ = user
    repo = NotificationRepository(session)
    first = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="license_expired",
        title="Licencia vencida",
        body="Primera licencia.",
        dedup_key=f"license_expired:outbox-test-2a:{owner.id}",
    )
    second = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="license_expired",
        title="Licencia vencida",
        body="Segunda licencia.",
        dedup_key=f"license_expired:outbox-test-2b:{owner.id}",
    )

    result = await session.execute(
        select(EmailOutbox.dedup_key).where(
            EmailOutbox.notification_id.in_([first.id, second.id])
        )
    )
    dedup_keys = {row[0] for row in result.all()}
    assert dedup_keys == {f"immediate:{first.id}", f"immediate:{second.id}"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_non_urgent_notification_does_not_enqueue_outbox_row(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-urgent rule_type (e.g. task_overdue) waits for the digest: no
    outbox row, emailed_at stays NULL."""

    from app.email.models import EmailOutbox
    from app.modules.notifications.repository import NotificationRepository

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    owner, _ = user
    repo = NotificationRepository(session)
    notification = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="task_overdue",
        title="Tarea vencida",
        body="La tarea X está vencida.",
        dedup_key=f"task_overdue:outbox-test-3:{owner.id}",
    )

    assert notification.emailed_at is None

    result = await session.execute(
        select(EmailOutbox).where(EmailOutbox.notification_id == notification.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_email_disabled_urgent_notification_persists_without_outbox_row(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EMAIL_ENABLED=false: the notification still persists normally, but the
    interruptor maestro prevents any outbox row or emailed_at mark."""

    from app.email.models import EmailOutbox
    from app.modules.notifications.repository import NotificationRepository

    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)

    owner, _ = user
    repo = NotificationRepository(session)
    notification = await repo.create(
        organization_id=tenant.id,
        recipient_user_id=owner.id,
        rule_type="license_expired",
        title="Licencia vencida",
        body="Una licencia crítica venció.",
        dedup_key=f"license_expired:outbox-test-4:{owner.id}",
    )

    assert notification.emailed_at is None

    result = await session.execute(
        select(EmailOutbox).where(EmailOutbox.notification_id == notification.id)
    )
    assert result.scalar_one_or_none() is None
