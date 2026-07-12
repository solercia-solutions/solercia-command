"""Tests for the shared pagination module (``app/shared/pagination.py``).

Covers the three building blocks consumed by every list endpoint:
``pagination_params`` (validation), ``paginate`` (ORDER BY/LIMIT/OFFSET/COUNT)
and ``build_list_meta`` (envelope ``meta`` merging without dropping foreign
keys, e.g. menus' ``tree``).
"""

import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.shared.exceptions import register_exception_handlers
from app.shared.pagination import (
    PaginationParams,
    build_list_meta,
    paginate,
    pagination_params,
)
from tests.conftest import skip_no_db

# ---------------------------------------------------------------------------
# pagination_params — validation (no DB needed: isolated probe app)
# ---------------------------------------------------------------------------


def _build_probe_app() -> FastAPI:
    """A throwaway app exposing ``pagination_params`` as its only route.

    Lets the dependency's ``Query(...)`` validation run through a real
    request cycle without wiring any domain router.
    """

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/probe")
    async def probe(params: PaginationParams = Depends(pagination_params)) -> dict:
        return {
            "page": params.page,
            "size": params.size,
            "sort": params.sort,
            "order": params.order,
            "requested": params.requested,
        }

    return app


@pytest.mark.asyncio
async def test_pagination_params_defaults_without_query_string() -> None:
    """No query params → ``size=20``, ``order='desc'``, nothing requested."""

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {
        "page": None,
        "size": 20,
        "sort": None,
        "order": "desc",
        "requested": False,
    }


@pytest.mark.asyncio
async def test_pagination_params_page_below_one_is_422() -> None:
    """``page=0`` violates ``ge=1`` and never reaches the route body."""

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe", params={"page": 0})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "errors" in body


@pytest.mark.asyncio
async def test_pagination_params_size_above_max_is_422() -> None:
    """``size=101`` violates ``le=100``."""

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe", params={"size": 101})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_pagination_params_order_outside_asc_desc_is_422() -> None:
    """``order`` only accepts the literal ``asc``/``desc``."""

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe", params={"order": "sideways"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_pagination_params_page_and_sort_mark_requested() -> None:
    """Supplying ``page`` or ``sort`` flips ``requested`` to ``True``."""

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        by_page = await client.get("/probe", params={"page": 2})
        by_sort = await client.get("/probe", params={"sort": "email"})

    assert by_page.json()["requested"] is True
    assert by_page.json() == {
        "page": 2,
        "size": 20,
        "sort": None,
        "order": "desc",
        "requested": True,
    }
    assert by_sort.json()["requested"] is True


# ---------------------------------------------------------------------------
# paginate() — ORDER BY / LIMIT / OFFSET / COUNT against a real table
# ---------------------------------------------------------------------------


async def _seed_users(session: AsyncSession, count: int) -> list[User]:
    users = [
        User(
            email=f"pagination-{i:02d}-{uuid.uuid4().hex[:8]}@example.com",
            primer_nombre=f"User{i:02d}",
            primer_apellido="Pagination",
            hashed_password="x",
        )
        for i in range(count)
    ]
    session.add_all(users)
    await session.flush()
    return users


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_paginate_applies_order_by_limit_offset_and_count(
    session: AsyncSession,
) -> None:
    """A slice of a 25-row table returns the right page and the full total."""

    await _seed_users(session, 25)
    stmt = select(User).where(User.primer_apellido == "Pagination")
    params = PaginationParams(page=2, size=10, sort="email", order="asc")
    sortable = {"email": User.email}

    rows, total = await paginate(session, stmt, params, sortable)

    assert total == 25
    assert len(rows) == 10
    emails = [row.email for row in rows]
    assert emails == sorted(emails)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_paginate_last_page_returns_remainder(
    session: AsyncSession,
) -> None:
    """Triangulation: a non-full last page still returns the correct remainder."""

    await _seed_users(session, 5)
    stmt = select(User).where(User.primer_apellido == "Pagination")
    params = PaginationParams(page=1, size=3, sort="email", order="asc")
    sortable = {"email": User.email}

    first_page, total = await paginate(session, stmt, params, sortable)
    second_page, _ = await paginate(
        session, stmt, PaginationParams(page=2, size=3, sort="email", order="asc"), sortable
    )

    assert total == 5
    assert len(first_page) == 3
    assert len(second_page) == 2


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_paginate_sort_outside_whitelist_raises_422_without_querying(
    session: AsyncSession,
) -> None:
    """A ``sort`` key absent from ``sortable`` is rejected before hitting the DB."""

    from app.shared.exceptions import AppException

    stmt = select(User).where(User.primer_apellido == "Pagination")
    params = PaginationParams(page=1, size=10, sort="hashed_password", order="asc")
    sortable = {"email": User.email}

    with pytest.raises(AppException) as exc_info:
        await paginate(session, stmt, params, sortable)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_sort_field"


# ---------------------------------------------------------------------------
# build_list_meta() — additive merge, never drops foreign keys
# ---------------------------------------------------------------------------


def test_build_list_meta_without_params_returns_only_total() -> None:
    """The byte-compat path: no params → ``meta`` is exactly ``{total}``."""

    params = PaginationParams(page=None, size=20, sort=None, order="desc")

    meta = build_list_meta(params, total=7)

    assert meta == {"total": 7}


def test_build_list_meta_with_params_returns_page_size_total() -> None:
    """The paginated path adds ``page``/``size`` alongside ``total``."""

    params = PaginationParams(page=2, size=10, sort="created_at", order="desc")

    meta = build_list_meta(params, total=25)

    assert meta == {"page": 2, "size": 10, "total": 25}


def test_build_list_meta_preserves_foreign_keys_like_menus_tree() -> None:
    """Merging over an existing ``meta`` (e.g. menus' ``tree``) keeps it intact."""

    params = PaginationParams(page=None, size=20, sort=None, order="desc")
    existing = {"tree": [{"id": "root", "children": []}]}

    meta_without_params = build_list_meta(params, total=3, base=existing)
    meta_with_params = build_list_meta(
        PaginationParams(page=1, size=20, sort=None, order="desc"),
        total=3,
        base=existing,
    )

    assert meta_without_params == {"total": 3, "tree": existing["tree"]}
    assert meta_with_params == {
        "page": 1,
        "size": 20,
        "total": 3,
        "tree": existing["tree"],
    }
