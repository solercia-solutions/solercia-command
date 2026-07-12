"""Tests for the assets module — Asset CRUD, AssetTask links (change 07).

R1 Creación con taxonomía validada · R2 Consulta por cualquier miembro ·
R3 Edición/borrado admin · R5 Vínculo activo↔tarea existente ·
R6 Aislamiento multi-tenant (specs/assets/spec.md). Escrituras exigen RBAC
admin vía la fixture ``rbac_admin`` — ``two_orgs`` siembra
``OrganizationMember.role=admin``, que NO satisface ``require_admin``.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1 — Creación de activo con taxonomía validada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_asset_by_admin_returns_201(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """POST /assets by an org admin creates the asset with created_by/updated_by set."""

    owner, token = user
    await rbac_admin(session, tenant, owner)

    response = await client.post(
        "/assets",
        json={"name": "Laptop Dell 7420", "asset_type": "hardware"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["name"] == "Laptop Dell 7420"
    assert body["asset_type"] == "hardware"
    assert body["created_by"] == str(owner.id)
    assert body["updated_by"] == str(owner.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_asset_with_invalid_asset_type_returns_422(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """asset_type='license' (removed from the enum) is rejected with 422."""

    owner, token = user
    await rbac_admin(session, tenant, owner)

    response = await client.post(
        "/assets",
        json={"name": "Activo inválido", "asset_type": "license"},
        headers=_auth(token),
    )

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_asset_rejected_for_non_admin(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """A member without the ADMIN RBAC role gets 403 on POST /assets."""

    _, token = user

    response = await client.post(
        "/assets",
        json={"name": "Impresora", "asset_type": "hardware"},
        headers=_auth(token),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# R2 — Consulta de activos por cualquier miembro
# ---------------------------------------------------------------------------


async def _seed_assets(
    session: AsyncSession, tenant: Organization, *, hardware: int, software: int
) -> None:
    from app.modules.assets.models import Asset

    for i in range(hardware):
        session.add(
            Asset(
                organization_id=tenant.id,
                name=f"Hardware {i}",
                asset_type="hardware",
            )
        )
    for i in range(software):
        session.add(
            Asset(
                organization_id=tenant.id,
                name=f"Software {i}",
                asset_type="software",
            )
        )
    await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_assets_filtered_by_asset_type(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """GET /assets?asset_type=hardware returns only the 5 hardware assets."""

    _, token = user
    await _seed_assets(session, tenant, hardware=5, software=3)

    response = await client.get(
        "/assets", params={"asset_type": "hardware", "page": 1, "size": 10}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) == 5
    assert all(row["asset_type"] == "hardware" for row in body["data"])
    assert body["meta"]["total"] == 5


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_assets_filtered_by_q_and_category(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """GET /assets?q=&category= combines a name substring search with the taxonomy's 2nd axis."""

    from app.modules.assets.models import Asset

    _, token = user
    session.add_all(
        [
            Asset(
                organization_id=tenant.id,
                name="Antivirus Corporativo",
                asset_type="software",
                category="seguridad",
            ),
            Asset(
                organization_id=tenant.id,
                name="Suite Ofimática",
                asset_type="software",
                category="productividad",
            ),
        ]
    )
    await session.flush()

    response = await client.get(
        "/assets", params={"q": "antivirus", "category": "seguridad"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["data"]}
    assert names == {"Antivirus Corporativo"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_nonexistent_asset_returns_404(
    client: AsyncClient, user
) -> None:
    """GET /assets/{id} for a random id that does not exist returns 404."""

    _, token = user

    response = await client.get(f"/assets/{uuid.uuid4()}", headers=_auth(token))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# R3 — Edición y borrado de un activo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_asset_by_admin_updates_status_and_criticality(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """PATCH /assets/{id} by an admin updates status/criticality and updated_by."""

    from app.modules.assets.models import Asset

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = Asset(organization_id=tenant.id, name="Servidor", asset_type="hardware")
    session.add(asset)
    await session.flush()

    response = await client.patch(
        f"/assets/{asset.id}",
        json={"status": "under_review", "criticality": "critical"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "under_review"
    assert body["criticality"] == "critical"
    assert body["updated_by"] == str(owner.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_asset_is_soft_delete_and_disappears_from_list(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """DELETE /assets/{id} responds 204 and the asset no longer appears in GET /assets."""

    from app.modules.assets.models import Asset

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset = Asset(organization_id=tenant.id, name="Router", asset_type="hardware")
    session.add(asset)
    await session.flush()

    response = await client.delete(f"/assets/{asset.id}", headers=_auth(token))

    assert response.status_code == 204

    listing = await client.get("/assets", headers=_auth(token))
    listed_ids = {row["id"] for row in listing.json()["data"]}
    assert str(asset.id) not in listed_ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_asset_rejected_for_non_admin(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user
) -> None:
    """A member without the ADMIN RBAC role gets 403 on PATCH /assets/{id}."""

    from app.modules.assets.models import Asset

    _, token = user
    asset = Asset(organization_id=tenant.id, name="Monitor", asset_type="hardware")
    session.add(asset)
    await session.flush()

    response = await client.patch(
        f"/assets/{asset.id}", json={"status": "retired"}, headers=_auth(token)
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# R5 — Vínculo activo↔tarea con tareas existentes
# ---------------------------------------------------------------------------


async def _seed_asset_and_task(session: AsyncSession, tenant: Organization):
    from app.modules.assets.models import Asset
    from app.modules.projects.models import Project
    from app.modules.tasks.models import Task

    asset = Asset(organization_id=tenant.id, name="Portátil", asset_type="hardware")
    project = Project(
        organization_id=tenant.id,
        name="Proyecto Activos",
        methodology="kanban",
        code=f"AST{uuid.uuid4().hex[:6]}",
    )
    session.add_all([asset, project])
    await session.flush()

    task = Task(project_id=project.id, title="Renovar licencia", status="Backlog")
    session.add(task)
    await session.flush()

    return asset, task


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_link_existing_task_appears_in_list(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """POST /assets/{id}/tasks links an existing task; it then appears in GET .../tasks."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset, task = await _seed_asset_and_task(session, tenant)

    link_response = await client.post(
        f"/assets/{asset.id}/tasks", json={"task_id": str(task.id)}, headers=_auth(token)
    )
    assert link_response.status_code == 201, link_response.text

    list_response = await client.get(f"/assets/{asset.id}/tasks", headers=_auth(token))
    task_ids = {row["task_id"] for row in list_response.json()["data"]}
    assert str(task.id) in task_ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_link_task_from_another_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Linking a task that belongs to org B, using org A's admin token, returns 404."""

    from app.modules.assets.models import Asset

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    asset = Asset(
        organization_id=two_orgs.a.organization.id, name="Servidor A", asset_type="hardware"
    )
    session.add(asset)
    await session.flush()

    response = await client.post(
        f"/assets/{asset.id}/tasks",
        json={"task_id": str(two_orgs.b.task.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unlink_task_removes_it_from_list(
    client: AsyncClient, session: AsyncSession, tenant: Organization, user, rbac_admin
) -> None:
    """DELETE /assets/{id}/tasks/{task_id} makes the link disappear from GET .../tasks."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    asset, task = await _seed_asset_and_task(session, tenant)

    await client.post(
        f"/assets/{asset.id}/tasks", json={"task_id": str(task.id)}, headers=_auth(token)
    )

    response = await client.delete(
        f"/assets/{asset.id}/tasks/{task.id}", headers=_auth(token)
    )
    assert response.status_code == 204

    list_response = await client.get(f"/assets/{asset.id}/tasks", headers=_auth(token))
    task_ids = {row["task_id"] for row in list_response.json()["data"]}
    assert str(task.id) not in task_ids


# ---------------------------------------------------------------------------
# R6 — Aislamiento multi-tenant en activos, licencias y vínculos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_assets_never_crosses_organizations(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """GET /assets for org A never lists an asset that only belongs to org B."""

    from app.modules.assets.models import Asset

    session.add(
        Asset(organization_id=two_orgs.b.organization.id, name="Solo B", asset_type="hardware")
    )
    await session.flush()

    response = await client.get("/assets", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["data"]}
    assert "Solo B" not in names


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_asset_of_another_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """GET /assets/{id} of an org-B asset, using org A's token, returns 404."""

    from app.modules.assets.models import Asset

    asset = Asset(
        organization_id=two_orgs.b.organization.id, name="Firewall B", asset_type="hardware"
    )
    session.add(asset)
    await session.flush()

    response = await client.get(f"/assets/{asset.id}", headers=_auth(two_orgs.a.token))

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_asset_task_link_of_another_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Unlinking an asset-task pair of org B, using org A's admin token, is unreachable (404)."""

    from app.modules.assets.models import Asset

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    asset_b = Asset(
        organization_id=two_orgs.b.organization.id, name="Router B", asset_type="hardware"
    )
    session.add(asset_b)
    await session.flush()

    response = await client.get(f"/assets/{asset_b.id}/tasks", headers=_auth(two_orgs.a.token))

    assert response.status_code == 404
