"""Read-only Jira client + snapshot tests with ``httpx.MockTransport``."""

import json
import stat

import httpx
import pytest

from app.modules.jira_import.client import JiraReadClient, JiraReadError, validate_base_url
from app.modules.jira_import.snapshot import fetch_snapshot, load_snapshot, read_jira_credentials

BASE = "https://ejemplo.atlassian.net"


def _client(handler, sleeps=None):
    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return JiraReadClient(
        BASE,
        "bot@ejemplo.gov.co",
        "secreto-123",
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
    )


def test_base_url_must_be_atlassian_https():
    assert validate_base_url("https://x.atlassian.net/") == "https://x.atlassian.net"
    for bad in ("http://x.atlassian.net", "https://evil.example.com"):
        with pytest.raises(ValueError):
            validate_base_url(bad)


@pytest.mark.asyncio(loop_scope="session")
async def test_search_follows_next_page_token_and_honours_retry_after():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        token = request.url.params.get("nextPageToken")
        if token is None and len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if token is None:
            return httpx.Response(
                200, json={"issues": [{"key": "A-1"}], "nextPageToken": "p2", "isLast": False}
            )
        return httpx.Response(200, json={"issues": [{"key": "A-2"}], "isLast": True})

    async with _client(handler, sleeps) as client:
        issues = await client.search_jql("project = A", ["summary"])
    assert [i["key"] for i in issues] == ["A-1", "A-2"]
    assert sleeps == [7.0]
    assert {r.method for r in calls} == {"GET"}
    assert all(r.url.path == "/rest/api/3/search/jql" for r in calls)


@pytest.mark.asyncio(loop_scope="session")
async def test_paginate_values_stops_on_is_last_and_errors_hide_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/denied":
            return httpx.Response(403, json={"errorMessages": ["no"]})
        start = int(request.url.params["startAt"])
        return httpx.Response(200, json={"values": [{"id": start}], "isLast": start >= 1})

    async with _client(handler) as client:
        values = await client.paginate_values("/rest/agile/1.0/board", page_size=1)
        with pytest.raises(JiraReadError) as error:
            await client.get("/denied")
    assert [v["id"] for v in values] == [0, 1]
    assert "secreto-123" not in str(error.value)
    assert error.value.status_code == 403


def test_read_credentials_reads_only_prefixed_keys(tmp_path, monkeypatch):
    for key in ("JIRA_X_URL", "JIRA_X_EMAIL", "JIRA_X_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "OTRA_CLAVE=no-leer\nJIRA_X_URL=https://x.atlassian.net\n"
        'export JIRA_X_EMAIL="a@b.co"\nJIRA_X_API_TOKEN=tok\n',
        encoding="utf-8",
    )
    assert read_jira_credentials(env, "JIRA_X") == ("https://x.atlassian.net", "a@b.co", "tok")
    with pytest.raises(ValueError):
        read_jira_credentials(env, "JIRA_Y")


@pytest.mark.asyncio(loop_scope="session")
async def test_fetch_snapshot_writes_private_files_and_loads_back(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        path = request.url.path
        params = request.url.params
        if path == "/rest/api/3/field":
            return httpx.Response(
                200,
                json=[
                    {"id": "customfield_1", "name": "Story Points"},
                    {"id": "customfield_2", "name": "Sprint"},
                ],
            )
        if path == "/rest/api/3/project/search":
            return httpx.Response(
                200, json={"values": [{"key": "A"}, {"key": "B"}], "isLast": True}
            )
        if path == "/rest/api/3/users/search":
            users = [{"accountId": "u1", "accountType": "atlassian"}]
            return httpx.Response(200, json=users if params["startAt"] == "0" else [])
        if path == "/rest/api/3/search/jql":
            jql = params["jql"]
            if jql.startswith("key in"):
                return httpx.Response(200, json={"issues": [{"key": "A-0", "fields": {}}]})
            if '"A"' in jql:
                issues = [{"key": "A-1", "fields": {"parent": {"key": "A-0"}}}]
                return httpx.Response(200, json={"issues": issues, "isLast": True})
            return httpx.Response(200, json={"issues": [], "isLast": True})
        if path == "/rest/api/3/project/A/statuses":
            return httpx.Response(200, json=[])
        if path == "/rest/agile/1.0/board":
            return httpx.Response(
                200, json={"values": [{"id": 9, "type": "scrum"}], "isLast": True}
            )
        if path == "/rest/agile/1.0/board/9/configuration":
            return httpx.Response(200, json={"columnConfig": {"columns": []}})
        if path == "/rest/agile/1.0/board/9/sprint":
            return httpx.Response(
                200, json={"values": [{"id": 3, "state": "active"}], "isLast": True}
            )
        return httpx.Response(404)

    raw = tmp_path / "raw"
    async with _client(handler) as client:
        manifest = await fetch_snapshot(client, raw, base_url=BASE, log=lambda _m: None)
    assert manifest["projects_in_scope"] == {"A": 1}
    assert manifest["story_point_fields"] == ["customfield_1"]
    files = [p for p in raw.rglob("*") if p.is_file()]
    assert files and all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in files)
    assert "secreto-123" not in "".join(p.read_text() for p in files)
    snapshot = load_snapshot(raw)
    assert [i["key"] for i in snapshot.context_issues] == ["A-0"]
    assert snapshot.sprints == {9: [{"id": 3, "state": "active"}]}
    assert json.loads((raw / "manifest.json").read_text())["site_host"] == "ejemplo.atlassian.net"
