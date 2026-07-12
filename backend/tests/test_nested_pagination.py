"""Pagination tests for ``GET /tasks/{task_id}/comments``,
``GET /tasks/{task_id}/attachments`` and ``GET /alert-rules`` (R1, R2, R3).

Sort/order scenarios avoid ``created_at`` and instead use a deterministic
text field: Postgres ``now()`` is transaction-scoped, so every write inside
the shared SAVEPOINT session gets the SAME ``created_at`` (see
test_tasks_pagination.py).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alert_rules.models import AlertRule
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_task_project(client: AsyncClient, token: str) -> tuple[str, str]:
    project_response = await client.post(
        "/projects",
        json={"name": "Nested Pagination Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["data"]["id"]

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Host task"},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
    task_id = task_response.json()["data"]["id"]
    return project_id, task_id


async def _create_comments(
    client: AsyncClient, token: str, task_id: str, bodies: list[str]
) -> None:
    for body in bodies:
        response = await client.post(
            f"/tasks/{task_id}/comments",
            json={"body": body},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text


async def _upload_attachments(
    client: AsyncClient, token: str, task_id: str, names: list[str]
) -> None:
    for name in names:
        response = await client.post(
            f"/tasks/{task_id}/attachments",
            files={"file": (name, b"content", "text/plain")},
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text


async def _seed_alert_rules(
    session: AsyncSession, tenant: Organization, rule_types: list[str]
) -> None:
    for rule_type in rule_types:
        session.add(AlertRule(organization_id=tenant.id, rule_type=rule_type))
    await session.flush()


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}/comments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_comments_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _create_comments(client, token, task_id, ["Comment A", "Comment B"])

    response = await client.get(f"/tasks/{task_id}/comments", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"total": 2}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_comments_page_and_size_returns_correct_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _create_comments(
        client, token, task_id, ["Comment A", "Comment B", "Comment C", "Comment D", "Comment E"]
    )

    response = await client.get(
        f"/tasks/{task_id}/comments",
        params={"page": 2, "size": 2, "sort": "body", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [c["body"] for c in body["data"]] == ["Comment C", "Comment D"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_comments_sort_outside_whitelist_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)

    response = await client.get(
        f"/tasks/{task_id}/comments",
        params={"sort": "mentioned_user_ids"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_comments_sort_body_desc_orders_results(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _create_comments(client, token, task_id, ["Comment A", "Comment B"])

    response = await client.get(
        f"/tasks/{task_id}/comments",
        params={"sort": "body", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [c["body"] for c in response.json()["data"]] == ["Comment B", "Comment A"]


# ---------------------------------------------------------------------------
# GET /tasks/{task_id}/attachments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_attachments_without_params_is_byte_compatible(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _upload_attachments(client, token, task_id, ["a.txt", "b.txt"])

    response = await client.get(
        f"/tasks/{task_id}/attachments", headers=_auth(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"total": 2}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_attachments_page_and_size_returns_correct_slice(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _upload_attachments(
        client, token, task_id, ["a.txt", "b.txt", "c.txt", "d.txt", "e.txt"]
    )

    response = await client.get(
        f"/tasks/{task_id}/attachments",
        params={"page": 2, "size": 2, "sort": "original_name", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [a["original_name"] for a in body["data"]] == ["c.txt", "d.txt"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_attachments_sort_outside_whitelist_is_422(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)

    response = await client.get(
        f"/tasks/{task_id}/attachments",
        params={"sort": "content_type"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_attachments_sort_name_desc_orders_results(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    _, token = user
    _, task_id = await _create_task_project(client, token)
    await _upload_attachments(client, token, task_id, ["a.txt", "b.txt"])

    response = await client.get(
        f"/tasks/{task_id}/attachments",
        params={"sort": "original_name", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [a["original_name"] for a in response.json()["data"]] == ["b.txt", "a.txt"]


# ---------------------------------------------------------------------------
# GET /alert-rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_alert_rules_without_params_is_byte_compatible(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    _, token = user
    await _seed_alert_rules(session, tenant, ["task_overdue", "sprint_at_risk"])

    response = await client.get("/alert-rules", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"total": 2}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_alert_rules_page_and_size_returns_correct_slice(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    _, token = user
    await _seed_alert_rules(
        session,
        tenant,
        ["rule_a", "rule_b", "rule_c", "rule_d", "rule_e"],
    )

    response = await client.get(
        "/alert-rules",
        params={"page": 2, "size": 2, "sort": "rule_type", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [r["rule_type"] for r in body["data"]] == ["rule_c", "rule_d"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_alert_rules_sort_outside_whitelist_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    _, token = user
    await _seed_alert_rules(session, tenant, ["task_overdue"])

    response = await client.get(
        "/alert-rules", params={"sort": "threshold_params"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_alert_rules_sort_rule_type_desc_orders_results(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    _, token = user
    await _seed_alert_rules(session, tenant, ["rule_a", "rule_b"])

    response = await client.get(
        "/alert-rules",
        params={"sort": "rule_type", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [r["rule_type"] for r in response.json()["data"]] == ["rule_b", "rule_a"]
