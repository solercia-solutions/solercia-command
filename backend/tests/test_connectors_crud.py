"""Tests for the connectors module — CRUD with RBAC (change 14-integration-ports).

C-R1 Aislamiento multi-tenant · C-R2 CRUD con permisos por rol (`require_role
admin|manager` — PRIMER consumidor real de esta dependencia,
`app/dependencies.py:149`, distinta del RBAC `require_admin` que usa
`assets`) · C-R9 Envelope `{data, message, meta}`. Escrituras: `two_orgs` ya
siembra `role=admin`, así que `create_asset`-style `rbac_admin` NO aplica
aquí — se usa `make_member` para construir un `manager` y un `member`.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# C-R2 — Creación por admin/manager, rechazo para member
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_connector_by_admin_returns_201_with_envelope(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """POST /connectors by an org admin creates the connector, 201, {data, message}."""

    response = await client.post(
        "/connectors",
        json={"provider": "microsoft365", "scopes": ["mail.read"]},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["data"]["provider"] == "microsoft365"
    assert body["data"]["scopes"] == ["mail.read"]
    assert body["data"]["created_by"] == str(two_orgs.a.user.id)
    assert body["data"]["updated_by"] == str(two_orgs.a.user.id)
    assert "message" in body


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_connector_by_manager_also_allowed(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """A `manager` (not just `admin`) may create a connector too."""

    from app.shared.enums import MemberRole

    _, manager_token = await make_member(session, two_orgs.a.organization, MemberRole.manager)

    response = await client.post(
        "/connectors",
        json={"provider": "google"},
        headers=_auth(manager_token),
    )

    assert response.status_code == 201, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_connector_rejected_for_member(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """A `member` (without admin/manager role) gets 403 on POST /connectors."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post(
        "/connectors",
        json={"provider": "glpi"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# C-R2 — Cualquier miembro puede listar/ver conectores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_can_list_connectors_without_admin_or_manager_role(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """GET /connectors succeeds for a plain `member`, no admin/manager role
    required, and returns the {data, meta.total} envelope."""

    from app.shared.enums import MemberRole

    await client.post(
        "/connectors",
        json={"provider": "jira"},
        headers=_auth(two_orgs.a.token),
    )
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get("/connectors", headers=_auth(member_token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["provider"] == "jira"


# ---------------------------------------------------------------------------
# C-R2 — Edición/borrado por admin/manager; borrado es soft-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_connector_by_admin_updates_status(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """PATCH /connectors/{id} by an admin edits the connector's status."""

    created = await client.post(
        "/connectors",
        json={"provider": "microsoft365"},
        headers=_auth(two_orgs.a.token),
    )
    connector_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/connectors/{connector_id}",
        json={"status": "inactive"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "inactive"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_connector_is_soft_delete_and_disappears_from_list(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """DELETE /connectors/{id} soft-deletes; it no longer appears in GET /connectors."""

    created = await client.post(
        "/connectors",
        json={"provider": "microsoft365"},
        headers=_auth(two_orgs.a.token),
    )
    connector_id = created.json()["data"]["id"]

    delete_response = await client.delete(
        f"/connectors/{connector_id}", headers=_auth(two_orgs.a.token)
    )
    assert delete_response.status_code == 204

    list_response = await client.get("/connectors", headers=_auth(two_orgs.a.token))
    assert list_response.json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# C-R1 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connector_of_another_org_returns_404_on_get_patch_delete(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A connector of org A is invisible (404) to org B on GET/PATCH/DELETE."""

    created = await client.post(
        "/connectors",
        json={"provider": "microsoft365"},
        headers=_auth(two_orgs.a.token),
    )
    connector_id = created.json()["data"]["id"]

    get_response = await client.get(
        f"/connectors/{connector_id}", headers=_auth(two_orgs.b.token)
    )
    assert get_response.status_code == 404

    patch_response = await client.patch(
        f"/connectors/{connector_id}",
        json={"status": "inactive"},
        headers=_auth(two_orgs.b.token),
    )
    assert patch_response.status_code == 404

    delete_response = await client.delete(
        f"/connectors/{connector_id}", headers=_auth(two_orgs.b.token)
    )
    assert delete_response.status_code == 404
