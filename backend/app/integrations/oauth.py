"""Generic OAuth handshake orchestration (design.md "Data Flow"). Delegates
every provider-specific detail to the registered ``IntegrationAdapter`` —
this module never branches on ``provider`` (IP-R3, "el núcleo delega el
canje de tokens al adaptador, sin lógica específica del proveedor en el
núcleo").

``build_authorize``/``handle_callback`` elaborate design.md's simplified
pseudocode signatures with the state ``payload``/``ttl`` plumbing a caller
needs in practice: the OAuth callback route is GLOBAL
(``GET /connectors/oauth/callback``, no ``{id}`` in the path), so the
``state`` payload popped by ``handle_callback`` — not a path parameter — is
what tells the caller which connector/user this callback belongs to
(specs/connectors/spec.md, "el `state` transporta la referencia al
conector/usuario").
"""

import secrets
from collections.abc import Sequence
from typing import Any

from app.integrations import state_store
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import IntegrationAdapter


class StateNotFoundError(Exception):
    """Raised when a callback's ``state`` is missing, expired or reused."""

    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"OAuth state not found or expired: {state}")


async def build_authorize(
    adapter: IntegrationAdapter,
    redirect_uri: str,
    scopes: Sequence[str],
    *,
    state_payload: dict[str, Any],
    ttl: int,
) -> tuple[str, str]:
    """Generate a CSRF ``state``, persist ``state_payload`` with ``ttl`` and
    return ``(state, authorize_url)`` for ``adapter``."""

    state = secrets.token_urlsafe(32)
    await state_store.put(state, state_payload, ttl)
    url = adapter.authorize_url(state, redirect_uri, scopes)
    return state, url


async def handle_callback(
    adapter: IntegrationAdapter, code: str, state: str, redirect_uri: str
) -> tuple[dict[str, Any], OAuthTokens]:
    """Pop+validate ``state`` and exchange ``code`` for tokens via ``adapter``.

    Returns ``(state_payload, tokens)``. Raises :class:`StateNotFoundError`
    when ``state`` does not exist in Redis (missing/expired/already
    consumed — single-use anti-replay, specs/connectors/spec.md); the code
    is NEVER exchanged in that case, so nothing is created/updated.
    """

    payload = await state_store.pop(state)
    if payload is None:
        raise StateNotFoundError(state)
    tokens = await adapter.exchange_code(code, redirect_uri)
    return payload, tokens
