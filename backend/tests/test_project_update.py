"""Tests for PATCH /projects/{project_id} (edit name/description/code).

The endpoint shares the reparent write guard (admin/manager, R7) and the
create flow's duplicate-code contract (409 ``project_code_taken``).
``methodology`` is NEVER editable (422 ``methodology_not_editable``): the
seeded board and the task statuses derive from the methodology Strategy.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, name: str, *, code: str | None = None
) -> dict:
    payload: dict = {"name": name, "methodology": "kanban"}
    if code is not None:
        payload["code"] = code
    response = await client.post("/projects", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_name_and_description(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """A manager edits name and description; both persist and are returned."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Original")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"name": "Proyecto Renombrado", "description": "Nueva descripción"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["name"] == "Proyecto Renombrado"
    assert body["description"] == "Nueva descripción"

    fetched = await client.get(f"/projects/{project['id']}", headers=_auth(owner_token))
    assert fetched.json()["data"]["name"] == "Proyecto Renombrado"
    assert fetched.json()["data"]["description"] == "Nueva descripción"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_code_to_free_code(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """Editing ``code`` to a free value succeeds and normalizes to uppercase."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Código", code="PCOD")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"code": "nuevo1"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["code"] == "NUEVO1"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_keeping_own_code_is_not_a_conflict(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """Re-submitting the project's OWN code passes: ``code_exists`` excludes
    the project itself (``exclude_id``), so no false 409."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Mismo", code="MISMO")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"code": "MISMO", "name": "Proyecto Mismo Editado"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["code"] == "MISMO"
    assert response.json()["data"]["name"] == "Proyecto Mismo Editado"


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_duplicate_code_conflict(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """Editing ``code`` to another project's code in the same org raises the
    SAME 409 ``project_code_taken`` the create flow uses."""

    _, owner_token = user
    await _create_project(client, owner_token, "Proyecto Uno", code="UNO1")
    second = await _create_project(client, owner_token, "Proyecto Dos", code="DOS2")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{second['id']}",
        json={"code": "UNO1"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "project_code_taken"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_methodology_not_editable(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """``methodology`` in the payload is rejected with 422
    ``methodology_not_editable`` — the seeded board depends on the strategy."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Metodología")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"methodology": "scrum"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "methodology_not_editable"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_invalid_code_format_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """A code outside ``^[A-Z0-9]{2,10}$`` is rejected by schema validation."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Código Malo")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"code": "x"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Aislamiento y permisos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_cross_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """An admin of org A can never edit org B's project — 404, never 200."""

    response = await client.patch(
        f"/projects/{two_orgs.b.project.id}",
        json={"name": "Intento Cruzado"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "project_not_found"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_update_project(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """A plain ``member`` gets 403 — same write guard as the reparent (R7)."""

    _, owner_token = user
    project = await _create_project(client, owner_token, "Proyecto Restringido")
    _, member_token = await make_member(session, tenant, MemberRole.member)

    response = await client.patch(
        f"/projects/{project['id']}",
        json={"name": "No Deberías Poder"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403
