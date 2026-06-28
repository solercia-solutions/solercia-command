"""Tests for project code + task_number / task_key features (Feature #3)."""

import re
import uuid

import pytest

from app.modules.projects.service import _derive_code


# ---------------------------------------------------------------------------
# Unit tests — no DB needed
# ---------------------------------------------------------------------------


class TestDeriveCode:
    """ProjectService._derive_code generates consistent, valid codes."""

    def test_single_word_truncated(self) -> None:
        code = _derive_code("Plataforma")
        assert re.match(r"^[A-Z0-9]{2,10}$", code), f"Invalid code: {code}"

    def test_multi_word_initials(self) -> None:
        code = _derive_code("Plataforma Web")
        assert code == "PW"

    def test_three_words(self) -> None:
        code = _derive_code("Soporte Técnico Colombia")
        assert code == "STC"

    def test_special_chars_stripped(self) -> None:
        code = _derive_code("Gestión de Proyectos!")
        assert re.match(r"^[A-Z0-9]{2,10}$", code)

    def test_empty_fallback(self) -> None:
        code = _derive_code("!!!")
        assert code == "PRJ"

    def test_max_length_respected(self) -> None:
        long_name = " ".join("Word" for _ in range(20))
        code = _derive_code(long_name)
        assert len(code) <= 10


class TestTaskKeyParsing:
    """The task key regex _KEY_RE parses valid keys and rejects invalid ones."""

    def test_valid_key(self) -> None:
        from app.modules.tasks.service import _KEY_RE

        m = _KEY_RE.match("SDM-7")
        assert m is not None
        assert m.group(1) == "SDM"
        assert m.group(2) == "7"

    def test_valid_key_long_code(self) -> None:
        from app.modules.tasks.service import _KEY_RE

        m = _KEY_RE.match("PLT2-123")
        assert m is not None

    def test_invalid_key_no_dash(self) -> None:
        from app.modules.tasks.service import _KEY_RE

        assert _KEY_RE.match("SDM7") is None

    def test_invalid_key_too_short(self) -> None:
        from app.modules.tasks.service import _KEY_RE

        assert _KEY_RE.match("S-7") is None

    def test_invalid_key_no_number(self) -> None:
        from app.modules.tasks.service import _KEY_RE

        assert _KEY_RE.match("SDM-") is None


# ---------------------------------------------------------------------------
# Integration tests — require TEST_DATABASE_URL
# ---------------------------------------------------------------------------

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


@pytest.mark.asyncio
@skip_no_db
async def test_create_task_assigns_task_key() -> None:
    """Creating a task returns a response with a non-null task_key."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        # List projects to get a valid project_id.
        r = await client.get("/projects")
        assert r.status_code == 200
        projects = r.json()["data"]
        assert projects, "No projects found — run seed first"

        project_id = projects[0]["id"]

        payload = {"title": "Test task key assignment"}
        r = await client.post(f"/projects/{project_id}/tasks", json=payload)
        assert r.status_code == 201, r.text
        task = r.json()["data"]
        assert task["task_number"] is not None
        assert task["task_key"] is not None
        code = task["task_key"].split("-")[0]
        number = int(task["task_key"].split("-")[1])
        assert number == task["task_number"]
        assert code == projects[0]["code"]


@pytest.mark.asyncio
@skip_no_db
async def test_get_task_by_key() -> None:
    """GET /tasks/by-key/{key} resolves the task created above."""

    import os

    import httpx

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    token = os.getenv("TEST_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=base_url, headers=headers) as client:
        r = await client.get("/projects")
        projects = r.json()["data"]
        project_id = projects[0]["id"]
        code = projects[0]["code"]

        # Create a task to resolve.
        r = await client.post(
            f"/projects/{project_id}/tasks", json={"title": "Resolve-by-key test"}
        )
        assert r.status_code == 201
        task_key = r.json()["data"]["task_key"]

        # Resolve it.
        r = await client.get(f"/tasks/by-key/{task_key}")
        assert r.status_code == 200
        resolved = r.json()["data"]
        assert resolved["task_key"] == task_key
