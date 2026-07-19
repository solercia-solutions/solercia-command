"""API tests for org-role-templates (change 23-org-role-templates).

R1 catálogo sembrado · R2 instanciación con responsable · R4 validaciones ·
R5 aislamiento multi-tenant (specs/org-role-templates/spec.md). Idempotencia
(R3) and cross-tenant isolation scenarios live in Lote 5.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org_role_templates.seeder import ensure_system_templates
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _template_id_by_name(client: AsyncClient, token: str, name: str) -> str:
    response = await client.get("/org-role-templates", headers=_auth(token))
    row = next(row for row in response.json()["data"] if row["name"] == name)
    return row["id"]


async def _promote_to_admin(session: AsyncSession, user_id) -> None:
    """Promote the ``user`` fixture's default ``MemberRole.member`` to
    ``admin`` — ``require_role`` reads ``OrganizationMember.role``."""

    result = await session.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user_id)
    )
    membership = result.scalar_one()
    membership.role = MemberRole.admin
    await session.flush()


# ---------------------------------------------------------------------------
# R1 — catálogo sembrado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_templates_returns_the_five_system_templates(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    _, token = user

    response = await client.get("/org-role-templates", headers=_auth(token))

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 5
    assert all(row["is_system"] is True for row in rows)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_jefe_oap_ti_detail_exposes_umbrella_two_branches_and_eight_teams(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    _, token = user
    template_id = await _template_id_by_name(client, token, "Jefe OAP‑TI")

    response = await client.get(
        f"/org-role-templates/{template_id}", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    tree = response.json()["data"]["tree"]
    assert tree["name"] == "OAP‑TI"
    assert {branch["name"] for branch in tree["children"]} == {
        "Planeación",
        "Tecnología",
    }
    total_teams = sum(len(branch["children"]) for branch in tree["children"])
    assert total_teams == 8


# ---------------------------------------------------------------------------
# R2 — instanciación genera el árbol de proyectos con responsable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_flat_template_creates_five_projects_with_lead_and_planner(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """"Jefe de Planeación" (plana): 1 sombrilla + 4 equipos = 5 proyectos."""

    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe de Planeación")

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 5
    assert all(row["lead_user_id"] == str(new_user.id) for row in rows)
    assert all(row["methodology"] == "planner" for row in rows)
    roots = [row for row in rows if row["parent_project_id"] is None]
    assert len(roots) == 1
    assert roots[0]["name"] == "Planeación"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_jefe_oap_ti_creates_eleven_projects_across_three_levels(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """"Jefe OAP‑TI": 1 sombrilla + 2 ramas + 8 equipos = 11 proyectos, 3 niveles."""

    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe OAP‑TI")

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 11
    assert all(row["lead_user_id"] == str(new_user.id) for row in rows)
    roots = [row for row in rows if row["parent_project_id"] is None]
    assert len(roots) == 1
    root_id = roots[0]["id"]
    branches = [row for row in rows if row["parent_project_id"] == root_id]
    assert len(branches) == 2
    branch_ids = {b["id"] for b in branches}
    teams = [row for row in rows if row["parent_project_id"] in branch_ids]
    assert len(teams) == 8


# ---------------------------------------------------------------------------
# R4 — validaciones de instanciación (rol)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_role_cannot_instantiate(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    new_user, member_token = user  # `user` fixture defaults to MemberRole.member
    template_id = await _template_id_by_name(
        client, member_token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(member_token),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_role_instantiates_successfully(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    await ensure_system_templates(session)
    manager, manager_token = await make_member(session, tenant, MemberRole.manager)
    template_id = await _template_id_by_name(
        client, manager_token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(manager.id)},
        headers=_auth(manager_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 1  # "Equipo de desarrollo" = solo sombrilla, sin equipos
    assert rows[0]["name"] == "Desarrollo"
