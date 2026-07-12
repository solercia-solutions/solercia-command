"""Tests for the reminder dispatch engine (change 06, Fase B).

R6 Disparo idempotente + claim atómico anti-carrera · R8 Omisión por tarea
completada/cancelada/borrada · R9 Disparo de la regla task_due_soon
(specs/reminders/spec.md) · R10 Origen "reminder" en la bandeja compartida
(specs/notifications-inapp/spec.md).

Every dispatch test invokes ``dispatch_reminders``/``strategy.evaluate``
directly — never waits for the scheduler (pattern of
``test_blocked_task_alert.py``).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


async def _seed_project(session: AsyncSession, tenant: Organization, *, code: str):
    from app.modules.projects.models import Project

    project = Project(
        organization_id=tenant.id,
        name="Reminder Dispatch Project",
        methodology="kanban",
        code=code,
    )
    session.add(project)
    await session.flush()
    return project


async def _seed_task(
    session: AsyncSession,
    project,
    *,
    assignee_id=None,
    due_date=None,
    completed_at=None,
    is_active: bool = True,
):
    from app.modules.tasks.models import Task

    task = Task(
        project_id=project.id,
        title="Dispatch task",
        status="Backlog",
        assignee_id=assignee_id,
        due_date=due_date,
        completed_at=completed_at,
        is_active=is_active,
    )
    session.add(task)
    await session.flush()
    return task


async def _seed_reminder(
    session: AsyncSession,
    tenant: Organization,
    user_id,
    *,
    remind_at,
    task_id=None,
    message: str = "Recordatorio de prueba",
):
    from app.modules.reminders.models import Reminder
    from app.shared.enums import ReminderStatus

    reminder = Reminder(
        organization_id=tenant.id,
        user_id=user_id,
        task_id=task_id,
        remind_at=remind_at,
        message=message,
        status=ReminderStatus.scheduled,
    )
    session.add(reminder)
    await session.flush()
    return reminder


# ---------------------------------------------------------------------------
# R6 — Disparo idempotente de recordatorios manuales + claim atómico
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_fires_simple_reminder_without_task(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A due reminder with no task_id fires: 1 Notification, status=fired."""

    from app.modules.notifications.models import Notification
    from app.modules.reminders.models import Reminder
    from app.reminders.dispatcher import dispatch_reminders
    from app.shared.enums import ReminderStatus

    owner, _ = user
    reminder = await _seed_reminder(
        session, tenant, owner.id, remind_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    created = await dispatch_reminders(session)
    assert created == 1

    result = await session.execute(select(Reminder).where(Reminder.id == reminder.id))
    refreshed = result.scalar_one()
    assert refreshed.status == ReminderStatus.fired
    assert refreshed.fired_at is not None

    notif_result = await session.execute(
        select(Notification).where(
            Notification.organization_id == tenant.id,
            Notification.recipient_user_id == owner.id,
        )
    )
    notifications = notif_result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].rule_type == "reminder"
    assert notifications[0].dedup_key == f"reminder_manual:{reminder.id}"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_is_idempotent_across_runs(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the dispatcher twice on the same due reminder fires exactly once."""

    from app.reminders.dispatcher import dispatch_reminders

    owner, _ = user
    await _seed_reminder(
        session, tenant, owner.id, remind_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    first = await dispatch_reminders(session)
    assert first == 1

    second = await dispatch_reminders(session)
    assert second == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_claim_reminder_rejects_concurrently_cancelled_reminder(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """The atomic claim (WHERE status='scheduled') rejects a reminder cancelled
    between the dispatcher's SELECT and its claim UPDATE — closes the race the
    gate flagged (design.md Decision 4). Exercises ``_claim_reminder`` directly
    to reproduce the exact TOCTOU interleaving deterministically."""

    from app.modules.reminders.models import Reminder
    from app.reminders.dispatcher import _claim_reminder
    from app.shared.enums import ReminderStatus

    owner, _ = user
    reminder = await _seed_reminder(
        session, tenant, owner.id, remind_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    # Simulate the owner cancelling the reminder AFTER the dispatcher's SELECT
    # already loaded it as due+scheduled, but BEFORE the claim UPDATE runs.
    reminder.status = ReminderStatus.cancelled
    session.add(reminder)
    await session.flush()

    claimed = await _claim_reminder(
        session, reminder.id, ReminderStatus.fired, fired_at=datetime.now(UTC)
    )
    assert claimed is False

    result = await session.execute(select(Reminder).where(Reminder.id == reminder.id))
    refreshed = result.scalar_one()
    assert refreshed.status == ReminderStatus.cancelled
    assert refreshed.fired_at is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_does_not_fire_reminder_cancelled_before_run(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A due-but-cancelled reminder is skipped by dispatch_reminders end-to-end
    (no Notification, no status change) — the SELECT excludes it by status."""

    from app.modules.notifications.models import Notification
    from app.modules.reminders.models import Reminder
    from app.reminders.dispatcher import dispatch_reminders
    from app.shared.enums import ReminderStatus

    owner, _ = user
    reminder = await _seed_reminder(
        session, tenant, owner.id, remind_at=datetime.now(UTC) - timedelta(minutes=5)
    )
    reminder.status = ReminderStatus.cancelled
    session.add(reminder)
    await session.flush()

    created = await dispatch_reminders(session)
    assert created == 0

    result = await session.execute(select(Reminder).where(Reminder.id == reminder.id))
    refreshed = result.scalar_one()
    assert refreshed.status == ReminderStatus.cancelled

    notif_result = await session.execute(
        select(Notification).where(Notification.recipient_user_id == owner.id)
    )
    assert notif_result.scalars().all() == []


# ---------------------------------------------------------------------------
# R8 — Omisión ante tarea completada, cancelada o borrada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_skips_reminder_linked_to_completed_task(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A due reminder linked to an already-completed task transitions to skipped."""

    from app.modules.reminders.models import Reminder
    from app.reminders.dispatcher import dispatch_reminders
    from app.shared.enums import ReminderStatus

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT1")
    task = await _seed_task(
        session, project, assignee_id=owner.id, completed_at=datetime.now(UTC)
    )
    reminder = await _seed_reminder(
        session,
        tenant,
        owner.id,
        remind_at=datetime.now(UTC) - timedelta(minutes=5),
        task_id=task.id,
    )

    created = await dispatch_reminders(session)
    assert created == 0

    result = await session.execute(select(Reminder).where(Reminder.id == reminder.id))
    refreshed = result.scalar_one()
    assert refreshed.status == ReminderStatus.skipped


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatch_skips_reminder_linked_to_deleted_task(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A due reminder linked to a soft-deleted (borrada) task transitions to skipped."""

    from app.modules.reminders.models import Reminder
    from app.reminders.dispatcher import dispatch_reminders
    from app.shared.enums import ReminderStatus

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT2")
    task = await _seed_task(session, project, assignee_id=owner.id, is_active=False)
    reminder = await _seed_reminder(
        session,
        tenant,
        owner.id,
        remind_at=datetime.now(UTC) - timedelta(minutes=5),
        task_id=task.id,
    )

    created = await dispatch_reminders(session)
    assert created == 0

    result = await session.execute(select(Reminder).where(Reminder.id == reminder.id))
    refreshed = result.scalar_one()
    assert refreshed.status == ReminderStatus.skipped


# ---------------------------------------------------------------------------
# R9 — Disparo de la regla task_due_soon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_due_soon_notifies_within_lead_days(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A lead_days=3 rule notifies for a task due in 2 days, status in_progress."""

    from app.modules.reminders.models import ReminderRule
    from app.reminders.dispatcher import dispatch_reminders

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT3")
    task = await _seed_task(
        session,
        project,
        assignee_id=owner.id,
        due_date=datetime.now(UTC) + timedelta(days=2),
    )
    task.status = "Doing"
    session.add(task)

    session.add(
        ReminderRule(
            organization_id=tenant.id,
            user_id=owner.id,
            rule_type="task_due_soon",
            enabled=True,
            params={"lead_days": 3},
        )
    )
    await session.flush()

    created = await dispatch_reminders(session)
    assert created == 1

    from app.modules.notifications.models import Notification

    notif_result = await session.execute(
        select(Notification).where(Notification.recipient_user_id == owner.id)
    )
    notifications = notif_result.scalars().all()
    assert len(notifications) == 1
    assert notifications[0].target_id == task.id
    assert notifications[0].dedup_key.startswith(f"reminder_due_soon:{task.id}:{owner.id}:")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_due_soon_rerun_does_not_duplicate(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the dispatcher twice on an unchanged task_due_soon condition fires once."""

    from app.modules.reminders.models import ReminderRule
    from app.reminders.dispatcher import dispatch_reminders

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT4")
    await _seed_task(
        session,
        project,
        assignee_id=owner.id,
        due_date=datetime.now(UTC) + timedelta(days=2),
    )
    session.add(
        ReminderRule(
            organization_id=tenant.id,
            user_id=owner.id,
            rule_type="task_due_soon",
            enabled=True,
            params={"lead_days": 3},
        )
    )
    await session.flush()

    first = await dispatch_reminders(session)
    assert first == 1

    second = await dispatch_reminders(session)
    assert second == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_due_soon_completed_task_no_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A task completed before the run, even with due_date within lead_days, is excluded."""

    from app.modules.reminders.models import ReminderRule
    from app.reminders.dispatcher import dispatch_reminders

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT5")
    await _seed_task(
        session,
        project,
        assignee_id=owner.id,
        due_date=datetime.now(UTC) + timedelta(days=1),
        completed_at=datetime.now(UTC),
    )
    session.add(
        ReminderRule(
            organization_id=tenant.id,
            user_id=owner.id,
            rule_type="task_due_soon",
            enabled=True,
            params={"lead_days": 3},
        )
    )
    await session.flush()

    created = await dispatch_reminders(session)
    assert created == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_due_soon_rule_disabled_produces_no_candidates(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A disabled ReminderRule is skipped entirely by the dispatcher."""

    from app.modules.reminders.models import ReminderRule
    from app.reminders.dispatcher import dispatch_reminders

    owner, _ = user
    project = await _seed_project(session, tenant, code="RDT6")
    await _seed_task(
        session,
        project,
        assignee_id=owner.id,
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(
        ReminderRule(
            organization_id=tenant.id,
            user_id=owner.id,
            rule_type="task_due_soon",
            enabled=False,
            params={"lead_days": 3},
        )
    )
    await session.flush()

    created = await dispatch_reminders(session)
    assert created == 0


# ---------------------------------------------------------------------------
# R10 — Origen "reminder" en la bandeja compartida (specs/notifications-inapp)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dispatched_notification_visible_only_to_recipient(
    client, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    """A fired reminder's notification is visible via GET /notifications only
    to its recipient_user_id, not to another org member."""

    from app.reminders.dispatcher import dispatch_reminders
    from app.shared.enums import MemberRole

    owner, owner_token = user
    _, other_token = await make_member(session, tenant, MemberRole.member)

    await _seed_reminder(
        session, tenant, owner.id, remind_at=datetime.now(UTC) - timedelta(minutes=5)
    )

    created = await dispatch_reminders(session)
    assert created == 1

    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    owner_listing = await client.get("/notifications", headers=_auth(owner_token))
    assert owner_listing.status_code == 200
    owner_rule_types = [n["rule_type"] for n in owner_listing.json()["data"]]
    assert "reminder" in owner_rule_types

    other_listing = await client.get("/notifications", headers=_auth(other_token))
    assert other_listing.status_code == 200
    assert other_listing.json()["data"] == []
