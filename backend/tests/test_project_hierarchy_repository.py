"""Tests for ``ProjectRepository``'s hierarchy CTE methods (change
21-project-hierarchy, tasks.md T1.11): ``ancestor_ids``, ``subtree_height``,
``fetch_subtree`` and ``rollup_progress``.

Every test seeds data directly through the ORM (``session`` SAVEPOINT
fixture) — no HTTP layer involved, matching the codebase's repository-test
convention (e.g. ``BoardRepository`` has no dedicated HTTP-free repository
test file today, but ``TaskRepository``/other module tests use this exact
``session``-only pattern). All of these still require a live Postgres
connection (recursive CTEs + FILTER), hence ``@skip_no_db`` like every other
DB-touching test in this suite.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.factory import get_strategy
from app.modules.boards.service import BoardService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import Task
from app.shared.enums import Methodology
from tests.conftest import skip_no_db


async def _make_project(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    *,
    methodology: Methodology = Methodology.planner,
    parent_project_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> Project:
    project = Project(
        organization_id=organization_id,
        name=name,
        methodology=methodology,
        code=uuid.uuid4().hex[:8].upper(),
        task_counter=0,
        parent_project_id=parent_project_id,
        is_active=is_active,
    )
    session.add(project)
    await session.flush()
    return project


async def _seed_board(session: AsyncSession, project: Project) -> None:
    strategy = get_strategy(project.methodology)
    await BoardService(session).seed_board(project.id, strategy)
    await session.flush()


async def _make_task(
    session: AsyncSession,
    project: Project,
    status: str,
    *,
    is_active: bool = True,
) -> Task:
    task = Task(
        project_id=project.id,
        title=f"Task {uuid.uuid4().hex[:6]}",
        status=status,
        is_active=is_active,
    )
    session.add(task)
    await session.flush()
    return task


# ---------------------------------------------------------------------------
# ancestor_ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ancestor_ids_returns_chain_from_immediate_parent_to_root(
    session: AsyncSession, tenant
) -> None:
    """A -> B -> C: ancestor_ids(C) == [B.id, A.id] (immediate parent first)."""

    root = await _make_project(session, tenant.id, "Root A")
    middle = await _make_project(
        session, tenant.id, "Middle B", parent_project_id=root.id
    )
    leaf = await _make_project(
        session, tenant.id, "Leaf C", parent_project_id=middle.id
    )

    repo = ProjectRepository(session)
    ancestors = await repo.ancestor_ids(tenant.id, leaf.id)

    assert ancestors == [middle.id, root.id]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ancestor_ids_of_a_root_project_is_empty(
    session: AsyncSession, tenant
) -> None:
    """A project with no parent has an empty ancestor chain."""

    root = await _make_project(session, tenant.id, "Lonely Root")

    repo = ProjectRepository(session)
    ancestors = await repo.ancestor_ids(tenant.id, root.id)

    assert ancestors == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ancestor_ids_is_bounded_on_a_pre_existing_cycle(
    session: AsyncSession, tenant
) -> None:
    """Triangulation: a (hypothetical, pre-existing) direct cycle A<->B never
    hangs — the walk is bounded by ``PROJECT_HIERARCHY_MAX_DEPTH`` and
    terminates deterministically instead of looping forever."""

    from app.config import settings

    project_a = await _make_project(session, tenant.id, "Cycle A")
    project_b = await _make_project(
        session, tenant.id, "Cycle B", parent_project_id=project_a.id
    )
    project_a.parent_project_id = project_b.id
    await session.flush()

    repo = ProjectRepository(session)
    ancestors = await repo.ancestor_ids(tenant.id, project_a.id)

    assert len(ancestors) <= settings.PROJECT_HIERARCHY_MAX_DEPTH


# ---------------------------------------------------------------------------
# subtree_height
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_subtree_height_of_a_leaf_is_zero(
    session: AsyncSession, tenant
) -> None:
    leaf = await _make_project(session, tenant.id, "Childless")

    repo = ProjectRepository(session)
    height = await repo.subtree_height(tenant.id, leaf.id)

    assert height == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_subtree_height_of_a_three_level_chain_is_two(
    session: AsyncSession, tenant
) -> None:
    root = await _make_project(session, tenant.id, "Height Root")
    middle = await _make_project(
        session, tenant.id, "Height Middle", parent_project_id=root.id
    )
    await _make_project(
        session, tenant.id, "Height Leaf", parent_project_id=middle.id
    )

    repo = ProjectRepository(session)
    height = await repo.subtree_height(tenant.id, root.id)

    assert height == 2


# ---------------------------------------------------------------------------
# fetch_subtree
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_fetch_subtree_reproduces_a_three_level_hierarchy(
    session: AsyncSession, tenant
) -> None:
    root = await _make_project(session, tenant.id, "Seguridad de la Información")
    child = await _make_project(
        session, tenant.id, "Desarrollo", parent_project_id=root.id
    )
    grandchild = await _make_project(
        session, tenant.id, "Backend", parent_project_id=child.id
    )

    repo = ProjectRepository(session)
    subtree = await repo.fetch_subtree(tenant.id, root.id)

    ids = {project.id for project in subtree}
    assert ids == {root.id, child.id, grandchild.id}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_fetch_subtree_excludes_a_soft_deleted_branch(
    session: AsyncSession, tenant
) -> None:
    """Triangulation: a soft-deleted middle node cuts off its whole branch —
    the recursive step can never join THROUGH a row filtered out by
    ``is_active``, so an active grandchild under an inactive parent is
    excluded too."""

    root = await _make_project(session, tenant.id, "Isolation Root")
    inactive_child = await _make_project(
        session,
        tenant.id,
        "Inactive Child",
        parent_project_id=root.id,
        is_active=False,
    )
    await _make_project(
        session,
        tenant.id,
        "Orphaned Grandchild",
        parent_project_id=inactive_child.id,
    )

    repo = ProjectRepository(session)
    subtree = await repo.fetch_subtree(tenant.id, root.id)

    ids = {project.id for project in subtree}
    assert ids == {root.id}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_fetch_subtree_never_crosses_organization_boundary(
    session: AsyncSession, tenant, second_tenant
) -> None:
    """Defensive filter: even a (hypothetical, out-of-band) cross-tenant
    ``parent_project_id`` edge never lets ``fetch_subtree`` traverse into
    another organization's project."""

    root = await _make_project(session, tenant.id, "Org A Root")
    foreign_child = await _make_project(
        session, second_tenant.id, "Org B Child", parent_project_id=root.id
    )

    repo = ProjectRepository(session)
    subtree = await repo.fetch_subtree(tenant.id, root.id)

    ids = {project.id for project in subtree}
    assert ids == {root.id}
    assert foreign_child.id not in ids


# ---------------------------------------------------------------------------
# rollup_progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rollup_progress_reproduces_the_18_of_20_business_example(
    session: AsyncSession, tenant
) -> None:
    """Sombrilla (no own tasks) with two children: 8/10 (planner) + 10/10
    (scrum) sums to done=18, total=20 across the subtree."""

    umbrella = await _make_project(
        session, tenant.id, "Seguridad de la Información", methodology=Methodology.planner
    )
    await _seed_board(session, umbrella)

    development = await _make_project(
        session,
        tenant.id,
        "Desarrollo",
        methodology=Methodology.planner,
        parent_project_id=umbrella.id,
    )
    await _seed_board(session, development)
    for _ in range(8):
        await _make_task(session, development, "Completada")
    for _ in range(2):
        await _make_task(session, development, "Sin iniciar")

    security = await _make_project(
        session,
        tenant.id,
        "Seguridad",
        methodology=Methodology.scrum,
        parent_project_id=umbrella.id,
    )
    await _seed_board(session, security)
    for _ in range(10):
        await _make_task(session, security, "Done")

    repo = ProjectRepository(session)
    rows = await repo.rollup_progress(tenant.id, umbrella.id)

    total_done = sum(done for _, done, _ in rows)
    total_total = sum(total for _, _, total in rows)
    assert total_done == 18
    assert total_total == 20


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rollup_progress_excludes_cancelled_tasks_from_denominator(
    session: AsyncSession, tenant
) -> None:
    """10 tasks total, 2 cancelled, 5 done -> total=8 (10-2), done=5."""

    project = await _make_project(session, tenant.id, "Cancelled Mix")
    await _seed_board(session, project)
    for _ in range(5):
        await _make_task(session, project, "Completada")
    for _ in range(3):
        await _make_task(session, project, "Sin iniciar")
    for _ in range(2):
        await _make_task(session, project, "cancelled")

    repo = ProjectRepository(session)
    rows = await repo.rollup_progress(tenant.id, project.id)

    row = next(r for r in rows if r[0] == project.id)
    _, done, total = row
    assert done == 5
    assert total == 8
