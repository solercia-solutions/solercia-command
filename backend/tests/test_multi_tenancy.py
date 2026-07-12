"""Tests for multi-tenancy: row-level isolation and tenant resolution.

R1 aislamiento row-level en ``/projects`` · R2 tenant resuelto desde
``get_current_membership`` (1.ª membresía por ``created_at``, nunca por
parámetro del cliente) · R3 ``MemberRole`` como base de ``require_role`` ·
R4 seed idempotente de "Solercia" (openspec/specs/multi-tenancy/spec.md).

Uses the shared in-process fixtures (``client``/``session``) plus the
``two_orgs`` fixture (dos organizaciones con datos propios) for isolation.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1 — Aislamiento row-level en /projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_projects_only_returns_callers_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A member of org A listing /projects never sees org B's project."""

    response = await client.get("/projects", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.project.id) in ids
    assert str(two_orgs.b.project.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_project_from_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A member of org A cannot read org B's project by id (never 200)."""

    response = await client.get(
        f"/projects/{two_orgs.b.project.id}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# R2 — Tenant resuelto desde get_current_membership (nunca del cliente)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tenant_scope_ignores_client_supplied_organization_id(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Even if the client tries to smuggle org B's id in the query string,
    the response still reflects org A only — the tenant is server-resolved.
    """

    response = await client.get(
        f"/projects?organization_id={two_orgs.b.organization.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.b.project.id) not in ids
    assert str(two_orgs.a.project.id) in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_membership_resolved_from_first_membership_by_created_at(
    session: AsyncSession, client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A user with TWO memberships operates on the FIRST one created (org A),
    never on the later one (org B), confirming R2's resolution rule.
    """

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    session.add(
        OrganizationMember(
            organization_id=two_orgs.b.organization.id,
            user_id=two_orgs.a.user.id,
            role=MemberRole.member,
        )
    )
    await session.flush()

    response = await client.get("/projects", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.project.id) in ids
    assert str(two_orgs.b.project.id) not in ids


# ---------------------------------------------------------------------------
# R3 — MemberRole como base de require_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_role_rejects_role_outside_allowed_set(tenant) -> None:
    """``require_role(admin)``'s checker rejects a membership whose role is
    NOT in the allowed set, raising ``AppException`` with ``status_code=403``.

    Exercises the real ``_checker`` closure built by ``require_role`` directly
    (unit layer — the dependency itself contains no I/O beyond reading
    ``membership.role``), passing an explicit ``OrganizationMember`` to
    bypass FastAPI's ``Depends`` resolution.
    """

    import uuid

    from app.dependencies import require_role
    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole
    from app.shared.exceptions import AppException

    checker = require_role(MemberRole.admin)
    membership = OrganizationMember(
        organization_id=tenant.id, user_id=uuid.uuid4(), role=MemberRole.member
    )

    with pytest.raises(AppException) as exc_info:
        await checker(membership=membership)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_role_accepts_role_in_allowed_set(tenant) -> None:
    """``require_role(admin)``'s checker returns the membership unchanged
    when its role IS in the allowed set (no exception raised)."""

    import uuid

    from app.dependencies import require_role
    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    checker = require_role(MemberRole.admin)
    membership = OrganizationMember(
        organization_id=tenant.id, user_id=uuid.uuid4(), role=MemberRole.admin
    )

    result = await checker(membership=membership)

    assert result is membership


# ---------------------------------------------------------------------------
# R4 — Seed idempotente de "Solercia"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ensure_organization_creates_solercia_once(
    session: AsyncSession,
) -> None:
    """``_ensure_organization`` creates the "Solercia" org exactly once and
    returns the SAME row (same id) on a second call — idempotent seed (R4).
    """

    from app.db_init import _ensure_organization

    first = await _ensure_organization(session)
    await session.flush()
    second = await _ensure_organization(session)
    await session.flush()

    assert first.id == second.id
    assert first.slug == "solercia"
    assert first.name == "Solercia"
