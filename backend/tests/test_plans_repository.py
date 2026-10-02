"""Repository tests for institutional plans (change 45a-planes-modelo-api).

Real PostgreSQL through the shared ``session`` fixture (SAVEPOINT isolation):
mapping, JSONB, constraints and the cross-project CTE roll-up cannot be proven
with a fake (agents/rules/solercia-persistence.md).
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.plans.models import (
    PlanActivityReport,
    TaskPlanActivity,
)
from app.modules.plans.progress import progress_denominator
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import (
    PlanActivityReportUpsert,
    PlanActivityUpsert,
    PlanUpsert,
)
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.enums import Methodology
from tests.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


async def _seed_plan(
    repo: PlansRepository,
    organization_id: uuid.UUID,
    *,
    plan_code: str = "PSPI-2026",
    activity_codes: tuple[str, ...] = ("1.1",),
    **activity_overrides: Any,
):
    plan = await repo.upsert_plan(
        organization_id,
        PlanUpsert(
            code=plan_code,
            name="Plan de seguridad",
            plan_type="pspi",
            period_year=2026,
        ),
    )
    activities = []
    for index, code in enumerate(activity_codes):
        activities.append(
            await repo.upsert_activity(
                plan.id,
                PlanActivityUpsert(
                    code=code,
                    name=f"Actividad {code}",
                    group_code=code.split(".")[0],
                    group_name=f"Grupo {code.split('.')[0]}",
                    is_mine=True,
                    sort_order=index,
                    **activity_overrides,
                ),
            )
        )
    await repo.db.flush()
    return plan, activities


async def _seed_project_with_board(
    session: AsyncSession,
    organization_id: uuid.UUID,
    code: str,
    status_keys: tuple[str, ...],
) -> Project:
    """A project with its own board; the LAST key is the last column."""

    project = Project(
        organization_id=organization_id,
        name=f"Proyecto {code}",
        methodology=Methodology.kanban,
        code=code,
        task_counter=0,
    )
    session.add(project)
    await session.flush()
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()
    for order, key in enumerate(status_keys):
        session.add(BoardColumn(board_id=board.id, name=key, status_key=key, order=order))
    await session.flush()
    return project


async def _seed_task(session: AsyncSession, project: Project, title: str, status: str) -> Task:
    task = Task(project_id=project.id, title=title, status=status)
    session.add(task)
    await session.flush()
    return task


async def _link(repo: PlansRepository, task: Task, activity: Any, role: str) -> TaskPlanActivity:
    link = await repo.upsert_task_link(task.id, activity.id, role)
    await repo.db.flush()
    return link


# ---------------------------------------------------------------------------
# Scenario 2 — JSONB round trip
# ---------------------------------------------------------------------------


async def test_activity_keeps_both_external_codes_after_roundtrip(
    session: AsyncSession, tenant
) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id, external_codes=["OM-05", "OM-08"])
    activity_id, organization_id = activity.id, tenant.id
    session.expire_all()

    loaded = await repo.get_activity(organization_id, activity_id)

    assert loaded is not None
    assert loaded.external_codes == ["OM-05", "OM-08"]


# ---------------------------------------------------------------------------
# Scenarios 5, 6 — period reports
# ---------------------------------------------------------------------------


async def test_a_period_without_a_report_has_no_row(session: AsyncSession, tenant) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id)
    await repo.upsert_report(activity.id, "I", PlanActivityReportUpsert(reported_progress=40))
    await session.flush()

    reports = await repo.list_reports(tenant.id, activity.id)

    assert [r.period for r in reports] == ["I"]
    assert await repo.list_reports_for_period(tenant.id, [activity.id], "II") == {}


async def test_upsert_report_replaces_the_period_value_without_duplicating(
    session: AsyncSession, tenant
) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id)
    await repo.upsert_report(activity.id, "I", PlanActivityReportUpsert(reported_progress=10))
    await session.flush()
    await repo.upsert_report(activity.id, "I", PlanActivityReportUpsert(reported_progress=75))
    await session.flush()

    rows = (
        await session.execute(
            select(func.count())
            .select_from(PlanActivityReport)
            .where(PlanActivityReport.plan_activity_id == activity.id)
        )
    ).scalar_one()
    reported = await repo.list_reports_for_period(tenant.id, [activity.id], "I")

    assert rows == 1
    assert reported[activity.id] == 75


# ---------------------------------------------------------------------------
# Scenario 8 — conflict link is listed and never enters the roll-up
# ---------------------------------------------------------------------------


async def test_conflict_link_is_listed_but_never_counted_as_confirmed(
    session: AsyncSession, tenant
) -> None:
    repo = PlansRepository(session)
    _, (a, b) = await _seed_plan(repo, tenant.id, activity_codes=("1.1", "1.2"))
    project = await _seed_project_with_board(session, tenant.id, "CNF", ("To Do", "Done"))
    task = await _seed_task(session, project, "t", "Done")
    await _link(repo, task, a, "primary")

    before = await repo.rollup_activity_progress(tenant.id, [a.id, b.id])
    await repo.upsert_activity_link(
        a.id, b.id, "contributes_to", "conflict", source_reference="4.5 (OM-03)"
    )
    await session.flush()
    after = await repo.rollup_activity_progress(tenant.id, [a.id, b.id])

    out = await repo.list_links(tenant.id, a.id)
    inbound = await repo.list_links(tenant.id, b.id)
    assert [(link.resolution, link.source_reference) for link in out] == [
        ("conflict", "4.5 (OM-03)")
    ]
    assert [link.resolution for link in inbound] == ["conflict"]
    assert before == after == {a.id: (1, 1, 0)}


# ---------------------------------------------------------------------------
# Scenario 9 — one task, primary of two activities
# ---------------------------------------------------------------------------


async def test_a_task_can_be_primary_of_two_activities(session: AsyncSession, tenant) -> None:
    repo = PlansRepository(session)
    _, (a, b) = await _seed_plan(repo, tenant.id, activity_codes=("2.5", "5.3"))
    project = await _seed_project_with_board(session, tenant.id, "TWO", ("To Do", "Done"))
    task = await _seed_task(session, project, "shared", "To Do")
    await _link(repo, task, a, "primary")
    await _link(repo, task, b, "primary")

    rollup = await repo.rollup_activity_progress(tenant.id, [a.id, b.id])

    assert rollup[a.id] == (0, 1, 0)
    assert rollup[b.id] == (0, 1, 0)


# ---------------------------------------------------------------------------
# Scenario 12 (repository layer) — no primary links => no data, never zero
# ---------------------------------------------------------------------------


async def test_calculated_progress_is_none_without_primary_links(
    session: AsyncSession, tenant
) -> None:
    repo = PlansRepository(session)
    _, (alone, only_contrib) = await _seed_plan(repo, tenant.id, activity_codes=("1.1", "1.2"))
    project = await _seed_project_with_board(session, tenant.id, "NOP", ("To Do", "Done"))
    task = await _seed_task(session, project, "support", "To Do")
    await _link(repo, task, only_contrib, "contributes")

    rollup = await repo.rollup_activity_progress(tenant.id, [alone.id, only_contrib.id])

    # An activity without links does not even appear (the service turns the
    # absence into None); one with only `contributes` has primary_total 0.
    assert alone.id not in rollup
    assert rollup[only_contrib.id] == (0, 0, 1)


# ---------------------------------------------------------------------------
# Scenario 13 — each task is judged against ITS OWN project's last column
# ---------------------------------------------------------------------------


async def test_rollup_uses_each_tasks_own_board_last_column(session: AsyncSession, tenant) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id)
    p1 = await _seed_project_with_board(session, tenant.id, "PRA", ("To Do", "Done"))
    p2 = await _seed_project_with_board(session, tenant.id, "PRB", ("Backlog", "Doing", "Shipped"))
    t1 = await _seed_task(session, p1, "in P1 last column", "Done")
    # "Done" is NOT the last column of P2 (its last one is "Shipped").
    t2 = await _seed_task(session, p2, "in P2 middle", "Done")
    await _link(repo, t1, activity, "primary")
    await _link(repo, t2, activity, "primary")

    assert (await repo.rollup_activity_progress(tenant.id, [activity.id]))[activity.id] == (1, 2, 0)

    t2.status = "Shipped"
    await session.flush()
    assert (await repo.rollup_activity_progress(tenant.id, [activity.id]))[activity.id] == (2, 2, 0)


# ---------------------------------------------------------------------------
# Scenario 14 — contributes stays out of the ratio
# ---------------------------------------------------------------------------


async def test_contributes_links_stay_out_of_the_ratio_and_only_feed_the_count(
    session: AsyncSession, tenant
) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id)
    project = await _seed_project_with_board(session, tenant.id, "CTB", ("To Do", "Done"))
    await _link(repo, await _seed_task(session, project, "p", "Done"), activity, "primary")
    for index in range(3):
        await _link(
            repo,
            await _seed_task(session, project, f"c{index}", "To Do"),
            activity,
            "contributes",
        )

    done, primary_total, contributing = (
        await repo.rollup_activity_progress(tenant.id, [activity.id])
    )[activity.id]

    assert done / primary_total == 1.0
    assert contributing == 3


# ---------------------------------------------------------------------------
# Scenario 28 — the seam is idempotent and never commits
# ---------------------------------------------------------------------------


async def test_reupserting_plan_and_activity_creates_no_new_rows(
    session: AsyncSession, tenant, monkeypatch
) -> None:
    commits: list[str] = []
    original_commit = session.commit

    async def _spy_commit() -> None:
        commits.append("commit")
        await original_commit()

    monkeypatch.setattr(session, "commit", _spy_commit)
    repo = PlansRepository(session)

    async def _counts() -> tuple[int, int]:
        from app.modules.plans.models import Plan, PlanActivity

        plans = (await session.execute(select(func.count()).select_from(Plan))).scalar_one()
        acts = (await session.execute(select(func.count()).select_from(PlanActivity))).scalar_one()
        return plans, acts

    await _seed_plan(repo, tenant.id, external_codes=["OM-05"])
    first = await _counts()
    plan, (activity,) = await _seed_plan(repo, tenant.id, external_codes=["OM-05"])
    second = await _counts()

    assert first == second == (1, 1)
    assert commits == [], "the seam must not commit its own transaction"
    # Same natural keys resolve to the same rows.
    again = await repo.upsert_activity(
        plan.id,
        PlanActivityUpsert(code="1.1", name="Renombrada"),
    )
    assert again.id == activity.id
    assert again.name == "Renombrada"


# ---------------------------------------------------------------------------
# H4 — the task side of an activity is served by ONE query
# ---------------------------------------------------------------------------


async def test_list_activity_tasks_is_a_single_query(session: AsyncSession, tenant) -> None:
    repo = PlansRepository(session)
    _, (activity,) = await _seed_plan(repo, tenant.id)
    project = await _seed_project_with_board(session, tenant.id, "SQL", ("To Do", "Done"))
    counted = await _seed_task(session, project, "counted", "To Do")
    cancelled = await _seed_task(session, project, "cancelled", "cancelled")
    support = await _seed_task(session, project, "support", "To Do")
    await _link(repo, counted, activity, "primary")
    await _link(repo, cancelled, activity, "primary")
    await _link(repo, support, activity, "contributes")
    await session.flush()

    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    sync_conn = (await session.connection()).sync_connection
    event.listen(sync_conn, "before_cursor_execute", _count)
    try:
        rows = await repo.list_activity_tasks(tenant.id, activity.id)
    finally:
        event.remove(sync_conn, "before_cursor_execute", _count)

    assert len(statements) == 1, statements
    by_task = {row.task_id: row for row in rows}
    assert by_task[counted.id].counts_toward_progress is True
    assert by_task[cancelled.id].counts_toward_progress is False
    assert by_task[support.id].counts_toward_progress is False

    # counts_toward_progress agrees, task by task, with the roll-up denominator.
    predicate_rows = (
        (
            await session.execute(
                select(Task.id).where(
                    Task.id.in_([counted.id, cancelled.id]),
                    progress_denominator().predicate,
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(predicate_rows) == {counted.id}

    primary_only = await repo.list_activity_tasks(tenant.id, activity.id, role="primary")
    assert {r.task_id for r in primary_only} == {counted.id, cancelled.id}


# ---------------------------------------------------------------------------
# D-D — tenant scope is centralized (supporting checks)
# ---------------------------------------------------------------------------


async def test_another_organization_never_reaches_the_activity(
    session: AsyncSession, tenant, second_tenant
) -> None:
    repo = PlansRepository(session)
    plan, (activity,) = await _seed_plan(repo, tenant.id)

    assert await repo.get_activity(second_tenant.id, activity.id) is None
    assert await repo.get_plan(second_tenant.id, plan.id) is None
    rows, total = await repo.list_activities(second_tenant.id)
    assert (list(rows), total) == ([], 0)
    assert await repo.count_activities_by_group(second_tenant.id, plan.id) == []
    assert await repo.rollup_activity_progress(second_tenant.id, [activity.id]) == {}


async def test_count_activities_by_group_groups_in_sql(session: AsyncSession, tenant) -> None:
    repo = PlansRepository(session)
    plan, _ = await _seed_plan(repo, tenant.id, activity_codes=("1.1", "1.2", "2.1"))

    groups = await repo.count_activities_by_group(tenant.id, plan.id)

    assert groups == [("1", "Grupo 1", 2), ("2", "Grupo 2", 1)]
