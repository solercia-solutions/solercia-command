"""Tests for audit stamping (R4) — actor_id threaded router→service→repository.

Representative module: tasks. The same explicit-assignment pattern is
mechanically applied to the other 9 audited modules with services
(projects, sprints, comments, attachments, roles, menus, dependencies,
alert_rules, users — ``organizations`` is excluded, seed-only, no service).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import TaskService
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/projects",
        json={"name": "Audit Stamping Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_post_task_stamps_created_by_and_updated_by_with_actor_id(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /projects/{id}/tasks stamps created_by = updated_by = actor.id."""

    caller, token = user
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Audited task"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    task = response.json()["data"]
    assert task["created_by"] == str(caller.id)
    assert task["updated_by"] == str(caller.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_task_stamps_updated_by_via_http(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """PATCH /tasks/{id} threads actor_id through router→service→repository.

    A distinct-editor scenario (created_by preserved while a DIFFERENT actor
    stamps updated_by) is triangulated at the service layer below — HTTP-only
    tests share a single authenticated caller per request.
    """

    author, token = user
    project_id = await _create_project(client, token)

    create_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Task to edit"},
        headers=_auth(token),
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["data"]["id"]
    assert create_response.json()["data"]["created_by"] == str(author.id)

    patch_response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "Edited title"},
        headers=_auth(token),
    )

    assert patch_response.status_code == 200, patch_response.text
    patched = patch_response.json()["data"]
    assert patched["updated_by"] == str(author.id)
    assert patched["created_by"] == str(author.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_service_layer_patch_stamps_different_editor_preserves_created_by(
    session: AsyncSession, tenant: Organization, user: tuple[User, str]
) -> None:
    """Service-level triangulation: a DIFFERENT actor_id on update only changes updated_by."""

    author, _ = user
    editor = User(
        email="editor-triangulation@example.com",
        primer_nombre="Editor",
        primer_apellido="Triangulation",
        hashed_password="x",
    )
    session.add(editor)
    await session.flush()
    editor_id = editor.id

    service = TaskService(session)
    from app.modules.projects.models import Project

    project = Project(
        organization_id=tenant.id, name="Svc Project", methodology="kanban", code="SVP"
    )
    session.add(project)
    await session.flush()

    created = await service.create_task(
        tenant.id,
        project.id,
        TaskCreate(title="Service-created task"),
        actor_id=author.id,
    )
    assert created.created_by == author.id
    assert created.updated_by == author.id

    from app.modules.tasks.schemas import TaskUpdate

    updated = await service.update_task(
        tenant.id, created.id, TaskUpdate(title="Renamed"), actor_id=editor_id
    )
    assert updated.updated_by == editor_id
    assert updated.created_by == author.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_without_actor_id_leaves_audit_fields_null(
    session: AsyncSession, tenant: Organization
) -> None:
    """A write with no authenticated actor (e.g. the alert scheduler) tolerates None."""

    from app.modules.projects.models import Project

    project = Project(
        organization_id=tenant.id, name="Job Project", methodology="kanban", code="JOB"
    )
    session.add(project)
    await session.flush()

    service = TaskService(session)
    created = await service.create_task(
        tenant.id, project.id, TaskCreate(title="System-created task"), actor_id=None
    )

    assert created.created_by is None
    assert created.updated_by is None

    result = await session.get(Task, created.id)
    assert result is not None
    assert result.created_by is None
