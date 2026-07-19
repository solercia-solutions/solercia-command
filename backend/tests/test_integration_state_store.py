"""RED tests for the OAuth `state` store (Redis, single-use — design.md
"state OAuth en Redis", decisión ratificada #2). Uses `fakeredis` via the
`patched_redis` conftest fixture so no real Redis is ever touched.
"""

import asyncio

import pytest

from app.integrations import state_store


@pytest.mark.asyncio
async def test_put_then_pop_returns_payload_once(patched_redis) -> None:
    """put()+pop() round-trips the payload exactly once."""

    await state_store.put("state-abc", {"connector_id": "conn-1"}, ttl=60)

    first = await state_store.pop("state-abc")
    assert first == {"connector_id": "conn-1"}


@pytest.mark.asyncio
async def test_second_pop_of_the_same_state_returns_none(patched_redis) -> None:
    """A second pop() of an already-consumed state returns None — GETDEL,
    the anti-replay boundary the OAuth callback relies on."""

    await state_store.put("state-xyz", {"connector_id": "conn-2"}, ttl=60)
    await state_store.pop("state-xyz")

    second = await state_store.pop("state-xyz")
    assert second is None


@pytest.mark.asyncio
async def test_pop_after_ttl_expiry_returns_none(patched_redis) -> None:
    """A state whose TTL already elapsed is treated as absent."""

    await state_store.put("state-expiring", {"connector_id": "conn-3"}, ttl=1)
    await asyncio.sleep(1.2)

    assert await state_store.pop("state-expiring") is None


# ---------------------------------------------------------------------------
# Redis caído — traducción a AppException 503 (Fix WARNING 14-integration-ports,
# revisión 4R). Both `put` and `pop` must never leak a raw ``RedisError``.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_translates_redis_errors_to_a_503_app_exception(
    patched_redis, monkeypatch
) -> None:
    """A Redis connection failure on ``put()`` surfaces as a 503
    ``AppException`` with a stable code, never a raw ``ConnectionError``."""

    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.shared.exceptions import AppException

    async def _boom(*args, **kwargs):
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr(patched_redis, "set", _boom)

    with pytest.raises(AppException) as exc_info:
        await state_store.put("state-unavailable", {"connector_id": "conn-1"}, ttl=60)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "integration_state_unavailable"


@pytest.mark.asyncio
async def test_pop_translates_redis_errors_to_a_503_app_exception(
    patched_redis, monkeypatch
) -> None:
    """Same translation on ``pop()`` — the OAuth callback's read path."""

    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.shared.exceptions import AppException

    async def _boom(*args, **kwargs):
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr(patched_redis, "getdel", _boom)

    with pytest.raises(AppException) as exc_info:
        await state_store.pop("state-unavailable")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "integration_state_unavailable"
