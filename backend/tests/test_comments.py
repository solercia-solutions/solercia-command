"""Tests for task comments and @-mention parsing (Feature #4 — comments part)."""

import uuid

import pytest

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


# ---------------------------------------------------------------------------
# Unit tests — no DB needed
# ---------------------------------------------------------------------------


class TestMentionParsing:
    """_parse_mentioned_ids extracts UUID strings from comment bodies."""

    def test_single_mention(self) -> None:
        from app.modules.comments.service import _parse_mentioned_ids

        uid = "550e8400-e29b-41d4-a716-446655440000"
        result = _parse_mentioned_ids(f"Hello @{uid} please review")
        assert uid in result

    def test_multiple_mentions_deduplicated(self) -> None:
        from app.modules.comments.service import _parse_mentioned_ids

        uid = "550e8400-e29b-41d4-a716-446655440000"
        result = _parse_mentioned_ids(f"@{uid} and again @{uid}")
        assert result.count(uid) == 1

    def test_no_mentions(self) -> None:
        from app.modules.comments.service import _parse_mentioned_ids

        result = _parse_mentioned_ids("No UUIDs here, just text.")
        assert result == []

    def test_uuid_in_html_attribute(self) -> None:
        from app.modules.comments.service import _parse_mentioned_ids

        uid = "550e8400-e29b-41d4-a716-446655440000"
        html = f'<span data-user-id="{uid}">@Alice</span>'
        result = _parse_mentioned_ids(html)
        assert uid in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@skip_no_db
async def test_create_comment_with_mentions() -> None:
    """POST /tasks/{task_id}/comments stores mentioned_user_ids parsed from body."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}
    mentioned_id = str(uuid.uuid4())

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        project_id = projects[0]["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks", json={"title": "Comment test task"}
        )
        assert r.status_code == 201
        task_id = r.json()["data"]["id"]

        body = f"Hey @{mentioned_id} please review this."
        r = await client.post(
            f"/tasks/{task_id}/comments", json={"body": body}
        )
        assert r.status_code == 201, r.text
        comment = r.json()["data"]
        assert comment["body"] == body
        assert mentioned_id in comment["mentioned_user_ids"]


@pytest.mark.asyncio
@skip_no_db
async def test_create_comment_empty_body_rejected() -> None:
    """POST /tasks/{task_id}/comments rejects an empty body with 422."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        project_id = r.json()["data"][0]["id"]
        r = await client.post(
            f"/projects/{project_id}/tasks", json={"title": "Task for empty comment"}
        )
        task_id = r.json()["data"]["id"]

        r = await client.post(
            f"/tasks/{task_id}/comments", json={"body": "   "}
        )
        assert r.status_code == 422
