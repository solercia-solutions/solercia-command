"""``GET /plans/activities/conflict-counts`` (task N3, read-only).

Per-activity count of ``conflict`` links, both ends, tenant-scoped. Seeds go
through the repository write seam, like the rest of the plans tests.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans.repository import PlansRepository
from tests.conftest import TwoOrgs, skip_no_db
from tests.test_plans_endpoints import _auth, _seed_plan

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


async def test_conflict_counts_cover_both_ends_and_skip_confirmed_links(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    _, (a, b, c) = await _seed_plan(session, tenant.id, activity_codes=("1.1", "1.2", "1.3"))
    repo = PlansRepository(session)
    await repo.upsert_activity_link(a.id, b.id, "contributes_to", "conflict")
    await repo.upsert_activity_link(c.id, b.id, "contributes_to", "conflict")
    await repo.upsert_activity_link(a.id, c.id, "contributes_to", "exact")
    await session.commit()

    response = await client.get("/plans/activities/conflict-counts", headers=_auth(token))

    assert response.status_code == 200, response.text
    counts = {row["activity_id"]: row["conflict_count"] for row in response.json()["data"]}
    assert counts == {str(a.id): 1, str(b.id): 2, str(c.id): 1}


async def test_conflict_counts_route_is_not_parsed_as_an_activity_id(
    client: AsyncClient, user
) -> None:
    _, token = user

    response = await client.get("/plans/activities/conflict-counts", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


async def test_conflict_counts_never_return_another_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    _, (a, b) = await _seed_plan(session, two_orgs.b.organization.id, activity_codes=("1.1", "1.2"))
    await PlansRepository(session).upsert_activity_link(a.id, b.id, "contributes_to", "conflict")
    await session.commit()

    response = await client.get(
        "/plans/activities/conflict-counts", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []
