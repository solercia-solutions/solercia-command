"""RED tests for the `jira_import` REST surface (change 18-adapter-jira,
specs/jira-import/spec.md "Superficie REST de import solo-lectura, con
permisos y multi-tenant" + "Frontera solo-lectura estricta"). Runs the ASGI
app end-to-end against a real Postgres test DB (connector + credentials
persisted for real) with the Jira HTTP boundary mocked via
`httpx.MockTransport` — ZERO real network, ZERO real Jira instance.
"""

import io
import json
import logging
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.registry import register_adapter
from tests.conftest import TwoOrgs, skip_no_db

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "jira"
_MYSELF_PAYLOAD = {
    "accountId": "5b10a2844c20165700ede21g",
    "displayName": "Mia Krystof",
    "emailAddress": "mia@acme.com",
    "active": True,
}


def _load_fixture(name: str) -> dict | list:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _read_fixture_bytes(name: str) -> bytes:
    return (_FIXTURES_DIR / name).read_bytes()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mock_jira_handler(*, search_pages: list[dict] | None = None, search_responder=None):
    """Route Jira Cloud's three endpoints this flow touches — `/field` from
    a fixture, `/search/jql` from `search_pages` (cycled per call, original
    behavior) OR from `search_responder(request)` when given (lets a
    scenario inspect the request or simulate a 429)."""

    fields = _load_fixture("fields.json")
    calls = {"search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/rest/api/3/myself":
            return httpx.Response(200, json=_MYSELF_PAYLOAD)
        if path == "/rest/api/3/field":
            return httpx.Response(200, json=fields)
        if path == "/rest/api/3/search/jql":
            if search_responder is not None:
                return search_responder(request)
            pages = search_pages or []
            index = min(calls["search"], len(pages) - 1)
            calls["search"] += 1
            return httpx.Response(200, json=pages[index])
        return httpx.Response(404, json={"errorMessages": ["not mocked"]})

    return handler


async def _create_connector_and_credentials(client: AsyncClient, token: str) -> str:
    """Register a `jira` connector + its `api_token` credentials — assumes
    the caller already called `register_adapter(JiraAdapter(...))`."""

    connector_response = await client.post(
        "/connectors",
        json={
            "provider": "jira",
            "credential_kind": "api_token",
            "settings": {"jira": {"base_url": "https://acme.atlassian.net"}},
        },
        headers=_auth(token),
    )
    assert connector_response.status_code == 201, connector_response.text
    connector_id = connector_response.json()["data"]["id"]

    credentials_response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={
            "base_url": "https://acme.atlassian.net",
            "email": "mia@acme.com",
            "api_token": "JIRA-SECRET-TOKEN",
        },
        headers=_auth(token),
    )
    assert credentials_response.status_code == 201, credentials_response.text
    return connector_id


async def _create_jira_connector_with_credentials(
    client: AsyncClient, token: str, *, search_pages: list[dict]
) -> str:
    register_adapter(
        JiraAdapter(transport=httpx.MockTransport(_mock_jira_handler(search_pages=search_pages)))
    )
    return await _create_connector_and_credentials(client, token)


class TestImportViaApi:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_returns_normalized_issues_and_a_summary(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """Scenario: Import por API devuelve issues + resumen. Uses BOTH
        fixture pages (page1 isLast=false -> page2 isLast=true) so the
        client's own pagination loop terminates naturally, end-to-end."""

        page1 = _load_fixture("search_page1.json")
        page2 = _load_fixture("search_page2.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1, page2]
        )

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert len(body["issues"]) == 3  # page1's 2 issues + page2's 1
        assert body["report"]["total"] == 3
        assert body["report"]["unmapped_priorities"] == {"Blocker": 1}
        assert response.json()["meta"]["total"] == 3

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_member_cannot_trigger_an_import(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
    ) -> None:
        from app.shared.enums import MemberRole

        page1 = _load_fixture("search_page1.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1]
        )
        _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(member_token),
        )

        assert response.status_code == 403, response.text

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_foreign_org_connector_returns_404(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """Scenario: Conector ajeno."""

        page1 = _load_fixture("search_page1.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1]
        )

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(two_orgs.b.token),
        )

        assert response.status_code == 404, response.text

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_token_never_appears_in_the_response_or_logs(
        self, client: AsyncClient, two_orgs: TwoOrgs, caplog
    ) -> None:
        page1 = _load_fixture("search_page1.json")
        page2 = _load_fixture("search_page2.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1, page2]
        )

        with caplog.at_level(logging.DEBUG):
            response = await client.post(
                f"/connectors/{connector_id}/jira/import",
                json={"jql": "project = PROJ"},
                headers=_auth(two_orgs.a.token),
            )

        assert response.status_code == 200, response.text
        assert "JIRA-SECRET-TOKEN" not in response.text
        for record in caplog.records:
            assert "JIRA-SECRET-TOKEN" not in record.getMessage()

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_exhausted_429_on_page_two_returns_200_with_page_one_truncated(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """'Reintentos agotados': page 2's 429 is exhausted, page 1's issues
        still answer 200 with `truncated=true`, never a 503 that loses them."""

        page1 = _load_fixture("search_page1.json")
        error_payload = _load_fixture("search_429.json")
        calls = {"n": 0}

        def responder(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(429, json=error_payload, headers={"Retry-After": "0"})

        handler = _mock_jira_handler(search_responder=responder)
        register_adapter(JiraAdapter(transport=httpx.MockTransport(handler)))
        connector_id = await _create_connector_and_credentials(client, two_orgs.a.token)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["truncated"] is True
        assert body["truncation_reason"] == "rate_limited"
        assert {issue["key"] for issue in body["issues"]} == {"PROJ-42", "PROJ-43"}

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_since_payload_reaches_the_search_request(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """The router's `since` payload reaches the search request's JQL."""

        page2 = _load_fixture("search_page2.json")
        seen_jql: list[str | None] = []

        def responder(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params.get("jql"))
            return httpx.Response(200, json=page2)

        handler = _mock_jira_handler(search_responder=responder)
        register_adapter(JiraAdapter(transport=httpx.MockTransport(handler)))
        connector_id = await _create_connector_and_credentials(client, two_orgs.a.token)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ", "since": "2024-01-01T08:30:00"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        assert seen_jql == ['(project = PROJ) AND updated >= "2024-01-01 08:30"']


class TestImportViaFile:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_returns_the_same_contract_as_the_api_via(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """Scenario: Import por archivo devuelve el mismo contrato."""

        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[]
        )
        content = _read_fixture_bytes("export.csv")

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={"file": ("export.csv", io.BytesIO(content), "text/csv")},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert len(body["issues"]) == 1
        assert body["issues"][0]["key"] == "PROJ-42"
        assert body["report"]["source"] == "file"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_malformed_file_propagates_the_controlled_parser_error(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[]
        )
        content = _read_fixture_bytes("export_malformado.csv")

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={"file": ("export_malformado.csv", io.BytesIO(content), "text/csv")},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "jira_file_format_invalid"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_oversized_file_is_rejected_before_parsing(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[]
        )
        oversized_content = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={"file": ("big.csv", io.BytesIO(oversized_content), "text/csv")},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 413, response.text
        assert response.json()["code"] == "jira_file_upload_too_large"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_non_utf8_csv_is_rejected_with_a_controlled_422(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """Binary/mislabeled bytes uploaded as .csv (UnicodeDecodeError in
        the parser) answer a controlled 422, never a 500 (revisión 4R, W3)."""

        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[]
        )
        content = b"\xff\xfe\x00\x01no soy texto utf-8\x80\x81"

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={"file": ("corrupto.csv", io.BytesIO(content), "text/csv")},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "jira_file_invalid"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_garbage_xlsx_is_rejected_with_a_controlled_422(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        """Non-zip bytes uploaded as .xlsx (BadZipFile in openpyxl) answer a
        controlled 422, never a 500 (revisión 4R, W3)."""

        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[]
        )
        content = b"esto no es un zip ni de lejos"

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={
                "file": (
                    "corrupto.xlsx",
                    io.BytesIO(content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "jira_file_invalid"


class TestReadOnlyBoundary:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_import_creates_no_task_sprint_or_label_rows(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        """Scenario: Ningún efecto secundario en la plataforma
        (specs/jira-import/spec.md 'Frontera solo-lectura estricta')."""

        from app.modules.labels.models import Label
        from app.modules.sprints.models import Sprint
        from app.modules.tasks.models import Task

        async def _count(model) -> int:
            result = await session.execute(select(func.count()).select_from(model))
            return int(result.scalar_one() or 0)

        tasks_before = await _count(Task)
        sprints_before = await _count(Sprint)
        labels_before = await _count(Label)

        page1 = _load_fixture("search_page1.json")
        page2 = _load_fixture("search_page2.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1, page2]
        )
        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(two_orgs.a.token),
        )
        assert response.status_code == 200, response.text

        assert await _count(Task) == tasks_before
        assert await _count(Sprint) == sprints_before
        assert await _count(Label) == labels_before


# ---------------------------------------------------------------------------
# User-driven project import: projects -> preview -> import-project
# ---------------------------------------------------------------------------


def _raw_issue(key: str, type_name: str, *, subtask: bool = False, **fields: object) -> dict:
    base: dict = {
        "summary": f"Issue {key}",
        "description": None,
        "issuetype": {"name": type_name, "subtask": subtask},
        "status": {"name": "To Do", "statusCategory": {"key": "new"}},
        "priority": {"name": "Medium"},
        "assignee": None,
        "labels": [],
        "created": "2024-01-15T10:30:00.000+0000",
    }
    base.update(fields)
    return {"id": key, "key": key, "fields": base}


def _project_issues() -> list[dict]:
    sprint = [{"id": 7, "name": "Sprint 1", "state": "active"}]
    return [
        _raw_issue("PROJ-1", "Epic"),
        _raw_issue(
            "PROJ-2",
            "Story",
            parent={"key": "PROJ-1"},
            timeoriginalestimate=14400,
            customfield_10032=5,
            customfield_10020=sprint,
            status={"name": "En curso", "statusCategory": {"key": "indeterminate"}},
        ),
        _raw_issue("PROJ-3", "Sub-task", subtask=True, parent={"key": "PROJ-2"}),
        _raw_issue(
            "PROJ-4",
            "Bug",
            customfield_10020=sprint,
            status={"name": "Hecho", "statusCategory": {"key": "done"}},
        ),
    ]


def _project_handler(
    *,
    issues: list[dict] | None = None,
    projects: list[dict] | None = None,
    calls: dict | None = None,
    search_status: int = 200,
    fail_on_page_two: bool = False,
    jira_status: int | None = None,
):
    fields = _load_fixture("fields.json")
    calls = calls if calls is not None else {}
    calls.setdefault("search", 0)
    calls.setdefault("jql", [])

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if jira_status is not None and path != "/rest/api/3/myself":
            return httpx.Response(jira_status, json={"errorMessages": ["x"]})
        if path == "/rest/api/3/myself":
            return httpx.Response(200, json=_MYSELF_PAYLOAD)
        if path == "/rest/api/3/field":
            return httpx.Response(200, json=fields)
        if path == "/rest/api/3/project/search":
            return httpx.Response(
                200,
                json={
                    "values": projects
                    if projects is not None
                    else [{"key": "PROJ", "name": "Proyecto Jira"}],
                    "isLast": True,
                },
            )
        if path == "/rest/api/3/search/jql":
            calls["search"] += 1
            calls["jql"].append(request.url.params.get("jql"))
            if search_status != 200:
                return httpx.Response(search_status, json={"errorMessages": ["no existe"]})
            all_issues = issues if issues is not None else _project_issues()
            if fail_on_page_two:
                if request.url.params.get("nextPageToken"):
                    return httpx.Response(500, json={"errorMessages": ["boom"]})
                return httpx.Response(
                    200, json={"issues": all_issues[:2], "isLast": False, "nextPageToken": "N2"}
                )
            return httpx.Response(200, json={"issues": all_issues, "isLast": True})
        return httpx.Response(404, json={"errorMessages": ["not mocked"]})

    return handler


async def _project_connector(client: AsyncClient, token: str, **handler_kwargs) -> str:
    register_adapter(JiraAdapter(transport=httpx.MockTransport(_project_handler(**handler_kwargs))))
    return await _create_connector_and_credentials(client, token)


async def _counts(session: AsyncSession) -> tuple[int, int, int]:
    from app.modules.projects.models import Project
    from app.modules.sprints.models import Sprint
    from app.modules.tasks.models import Task

    values = []
    for model in (Project, Sprint, Task):
        result = await session.execute(select(func.count()).select_from(model))
        values.append(int(result.scalar_one()))
    return tuple(values)  # type: ignore[return-value]


class TestJiraProjectsEndpoint:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_projects_endpoint_lists_accessible_projects(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _project_connector(client, two_orgs.a.token)

        response = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(two_orgs.a.token)
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"] == [
            {"key": "PROJ", "name": "Proyecto Jira", "imported_project": None}
        ]
        assert "JIRA-SECRET-TOKEN" not in response.text

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_projects_endpoint_without_credentials_is_a_controlled_error(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        register_adapter(JiraAdapter(transport=httpx.MockTransport(_project_handler())))
        created = await client.post(
            "/connectors",
            json={"provider": "jira", "credential_kind": "api_token"},
            headers=_auth(two_orgs.a.token),
        )
        connector_id = created.json()["data"]["id"]

        response = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(two_orgs.a.token)
        )

        assert response.status_code == 400, response.text
        assert response.json()["code"] == "jira_credentials_missing"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_projects_endpoint_revoked_token_is_400_without_secret(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _project_connector(client, two_orgs.a.token, jira_status=401)

        response = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(two_orgs.a.token)
        )

        # 400, not 401: a 401 would be read by the web client as an expired session.
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "jira_auth_error"
        assert "JIRA-SECRET-TOKEN" not in response.text

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_projects_endpoint_foreign_org_is_404_and_member_is_403(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
    ) -> None:
        from app.shared.enums import MemberRole

        connector_id = await _project_connector(client, two_orgs.a.token)
        _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

        foreign = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(two_orgs.b.token)
        )
        member = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(member_token)
        )

        assert foreign.status_code == 404, foreign.text
        assert member.status_code == 403, member.text


class TestJiraPreviewEndpoint:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_preview_endpoint_counts_and_mapping_without_writing(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        calls: dict = {}
        connector_id = await _project_connector(client, two_orgs.a.token, calls=calls)
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/preview",
            json={"project_key": "PROJ"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total"] == 4
        assert data["counts_by_type"] == {"epic": 1, "story": 1, "subtask": 1, "bug": 1}
        assert data["suggested_code"] == "PROJ"
        assert data["methodology"] == "scrum"
        assert data["existing_project"] is None
        assert [s["name"] for s in data["sprints"]] == ["Sprint 1"]
        assert {m["jira_status"]: m["target_status"] for m in data["status_mapping"]} == {
            "En curso": "In Progress",
            "Hecho": "Done",
            "To Do": "To Do",
        }
        assert float(data["estimated_hours"]) == 4.0
        assert calls["jql"] == ['project = "PROJ" ORDER BY key ASC']
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_preview_endpoint_unavailable_project_is_controlled(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _project_connector(client, two_orgs.a.token, search_status=400)
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/preview",
            json={"project_key": "GONE"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "jira_project_unavailable"
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_preview_endpoint_rejects_unsafe_key_without_calling_jira(
        self, client: AsyncClient, two_orgs: TwoOrgs
    ) -> None:
        calls: dict = {}
        connector_id = await _project_connector(client, two_orgs.a.token, calls=calls)

        response = await client.post(
            f"/connectors/{connector_id}/jira/preview",
            json={"project_key": 'PROJ" OR project = "SECRET'},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "jira_project_key_invalid"
        assert calls["search"] == 0

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_preview_endpoint_foreign_org_is_404_and_member_is_403(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
    ) -> None:
        from app.shared.enums import MemberRole

        connector_id = await _project_connector(client, two_orgs.a.token)
        _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
        body = {"project_key": "PROJ"}

        foreign = await client.post(
            f"/connectors/{connector_id}/jira/preview", json=body, headers=_auth(two_orgs.b.token)
        )
        member = await client.post(
            f"/connectors/{connector_id}/jira/preview", json=body, headers=_auth(member_token)
        )

        assert foreign.status_code == 404, foreign.text
        assert member.status_code == 403, member.text


class TestJiraImportProjectEndpoint:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_import_project_endpoint_creates_then_reconciles(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, caplog
    ) -> None:
        from app.modules.tasks.models import Task

        connector_id = await _project_connector(client, two_orgs.a.token)
        before = await _counts(session)
        body = {"project_key": "PROJ", "project_name": "Proyecto importado", "project_code": "PRJ"}

        with caplog.at_level(logging.DEBUG):
            first = await client.post(
                f"/connectors/{connector_id}/jira/import-project",
                json=body,
                headers=_auth(two_orgs.a.token),
            )

        assert first.status_code == 200, first.text
        data = first.json()["data"]
        assert data["project_created"] is True
        assert data["project_code"] == "PRJ"
        assert data["project_name"] == "Proyecto importado"
        assert data["tasks"] == {"created": 4, "updated": 0, "unchanged": 0}
        assert data["sprints"]["created"] == 1
        assert data["parents_linked"] == 2
        assert await _counts(session) == (before[0] + 1, before[1] + 1, before[2] + 4)
        assert "JIRA-SECRET-TOKEN" not in first.text
        assert all("JIRA-SECRET-TOKEN" not in r.getMessage() for r in caplog.records)
        story = (
            await session.execute(select(Task).where(Task.external_key == "PROJ-2"))
        ).scalar_one()
        assert float(story.estimation_hours) == 4.0
        assert story.estimation_points == 5

        listed = await client.get(
            f"/connectors/{connector_id}/jira/projects", headers=_auth(two_orgs.a.token)
        )
        assert listed.json()["data"][0]["imported_project"]["code"] == "PRJ"

        second = await client.post(
            f"/connectors/{connector_id}/jira/import-project",
            json=body,
            headers=_auth(two_orgs.a.token),
        )

        assert second.status_code == 200, second.text
        again = second.json()["data"]
        assert again["project_created"] is False
        assert again["project_id"] == data["project_id"]
        assert again["tasks"] == {"created": 0, "updated": 0, "unchanged": 4}
        assert await _counts(session) == (before[0] + 1, before[1] + 1, before[2] + 4)

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_import_project_endpoint_rejects_unsafe_key_without_calling_jira(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        calls: dict = {}
        connector_id = await _project_connector(client, two_orgs.a.token, calls=calls)
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-project",
            json={"project_key": "proj OR 1=1"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 422, response.text
        assert calls["search"] == 0
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_import_project_endpoint_failure_mid_import_persists_nothing(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _project_connector(client, two_orgs.a.token, fail_on_page_two=True)
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-project",
            json={"project_key": "PROJ"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 503, response.text
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_import_project_endpoint_taken_code_is_409_and_persists_nothing(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _project_connector(client, two_orgs.a.token)
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-project",
            # Org A's seeded project already uses code "ORGA".
            json={"project_key": "PROJ", "project_code": two_orgs.a.project.code},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "project_code_taken"
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jira_import_project_endpoint_foreign_org_is_404_and_member_is_403(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
    ) -> None:
        from app.shared.enums import MemberRole

        connector_id = await _project_connector(client, two_orgs.a.token)
        _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
        before = await _counts(session)
        body = {"project_key": "PROJ"}
        url = f"/connectors/{connector_id}/jira/import-project"

        foreign = await client.post(url, json=body, headers=_auth(two_orgs.b.token))
        member = await client.post(url, json=body, headers=_auth(member_token))

        assert foreign.status_code == 404, foreign.text
        assert member.status_code == 403, member.text
        assert await _counts(session) == before


class TestReadOnlyEndpointsUnchanged:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_import_keeps_its_contract_and_creates_no_project(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        """`import` stays read-only and its issue shape gains no field."""

        page1 = _load_fixture("search_page1.json")
        page2 = _load_fixture("search_page2.json")
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[page1, page2]
        )
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import",
            json={"jql": "project = PROJ"},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        assert set(response.json()["data"]["issues"][0]) == {
            "key",
            "title",
            "description",
            "issue_type",
            "status_raw",
            "status_bucket",
            "priority",
            "assignee_raw",
            "sprint_name",
            "sprint_state",
            "story_points",
            "labels",
            "created_at",
            "source",
        }
        assert await _counts(session) == before

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_import_file_creates_no_project_sprint_or_task(
        self, client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        connector_id = await _create_jira_connector_with_credentials(
            client, two_orgs.a.token, search_pages=[_load_fixture("search_page1.json")]
        )
        before = await _counts(session)

        response = await client.post(
            f"/connectors/{connector_id}/jira/import-file",
            files={"file": ("export.csv", _read_fixture_bytes("export.csv"), "text/csv")},
            headers=_auth(two_orgs.a.token),
        )

        assert response.status_code == 200, response.text
        assert await _counts(session) == before
