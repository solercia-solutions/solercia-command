"""Pagination tests for ``GET /notifications`` (R1, R2, R3).

Notifications aren't created through a public POST endpoint, so tests seed
rows directly via the ``session`` fixture and read them back through the
in-process ``client``.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.shared.enums import NotificationStatus
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_notifications(
    session: AsyncSession, tenant: Organization, recipient_id, titles: list[str]
) -> None:
    for index, title in enumerate(titles):
        session.add(
            Notification(
                organization_id=tenant.id,
                recipient_user_id=recipient_id,
                rule_type="task_overdue",
                title=title,
                body=f"Body {index}",
                dedup_key=f"pagination-test-{tenant.id}-{index}",
                status=NotificationStatus.active,
            )
        )
    await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_without_params_is_byte_compatible(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """No pagination params → full collection, ``meta`` is exactly ``{total}``."""

    created_user, token = user
    await _seed_notifications(
        session, tenant, created_user.id, ["Alert 00", "Alert 01", "Alert 02"]
    )

    response = await client.get("/notifications", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3
    assert body["meta"] == {"total": 3}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_page_and_size_returns_correct_slice(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``?page=2&size=2&sort=title`` returns the third/fourth alphabetical rows."""

    created_user, token = user
    await _seed_notifications(
        session,
        tenant,
        created_user.id,
        ["Alert 00", "Alert 01", "Alert 02", "Alert 03", "Alert 04"],
    )

    response = await client.get(
        "/notifications",
        params={"page": 2, "size": 2, "sort": "title", "order": "asc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"page": 2, "size": 2, "total": 5}
    assert [n["title"] for n in body["data"]] == ["Alert 02", "Alert 03"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_sort_outside_whitelist_is_422(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """A field outside the whitelist (e.g. the raw ``body`` text) is rejected."""

    created_user, token = user
    await _seed_notifications(session, tenant, created_user.id, ["Alert 00"])

    response = await client.get(
        "/notifications", params={"sort": "body"}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sort_field"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_sort_title_desc_orders_results(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """``?sort=title&order=desc`` returns 200 ordered descending.

    Uses ``title`` (not ``created_at``, per the tasks.md scenario) because
    Postgres ``now()`` is transaction-scoped: every write inside the shared
    SAVEPOINT session gets the SAME ``created_at``, so it can't discriminate
    order. ``title`` exercises the identical code path deterministically.
    """

    created_user, token = user
    await _seed_notifications(
        session, tenant, created_user.id, ["Alert 00", "Alert 01", "Alert 02"]
    )

    response = await client.get(
        "/notifications",
        params={"sort": "title", "order": "desc"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert [n["title"] for n in response.json()["data"]] == [
        "Alert 02",
        "Alert 01",
        "Alert 00",
    ]
