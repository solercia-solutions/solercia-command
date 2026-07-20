"""Tests for epics as real parents (no subtask coercion for epic children).

A child of an ``epic`` parent KEEPS its requested ``task_type`` (default
``task``; ``story``/``task``/``bug`` allowed — never a nested ``epic``) and
MAY carry ``estimation_points``. The subtask coercion and the points guard
stay intact when the parent is NOT an epic. Nesting rules become: the parent
cannot be a ``subtask`` and an epic can never have a parent.
"""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_scrum_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Epic Hierarchy Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _create_task(
    client: AsyncClient, token: str, project_id: str, payload: dict
) -> dict:
    response = await client.post(
        f"/projects/{project_id}/tasks", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# Hijas de épica conservan tipo y puntos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_story_with_points_under_epic_keeps_type_and_points(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A ``story`` under an ``epic`` keeps its type AND its points — no
    subtask coercion, no ``subtask_points_not_allowed``."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica", "task_type": "epic"}
    )

    story = await _create_task(
        client,
        token,
        project_id,
        {
            "title": "Historia bajo épica",
            "task_type": "story",
            "parent_task_id": epic["id"],
            "estimation_points": 5,
        },
    )

    assert story["task_type"] == "story"
    assert story["estimation_points"] == 5
    assert story["parent_task_id"] == epic["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_child_of_epic_without_type_defaults_to_task(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A child of an epic with no explicit ``task_type`` defaults to ``task``
    (never ``subtask``)."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Default", "task_type": "epic"}
    )

    child = await _create_task(
        client,
        token,
        project_id,
        {"title": "Hija sin tipo", "parent_task_id": epic["id"]},
    )

    assert child["task_type"] == "task"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_epic_under_epic_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """An ``epic`` can never have a parent — nested epics are 422."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Raíz", "task_type": "epic"}
    )

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Épica Anidada",
            "task_type": "epic",
            "parent_task_id": epic["id"],
        },
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "epic_nesting_not_allowed"


# ---------------------------------------------------------------------------
# Anidamiento: subtarea bajo historia-de-épica sí; bajo subtarea no
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_subtask_under_story_hanging_from_epic_is_allowed(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """épica -> historia -> subtarea: the story's own parent being an epic no
    longer blocks creating its subtasks (old rule rejected ANY parent that
    itself had a parent)."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Cadena", "task_type": "epic"}
    )
    story = await _create_task(
        client,
        token,
        project_id,
        {
            "title": "Historia intermedia",
            "task_type": "story",
            "parent_task_id": epic["id"],
        },
    )

    subtask = await _create_task(
        client,
        token,
        project_id,
        {"title": "Subtarea de la historia", "parent_task_id": story["id"]},
    )

    assert subtask["task_type"] == "subtask"
    assert subtask["estimation_points"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_subtask_under_subtask_still_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Regression: a subtask can never be a parent (max one nesting level
    below a non-epic parent)."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    parent = await _create_task(client, token, project_id, {"title": "Tarea Padre"})
    subtask = await _create_task(
        client,
        token,
        project_id,
        {"title": "Subtarea", "parent_task_id": parent["id"]},
    )

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Sub-subtarea", "parent_task_id": subtask["id"]},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "subtask_nesting_not_allowed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_child_of_non_epic_parent_still_coerced_to_subtask(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Regression: under a NON-epic parent the child is still coerced to
    ``subtask`` (its requested type is ignored) and points are still
    rejected."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    parent = await _create_task(client, token, project_id, {"title": "Tarea Normal"})

    rejected = await client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Hija con puntos",
            "task_type": "story",
            "parent_task_id": parent["id"],
            "estimation_points": 3,
        },
        headers=_auth(token),
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "subtask_points_not_allowed"

    coerced = await _create_task(
        client,
        token,
        project_id,
        {
            "title": "Hija sin puntos",
            "task_type": "story",
            "parent_task_id": parent["id"],
        },
    )
    assert coerced["task_type"] == "subtask"


# ---------------------------------------------------------------------------
# update_task: puntos editables en hijas de épica, prohibidos en subtareas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_points_on_story_under_epic_is_allowed(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A story under an epic may UPDATE its points too — the guard applies to
    real ``subtask`` rows, not to every task with a parent."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Update", "task_type": "epic"}
    )
    story = await _create_task(
        client,
        token,
        project_id,
        {
            "title": "Historia editable",
            "task_type": "story",
            "parent_task_id": epic["id"],
            "estimation_points": 3,
        },
    )

    response = await client.patch(
        f"/tasks/{story['id']}",
        json={"estimation_points": 8},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["estimation_points"] == 8


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_points_on_subtask_still_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Regression: a real subtask still cannot receive points via PATCH."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    parent = await _create_task(client, token, project_id, {"title": "Padre Guard"})
    subtask = await _create_task(
        client,
        token,
        project_id,
        {"title": "Subtarea Guard", "parent_task_id": parent["id"]},
    )

    response = await client.patch(
        f"/tasks/{subtask['id']}",
        json={"estimation_points": 5},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "subtask_points_not_allowed"


# ---------------------------------------------------------------------------
# update_task: el guard aplica sobre el tipo EFECTIVO post-patch (ronda 4R)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_flipping_type_to_subtask_with_points_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A combined ``{"task_type": "subtask", "estimation_points": N}`` patch
    can never persist a subtask WITH points — the guard reads the EFFECTIVE
    type, not the pre-mutation one."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    task = await _create_task(client, token, project_id, {"title": "Tarea Flip"})

    response = await client.patch(
        f"/tasks/{task['id']}",
        json={"task_type": "subtask", "estimation_points": 3},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "subtask_points_not_allowed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_flipping_type_to_subtask_keeping_points_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Flipping a task that ALREADY has points to ``subtask`` without
    clearing them would also persist a subtask with points — 422."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    task = await _create_task(
        client, token, project_id,
        {"title": "Tarea Con Puntos", "estimation_points": 5},
    )

    response = await client.patch(
        f"/tasks/{task['id']}",
        json={"task_type": "subtask"},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "subtask_points_not_allowed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_flipping_type_to_subtask_clearing_points_is_allowed(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Flipping to ``subtask`` while EXPLICITLY clearing the points in the
    same patch keeps the invariant and passes."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    task = await _create_task(
        client, token, project_id,
        {"title": "Tarea Que Limpia", "estimation_points": 5},
    )

    response = await client.patch(
        f"/tasks/{task['id']}",
        json={"task_type": "subtask", "estimation_points": None},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["task_type"] == "subtask"
    assert body["estimation_points"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_type_to_epic_on_child_task_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCHing ``task_type`` to ``epic`` on a task that HAS a parent would
    create an epic with a parent — the create invariant holds on update too.
    A top-level task may still become an epic."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Invariante", "task_type": "epic"}
    )
    story = await _create_task(
        client, token, project_id,
        {"title": "Historia Hija", "task_type": "story", "parent_task_id": epic["id"]},
    )

    rejected = await client.patch(
        f"/tasks/{story['id']}",
        json={"task_type": "epic"},
        headers=_auth(token),
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["code"] == "epic_nesting_not_allowed"

    top_level = await _create_task(client, token, project_id, {"title": "Tarea Suelta"})
    promoted = await client.patch(
        f"/tasks/{top_level['id']}",
        json={"task_type": "epic"},
        headers=_auth(token),
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["data"]["task_type"] == "epic"


# ---------------------------------------------------------------------------
# create_task: whitelist de tipos bajo épica (ronda 4R)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_arbitrary_task_type_under_epic_is_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Under an epic parent only task/story/bug/subtask are accepted — an
    arbitrary string is 422 ``invalid_task_type`` (before epics-as-parents
    every child was coerced, so no arbitrary type could ever hang from a
    parent)."""

    _, token = user
    project_id = await _create_scrum_project(client, token)
    epic = await _create_task(
        client, token, project_id, {"title": "Épica Whitelist", "task_type": "epic"}
    )

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Tipo Raro", "task_type": "foo", "parent_task_id": epic["id"]},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_task_type"
