"""Tests for ``get_actor_id`` (R4) — the audit-stamping actor dependency.

Unlike ``get_current_user``, this dependency NEVER raises 401: routes that
require authentication already enforce it via ``get_current_membership``.
``get_actor_id`` exists so audit stamping degrades gracefully to ``NULL``
for writes that happen with no authenticated context (e.g. the alert
scheduler, which calls services directly — no HTTP request at all).
"""

import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_actor_id
from app.shared.security import create_access_token


def _build_probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe(actor_id: uuid.UUID | None = Depends(get_actor_id)) -> dict:
        return {"actor_id": str(actor_id) if actor_id is not None else None}

    return app


@pytest.mark.asyncio
async def test_get_actor_id_returns_uuid_with_valid_jwt() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(str(user_id))

    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/probe", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json()["actor_id"] == str(user_id)


@pytest.mark.asyncio
async def test_get_actor_id_returns_none_without_authorization_header() -> None:
    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe")

    assert response.status_code == 200
    assert response.json()["actor_id"] is None


@pytest.mark.asyncio
async def test_get_actor_id_returns_none_with_malformed_token() -> None:
    transport = ASGITransport(app=_build_probe_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/probe", headers={"Authorization": "Bearer not-a-real-jwt"}
        )

    assert response.status_code == 200
    assert response.json()["actor_id"] is None
