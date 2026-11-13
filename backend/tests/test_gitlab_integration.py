"""Tests for the GitLab repository mapping (S2) and the per-task development
activity (S3), through the public HTTP endpoints.

The registered `gitlab` adapter is swapped for one bound to an
`httpx.MockTransport`; credentials are registered through the real
`POST /connectors/{id}/credentials` flow. Zero real network.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.adapters.gitlab.adapter import GitlabAdapter, mentions_task_key
from app.integrations.registry import get_adapter, register_adapter
from app.modules.connectors.models import Connector
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gitlab"
_BASE_URL = "https://gitlab.com"
_TOKEN = "glpat-SECRETO-DE-PRUEBA"


def _fixture(name: str) -> object:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _json(name: str) -> Callable[[], httpx.Response]:
    return lambda: httpx.Response(200, json=_fixture(name))


class _Recorder:
    def __init__(self, routes: dict[str, Callable[[], httpx.Response]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        factory = self.routes.get(request.url.path)
        if factory is None:
            return httpx.Response(404, json={"message": "404 Project Not Found"})
        return factory()


def _routes() -> dict[str, Callable[[], httpx.Response]]:
    return {
        "/api/v4/user": _json("user.json"),
        "/api/v4/personal_access_tokens/self": _json("token_read_api.json"),
        "/api/v4/projects": _json("projects.json"),
        "/api/v4/projects/grupo/api": _json("project_api.json"),
        "/api/v4/projects/grupo/api/merge_requests": _json("merge_requests.json"),
        "/api/v4/projects/grupo/api/repository/commits": _json("commits.json"),
    }


@pytest.fixture
def gitlab_mock() -> Iterator[_Recorder]:
    original = get_adapter("gitlab")
    recorder = _Recorder(_routes())

    async def _no_sleep(_seconds: float) -> None:
        return None

    register_adapter(
        GitlabAdapter(
            settings=Settings(GITLAB_BASE_URL_ALLOWLIST="gitlab.com"),  # type: ignore[call-arg]
            transport=httpx.MockTransport(recorder),
            sleep=_no_sleep,
        )
    )
    yield recorder
    if original is not None:
        register_adapter(original)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _connect_gitlab(client: AsyncClient, token: str) -> str:
    created = await client.post(
        "/connectors",
        json={"provider": "gitlab", "credential_kind": "api_token"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    connector_id = created.json()["data"]["id"]
    registered = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"base_url": _BASE_URL, "access_token": _TOKEN},
        headers=_auth(token),
    )
    assert registered.status_code == 201, registered.text
    return connector_id


async def _link(client: AsyncClient, token: str, project_id, repositories: list[str]):
    return await client.put(
        f"/gitlab/projects/{project_id}/repositories",
        json={"repositories": repositories},
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# Key matching (pure)
# ---------------------------------------------------------------------------


class TestMentionsTaskKey:
    @pytest.mark.parametrize(
        "text",
        ["CMD-12: login", "fix [CMD-12]", "feature/CMD-12-login", "cmd-12 en minúsculas", "CMD-12"],
    )
    def test_matches_whole_token(self, text: str) -> None:
        assert mentions_task_key(text, "CMD-12") is True

    @pytest.mark.parametrize("text", ["CMD-123 otra", "XCMD-12", "CMD-12a", "CMD-1", "", None])
    def test_rejects_partial_tokens(self, text: str | None) -> None:
        assert mentions_task_key(text, "CMD-12") is False


# ---------------------------------------------------------------------------
# S2 — repositories and project mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_lists_accessible_repositories(
    client: AsyncClient, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)

    response = await client.get("/gitlab/repositories", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [repo["path_with_namespace"] for repo in data] == ["grupo/api", "grupo/web"]
    assert _TOKEN not in response.text
    listing = next(r for r in gitlab_mock.requests if r.url.path == "/api/v4/projects")
    assert listing.url.params["membership"] == "true"
    assert listing.url.params["simple"] == "true"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repositories_without_connector_is_controlled(
    client: AsyncClient, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    response = await client.get("/gitlab/repositories", headers=_auth(two_orgs.a.token))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "gitlab_not_connected"
    assert gitlab_mock.requests == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_saves_and_reads_project_mapping_in_connector_settings(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    connector_id = await _connect_gitlab(client, two_orgs.a.token)
    project_id = two_orgs.a.project.id

    saved = await _link(client, two_orgs.a.token, project_id, ["grupo/api", "grupo/api"])

    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["repositories"] == ["grupo/api"]
    by_id = next(r for r in gitlab_mock.requests if r.url.path == "/api/v4/projects/grupo/api")
    assert b"grupo%2Fapi" in by_id.url.raw_path

    connector = (
        await session.execute(select(Connector).where(Connector.id == connector_id))
    ).scalar_one()
    await session.refresh(connector)
    assert connector.settings["gitlab"]["project_repositories"] == {str(project_id): ["grupo/api"]}

    read = await client.get(
        f"/gitlab/projects/{project_id}/repositories", headers=_auth(two_orgs.a.token)
    )
    assert read.status_code == 200, read.text
    assert read.json()["data"] == {"project_id": str(project_id), "repositories": ["grupo/api"]}

    cleared = await _link(client, two_orgs.a.token, project_id, [])
    assert cleared.status_code == 200
    assert cleared.json()["data"]["repositories"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_mapping_rejects_repository_the_token_cannot_see(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    connector_id = await _connect_gitlab(client, two_orgs.a.token)

    response = await _link(client, two_orgs.a.token, two_orgs.a.project.id, ["otro/privado"])

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "gitlab_repository_not_found"
    connector = (
        await session.execute(select(Connector).where(Connector.id == connector_id))
    ).scalar_one()
    await session.refresh(connector)
    assert "gitlab" not in (connector.settings or {})


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_mapping_rejects_malformed_path_without_http_call(
    client: AsyncClient, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)
    calls_before = len(gitlab_mock.requests)

    response = await _link(client, two_orgs.a.token, two_orgs.a.project.id, ["../../admin"])

    assert response.status_code == 422, response.text
    assert len(gitlab_mock.requests) == calls_before


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_list_or_link_repositories(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    gitlab_mock: _Recorder,
    make_member,
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)
    _member, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    listing = await client.get("/gitlab/repositories", headers=_auth(member_token))
    read = await client.get(
        f"/gitlab/projects/{two_orgs.a.project.id}/repositories", headers=_auth(member_token)
    )
    write = await _link(client, member_token, two_orgs.a.project.id, ["grupo/api"])

    assert listing.status_code == 403
    assert read.status_code == 403
    assert write.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_of_another_org_is_not_found(
    client: AsyncClient, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)

    read = await client.get(
        f"/gitlab/projects/{two_orgs.b.project.id}/repositories",
        headers=_auth(two_orgs.a.token),
    )
    write = await _link(client, two_orgs.a.token, two_orgs.b.project.id, ["grupo/api"])

    assert read.status_code == 404
    assert write.status_code == 404
    assert read.json()["code"] == "project_not_found"


# ---------------------------------------------------------------------------
# S3 — development activity per task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_sees_merge_requests_and_commits_mentioning_the_key(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    gitlab_mock: _Recorder,
    make_member,
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)
    assert (
        await _link(client, two_orgs.a.token, two_orgs.a.project.id, ["grupo/api"])
    ).status_code == 200
    two_orgs.a.task.task_number = 12
    await session.flush()
    _member, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get(
        f"/tasks/{two_orgs.a.task.id}/gitlab/activity", headers=_auth(member_token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["connected"] is True
    assert data["task_key"] == "ORGA-12"
    assert data["repositories"] == ["grupo/api"]
    assert [mr["iid"] for mr in data["merge_requests"]] == [9, 7]
    assert data["merge_requests"][1] == {
        "repository": "grupo/api",
        "iid": 7,
        "title": "ORGA-12: agrega el inicio de sesión",
        "state": "merged",
        "author": "Ana Pérez",
        "source_branch": "feature/ORGA-12-login",
        "updated_at": "2026-11-10T15:00:00Z",
        "web_url": "https://gitlab.com/grupo/api/-/merge_requests/7",
    }
    assert [c["short_id"] for c in data["commits"]] == ["a1b2c3d4"]
    assert _TOKEN not in response.text
    mr_request = next(r for r in gitlab_mock.requests if r.url.path.endswith("/merge_requests"))
    assert mr_request.url.params["search"] == "ORGA-12"
    assert all(r.method == "GET" for r in gitlab_mock.requests)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_activity_without_connector_or_links_is_empty_not_error(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    two_orgs.a.task.task_number = 12
    await session.flush()

    not_connected = await client.get(
        f"/tasks/{two_orgs.a.task.id}/gitlab/activity", headers=_auth(two_orgs.a.token)
    )
    assert not_connected.status_code == 200, not_connected.text
    assert not_connected.json()["data"]["connected"] is False
    assert not_connected.json()["data"]["merge_requests"] == []

    await _connect_gitlab(client, two_orgs.a.token)
    calls_before = len(gitlab_mock.requests)
    no_links = await client.get(
        f"/tasks/{two_orgs.a.task.id}/gitlab/activity", headers=_auth(two_orgs.a.token)
    )
    assert no_links.status_code == 200
    assert no_links.json()["data"]["connected"] is True
    assert no_links.json()["data"]["repositories"] == []
    assert len(gitlab_mock.requests) == calls_before


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_activity_of_task_in_another_org_is_not_found(
    client: AsyncClient, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    response = await client.get(
        f"/tasks/{two_orgs.b.task.id}/gitlab/activity", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "task_not_found"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_activity_maps_revoked_token_to_controlled_error(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_mock: _Recorder
) -> None:
    await _connect_gitlab(client, two_orgs.a.token)
    assert (
        await _link(client, two_orgs.a.token, two_orgs.a.project.id, ["grupo/api"])
    ).status_code == 200
    two_orgs.a.task.task_number = 12
    await session.flush()
    gitlab_mock.routes["/api/v4/projects/grupo/api/merge_requests"] = lambda: httpx.Response(401)

    response = await client.get(
        f"/tasks/{two_orgs.a.task.id}/gitlab/activity", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "gitlab_auth_error"
    assert _TOKEN not in response.text
