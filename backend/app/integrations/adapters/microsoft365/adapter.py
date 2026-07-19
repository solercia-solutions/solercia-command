"""``Microsoft365Adapter`` — the ``IntegrationAdapter`` implementation for
Microsoft Graph (change 15-adapter-microsoft365, design.md "PRIMER
adaptador real sobre los puertos del 14"). Read-only; delegated OAuth
(Entra ID) via ``oauth.py``.

``_ports`` starts EMPTY here (Lote 3): the concrete port implementations
(``GraphMailReader``/``GraphCalendarReader``/``GraphExternalTaskReader``/
``GraphMeetingNotesReader``, ``ports.py``) are wired in incrementally by
Lotes 4-7, one capability per lote — ``capabilities`` already declares the
full set this adapter WILL support (spec.md, "Registro del adaptador").
"""

from collections.abc import Sequence

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.microsoft365 import oauth
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import Capability


class Microsoft365Adapter:
    """Microsoft Graph adapter — read-only, delegated OAuth (Entra ID)."""

    provider = "microsoft365"
    capabilities = frozenset(
        {
            Capability.mail,
            Capability.calendar,
            Capability.external_tasks,
            Capability.meeting_notes,
        }
    )

    def __init__(self, settings: Settings = default_settings) -> None:
        self._settings = settings
        self._ports: dict[Capability, object] = {}

    def authorize_url(
        self, state: str, redirect_uri: str, scopes: Sequence[str]
    ) -> str:
        return oauth.authorize_url(
            state, redirect_uri, scopes, settings=self._settings
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        return await oauth.exchange_code(
            code, redirect_uri, settings=self._settings
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        return await oauth.refresh(refresh_token, settings=self._settings)

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when it is not (yet) wired."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)
