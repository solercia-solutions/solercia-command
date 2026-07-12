"""Tests for the task_links module (change 04, Batch C).

R8 enlazar mismo proyecto · R9 prevención de ciclos · R10 desenlazar/listar ·
R11 estado de bloqueo en detalle. Uses the shared in-process fixtures
(``client``/``tenant``/``user``).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str, name: str = "Links Project") -> str:
    response = await client.post(
        "/projects",
        json={"name": name, "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _create_task(client: AsyncClient, token: str, project_id: str, title: str) -> str:
    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": title},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _link(
    client: AsyncClient, token: str, task_id: str, related_task_id: str, type_: str = "blocks"
):
    return await client.post(
        f"/tasks/{task_id}/dependencies",
        json={"related_task_id": related_task_id, "type": type_},
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# T10 — model constraint: UNIQUE(blocker_task_id, blocked_task_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_duplicate_edge_violates_unique_constraint(
    session: AsyncSession, tenant: Organization
) -> None:
    """Two rows with the exact same (blocker, blocked) pair violate the DB constraint."""

    from app.modules.projects.models import Project
    from app.modules.task_links.models import TaskDependency
    from app.modules.tasks.models import Task

    project = Project(
        organization_id=tenant.id, name="Constraint Project", methodology="kanban",
        code="CST1",
    )
    session.add(project)
    await session.flush()

    task_a = Task(project_id=project.id, title="A", status="Backlog")
    task_b = Task(project_id=project.id, title="B", status="Backlog")
    session.add_all([task_a, task_b])
    await session.flush()

    session.add(
        TaskDependency(
            organization_id=tenant.id, blocker_task_id=task_a.id, blocked_task_id=task_b.id
        )
    )
    await session.flush()

    session.add(
        TaskDependency(
            organization_id=tenant.id, blocker_task_id=task_a.id, blocked_task_id=task_b.id
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


# ---------------------------------------------------------------------------
# T11 — RED+GREEN: link exige mismo proyecto; rechaza auto-lazo y distintos (R8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_link_two_tasks_same_project_succeeds(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Linking 'A is_blocked_by B' succeeds; both tasks expose the relation."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    response = await _link(client, token, task_a, task_b, "is_blocked_by")

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["direction"] == "is_blocked_by"
    assert body["related_task_id"] == task_b


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_link_task_to_itself_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A task cannot depend on itself."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")

    response = await _link(client, token, task_a, task_a)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "dependency_self_loop"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_link_tasks_of_different_projects_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Linking two tasks from different projects is rejected."""

    _, token = user
    project_1 = await _create_project(client, token, "Project 1")
    project_2 = await _create_project(client, token, "Project 2")
    task_in_1 = await _create_task(client, token, project_1, "In project 1")
    task_in_2 = await _create_task(client, token, project_2, "In project 2")

    response = await _link(client, token, task_in_1, task_in_2)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "dependency_project_mismatch"


# ---------------------------------------------------------------------------
# T12/T13/T14 — cycle prevention: direct and transitive (R9)
# ---------------------------------------------------------------------------


class TestDetectsCycleUnit:
    """Pure unit tests for the DFS cycle detector — no DB needed."""

    def test_no_edges_never_detects_a_cycle(self) -> None:
        from app.modules.task_links.service import detects_cycle

        a, b = uuid.uuid4(), uuid.uuid4()
        assert detects_cycle([], a, b) is False

    def test_direct_cycle_is_detected(self) -> None:
        """Existing edge B->A (B blocks A); inserting A->B closes a direct cycle."""

        from app.modules.task_links.service import detects_cycle

        a, b = uuid.uuid4(), uuid.uuid4()
        edges = [(b, a)]  # B blocks A

        assert detects_cycle(edges, a, b) is True

    def test_transitive_cycle_is_detected(self) -> None:
        """Existing chain C->B->A; inserting A->C closes a transitive cycle."""

        from app.modules.task_links.service import detects_cycle

        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        edges = [(c, b), (b, a)]  # C blocks B, B blocks A

        assert detects_cycle(edges, a, c) is True

    def test_unrelated_edges_do_not_trigger_false_positive(self) -> None:
        from app.modules.task_links.service import detects_cycle

        a, b, x, y = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        edges = [(x, y)]  # unrelated edge

        assert detects_cycle(edges, a, b) is False


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_direct_cycle_via_api_is_422_with_cycle_code(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """'A is_blocked_by B' then 'B is_blocked_by A' -> 422 dependency_cycle."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    first = await _link(client, token, task_a, task_b, "is_blocked_by")
    assert first.status_code == 201, first.text

    second = await _link(client, token, task_b, task_a, "is_blocked_by")

    assert second.status_code == 422, second.text
    assert second.json()["code"] == "dependency_cycle"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_transitive_cycle_via_api_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """'A is_blocked_by B' + 'B is_blocked_by C' then 'C is_blocked_by A' -> 422."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")
    task_c = await _create_task(client, token, project_id, "C")

    assert (await _link(client, token, task_a, task_b, "is_blocked_by")).status_code == 201
    assert (await _link(client, token, task_b, task_c, "is_blocked_by")).status_code == 201

    response = await _link(client, token, task_c, task_a, "is_blocked_by")

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "dependency_cycle"


# ---------------------------------------------------------------------------
# T15 — RED+GREEN: direction inversion for type=is_blocked_by
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_type_is_blocked_by_inverts_before_persisting(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """'A is_blocked_by B' makes B the blocker: B's listing reports 'blocks' A."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    await _link(client, token, task_a, task_b, "is_blocked_by")

    a_listing = await client.get(f"/tasks/{task_a}/dependencies", headers=_auth(token))
    b_listing = await client.get(f"/tasks/{task_b}/dependencies", headers=_auth(token))

    assert a_listing.json()["data"][0]["direction"] == "is_blocked_by"
    assert a_listing.json()["data"][0]["related_task_id"] == task_b
    assert b_listing.json()["data"][0]["direction"] == "blocks"
    assert b_listing.json()["data"][0]["related_task_id"] == task_a


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_type_blocks_does_not_invert(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """'A blocks B' (default type) keeps A as the blocker verbatim."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    await _link(client, token, task_a, task_b, "blocks")

    a_listing = await client.get(f"/tasks/{task_a}/dependencies", headers=_auth(token))
    assert a_listing.json()["data"][0]["direction"] == "blocks"
    assert a_listing.json()["data"][0]["related_task_id"] == task_b


# ---------------------------------------------------------------------------
# T16 — RED+GREEN: unlink = soft delete; listado bidireccional (R10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_is_bidirectional(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Linking 'A is_blocked_by B' shows on BOTH A's and B's listings (R10)."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    await _link(client, token, task_a, task_b, "is_blocked_by")

    a_listing = await client.get(f"/tasks/{task_a}/dependencies", headers=_auth(token))
    b_listing = await client.get(f"/tasks/{task_b}/dependencies", headers=_auth(token))

    assert a_listing.json()["meta"]["total"] == 1
    assert b_listing.json()["meta"]["total"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unlink_removes_edge_from_both_listings(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Deleting the edge unlinks it from BOTH tasks' listings (soft delete, never hard)."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    created = await _link(client, token, task_a, task_b, "is_blocked_by")
    dependency_id = created.json()["data"]["id"]

    delete_response = await client.delete(
        f"/tasks/{task_a}/dependencies/{dependency_id}", headers=_auth(token)
    )
    assert delete_response.status_code == 204, delete_response.text

    a_listing = await client.get(f"/tasks/{task_a}/dependencies", headers=_auth(token))
    b_listing = await client.get(f"/tasks/{task_b}/dependencies", headers=_auth(token))
    assert a_listing.json()["meta"]["total"] == 0
    assert b_listing.json()["meta"]["total"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unlink_is_soft_delete_row_still_exists_in_db(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """Unlinking never physically deletes the row — is_active flips to False."""

    from sqlalchemy import select

    from app.modules.task_links.models import TaskDependency

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")

    created = await _link(client, token, task_a, task_b, "is_blocked_by")
    dependency_id = created.json()["data"]["id"]

    await client.delete(
        f"/tasks/{task_a}/dependencies/{dependency_id}", headers=_auth(token)
    )

    result = await session.execute(
        select(TaskDependency).where(TaskDependency.id == uuid.UUID(dependency_id))
    )
    row = result.scalar_one()
    assert row.is_active is False
    assert row.deleted_at is not None


# ---------------------------------------------------------------------------
# T18 — GREEN: router pagination contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """No pagination params -> full collection, meta is exactly {total}."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")
    task_c = await _create_task(client, token, project_id, "C")

    await _link(client, token, task_a, task_b, "is_blocked_by")
    await _link(client, token, task_a, task_c, "is_blocked_by")

    response = await client.get(f"/tasks/{task_a}/dependencies", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"total": 2}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependencies_page_and_size_returns_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """``?page=1&size=1`` returns a single-edge slice with page metadata."""

    _, token = user
    project_id = await _create_project(client, token)
    task_a = await _create_task(client, token, project_id, "A")
    task_b = await _create_task(client, token, project_id, "B")
    task_c = await _create_task(client, token, project_id, "C")

    await _link(client, token, task_a, task_b, "is_blocked_by")
    await _link(client, token, task_a, task_c, "is_blocked_by")

    response = await client.get(
        f"/tasks/{task_a}/dependencies",
        params={"page": 1, "size": 1},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) == 1
    assert body["meta"] == {"page": 1, "size": 1, "total": 2}
