"""Tests for the boards module: model constraints, seeding and the board GET endpoint.

Batch A (change 03-boards-persistentes): Board/BoardColumn persistence, seeded
from ``strategy.default_columns()`` at project-creation time (boards.md R1,
R2). See design.md D1-D2.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project_row(
    session: AsyncSession, tenant: Organization, methodology: str, code: str
):
    from app.modules.projects.models import Project

    project = Project(
        organization_id=tenant.id,
        name=f"{methodology.title()} Project",
        methodology=methodology,
        code=code,
    )
    session.add(project)
    await session.flush()
    return project


# ---------------------------------------------------------------------------
# T01 — model constraints (Board unique per project; BoardColumn requires
# name/status_key; UNIQUE(board_id, status_key))
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_board_is_unique_per_project(
    session: AsyncSession, tenant: Organization
) -> None:
    """A second Board for the same project_id violates the UNIQUE constraint."""

    from app.modules.boards.models import Board

    project = await _create_project_row(session, tenant, "kanban", "UNQ1")

    session.add(Board(project_id=project.id))
    await session.flush()

    session.add(Board(project_id=project.id))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_board_column_status_key_is_unique_per_board(
    session: AsyncSession, tenant: Organization
) -> None:
    """Two columns of the same board cannot share a status_key."""

    from app.modules.boards.models import Board, BoardColumn

    project = await _create_project_row(session, tenant, "kanban", "UNQ2")
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()

    session.add(
        BoardColumn(board_id=board.id, name="Backlog", status_key="backlog", order=0)
    )
    await session.flush()

    session.add(
        BoardColumn(
            board_id=board.id, name="Backlog otra vez", status_key="backlog", order=1
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_board_column_requires_name(
    session: AsyncSession, tenant: Organization
) -> None:
    """A BoardColumn without a name violates the NOT NULL constraint."""

    from app.modules.boards.models import Board, BoardColumn

    project = await _create_project_row(session, tenant, "kanban", "REQ1")
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()

    session.add(
        BoardColumn(board_id=board.id, name=None, status_key="backlog", order=0)  # type: ignore[arg-type]
    )
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_board_column_requires_status_key(
    session: AsyncSession, tenant: Organization
) -> None:
    """A BoardColumn without a status_key violates the NOT NULL constraint."""

    from app.modules.boards.models import Board, BoardColumn

    project = await _create_project_row(session, tenant, "kanban", "REQ2")
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()

    session.add(
        BoardColumn(board_id=board.id, name="Backlog", status_key=None, order=0)  # type: ignore[arg-type]
    )
    with pytest.raises(IntegrityError):
        await session.flush()


# ---------------------------------------------------------------------------
# T04 — create_project seeds the board (service layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_seeds_board_with_default_columns_in_order(
    session: AsyncSession, tenant: Organization
) -> None:
    """Creating a kanban project persists a Board with [Backlog, Doing, Done] in order."""

    from app.modules.boards.service import BoardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    service = ProjectService(session)
    project = await service.create_project(
        tenant.id, ProjectCreate(name="Kanban Project", methodology="kanban")
    )

    board = await BoardService(session).get_board(project.id)
    assert board is not None
    assert [c.name for c in board.columns] == ["Backlog", "Doing", "Done"]
    assert [c.status_key for c in board.columns] == ["Backlog", "Doing", "Done"]
    assert [c.order for c in board.columns] == [0, 1, 2]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_project_custom_methodology_seeds_empty_board(
    session: AsyncSession, tenant: Organization
) -> None:
    """Creating a custom project persists a Board with zero columns."""

    from app.modules.boards.service import BoardService
    from app.modules.projects.schemas import ProjectCreate
    from app.modules.projects.service import ProjectService

    service = ProjectService(session)
    project = await service.create_project(
        tenant.id, ProjectCreate(name="Custom Project", methodology="custom")
    )

    board = await BoardService(session).get_board(project.id)
    assert board is not None
    assert board.columns == []


# ---------------------------------------------------------------------------
# T09 — GET /projects/{id}/board is verbatim for every methodology
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize(
    ("methodology", "expected_columns"),
    [
        ("planner", ["Sin iniciar", "En curso", "Completada"]),
        ("kanban", ["Backlog", "Doing", "Done"]),
        ("scrum", ["To Do", "In Progress", "In Review", "Done"]),
        ("custom", []),
    ],
)
async def test_get_project_board_verbatim_by_methodology(
    client: AsyncClient,
    tenant: Organization,
    user: tuple[User, str],
    methodology: str,
    expected_columns: list[str],
) -> None:
    """GET /projects/{id}/board returns the seeded columns verbatim, in order."""

    _, token = user
    create_response = await client.post(
        "/projects",
        json={
            "name": f"{methodology.title()} Board Project",
            "methodology": methodology,
        },
        headers=_auth(token),
    )
    assert create_response.status_code == 201, create_response.text
    project_id = create_response.json()["data"]["id"]

    response = await client.get(f"/projects/{project_id}/board", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["project_id"] == project_id
    assert [c["name"] for c in body["columns"]] == expected_columns
    assert [c["status_key"] for c in body["columns"]] == expected_columns


# ---------------------------------------------------------------------------
# T37 — ensure_board self-heals legacy projects with no board (GET endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_board_self_heals_legacy_project_without_board(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """A project created without going through ProjectService (no board seeded)
    still returns 200 from GET /projects/{id}/board — ensure_board lazily
    seeds it from the project's methodology instead of 404ing (design.md D4).
    """

    _, token = user
    project = await _create_project_row(session, tenant, "kanban", "LEGACY")

    response = await client.get(f"/projects/{project.id}/board", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert [c["status_key"] for c in body["columns"]] == ["Backlog", "Doing", "Done"]
