"""Tests for project code + task_number / task_key features (Feature #3)."""

import re

import pytest
from httpx import AsyncClient

from app.modules.organizations.models import Organization
from app.modules.projects.service import _derive_code
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
# Integration tests — shared in-process fixtures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_assigns_task_key(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Creating a task returns a non-null task_key equal to {project.code}-{task_number}."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Task Key Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()["data"]

    response = await client.post(
        f"/projects/{project['id']}/tasks",
        json={"title": "Test task key assignment"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    task = response.json()["data"]
    assert task["task_number"] is not None
    assert task["task_key"] == f"{project['code']}-{task['task_number']}"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_task_by_key(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """GET /tasks/by-key/{key} resolves the task created with that key."""

    _, token = user

    project_response = await client.post(
        "/projects",
        json={"name": "Resolve By Key Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Resolve-by-key test"},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    created = task_response.json()["data"]
    task_key = created["task_key"]

    response = await client.get(f"/tasks/by-key/{task_key}", headers=_auth(token))
    assert response.status_code == 200
    resolved = response.json()["data"]
    assert resolved["task_key"] == task_key
    assert resolved["id"] == created["id"]
