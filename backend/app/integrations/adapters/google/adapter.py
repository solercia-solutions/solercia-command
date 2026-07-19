"""``GoogleAdapter`` — the ``IntegrationAdapter`` implementation for Gmail,
Calendar and Drive (change 16-adapter-google, design.md "PRIMER adaptador
Google sobre los puertos del 14"). Read-only; plain OAuth 2.0
(``oauth.py``) — the second real provider over the 14's ports, sibling to
``adapters/microsoft365`` (15).

``capabilities`` deliberately excludes ``external_tasks``/``tickets``:
Google Tasks is out of scope for this first cut (GA-R10, spec.md
"Google Tasks fuera del primer corte") and Google has no ticketing
provider to speak of.
"""

from collections.abc import Sequence

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.google import oauth
from app.integrations.adapters.google.calendar import GoogleCalendarReader
from app.integrations.adapters.google.mail import GmailMailReader
from app.integrations.adapters.google.meeting_notes import DriveMeetingNotesReader
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import (
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)


class GoogleAdapter:
    """Google Workspace adapter — read-only, plain OAuth 2.0."""

    provider = "google"
    capabilities = frozenset(
        {
            Capability.mail,
            Capability.calendar,
            Capability.meeting_notes,
        }
    )

    credential_kind = CredentialKind.oauth

    def __init__(self, settings: Settings = default_settings) -> None:
        self._settings = settings
        self._ports: dict[Capability, object] = {
            Capability.mail: GmailMailReader(settings=settings),
            Capability.calendar: GoogleCalendarReader(settings=settings),
            Capability.meeting_notes: DriveMeetingNotesReader(settings=settings),
        }
        # See `adapters/fake.py`'s identical comment: `oauth = self` exposes
        # the OAuth methods below through the `IntegrationAdapter.oauth`
        # slot the core now reads (change 17, IP17-R2). Never `api_token`.
        self.oauth: OAuthHandshake | None = self
        self.api_token: ApiTokenHandshake | None = None

    def authorize_url(
        self, state: str, redirect_uri: str, scopes: Sequence[str]
    ) -> str:
        """Delegate to ``oauth.authorize_url`` — an empty ``scopes``
        assembles ``oauth.DEFAULT_READONLY_SCOPES`` there; explicit scopes
        are respected unchanged."""

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
        or ``None`` when it is not supported (never declared for
        ``external_tasks``/``tickets``, GA-R10)."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)
