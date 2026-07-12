"""Regression tests for the 4 resolve_board_strategy call sites (Batch B, T16).

``dashboard._bounds_for``, ``sprints`` burndown's ``done_status`` and
``projects._attach_methodology_info`` must reflect the project's PERSISTED
board columns, not the stale hardcoded base strategy. Reordering a board
column changes which ``status_key`` is "done" — the base strategy would never
notice this, since it always returns the ORIGINAL ``default_columns()``
list. Column configuration endpoints do not exist yet (Batch D), so these
tests reorder columns directly through the session, exactly the shape a
future config API mutation would produce.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


async def _reorder_so_in_review_is_last(session: AsyncSession, project_id: uuid.UUID) -> None:
    """Swap 'Done' and 'In Review' order so 'In Review' becomes the last column."""

    from app.modules.boards.service import BoardService

    board = await BoardService(session).get_board(project_id)
    assert board is not None
    columns = {c.status_key: c for c in board.columns}
    columns["Done"].order = 2
    columns["In Review"].order = 3
    await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_dashboard_bounds_reflect_reordered_board_not_stale_strategy(
    session: AsyncSession, tenant: Organization
) -> None:
    """dashboard._bounds_for's 'last' (done) bound follows the persisted column order."""

    from app.modules.dashboard.service import DashboardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="Reorder Dashboard", methodology="scrum")
    )
    await _reorder_so_in_review_is_last(session, project.id)

    bounds = await DashboardService(session)._bounds_for(project)  # noqa: SLF001
    assert bounds.last == "In Review"
    assert bounds.is_done("In Review") is True
    assert bounds.is_done("Done") is False


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_projects_attach_methodology_info_reflects_reordered_board(
    session: AsyncSession, tenant: Organization
) -> None:
    """projects._attach_methodology_info's allowed_statuses follows the persisted order."""

    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    service = ProjectService(session)
    project = await service.create_project(
        tenant.id, ProjectCreate(name="Reorder Info", methodology="scrum")
    )
    await _reorder_so_in_review_is_last(session, project.id)

    fetched = await service.get_project(tenant.id, project.id)
    assert fetched.methodology_info["allowed_statuses"][-1] == "In Review"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sprint_burndown_done_status_reflects_reordered_board(
    session: AsyncSession, tenant: Organization
) -> None:
    """burndown()'s completed_tasks count follows the NEW last column, not 'Done'."""

    from datetime import UTC, datetime, timedelta

    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService
    from app.modules.sprints.models import Sprint
    from app.modules.sprints.service import SprintService
    from app.modules.tasks.schemas import TaskCreate
    from app.modules.tasks.service import TaskService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="Reorder Burndown", methodology="scrum")
    )
    await _reorder_so_in_review_is_last(session, project.id)

    sprint = Sprint(
        project_id=project.id,
        name="Sprint 1",
        status="active",
        start_date=datetime.now(UTC) - timedelta(days=1),
        end_date=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(sprint)
    await session.flush()

    task_service = TaskService(session)
    created = await task_service.create_task(
        tenant.id,
        project.id,
        TaskCreate(title="In review task", estimation_points=3, sprint_id=sprint.id),
    )
    # Move the task to the NEW last column ("In Review") via the service layer
    # (board_column_id explicit) — completed_at should stamp because it is now
    # the done column post-reorder.
    from app.modules.tasks.schemas import TaskUpdate

    board = await task_service.repo.get(tenant.id, created.id)
    assert board is not None
    from app.modules.boards.service import BoardService

    board_obj = await BoardService(session).get_board(project.id)
    assert board_obj is not None
    in_review_column = next(
        c for c in board_obj.columns if c.status_key == "In Review"
    )
    await task_service.update_task(
        tenant.id, created.id, TaskUpdate(status="In Review")
    )

    result = await SprintService(session).burndown(tenant.id, project.id, sprint.id)
    assert result["completed_tasks"] == 1
    assert in_review_column.status_key == "In Review"


# ---------------------------------------------------------------------------
# T18 — list_projects batches board columns (no N+1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_batches_board_columns_without_n_plus_one(
    session: AsyncSession, engine: AsyncEngine, tenant: Organization
) -> None:
    """list_projects issues a constant number of SELECTs regardless of project count."""

    from sqlalchemy import event

    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    service = ProjectService(session)
    for i in range(5):
        await service.create_project(
            tenant.id, ProjectCreate(name=f"Batch Project {i}", methodology="kanban")
        )

    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        projects, total = await service.list_projects(tenant.id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)

    assert total == 5
    selects = [s for s in statements if s.strip().upper().startswith("SELECT")]
    # 1 (projects list) + 1 (boards batch) + 1 (columns batch) = 3, independent of N.
    assert len(selects) == 3, f"Expected 3 SELECTs, got {len(selects)}:\n" + "\n".join(
        selects
    )
