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


def _mock_jira_handler(*, search_pages: list[dict]):
    """Route Jira Cloud's three endpoints this flow touches to fixtures —
    `/field` and one `/search/jql` page per call, in order."""

    fields = _load_fixture("fields.json")
    calls = {"search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/rest/api/3/myself":
            return httpx.Response(200, json=_MYSELF_PAYLOAD)
        if path == "/rest/api/3/field":
            return httpx.Response(200, json=fields)
        if path == "/rest/api/3/search/jql":
            index = min(calls["search"], len(search_pages) - 1)
            calls["search"] += 1
            return httpx.Response(200, json=search_pages[index])
        return httpx.Response(404, json={"errorMessages": ["not mocked"]})

    return handler


async def _create_jira_connector_with_credentials(
    client: AsyncClient, token: str, *, search_pages: list[dict]
) -> str:
    register_adapter(JiraAdapter(transport=httpx.MockTransport(_mock_jira_handler(
        search_pages=search_pages
    ))))

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
