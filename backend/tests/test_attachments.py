"""Tests for file attachment upload and download (Feature #8)."""

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
        json={"name": "Attachments Project", "methodology": "kanban"},
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


class TestAttachmentServiceHelpers:
    """Validate helper constants and blocked-type list."""

    def test_max_size_constant(self) -> None:
        from app.modules.attachments.service import _MAX_UPLOAD_BYTES

        assert _MAX_UPLOAD_BYTES == 10 * 1024 * 1024

    def test_blocked_types_contains_executables(self) -> None:
        from app.modules.attachments.service import _BLOCKED_TYPES

        assert "application/x-msdownload" in _BLOCKED_TYPES
        assert "application/x-sh" in _BLOCKED_TYPES


# ---------------------------------------------------------------------------
# Integration tests — shared in-process fixtures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_upload_and_download_attachment(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /tasks/{task_id}/attachments → GET /attachments/{id}/download round-trip."""

    _, token = user
    task_id = await _create_task(client, token, "Attachment test task")
    file_content = b"Hello, this is a test attachment."

    upload = await client.post(
        f"/tasks/{task_id}/attachments",
        files={"file": ("test.txt", file_content, "text/plain")},
        headers=_auth(token),
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["data"]
    assert attachment["original_name"] == "test.txt"
    assert attachment["content_type"] == "text/plain"
    assert attachment["size_bytes"] == len(file_content)

    download = await client.get(
        f"/attachments/{attachment['id']}/download", headers=_auth(token)
    )
    assert download.status_code == 200
    assert download.content == file_content


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_upload_rejects_oversized_file(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """POST /tasks/{task_id}/attachments rejects files larger than 10 MB with 413."""

    _, token = user
    task_id = await _create_task(client, token, "Oversized upload test")
    # 10 MB + 1 byte.
    big_content = b"x" * (10 * 1024 * 1024 + 1)

    upload = await client.post(
        f"/tasks/{task_id}/attachments",
        files={"file": ("big.bin", big_content, "application/octet-stream")},
        headers=_auth(token),
    )
    assert upload.status_code == 413
    assert upload.json()["code"] == "file_too_large"
