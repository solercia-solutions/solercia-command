"""Tests for task comments and @-mention parsing (Feature #4 — comments part)."""

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_task(client: AsyncClient, token: str, title: str) -> str:
    project_response = await client.post(
        "/projects",
        json={"name": "Comments Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": title},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    return task_response.json()["data"]["id"]


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
# Integration tests — shared in-process fixtures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_comment_with_mentions(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /tasks/{task_id}/comments stores mentioned_user_ids parsed from body."""

    author, token = user
    task_id = await _create_task(client, token, "Comment test task")
    mentioned_id = str(author.id)

    body = f"Hey @{mentioned_id} please review this."
    response = await client.post(
        f"/tasks/{task_id}/comments", json={"body": body}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    comment = response.json()["data"]
    assert comment["body"] == body
    assert mentioned_id in comment["mentioned_user_ids"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_comment_empty_body_rejected(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /tasks/{task_id}/comments rejects a whitespace-only body with 422."""

    _, token = user
    task_id = await _create_task(client, token, "Task for empty comment")

    response = await client.post(
        f"/tasks/{task_id}/comments", json={"body": "   "}, headers=_auth(token)
    )
    assert response.status_code == 422
