"""Tests for move_to_column: WIP enforcement and the PATCH /tasks/{id}/column
endpoint (change 03-boards-persistentes, Batch C).

Covers boards.md "Límite WIP al mover tareas" (R6) and tasks.md delta
"Estado validado por metodología" (R7): a canonical column-id move and the
existing status-string PATCH share the SAME WIP-enforcing code path.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.shared.exceptions import AppException
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T19 — WIP counting: lock -> count -> conditional write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_move_to_column_rejects_when_wip_limit_reached(
    session: AsyncSession, tenant: Organization
) -> None:
    """A 3rd task into a wip_limit=2 column is rejected with 409."""

    from app.modules.boards.service import BoardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService
    from app.modules.tasks.schemas import TaskCreate
    from app.modules.tasks.service import TaskService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="WIP Project", methodology="kanban")
    )
    board_service = BoardService(session)
    board = await board_service.get_board(project.id)
    assert board is not None
    doing = next(c for c in board.columns if c.status_key == "Doing")
    doing.wip_limit = 2
    await session.flush()

    task_service = TaskService(session)
    created = [
        await task_service.create_task(tenant.id, project.id, TaskCreate(title=f"T{i}"))
        for i in range(3)
    ]
    tasks = [await task_service.repo.get(tenant.id, t.id) for t in created]
    assert all(t is not None for t in tasks)

    await board_service.move_to_column(tasks[0], doing, actor_id=None)
    await board_service.move_to_column(tasks[1], doing, actor_id=None)

    with pytest.raises(AppException) as exc_info:
        await board_service.move_to_column(tasks[2], doing, actor_id=None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "wip_limit_exceeded"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_move_to_column_ignores_null_wip_limit(
    session: AsyncSession, tenant: Organization
) -> None:
    """A column with wip_limit=None never rejects a move, regardless of count."""

    from app.modules.boards.service import BoardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService
    from app.modules.tasks.schemas import TaskCreate
    from app.modules.tasks.service import TaskService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="No WIP Project", methodology="kanban")
    )
    board_service = BoardService(session)
    board = await board_service.get_board(project.id)
    assert board is not None
    doing = next(c for c in board.columns if c.status_key == "Doing")
    assert doing.wip_limit is None

    task_service = TaskService(session)
    created = [
        await task_service.create_task(tenant.id, project.id, TaskCreate(title=f"U{i}"))
        for i in range(5)
    ]
    tasks = [await task_service.repo.get(tenant.id, t.id) for t in created]

    for task in tasks:
        assert task is not None
        moved = await board_service.move_to_column(task, doing, actor_id=None)
        assert moved.board_column_id == doing.id


# ---------------------------------------------------------------------------
# T21/T22 — PATCH /tasks/{id}/column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_tasks_column_moves_and_derives_status(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    create_response = await client.post(
        "/projects", json={"name": "Move Kanban", "methodology": "kanban"}, headers=_auth(token)
    )
    project_id = create_response.json()["data"]["id"]
    task_response = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "Move me"}, headers=_auth(token)
    )
    task_id = task_response.json()["data"]["id"]

    board_response = await client.get(f"/projects/{project_id}/board", headers=_auth(token))
    doing_column = next(
        c for c in board_response.json()["data"]["columns"] if c["status_key"] == "Doing"
    )

    response = await client.patch(
        f"/tasks/{task_id}/column",
        json={"board_column_id": doing_column["id"]},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    task = response.json()["data"]
    assert task["board_column_id"] == doing_column["id"]
    assert task["status"] == "Doing"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_tasks_column_invalid_column_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    create_response = await client.post(
        "/projects",
        json={"name": "Move Kanban Invalid", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = create_response.json()["data"]["id"]
    task_response = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "Move me"}, headers=_auth(token)
    )
    task_id = task_response.json()["data"]["id"]

    response = await client.patch(
        f"/tasks/{task_id}/column",
        json={"board_column_id": str(uuid.uuid4())},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_board_column"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_tasks_column_rejects_column_not_on_this_project_board(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A planner board has no 'In Review' column — targeting a foreign one 422s (R7)."""

    _, token = user
    planner_response = await client.post(
        "/projects",
        json={"name": "Planner No Review", "methodology": "planner"},
        headers=_auth(token),
    )
    planner_id = planner_response.json()["data"]["id"]
    task_response = await client.post(
        f"/projects/{planner_id}/tasks", json={"title": "Planner Task"}, headers=_auth(token)
    )
    task_id = task_response.json()["data"]["id"]

    scrum_response = await client.post(
        "/projects",
        json={"name": "Scrum With Review", "methodology": "scrum"},
        headers=_auth(token),
    )
    scrum_id = scrum_response.json()["data"]["id"]
    scrum_board = await client.get(f"/projects/{scrum_id}/board", headers=_auth(token))
    in_review_column_id = next(
        c for c in scrum_board.json()["data"]["columns"] if c["status_key"] == "In Review"
    )["id"]

    response = await client.patch(
        f"/tasks/{task_id}/column",
        json={"board_column_id": in_review_column_id},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_board_column"


# ---------------------------------------------------------------------------
# T23 — PATCH /tasks/{id} status field shares the SAME WIP path as /column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_task_status_field_enforces_same_wip_limit_as_column_move(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    create_response = await client.post(
        "/projects",
        json={"name": "Status WIP Kanban", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = create_response.json()["data"]["id"]

    from app.modules.boards.service import BoardService

    board = await BoardService(session).get_board(uuid.UUID(project_id))
    assert board is not None
    doing = next(c for c in board.columns if c.status_key == "Doing")
    doing.wip_limit = 1
    await session.flush()

    t1 = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "T1"}, headers=_auth(token)
    )
    t2 = await client.post(
        f"/projects/{project_id}/tasks", json={"title": "T2"}, headers=_auth(token)
    )

    ok = await client.patch(
        f"/tasks/{t1.json()['data']['id']}", json={"status": "Doing"}, headers=_auth(token)
    )
    assert ok.status_code == 200, ok.text

    rejected = await client.patch(
        f"/tasks/{t2.json()['data']['id']}", json={"status": "Doing"}, headers=_auth(token)
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "wip_limit_exceeded"


# ---------------------------------------------------------------------------
# T24 — 2 -> 3 accepted at wip_limit=3 (not yet at the boundary); concurrent
# movers into the SAME column serialize via the row lock (real, separate
# connections/transactions — the shared SAVEPOINT `session` fixture cannot
# exercise real Postgres row-lock concurrency).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_move_to_column_accepts_third_task_at_wip_limit_three(
    session: AsyncSession, tenant: Organization
) -> None:
    """2 tasks already in a wip_limit=3 column; a 3rd is accepted (below the limit)."""

    from app.modules.boards.service import BoardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService
    from app.modules.tasks.schemas import TaskCreate
    from app.modules.tasks.service import TaskService

    project = await ProjectService(session).create_project(
        tenant.id, ProjectCreate(name="WIP Three Project", methodology="kanban")
    )
    board_service = BoardService(session)
    board = await board_service.get_board(project.id)
    assert board is not None
    doing = next(c for c in board.columns if c.status_key == "Doing")
    doing.wip_limit = 3
    await session.flush()

    task_service = TaskService(session)
    created = [
        await task_service.create_task(tenant.id, project.id, TaskCreate(title=f"T{i}"))
        for i in range(3)
    ]
    tasks = [await task_service.repo.get(tenant.id, t.id) for t in created]
    assert all(t is not None for t in tasks)

    await board_service.move_to_column(tasks[0], doing, actor_id=None)
    await board_service.move_to_column(tasks[1], doing, actor_id=None)
    moved_third = await board_service.move_to_column(tasks[2], doing, actor_id=None)
    assert moved_third.board_column_id == doing.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_move_to_column_wip_serializes_concurrent_movers_via_row_lock(
    engine: AsyncEngine,
) -> None:
    """Two REAL concurrent transactions racing into a wip_limit=1 column:

    exactly one succeeds and the other gets 409 — the row lock on the target
    column serializes them so neither reads a stale count. Uses two
    independent connections (not the shared SAVEPOINT `session` fixture):
    real row-lock serialization only exists across genuinely separate
    Postgres transactions.
    """

    import asyncio

    task1_id: uuid.UUID
    task2_id: uuid.UUID

    setup_session = AsyncSession(bind=engine, expire_on_commit=False)
    organization = Organization(
        name="Concurrency Org", slug=f"concurrency-{uuid.uuid4().hex[:12]}"
    )
    try:
        from app.modules.boards.service import BoardService
        from app.modules.projects.schemas import ProjectCreate
        from app.modules.projects.service import ProjectService
        from app.modules.tasks.schemas import TaskCreate
        from app.modules.tasks.service import TaskService

        setup_session.add(organization)
        await setup_session.flush()

        project = await ProjectService(setup_session).create_project(
            organization.id, ProjectCreate(name="Concurrency Kanban", methodology="kanban")
        )
        board = await BoardService(setup_session).get_board(project.id)
        assert board is not None
        doing = next(c for c in board.columns if c.status_key == "Doing")
        doing.wip_limit = 1
        await setup_session.flush()

        task_service = TaskService(setup_session)
        t1 = await task_service.create_task(
            organization.id, project.id, TaskCreate(title="Racer 1")
        )
        t2 = await task_service.create_task(
            organization.id, project.id, TaskCreate(title="Racer 2")
        )
        await setup_session.commit()

        task1_id, task2_id = t1.id, t2.id
        organization_id, doing_column_id = organization.id, doing.id

        async def _mover(task_id: uuid.UUID) -> str:
            async with AsyncSession(bind=engine, expire_on_commit=False) as mover_session:
                mover_service = TaskService(mover_session)
                try:
                    await mover_service.move_task_column(
                        organization_id, task_id, doing_column_id, actor_id=None
                    )
                    return "ok"
                except AppException as exc:
                    return exc.code

        results = await asyncio.gather(_mover(task1_id), _mover(task2_id))
        assert sorted(results) == ["ok", "wip_limit_exceeded"]
    finally:
        await setup_session.execute(
            text("DELETE FROM organizations WHERE id = :id"),
            {"id": str(organization.id)},
        )
        await setup_session.commit()
        await setup_session.close()
