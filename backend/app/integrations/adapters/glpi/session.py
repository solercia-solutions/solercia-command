"""GLPI ``session_token`` cache in Redis (change 17-adapter-glpi,
specs/glpi-adapter/spec.md "Autenticación api_token vía initSession con
session_token cacheado"). Mirrors ``app/integrations/state_store.py``'s
module-qualified-reference convention (``from app.shared import redis as
shared_redis`` + ``shared_redis.get_redis_client()``) so tests can
monkeypatch ``app.shared.redis.get_redis_client`` via the ``patched_redis``
conftest fixture.

Isolated by ``connector_id`` (GA-R7, "aislamiento multi-tenant"): the Redis
key is ``glpi:session:{connector_id}``, never shared across connectors even
when two organizations point at the SAME GLPI instance.

NEVER logs/interpolates ``session_token``/``app_token``/``user_token`` —
every log line here references ``connector_id`` only (Threat Matrix, "sin
fuga de secretos").
"""

import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.glpi.client import GlpiClient
from app.shared import redis as shared_redis

logger = logging.getLogger("solercia.glpi.session")

_KEY_PREFIX = "glpi:session:"


def _key(connector_id: str) -> str:
    return f"{_KEY_PREFIX}{connector_id}"


async def get_or_init_session(
    connector_id: str,
    client: GlpiClient,
    app_token: str,
    user_token: str,
    *,
    settings: Settings = default_settings,
) -> str:
    """Return the cached ``session_token`` for ``connector_id``.

    A cache hit is returned as-is, WITHOUT calling ``initSession`` again
    (specs/glpi-adapter/spec.md, "Llamada subsiguiente reutiliza el
    cache"). A cache miss calls ``client.init_session`` and ``SETEX``s the
    result under ``glpi:session:{connector_id}`` with
    ``settings.GLPI_SESSION_TTL_SECONDS``.
    """

    redis_client = shared_redis.get_redis_client()
    cached: str | None = await redis_client.get(_key(connector_id))
    if cached is not None:
        return cached

    logger.info(
        "Sin session_token cacheado para connector_id=%s; iniciando sesión GLPI.",
        connector_id,
    )
    session_token = await client.init_session(app_token, user_token)
    await redis_client.set(
        _key(connector_id), session_token, ex=settings.GLPI_SESSION_TTL_SECONDS
    )
    return session_token


async def invalidate_session(connector_id: str) -> None:
    """Delete the cached ``session_token`` for ``connector_id``, if any."""

    redis_client = shared_redis.get_redis_client()
    await redis_client.delete(_key(connector_id))


async def with_session_retry[T](
    connector_id: str,
    client: GlpiClient,
    app_token: str,
    user_token: str,
    operation: Callable[[str], Awaitable[T]],
    *,
    settings: Settings = default_settings,
) -> T:
    """Run ``operation(session_token)`` using the cached/just-initialized
    session; on a ``401`` (expired/invalid session), invalidate the cache,
    reinitialize via ``initSession`` and retry ``operation`` exactly ONCE
    with the fresh token — transparent to the caller
    (specs/glpi-adapter/spec.md, "Reinicio de sesión ante expiración").

    If the reinit itself fails (revoked credentials), the underlying
    ``httpx.HTTPStatusError`` propagates and NO ``session_token`` — valid
    or invalid — is left cached (``invalidate_session`` already ran before
    the failed reinit attempt).
    """

    session_token = await get_or_init_session(
        connector_id, client, app_token, user_token, settings=settings
    )
    try:
        return await operation(session_token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        logger.warning(
            "GLPI rechazó el session_token vigente para connector_id=%s "
            "(401); invalidando cache y reiniciando sesión.",
            connector_id,
        )
        await invalidate_session(connector_id)
        # NOT wrapped in try/except: a failed reinit propagates as-is —
        # `invalidate_session` above already guarantees no stale/invalid
        # token is left cached regardless of what happens next.
        session_token = await client.init_session(app_token, user_token)
        redis_client = shared_redis.get_redis_client()
        await redis_client.set(
            _key(connector_id), session_token, ex=settings.GLPI_SESSION_TTL_SECONDS
        )
        return await operation(session_token)
