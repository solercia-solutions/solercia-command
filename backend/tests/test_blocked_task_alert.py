"""Tests for the blocked_task alert strategy (change 04, Batch D).

R12 estrategia en registry · R13 deduplicación · R14 seed idempotente.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


async def _seed_blocked_scenario(
    session: AsyncSession,
    tenant: Organization,
    *,
    edge_age_days: int,
    assignee_id=None,
):
    """Create project A/B tasks with an 'A is_blocked_by B' edge of a given age.

    Returns ``(blocked_task, dependency)``. B (the blocker) is left
    incomplete; A (the blocked task) gets ``assignee_id`` if provided.
    """
    from app.modules.projects.models import Project
    from app.modules.task_links.models import TaskDependency
    from app.modules.tasks.models import Task

    project = Project(
        organization_id=tenant.id,
        name="Blocked Task Alert Project",
        methodology="kanban",
        code=f"BTA{edge_age_days}",
    )
    session.add(project)
    await session.flush()

    blocked_task = Task(
        project_id=project.id,
        title="Blocked task",
        status="Backlog",
        assignee_id=assignee_id,
    )
    blocker_task = Task(project_id=project.id, title="Blocker task", status="Backlog")
    session.add_all([blocked_task, blocker_task])
    await session.flush()

    dependency = TaskDependency(
        organization_id=tenant.id,
        blocker_task_id=blocker_task.id,
        blocked_task_id=blocked_task.id,
    )
    session.add(dependency)
    await session.flush()

    # Backdate the edge to simulate it having existed for N days.
    dependency.created_at = datetime.now(UTC) - timedelta(days=edge_age_days)
    session.add(dependency)
    await session.flush()

    return blocked_task, dependency


# ---------------------------------------------------------------------------
# T19 — RED+GREEN: notifies the assignee after blocked_days (R12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluate_notifies_assignee_after_blocked_days(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A task blocked for 5 days (threshold 3) generates one candidate for its assignee."""

    from app.alerts.strategies.blocked_task import BlockedTaskStrategy

    owner, _ = user
    blocked_task, _dependency = await _seed_blocked_scenario(
        session, tenant, edge_age_days=5, assignee_id=owner.id
    )

    strategy = BlockedTaskStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"blocked_days": 3})

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.recipient_user_id == owner.id
    assert candidate.target_id == blocked_task.id
    assert candidate.dedup_key == f"blocked_task:{blocked_task.id}"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluate_skips_candidate_without_assignee(
    session: AsyncSession, tenant: Organization
) -> None:
    """A blocked task with no assignee produces no candidate (same pattern as task_at_risk)."""

    from app.alerts.strategies.blocked_task import BlockedTaskStrategy

    await _seed_blocked_scenario(session, tenant, edge_age_days=5, assignee_id=None)

    strategy = BlockedTaskStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"blocked_days": 3})

    assert candidates == []


# ---------------------------------------------------------------------------
# T20 — RED+GREEN: no notification for a recent block (R12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluate_skips_recently_blocked_task(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A task blocked only 1 day ago (threshold 3) produces no candidate."""

    from app.alerts.strategies.blocked_task import BlockedTaskStrategy

    owner, _ = user
    await _seed_blocked_scenario(
        session, tenant, edge_age_days=1, assignee_id=owner.id
    )

    strategy = BlockedTaskStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"blocked_days": 3})

    assert candidates == []


# ---------------------------------------------------------------------------
# T21 — RED+GREEN: deduplicación en corridas repetidas (R13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repeated_evaluation_does_not_duplicate_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the full evaluator twice creates exactly ONE notification (dedup_key)."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.alert_rules.models import AlertRule

    owner, _ = user
    await _seed_blocked_scenario(session, tenant, edge_age_days=5, assignee_id=owner.id)

    session.add(
        AlertRule(
            organization_id=tenant.id,
            rule_type="blocked_task",
            enabled=True,
            threshold_params={"blocked_days": 3},
        )
    )
    await session.flush()

    created_first = await evaluate_organization(session, tenant.id)
    assert created_first == 1

    created_second = await evaluate_organization(session, tenant.id)
    assert created_second == 0


# ---------------------------------------------------------------------------
# T22 — GREEN: registry + seed idempotente (R14)
# ---------------------------------------------------------------------------


def test_blocked_task_is_registered() -> None:
    """The registry exposes blocked_task among the registered rule types."""

    from app.alerts.registry import get_strategy, registered_rule_types

    assert "blocked_task" in registered_rule_types()
    strategy = get_strategy("blocked_task")
    assert strategy is not None
    assert strategy.rule_type == "blocked_task"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_seed_creates_five_rules_including_blocked_task(
    session: AsyncSession, tenant: Organization
) -> None:
    """Seeding a fresh organization creates exactly 7 default rules, one per rule_type."""

    from app.db_init import _ensure_alert_rules
    from app.modules.alert_rules.models import AlertRule

    await _ensure_alert_rules(session, tenant)
    await session.flush()

    result = await session.execute(
        select(AlertRule).where(AlertRule.organization_id == tenant.id)
    )
    rules = result.scalars().all()

    assert {r.rule_type for r in rules} == {
        "task_overdue",
        "task_at_risk",
        "sprint_at_risk",
        "workload_imbalance",
        "blocked_task",
        "license_expiring",
        "license_expired",
    }
    assert len(rules) == 7


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reseed_does_not_duplicate_rules(
    session: AsyncSession, tenant: Organization
) -> None:
    """Running the seed twice keeps exactly one rule per rule_type."""

    from app.db_init import _ensure_alert_rules
    from app.modules.alert_rules.models import AlertRule

    await _ensure_alert_rules(session, tenant)
    await session.flush()
    await _ensure_alert_rules(session, tenant)
    await session.flush()

    result = await session.execute(
        select(AlertRule).where(AlertRule.organization_id == tenant.id)
    )
    rules = result.scalars().all()

    rule_types = [r.rule_type for r in rules]
    assert len(rule_types) == len(set(rule_types)) == 7
