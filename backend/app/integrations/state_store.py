"""OAuth ``state`` (CSRF) storage in Redis (design.md "state OAuth en
Redis", decisión ratificada #2). Single-use: ``pop`` performs ``GETDEL`` so
a state can be consumed exactly once — the anti-replay boundary the
callback relies on (specs/connectors/spec.md, "Reutilización del state es
rechazada").

Calls ``shared_redis.get_redis_client()`` through the MODULE (not a direct
``from ... import get_redis_client``) so tests can monkeypatch
``app.shared.redis.get_redis_client`` and have it take effect here — see
``tests/conftest.py``'s ``patched_redis`` fixture.
"""

import json
from typing import Any

from redis.exceptions import RedisError

from app.shared import redis as shared_redis
from app.shared.exceptions import AppException

_KEY_PREFIX = "oauth:state:"

_UNAVAILABLE_MESSAGE = (
    "El servicio de autorización no está disponible en este momento. "
    "Inténtalo de nuevo en unos minutos."
)


def _key(state: str) -> str:
    return f"{_KEY_PREFIX}{state}"


def _unavailable(exc: Exception) -> AppException:
    return AppException(
        _UNAVAILABLE_MESSAGE,
        code="integration_state_unavailable",
        status_code=503,
    )


async def put(state: str, payload: dict[str, Any], ttl: int) -> None:
    """Persist ``payload`` under ``state`` with a ``ttl``-second expiry."""

    client = shared_redis.get_redis_client()
    try:
        await client.set(_key(state), json.dumps(payload), ex=ttl)
    except RedisError as exc:
        raise _unavailable(exc) from exc


async def pop(state: str) -> dict[str, Any] | None:
    """Atomically read-and-delete ``state``'s payload.

    Returns ``None`` when the state does not exist — missing, expired or
    already consumed by a previous callback are indistinguishable by design
    (Redis does not tell them apart either). A Redis-level failure (down,
    timeout) is a DIFFERENT case and is translated to a 503
    ``AppException`` instead — never confused with an absent/expired state.
    """

    client = shared_redis.get_redis_client()
    try:
        raw = await client.getdel(_key(state))
    except RedisError as exc:
        raise _unavailable(exc) from exc
    if raw is None:
        return None
    result: dict[str, Any] = json.loads(raw)
    return result
