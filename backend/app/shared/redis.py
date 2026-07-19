"""Shared Redis client factory.

Single, process-wide async client for any module that needs Redis directly.
``app/integrations/state_store.py`` (change 14-integration-ports) is the
FIRST real consumer — before this, ``REDIS_URL`` was declared in
``Settings`` but never actually connected to (only a TODO of lock in
``app/alerts/evaluator.py``). Change 20 reuses this SAME factory, hence its
own module under ``app/shared`` rather than ``app/integrations``.

Built lazily via ``@lru_cache`` so importing this module never opens a
connection; the first caller to actually use Redis triggers the connection
pool. Tests never touch this factory directly — they monkeypatch it via a
MODULE-qualified reference (see ``tests/conftest.py``'s ``patched_redis``
fixture) so ``fakeredis`` stands in without any real Redis connection.
"""

from functools import lru_cache

import redis.asyncio as redis

from app.config import settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """Return a cached, process-wide asyncio Redis client.

    ``socket_connect_timeout``/``socket_timeout`` bound how long a caller
    can hang against an unreachable or overloaded Redis instead of blocking
    indefinitely — a slow/dead Redis must fail fast, not stall the request.
    """

    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
