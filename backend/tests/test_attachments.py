"""Tests for file attachment upload and download (Feature #8)."""

import io

import pytest

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


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
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@skip_no_db
async def test_upload_and_download_attachment() -> None:
    """POST /tasks/{task_id}/attachments → GET /attachments/{id}/download round-trip."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}
    file_content = b"Hello, this is a test attachment."

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        project_id = r.json()["data"][0]["id"]

        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Attachment test task"},
        )
        assert r.status_code == 201
        task_id = r.json()["data"]["id"]

        # Upload.
        r = await client.post(
            f"/tasks/{task_id}/attachments",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert r.status_code == 201, r.text
        attachment = r.json()["data"]
        assert attachment["original_name"] == "test.txt"
        assert attachment["content_type"] == "text/plain"
        assert attachment["size_bytes"] == len(file_content)

        # Download.
        attachment_id = attachment["id"]
        r = await client.get(f"/attachments/{attachment_id}/download")
        assert r.status_code == 200
        assert r.content == file_content


@pytest.mark.asyncio
@skip_no_db
async def test_upload_rejects_oversized_file() -> None:
    """POST /tasks/{task_id}/attachments rejects files larger than 10 MB."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}
    # 10 MB + 1 byte.
    big_content = b"x" * (10 * 1024 * 1024 + 1)

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        project_id = r.json()["data"][0]["id"]
        r = await client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Oversized upload test"},
        )
        task_id = r.json()["data"]["id"]

        r = await client.post(
            f"/tasks/{task_id}/attachments",
            files={"file": ("big.bin", io.BytesIO(big_content), "application/octet-stream")},
        )
        assert r.status_code == 413


@pytest.mark.asyncio
@skip_no_db
async def test_download_requires_auth() -> None:
    """GET /attachments/{id}/download returns 401 without a token."""

    import os
    import uuid

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    async with httpx.AsyncClient(base_url=base_url) as client:
        r = await client.get(f"/attachments/{uuid.uuid4()}/download")
        assert r.status_code == 401
