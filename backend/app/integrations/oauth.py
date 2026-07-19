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

Both functions now check ``adapter.credential_kind`` FIRST (change
17-adapter-glpi, IP17-R2, MODIFIED Requirement "Protocolo de adaptador
uniforme", scenario "Adaptador `api_token` no participa del flujo OAuth")
— an ``api_token`` adapter (GLPI) is rejected with
:class:`CredentialKindMismatchError` BEFORE any ``state`` is generated
(``build_authorize``) or consumed (``handle_callback``); neither
``state_store.put`` nor ``state_store.pop`` is ever reached in that case.
"""

import secrets
from collections.abc import Sequence
from typing import Any

from app.integrations import state_store
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import CredentialKind, IntegrationAdapter


class StateNotFoundError(Exception):
    """Raised when a callback's ``state`` is missing, expired or reused."""

    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"OAuth state not found or expired: {state}")


class CredentialKindMismatchError(Exception):
    """Raised when the OAuth handshake is attempted against an adapter whose
    ``credential_kind`` is not ``oauth`` (e.g. GLPI's ``api_token``, change
    17-adapter-glpi) — the adapter must use direct credential registration
    instead (``app/modules/connectors/service.py``'s
    ``register_api_token_credentials``, change 17 Lote 3)."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"El adaptador {provider!r} no admite el flujo OAuth "
            "(authorize/callback); usa el registro directo de credenciales."
        )


def _require_oauth_handshake(adapter: IntegrationAdapter) -> None:
    if adapter.credential_kind != CredentialKind.oauth or adapter.oauth is None:
        raise CredentialKindMismatchError(adapter.provider)


async def build_authorize(
    adapter: IntegrationAdapter,
    redirect_uri: str,
    scopes: Sequence[str],
    *,
    state_payload: dict[str, Any],
    ttl: int,
) -> tuple[str, str]:
    """Generate a CSRF ``state``, persist ``state_payload`` with ``ttl`` and
    return ``(state, authorize_url)`` for ``adapter``.

    Raises :class:`CredentialKindMismatchError` for a non-``oauth`` adapter
    BEFORE generating any ``state`` (change 17, IP17-R2).
    """

    _require_oauth_handshake(adapter)
    state = secrets.token_urlsafe(32)
    await state_store.put(state, state_payload, ttl)
    url = adapter.oauth.authorize_url(state, redirect_uri, scopes)  # type: ignore[union-attr]
    return state, url


async def handle_callback(
    adapter: IntegrationAdapter, code: str, state: str, redirect_uri: str
) -> tuple[dict[str, Any], OAuthTokens]:
    """Pop+validate ``state`` and exchange ``code`` for tokens via ``adapter``.

    Returns ``(state_payload, tokens)``. Raises
    :class:`CredentialKindMismatchError` for a non-``oauth`` adapter BEFORE
    ever touching ``state_store`` (change 17, IP17-R2). Raises
    :class:`StateNotFoundError` when ``state`` does not exist in Redis
    (missing/expired/already consumed — single-use anti-replay,
    specs/connectors/spec.md); the code is NEVER exchanged in that case, so
    nothing is created/updated.
    """

    _require_oauth_handshake(adapter)
    payload = await state_store.pop(state)
    if payload is None:
        raise StateNotFoundError(state)
    tokens = await adapter.oauth.exchange_code(code, redirect_uri)  # type: ignore[union-attr]
    return payload, tokens
