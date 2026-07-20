"""Tests for active-organization resolution via ``X-Organization-Id``.

organizations-admin R4 / multi-tenancy R2 (modified): the tenant scope of a
request is resolved from ``X-Organization-Id`` when present and a valid
membership of the caller; falls back to the FIRST membership by
``created_at`` when the header is absent (gotcha 3 — the existing suite,
1210 tests, must keep passing WITHOUT this header); and rejects an ajena or
malformed header with ``403`` (``not_a_member``) — never ``404`` (would
imply the resource lookup happened) and never ``200`` (gotcha 2).

Two probe strategies are used:

- Tests 1.1-1.4 (header parsing) drive ``GET /organizations/me/theme`` — it
  already depends on ``get_current_membership`` and returns the tenant's
  ``theme``, set directly via the ``session`` fixture (bypassing the
  RBAC-gated ``PUT``) so org A/org B are distinguishable by their stored
  theme marker.
- Tests 1.6/1.7 (``require_org_admin``, gotcha 1 — target-scoped, NEVER the
  header) call the dependency directly, the same unit-style pattern
  ``test_multi_tenancy.py`` uses for ``require_role`` — ``PATCH
  /organizations/{id}`` does not exist until Phase 3.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import skip_no_db


def _auth(token: str, organization_id: object | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    return headers


async def _set_theme(session: AsyncSession, organization, value: dict) -> None:
    organization.theme = value
    await session.flush()


async def _two_memberships(session: AsyncSession, tenant, second_tenant, make_member):
    """A single user with membership in ``tenant`` (earlier) and
    ``second_tenant`` (later), explicit ``created_at`` to avoid a tie under
    the SAVEPOINT session (same gotcha as ``test_multi_tenancy.py``)."""

    from app.modules.organizations.models import OrganizationMember
    from app.shared.enums import MemberRole

    user_obj, token = await make_member(session, tenant, MemberRole.member)

    earlier = datetime.now(UTC) - timedelta(minutes=5)
    later = datetime.now(UTC)

    org_a_membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == tenant.id,
                OrganizationMember.user_id == user_obj.id,
            )
        )
    ).scalar_one()
    org_a_membership.created_at = earlier
    await session.flush()

    session.add(
        OrganizationMember(
            organization_id=second_tenant.id,
            user_id=user_obj.id,
            role=MemberRole.member,
            created_at=later,
        )
    )
    await session.flush()

    return user_obj, token


# ---------------------------------------------------------------------------
# 1.1 / 1.2 / 1.4 — header ausente / válido / malformado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_without_header_falls_back_to_first_membership_by_created_at(
    client: AsyncClient, session: AsyncSession, tenant, second_tenant, make_member
) -> None:
    """gotcha (3): sin header, el resolver conserva el comportamiento previo."""

    await _set_theme(session, tenant, {"marker": "org-a"})
    await _set_theme(session, second_tenant, {"marker": "org-b"})
    _, token = await _two_memberships(session, tenant, second_tenant, make_member)

    response = await client.get("/organizations/me/theme", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"marker": "org-a"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_valid_header_resolves_the_named_organization(
    client: AsyncClient, session: AsyncSession, tenant, second_tenant, make_member
) -> None:
    """Header válido resuelve la empresa activa (organizations-admin R4)."""

    await _set_theme(session, tenant, {"marker": "org-a"})
    await _set_theme(session, second_tenant, {"marker": "org-b"})
    _, token = await _two_memberships(session, tenant, second_tenant, make_member)

    response = await client.get(
        "/organizations/me/theme", headers=_auth(token, second_tenant.id)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"marker": "org-b"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_header_for_foreign_organization_returns_403(
    client: AsyncClient, second_tenant, user
) -> None:
    """gotcha (2): header de empresa ajena -> 403 not_a_member, nunca 404/200."""

    _, token = user  # only a member of `tenant`, not `second_tenant`

    response = await client.get(
        "/organizations/me/theme", headers=_auth(token, second_tenant.id)
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "not_a_member"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_malformed_header_returns_403_never_422(
    client: AsyncClient, user
) -> None:
    """UUID malformado -> 403 (mismo código que ajena), NUNCA 422."""

    _, token = user
    headers = {"Authorization": f"Bearer {token}", "X-Organization-Id": "no-es-un-uuid"}

    response = await client.get("/organizations/me/theme", headers=headers)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "not_a_member"


# ---------------------------------------------------------------------------
# 1.6 / 1.7 — require_org_admin es target-scoped, NUNCA depende del header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_org_admin_uses_route_target_not_the_header(
    session: AsyncSession, tenant, second_tenant, make_member
) -> None:
    """(a) admin de Y, miembro no-admin de X -> require_org_admin(Y) succeeds
    regardless of any header/current-membership context (it is never passed
    one — it resolves membership directly from ``organization_id``)."""

    from app.dependencies import require_org_admin
    from app.shared.enums import MemberRole

    user_obj, _ = await make_member(session, tenant, MemberRole.member)
    from app.modules.organizations.models import OrganizationMember

    session.add(
        OrganizationMember(
            organization_id=second_tenant.id,
            user_id=user_obj.id,
            role=MemberRole.admin,
        )
    )
    await session.flush()

    membership = await require_org_admin(
        organization_id=second_tenant.id, db=session, user=user_obj
    )

    assert membership.organization_id == second_tenant.id
    assert membership.role == MemberRole.admin


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_org_admin_non_member_of_route_target_returns_404(
    session: AsyncSession, tenant, second_tenant, make_member
) -> None:
    """(b) admin de Y, pero sin membresía en Z -> 404, nunca 403 (no revela existencia)."""

    from app.dependencies import require_org_admin
    from app.modules.organizations.models import Organization
    from app.shared.enums import MemberRole
    from app.shared.exceptions import AppException

    user_obj, _ = await make_member(session, second_tenant, MemberRole.admin)

    org_z = Organization(name="Org Z", slug="org-z-target-scoped")
    session.add(org_z)
    await session.flush()

    with pytest.raises(AppException) as exc_info:
        await require_org_admin(organization_id=org_z.id, db=session, user=user_obj)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_org_admin_member_but_not_admin_returns_403(
    session: AsyncSession, tenant, make_member
) -> None:
    """Miembro (no admin) de la empresa de la ruta -> 403 forbidden."""

    from app.dependencies import require_org_admin
    from app.shared.enums import MemberRole
    from app.shared.exceptions import AppException

    user_obj, _ = await make_member(session, tenant, MemberRole.member)

    with pytest.raises(AppException) as exc_info:
        await require_org_admin(organization_id=tenant.id, db=session, user=user_obj)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"
