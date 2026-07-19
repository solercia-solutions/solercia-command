"""Shared base for the Google adapter's read-only ports (change
16-adapter-google). ``mail.py``/``calendar.py``/``meeting_notes.py`` each
duplicated this EXACT plumbing verbatim (``limit`` bounding/defaulting,
``since`` defaulting, ``oauth.refresh`` wiring and :class:`GoogleClient`
construction) — same role as the 15's ``_GraphPortBase``
(``adapters/microsoft365/ports.py``). Parametrized by the target Google
API's ``base_url`` setting name so each concrete port only supplies which
API it talks to.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.google import oauth
from app.integrations.adapters.google.client import GOOGLE_PAGE_CAP, GoogleClient
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import AccessContext


class _GooglePortBase:
    """Shared plumbing for every Google-backed read port. Subclasses set
    ``_base_url_setting`` to the ``Settings`` attribute name for their
    target API (e.g. ``"GOOGLE_GMAIL_BASE_URL"``)."""

    _base_url_setting: str

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def _bounded_limit(self, limit: int | None) -> int:
        """``limit=None`` (caller didn't pass one — every Google port's
        ``list_*`` keeps the Protocol's ``limit`` parameter, just without a
        hardcoded literal default) resolves to ``GOOGLE_DEFAULT_LIMIT``
        BEFORE the usual ``GOOGLE_MAX_LIMIT`` clamp — the effective default
        this setting exists to control."""

        effective = self._settings.GOOGLE_DEFAULT_LIMIT if limit is None else limit
        return max(0, min(effective, self._settings.GOOGLE_MAX_LIMIT))

    def _page_size(self, limit: int | None) -> int:
        return min(self._bounded_limit(limit), GOOGLE_PAGE_CAP) or 1

    def _since_or_default(self, since: datetime | None) -> datetime:
        if since is not None:
            return since
        return datetime.now(UTC) - timedelta(
            days=self._settings.GOOGLE_DEFAULT_SINCE_DAYS
        )

    def _refresh(self) -> Callable[[str], Awaitable[OAuthTokens]]:
        async def _call(refresh_token: str) -> OAuthTokens:
            return await oauth.refresh(
                refresh_token, settings=self._settings, transport=self._transport
            )

        return _call

    def _client(self, ctx: AccessContext) -> GoogleClient:
        return GoogleClient(
            ctx,
            base_url=getattr(self._settings, self._base_url_setting),
            transport=self._transport,
            settings=self._settings,
            refresh=self._refresh(),
        )
