"""Tests for the alert engine: 4 strategies (minus blocked_task) + evaluator
+ dedup + admin endpoints + scheduler.

R1/R2 evaluación con dedup (task_overdue, task_at_risk, sprint_at_risk,
workload_imbalance) · R3 ``PATCH /alert-rules/{id}`` ajustable por admin ·
R4 ``POST /alerts/evaluate`` exige ``require_admin``
(openspec/specs/alert-engine/spec.md).

``blocked_task`` está EXCLUIDA — ya cubierta por ``test_blocked_task_alert.py``
(cambio 04); ningún test de esta suite la ejercita.

Sin dependencia del reloj real: se invoca ``evaluate_organization(db, org_id)``
directamente sobre la sesión de la prueba; el scheduler se prueba por
inspección de registro (``start_scheduler``/``stop_scheduler``), nunca
esperando el intervalo real.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_project(session: AsyncSession, tenant: Organization, code: str = "ALE"):
    from app.modules.projects.models import Project

    project = Project(
        organization_id=tenant.id,
        name="Alert Engine Project",
        methodology="kanban",
        code=code,
        task_counter=0,
    )
    session.add(project)
    await session.flush()
    return project


async def _seed_rule(
    session: AsyncSession, tenant: Organization, rule_type: str, *, enabled: bool = True, **params
):
    from app.modules.alert_rules.models import AlertRule

    rule = AlertRule(
        organization_id=tenant.id,
        rule_type=rule_type,
        enabled=enabled,
        threshold_params=params,
    )
    session.add(rule)
    await session.flush()
    return rule


# ---------------------------------------------------------------------------
# R1/R2 — Cada estrategia produce su alerta esperada (sin blocked_task)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_overdue_strategy_produces_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A task past ``due_date`` without ``completed_at`` notifies its assignee."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.notifications.models import Notification
    from app.modules.tasks.models import Task

    owner, _ = user
    project = await _seed_project(session, tenant)
    task = Task(
        project_id=project.id,
        title="Overdue task",
        status="Backlog",
        assignee_id=owner.id,
        due_date=datetime.now(UTC) - timedelta(days=2),
    )
    session.add(task)
    await session.flush()
    await _seed_rule(session, tenant, "task_overdue")

    created = await evaluate_organization(session, tenant.id)

    assert created == 1
    notification = (
        await session.execute(
            select(Notification).where(Notification.dedup_key == f"task_overdue:{task.id}")
        )
    ).scalar_one()
    assert notification.recipient_user_id == owner.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_at_risk_strategy_produces_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A task due soon with no recent activity (and no recent comments)
    notifies its assignee.
    """

    from app.alerts.evaluator import evaluate_organization
    from app.modules.notifications.models import Notification
    from app.modules.tasks.models import Task

    owner, _ = user
    project = await _seed_project(session, tenant)
    task = Task(
        project_id=project.id,
        title="At-risk task",
        status="Backlog",
        assignee_id=owner.id,
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(task)
    await session.flush()
    # Backdate updated_at past the inactivity window (default 3 days) — same
    # technique as test_blocked_task_alert.py's created_at backdating.
    task.updated_at = datetime.now(UTC) - timedelta(days=5)
    session.add(task)
    await session.flush()
    await _seed_rule(session, tenant, "task_at_risk")

    created = await evaluate_organization(session, tenant.id)

    assert created == 1
    notification = (
        await session.execute(
            select(Notification).where(Notification.dedup_key == f"task_at_risk:{task.id}")
        )
    ).scalar_one()
    assert notification.recipient_user_id == owner.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sprint_at_risk_strategy_produces_notification(
    session: AsyncSession, tenant: Organization, make_member
) -> None:
    """A sprint 75%+ elapsed with <50% of its points done notifies the admins."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.notifications.models import Notification
    from app.modules.sprints.models import Sprint
    from app.modules.tasks.models import Task

    admin_user, _ = await make_member(session, tenant, MemberRole.admin)
    project = await _seed_project(session, tenant)
    sprint = Sprint(
        project_id=project.id,
        name="Sprint at risk",
        status="active",
        start_date=datetime.now(UTC) - timedelta(days=9),
        end_date=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(sprint)
    await session.flush()
    task = Task(
        project_id=project.id,
        sprint_id=sprint.id,
        title="Sprint task",
        status="Backlog",
        estimation_points=10,
    )
    session.add(task)
    await session.flush()
    await _seed_rule(session, tenant, "sprint_at_risk")

    created = await evaluate_organization(session, tenant.id)

    assert created == 1
    notification = (
        await session.execute(
            select(Notification).where(
                Notification.dedup_key == f"sprint_at_risk:{sprint.id}:{admin_user.id}"
            )
        )
    ).scalar_one()
    assert notification.recipient_user_id == admin_user.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_workload_imbalance_strategy_produces_notification(
    session: AsyncSession, tenant: Organization, make_member
) -> None:
    """An assignee with more than ``max_active_tasks`` (default 8) active
    tasks triggers a notification to every admin.
    """

    from app.alerts.evaluator import evaluate_organization
    from app.modules.notifications.models import Notification
    from app.modules.tasks.models import Task

    admin_user, _ = await make_member(session, tenant, MemberRole.admin)
    overloaded_user, _ = await make_member(session, tenant, MemberRole.member)
    project = await _seed_project(session, tenant)
    for i in range(9):
        session.add(
            Task(
                project_id=project.id,
                title=f"Overloaded task {i}",
                status="Backlog",
                assignee_id=overloaded_user.id,
            )
        )
    await session.flush()
    await _seed_rule(session, tenant, "workload_imbalance")

    created = await evaluate_organization(session, tenant.id)

    assert created == 1
    notification = (
        await session.execute(
            select(Notification).where(
                Notification.dedup_key
                == f"workload_imbalance:{overloaded_user.id}:{admin_user.id}"
            )
        )
    ).scalar_one()
    assert notification.recipient_user_id == admin_user.id


# ---------------------------------------------------------------------------
# R1 — Solo reglas enabled + R2 dedup en corridas repetidas + aislamiento
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluator_ignores_disabled_rules(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A disabled rule's condition is met but produces NO notification."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.tasks.models import Task

    owner, _ = user
    project = await _seed_project(session, tenant)
    session.add(
        Task(
            project_id=project.id,
            title="Disabled-rule task",
            status="Backlog",
            assignee_id=owner.id,
            due_date=datetime.now(UTC) - timedelta(days=2),
        )
    )
    await session.flush()
    await _seed_rule(session, tenant, "task_overdue", enabled=False)

    created = await evaluate_organization(session, tenant.id)

    assert created == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repeated_evaluation_does_not_duplicate_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the evaluator twice on the SAME unchanged condition creates
    exactly ONE active notification (idempotent via ``exists_active``).
    """

    from app.alerts.evaluator import evaluate_organization
    from app.modules.tasks.models import Task

    owner, _ = user
    project = await _seed_project(session, tenant)
    session.add(
        Task(
            project_id=project.id,
            title="Repeated-eval task",
            status="Backlog",
            assignee_id=owner.id,
            due_date=datetime.now(UTC) - timedelta(days=2),
        )
    )
    await session.flush()
    await _seed_rule(session, tenant, "task_overdue")

    first = await evaluate_organization(session, tenant.id)
    second = await evaluate_organization(session, tenant.id)

    assert first == 1
    assert second == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluate_organization_only_yields_candidates_from_its_own_org(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Evaluating org A never creates a notification recipient-scoped to org B,
    even when both orgs have an ``enabled`` ``task_overdue`` rule (seeded by
    ``two_orgs``) — isolation between tenants.
    """

    from app.alerts.evaluator import evaluate_organization
    from app.modules.notifications.models import Notification
    from app.modules.tasks.models import Task

    project_a = await _seed_project(session, two_orgs.a.organization, code="ISOA")
    overdue_task_a = Task(
        project_id=project_a.id,
        title="Org A overdue task",
        status="Backlog",
        assignee_id=two_orgs.a.user.id,
        due_date=datetime.now(UTC) - timedelta(days=2),
    )
    session.add(overdue_task_a)
    await session.flush()

    created = await evaluate_organization(session, two_orgs.a.organization.id)

    assert created == 1
    org_b_notifications = (
        await session.execute(
            select(Notification).where(
                Notification.organization_id == two_orgs.b.organization.id,
                Notification.dedup_key == f"task_overdue:{overdue_task_a.id}",
            )
        )
    ).scalars().all()
    assert org_b_notifications == []


# ---------------------------------------------------------------------------
# R3 — PATCH /alert-rules/{id}: admin ajusta enabled/threshold_params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_alert_rule_allows_rbac_admin_to_adjust(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """An RBAC ADMIN can PATCH a rule's ``enabled``/``threshold_params``."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    rule = await _seed_rule(session, tenant, "workload_imbalance", max_active_tasks=8)

    response = await client.patch(
        f"/alert-rules/{rule.id}",
        json={"enabled": False, "threshold_params": {"max_active_tasks": 12}},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["enabled"] is False
    assert body["threshold_params"] == {"max_active_tasks": 12}


# ---------------------------------------------------------------------------
# R4 — POST /alerts/evaluate exige require_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_post_alerts_evaluate_rejects_non_admin(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """A member with no RBAC ADMIN role gets 403 on POST /alerts/evaluate."""

    _, token = user

    response = await client.post("/alerts/evaluate", headers=_auth(token))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Scheduler — registro del job, sin esperar el intervalo real
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_scheduler_registers_alert_evaluation_job_and_stops_cleanly() -> None:
    """``start_scheduler()`` registers the ``alert_evaluation`` job with an
    ``IntervalTrigger``; ``stop_scheduler()`` leaves ``_scheduler`` at ``None``.
    Neither waits for the interval nor executes ``_run_evaluation``.

    Runs as an ASYNC test (not a bare sync function) so it executes inside
    pytest-asyncio's managed event loop — ``AsyncIOScheduler`` resolves the
    running loop internally and errors with "no current event loop" when
    invoked from a plain sync test after other async tests have already
    closed their own per-test loops.
    """

    from apscheduler.triggers.interval import IntervalTrigger

    from app.alerts import scheduler as scheduler_module

    scheduler = scheduler_module.start_scheduler()
    try:
        job = scheduler.get_job("alert_evaluation")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)
    finally:
        scheduler_module.stop_scheduler()

    assert scheduler_module._scheduler is None
