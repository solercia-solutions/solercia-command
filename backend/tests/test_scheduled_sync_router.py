"""C02: POST /sync/run and GET /sync/runs — admin only, tenant-scoped, fake steps."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduled_sync import service as sync_service
from app.modules.scheduled_sync.router import get_sync_steps
from app.modules.scheduled_sync.service import StepSkipped
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeSteps:
    def __init__(self):
        self.calls = []

    async def checklist(self, organization_id):
        self.calls.append(("checklist", organization_id))
        raise StepSkipped("sin configurar")

    async def intake(self, organization_id, *, since, actor_id):
        self.calls.append(("intake", organization_id, since, actor_id))
        return {"accounts": 0}

    async def classify(self, organization_id):
        self.calls.append(("classification", organization_id))
        raise StepSkipped("pendiente")


@pytest.fixture
def fake_steps():
    from app.main import app

    steps = FakeSteps()
    app.dependency_overrides[get_sync_steps] = lambda: steps
    yield steps
    app.dependency_overrides.pop(get_sync_steps, None)


async def test_admin_runs_the_sync_for_its_own_organization(
    client: AsyncClient, two_orgs: TwoOrgs, fake_steps
):
    response = await client.post("/sync/run", headers=_auth(two_orgs.a.token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["trigger"] == "manual" and data["status"] == "success"
    assert data["organization_id"] == str(two_orgs.a.organization.id)
    assert [s["name"] for s in data["steps"]] == ["checklist", "intake", "classification"]
    assert {c[1] for c in fake_steps.calls} == {two_orgs.a.organization.id}
    intake = next(c for c in fake_steps.calls if c[0] == "intake")
    assert intake[3] == two_orgs.a.user.id


async def test_runs_are_listed_paginated_and_isolated(
    client: AsyncClient, two_orgs: TwoOrgs, fake_steps
):
    for _ in range(3):
        assert (await client.post("/sync/run", headers=_auth(two_orgs.a.token))).status_code == 200
    page = await client.get("/sync/runs", params={"size": 2}, headers=_auth(two_orgs.a.token))
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["meta"] == {"page": 1, "size": 2, "total": 3} and len(body["data"]) == 2
    first, second = body["data"]
    assert first["started_at"] >= second["started_at"]
    other = await client.get("/sync/runs", headers=_auth(two_orgs.b.token))
    assert other.status_code == 200 and other.json()["meta"]["total"] == 0


async def test_member_cannot_run_or_list(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, fake_steps
):
    _member, token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    assert (await client.post("/sync/run", headers=_auth(token))).status_code == 403
    assert (await client.get("/sync/runs", headers=_auth(token))).status_code == 403
    assert fake_steps.calls == []


async def test_anonymous_gets_401(client: AsyncClient, fake_steps):
    assert (await client.post("/sync/run")).status_code == 401
    assert (await client.get("/sync/runs")).status_code == 401


async def test_concurrent_run_is_rejected_with_409(
    client: AsyncClient, two_orgs: TwoOrgs, fake_steps
):
    async with sync_service.SYNC_LOCK:
        response = await client.post("/sync/run", headers=_auth(two_orgs.a.token))
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "SYNC_ALREADY_RUNNING"
    assert fake_steps.calls == []
