"""RED test for `_JiraTicketReader` (change 18-adapter-jira), precedent
`test_adapter_glpi.py::TestGlpiAdapterListTickets`: `port_for(Capability.
tickets)` from a REAL `MockTransport`-backed adapter, asserting the thin
`Ticket` DTO it returns."""

import json
from pathlib import Path

import httpx
import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "jira"
_ALLOWED_BASE_URL = "https://acme.atlassian.net"


def _load_fixture(name: str) -> dict | list:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


class TestJiraTicketReader:
    @pytest.mark.asyncio
    async def test_list_tickets_returns_the_thin_ticket_dto(self) -> None:
        from app.integrations.adapters.jira.adapter import JiraAdapter, encode_access_context
        from app.integrations.ports import AccessContext, Capability

        fields = _load_fixture("fields.json")
        page2 = _load_fixture("search_page2.json")  # isLast=true -> single page

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/rest/api/3/field":
                return httpx.Response(200, json=fields)
            if path == "/rest/api/3/search/jql":
                return httpx.Response(200, json=page2)
            return httpx.Response(404, json={"errorMessages": ["not mocked"]})

        adapter = JiraAdapter(transport=httpx.MockTransport(handler))
        port = adapter.port_for(Capability.tickets)
        assert port is not None

        token = encode_access_context(
            connector_id="conn-a",
            base_url=_ALLOWED_BASE_URL,
            email="mia@acme.com",
            api_token="secret-token",
        )
        ctx = AccessContext(access_token=token, refresh_token=None, scopes=())
        tickets = await port.list_tickets(ctx, limit=50)

        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.external_id == "PROJ-44"
        assert ticket.key == "PROJ-44"
        assert ticket.summary == "Corregir el calculo de horas extra"
        assert ticket.status == "Done"
        assert ticket.priority == "medium"
        assert ticket.assignees == ()
