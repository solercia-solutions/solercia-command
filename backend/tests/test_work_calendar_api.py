"""HTTP contract tests for the work-calendar endpoints (change
28-calendario-laboral, tasks.md T3.1-T3.13).

- ``GET/PUT /organizations/me/work-calendar`` — company calendar; ``GET``
  open to any member, ``PUT`` requires RBAC ``ADMIN`` (same gate as
  ``/organizations/me/theme``).
- ``GET/PUT /projects/{id}/work-calendar`` — root-project override; ``GET``
  open, ``PUT`` requires membership ``admin``/``manager`` and ONLY succeeds
  on a root project (``override_requires_root`` 422 otherwise).
- ``GET /projects/{id}/work-calendar/resolved`` — effective calendar at any
  depth, ``source`` in the PUBLIC wire values (``team``/``organization``/
  ``default``).

Tenant scope is ALWAYS resolved from the JWT membership (organization
endpoints) or scoped by ``organization_id`` (project endpoints) — asserted
here via ``two_orgs``/cross-tenant 404s, same convention as the rest of the
suite.
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
    client: AsyncClient,
    token: str,
    name: str,
    *,
    parent_project_id: str | None = None,
) -> dict:
    payload: dict = {"name": name, "methodology": "planner"}
    if parent_project_id is not None:
        payload["parent_project_id"] = parent_project_id
    response = await client.post("/projects", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# Calendario de empresa — GET abierto, PUT solo ADMIN (RBAC)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_organization_work_calendar_returns_defaults_for_a_new_org(
    client: AsyncClient, user
) -> None:
    _, token = user
    response = await client.get(
        "/organizations/me/work-calendar", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert float(data["working_hours_per_day"]) == 8
    assert data["working_days"] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_organization_work_calendar_as_admin_persists_new_values(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)

    put_response = await client.put(
        "/organizations/me/work-calendar",
        json={"working_hours_per_day": 10, "working_days": [6, 7]},
        headers=_auth(two_orgs.a.token),
    )
    assert put_response.status_code == 200, put_response.text

    get_response = await client.get(
        "/organizations/me/work-calendar", headers=_auth(two_orgs.a.token)
    )
    assert get_response.status_code == 200, get_response.text
    data = get_response.json()["data"]
    assert float(data["working_hours_per_day"]) == 10
    assert data["working_days"] == [6, 7]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_organization_work_calendar_rejected_for_non_admin(
    client: AsyncClient, session: AsyncSession, tenant: Organization, make_member
) -> None:
    for role in (MemberRole.manager, MemberRole.member, MemberRole.viewer):
        _, token = await make_member(session, tenant, role)

        response = await client.put(
            "/organizations/me/work-calendar",
            json={"working_hours_per_day": 10, "working_days": [6, 7]},
            headers=_auth(token),
        )
        assert response.status_code == 403, response.text

    get_response = await client.get(
        "/organizations/me/work-calendar", headers=_auth(token)
    )
    assert float(get_response.json()["data"]["working_hours_per_day"]) == 8


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_organization_work_calendar_validation_rejects_out_of_range(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    token = two_orgs.a.token

    invalid_payloads = [
        {"working_hours_per_day": 0, "working_days": [1, 2]},
        {"working_hours_per_day": 25, "working_days": [1, 2]},
        {"working_hours_per_day": 8, "working_days": []},
        {"working_hours_per_day": 8, "working_days": [1, 1, 2]},
    ]
    for payload in invalid_payloads:
        response = await client.put(
            "/organizations/me/work-calendar", json=payload, headers=_auth(token)
        )
        assert response.status_code == 422, response.text

    get_response = await client.get(
        "/organizations/me/work-calendar", headers=_auth(token)
    )
    data = get_response.json()["data"]
    assert float(data["working_hours_per_day"]) == 8
    assert data["working_days"] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Override de proyecto raíz — GET abierto, PUT admin/manager, solo raíz
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_work_calendar_root_exposes_raw_override_and_child_is_always_null(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    token = two_orgs.a.token

    root = await _create_project(client, token, "Soporte")
    put_response = await client.put(
        f"/projects/{root['id']}/work-calendar",
        json={"working_hours_per_day": 6, "working_days": [6, 7]},
        headers=_auth(token),
    )
    assert put_response.status_code == 200, put_response.text

    root_get = await client.get(
        f"/projects/{root['id']}/work-calendar", headers=_auth(token)
    )
    assert root_get.status_code == 200, root_get.text
    root_data = root_get.json()["data"]
    assert float(root_data["working_hours_per_day"]) == 6
    assert root_data["working_days"] == [6, 7]

    child = await _create_project(
        client, token, "Hijo de Soporte", parent_project_id=root["id"]
    )
    child_get = await client.get(
        f"/projects/{child['id']}/work-calendar", headers=_auth(token)
    )
    assert child_get.status_code == 200, child_get.text
    child_data = child_get.json()["data"]
    assert child_data["working_hours_per_day"] is None
    assert child_data["working_days"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_project_work_calendar_as_manager_persists_override_on_root(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    root = await _create_project(client, owner_token, "Raíz Manager")

    _, manager_token = await make_member(session, tenant, MemberRole.manager)
    response = await client.put(
        f"/projects/{root['id']}/work-calendar",
        json={"working_hours_per_day": 8, "working_days": [1, 2, 3, 4, 5, 6, 7]},
        headers=_auth(manager_token),
    )
    assert response.status_code == 200, response.text

    get_response = await client.get(
        f"/projects/{root['id']}/work-calendar", headers=_auth(owner_token)
    )
    data = get_response.json()["data"]
    assert float(data["working_hours_per_day"]) == 8
    assert data["working_days"] == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_project_work_calendar_on_non_root_is_rejected(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    root = await _create_project(client, owner_token, "Raíz No-Raíz Test")
    child = await _create_project(
        client, owner_token, "Hijo No-Raíz Test", parent_project_id=root["id"]
    )
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    response = await client.put(
        f"/projects/{child['id']}/work-calendar",
        json={"working_hours_per_day": 8, "working_days": [1, 2]},
        headers=_auth(manager_token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "override_requires_root"

    get_response = await client.get(
        f"/projects/{child['id']}/work-calendar", headers=_auth(owner_token)
    )
    assert get_response.json()["data"]["working_hours_per_day"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_project_work_calendar_null_clears_override_back_to_inherit(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    root = await _create_project(client, owner_token, "Raíz Limpiar Override")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    set_response = await client.put(
        f"/projects/{root['id']}/work-calendar",
        json={"working_hours_per_day": 6, "working_days": [6, 7]},
        headers=_auth(manager_token),
    )
    assert set_response.status_code == 200, set_response.text

    clear_response = await client.put(
        f"/projects/{root['id']}/work-calendar",
        json={"working_hours_per_day": None, "working_days": None},
        headers=_auth(manager_token),
    )
    assert clear_response.status_code == 200, clear_response.text

    get_response = await client.get(
        f"/projects/{root['id']}/work-calendar", headers=_auth(owner_token)
    )
    data = get_response.json()["data"]
    assert data["working_hours_per_day"] is None
    assert data["working_days"] is None

    resolved_response = await client.get(
        f"/projects/{root['id']}/work-calendar/resolved", headers=_auth(owner_token)
    )
    resolved_data = resolved_response.json()["data"]
    assert resolved_data["source"] == "organization"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_project_work_calendar_rejected_for_member(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    root = await _create_project(client, owner_token, "Raíz Rechazo Member")

    for role in (MemberRole.member, MemberRole.viewer):
        _, token = await make_member(session, tenant, role)
        response = await client.put(
            f"/projects/{root['id']}/work-calendar",
            json={"working_hours_per_day": 8, "working_days": [1, 2]},
            headers=_auth(token),
        )
        assert response.status_code == 403, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_project_work_calendar_validation_rejects_out_of_range(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    _, owner_token = user
    root = await _create_project(client, owner_token, "Raíz Validación")
    _, manager_token = await make_member(session, tenant, MemberRole.manager)

    for payload in (
        {"working_hours_per_day": 25, "working_days": [1, 2]},
        {"working_hours_per_day": 8, "working_days": [1, 1, 2]},
    ):
        response = await client.put(
            f"/projects/{root['id']}/work-calendar",
            json=payload,
            headers=_auth(manager_token),
        )
        assert response.status_code == 422, response.text

    get_response = await client.get(
        f"/projects/{root['id']}/work-calendar", headers=_auth(owner_token)
    )
    assert get_response.json()["data"]["working_hours_per_day"] is None


# ---------------------------------------------------------------------------
# Calendario resuelto — cualquier profundidad, aislamiento de tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_work_calendar_resolved_returns_team_source_for_a_grandchild(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    token = two_orgs.a.token

    root = await _create_project(client, token, "Soporte Resuelto")
    await client.put(
        f"/projects/{root['id']}/work-calendar",
        json={"working_hours_per_day": 6, "working_days": [6, 7]},
        headers=_auth(token),
    )
    child = await _create_project(
        client, token, "Atención Resuelto", parent_project_id=root["id"]
    )
    grandchild = await _create_project(
        client, token, "Turno Resuelto", parent_project_id=child["id"]
    )

    response = await client.get(
        f"/projects/{grandchild['id']}/work-calendar/resolved", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert float(data["working_hours_per_day"]) == 6
    assert data["working_days"] == [6, 7]
    assert data["source"] == "team"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_work_calendar_resolved_falls_back_to_organization_source(
    client: AsyncClient, user
) -> None:
    _, token = user
    root = await _create_project(client, token, "Raíz Sin Override Resuelto")
    child = await _create_project(
        client, token, "Hijo Sin Override Resuelto", parent_project_id=root["id"]
    )

    response = await client.get(
        f"/projects/{child['id']}/work-calendar/resolved", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["source"] == "organization"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_work_calendar_resolved_cross_tenant_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get(
        f"/projects/{two_orgs.b.project.id}/work-calendar/resolved",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404
