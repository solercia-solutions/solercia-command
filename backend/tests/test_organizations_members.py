"""Tests for organizations-admin membership management.

organizations-admin R2 (permisos por rol) · R3 (unicidad de membresía y
protección "sin admin"). Listing is open to any member; adding, changing
roles and removing require ``admin`` of THAT organization; any change that
would leave the organization with zero ``admin`` members is rejected.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 4.1-4.2 — GET /organizations/{id}/members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_members_any_member_can_read(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A member (here, the admin who owns the org) can list its members."""

    response = await client.get(
        f"/organizations/{two_orgs.a.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    emails = {row["email"] for row in response.json()["data"]}
    assert two_orgs.a.user.email in emails


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_members_non_member_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A non-member gets 404, not the members list of a foreign organization."""

    response = await client.get(
        f"/organizations/{two_orgs.b.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4.3-4.5 — POST /organizations/{id}/members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_add_member_by_email_as_admin(
    client: AsyncClient, two_orgs: TwoOrgs, user
) -> None:
    """Admin adds an EXISTING user (found by email) with a role."""

    new_member, _ = user  # a user with NO membership in two_orgs.a yet

    response = await client.post(
        f"/organizations/{two_orgs.a.organization.id}/members",
        json={"email": new_member.email, "role": "member"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["email"] == new_member.email
    assert body["role"] == "member"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_add_member_duplicate_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Adding a user who is ALREADY a member is rejected without duplicating."""

    response = await client.post(
        f"/organizations/{two_orgs.a.organization.id}/members",
        json={"email": two_orgs.a.user.email, "role": "member"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "membership_exists"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_add_member_rejected_for_member_role(
    client: AsyncClient, two_orgs: TwoOrgs, session: AsyncSession, make_member, user
) -> None:
    """A plain member cannot add other members (403)."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    new_member, _ = user

    response = await client.post(
        f"/organizations/{two_orgs.a.organization.id}/members",
        json={"email": new_member.email, "role": "member"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# 4.6-4.8 — PATCH /organizations/{id}/members/{member_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_member_role_as_admin_changes_another_member(
    client: AsyncClient,
    two_orgs: TwoOrgs,
    session: AsyncSession,
    make_member,
) -> None:
    """Admin promotes another member to `manager`."""

    from sqlalchemy import select

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    other_user, _ = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    other_membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == two_orgs.a.organization.id,
                OrganizationMember.user_id == other_user.id,
            )
        )
    ).scalar_one()

    response = await client.patch(
        f"/organizations/{two_orgs.a.organization.id}/members/{other_membership.id}",
        json={"role": "manager"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "manager"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_member_role_demoting_the_only_admin_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """The sole admin cannot demote themselves to `member` — membership intact."""

    own_membership_id = None
    # Resolve the admin's own membership id via the members listing endpoint
    # (keeps this test at the HTTP layer, consistent with the rest of the file).
    members_response = await client.get(
        f"/organizations/{two_orgs.a.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )
    for row in members_response.json()["data"]:
        if row["user_id"] == str(two_orgs.a.user.id):
            own_membership_id = row["id"]
    assert own_membership_id is not None

    response = await client.patch(
        f"/organizations/{two_orgs.a.organization.id}/members/{own_membership_id}",
        json={"role": "member"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "last_admin_protected"

    members_after = await client.get(
        f"/organizations/{two_orgs.a.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )
    roles = {row["id"]: row["role"] for row in members_after.json()["data"]}
    assert roles[own_membership_id] == "admin"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_member_role_rejected_for_member_role(
    client: AsyncClient,
    two_orgs: TwoOrgs,
    session: AsyncSession,
    make_member,
) -> None:
    """A plain member cannot change anyone's role (403)."""

    from sqlalchemy import select

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    other_user, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    other_membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == two_orgs.a.organization.id,
                OrganizationMember.user_id == other_user.id,
            )
        )
    ).scalar_one()

    response = await client.patch(
        f"/organizations/{two_orgs.a.organization.id}/members/{other_membership.id}",
        json={"role": "manager"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# 4.9-4.11 — DELETE /organizations/{id}/members/{member_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_member_as_admin_removes_non_admin(
    client: AsyncClient,
    two_orgs: TwoOrgs,
    session: AsyncSession,
    make_member,
) -> None:
    """Admin removes a non-admin member."""

    from sqlalchemy import select

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    other_user, _ = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    other_membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == two_orgs.a.organization.id,
                OrganizationMember.user_id == other_user.id,
            )
        )
    ).scalar_one()

    response = await client.delete(
        f"/organizations/{two_orgs.a.organization.id}/members/{other_membership.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text

    members_after = await client.get(
        f"/organizations/{two_orgs.a.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )
    remaining_ids = {row["id"] for row in members_after.json()["data"]}
    assert str(other_membership.id) not in remaining_ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_member_removing_the_only_admin_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """The sole admin cannot remove themselves (same "sin admin" protection)."""

    members_response = await client.get(
        f"/organizations/{two_orgs.a.organization.id}/members",
        headers=_auth(two_orgs.a.token),
    )
    own_membership_id = next(
        row["id"]
        for row in members_response.json()["data"]
        if row["user_id"] == str(two_orgs.a.user.id)
    )

    response = await client.delete(
        f"/organizations/{two_orgs.a.organization.id}/members/{own_membership_id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "last_admin_protected"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_remove_member_rejected_for_member_role(
    client: AsyncClient,
    two_orgs: TwoOrgs,
    session: AsyncSession,
    make_member,
) -> None:
    """A plain member cannot remove anyone (403)."""

    from sqlalchemy import select

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    other_user, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    other_membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == two_orgs.a.organization.id,
                OrganizationMember.user_id == other_user.id,
            )
        )
    ).scalar_one()

    response = await client.delete(
        f"/organizations/{two_orgs.a.organization.id}/members/{other_membership.id}",
        headers=_auth(member_token),
    )

    assert response.status_code == 403, response.text
