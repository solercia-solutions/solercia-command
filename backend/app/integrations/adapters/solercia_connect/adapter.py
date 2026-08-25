"""``SolerciaConnectAdapter`` — read mail, calendar and meeting notes through a
local Solercia Connect runtime.

Connect owns provider integration; Command owns work. The platform decision
record draws that line and forbids crossing it by import
(``docs/decisions/2026-08-23-solercia-platform-decisions.md`` §1, §2.2), so
this adapter is a client of Connect's published loopback contract and nothing
else. Connect decides its own routing — official API first, supervised browser
only as an explicit fallback (§3.1-3.2) — and this adapter never second-guesses
it; it only says whether the fallback is permitted for this connector.

``credential_kind=api_token``: the credential Command holds is the key to the
local runtime, never a provider credential. Microsoft and Google credentials
stay inside Connect, which is the whole point of the split — Command never sees
a token belonging to a person's mailbox.

Following the GLPI precedent, connector-specific fields are packed into
``AccessContext.access_token`` by :func:`encode_access_context` rather than
widening the core's ``AccessContext``.
"""

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.solercia_connect.client import SolerciaConnectClient
from app.integrations.adapters.solercia_connect.errors import (
    SolerciaConnectAccountMismatchError,
    SolerciaConnectAuthError,
    SolerciaConnectConfigError,
    SolerciaConnectProtocolError,
)
from app.integrations.adapters.solercia_connect.mapper import (
    map_calendar_event,
    map_mail_message,
    map_meeting_note,
)
from app.integrations.dtos import AccountRef, CalendarEvent, MailMessage, MeetingNote
from app.integrations.ports import (
    AccessContext,
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)

logger = logging.getLogger("solercia.connect.adapter")

PROVIDER = "solercia_connect"

# Connect names its own targets; these are the ones whose capabilities this
# adapter maps. A connector registers which one it reads.
_TARGETS = frozenset({"outlook", "teams", "onedrive", "gmail", "google_calendar"})

_CAPABILITY_TO_CONNECT = {
    Capability.mail: "mail.sent.list",
    Capability.calendar: "calendar.events.list",
    Capability.meeting_notes: "meeting.transcript.get",
}


def encode_access_context(
    *,
    connector_id: str,
    base_url: str,
    api_key: str,
    account: str,
    target: str,
    allow_browser_fallback: bool = False,
) -> str:
    """Build the opaque payload the ports expect in ``AccessContext.access_token``."""
    return json.dumps(
        {
            "connector_id": connector_id,
            "base_url": base_url,
            "api_key": api_key,
            "account": account,
            "target": target,
            "allow_browser_fallback": allow_browser_fallback,
        },
        separators=(",", ":"),
    )


def _decode_access_context(ctx: AccessContext) -> dict[str, Any]:
    try:
        payload = json.loads(ctx.access_token)
    except (TypeError, ValueError) as failure:
        raise SolerciaConnectConfigError(
            "Solercia Connect access context is not the expected payload"
        ) from failure
    if not isinstance(payload, dict):
        raise SolerciaConnectConfigError("Solercia Connect access context is malformed")
    for key in ("base_url", "api_key", "account", "target"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SolerciaConnectConfigError(
                f"Solercia Connect access context is missing {key!r}"
            )
    if payload["target"] not in _TARGETS:
        raise SolerciaConnectConfigError("Solercia Connect access context names an unknown target")
    return payload


def _canonical(account: str) -> str:
    return account.strip().casefold()


class _ConnectReader:
    """Shared read path for every capability this adapter serves."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or default_settings

    async def read(
        self,
        ctx: AccessContext,
        capability: Capability,
        *,
        since: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        payload = _decode_access_context(ctx)
        client = SolerciaConnectClient(
            base_url=payload["base_url"],
            api_key=payload["api_key"],
            settings=self._settings,
        )
        requested = payload["account"]
        body: dict[str, Any] = {
            "type": payload["target"],
            "account": requested,
            "capability": _CAPABILITY_TO_CONNECT[capability],
            "limit": min(max(limit, 1), 1000),
            "allow_browser_fallback": bool(payload.get("allow_browser_fallback", False)),
        }
        if since is not None:
            # Connect's windows are exact and end-exclusive; it rejects a half
            # window, so both bounds travel together or neither does.
            body["start"] = since.isoformat()
            body["end"] = datetime.now(tz=since.tzinfo).isoformat()

        envelope = await client.run(body)
        if not envelope.get("ok"):
            raise _envelope_failure(envelope)

        observed = envelope.get("account")
        if not isinstance(observed, str) or _canonical(observed) != _canonical(requested):
            # §4.1-4.3: one canonical observed identity before any read, and
            # provenance that never substitutes a requested identity for a
            # verified one. Anything else yields zero records.
            raise SolerciaConnectAccountMismatchError(
                "Solercia Connect answered for an account other than the one requested"
            )

        data = envelope.get("data")
        records = data.get("records") if isinstance(data, dict) else None
        if records is None:
            return []
        if not isinstance(records, list):
            raise SolerciaConnectProtocolError("Solercia Connect returned an unexpected record set")
        return [record for record in records if isinstance(record, dict)]


def _envelope_failure(envelope: Mapping[str, Any]) -> Exception:
    """Map Connect's typed error onto this adapter's own vocabulary."""
    error = envelope.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    detail = message if isinstance(message, str) else "Solercia Connect could not serve the request"
    if code in {"browser_identity_unavailable", "browser_login_required", "authorization_denied"}:
        return SolerciaConnectAuthError(detail)
    if code == "browser_account_mismatch":
        return SolerciaConnectAccountMismatchError(detail)
    return SolerciaConnectProtocolError(detail)


class SolerciaConnectMailPort:
    """``MailReaderPort`` over Connect's ``mail.sent.list``."""

    def __init__(self, reader: _ConnectReader) -> None:
        self._reader = reader

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MailMessage]:
        records = await self._reader.read(ctx, Capability.mail, since=since, limit=limit)
        return [map_mail_message(record) for record in records]


class SolerciaConnectCalendarPort:
    """``CalendarReaderPort`` over Connect's ``calendar.events.list``."""

    def __init__(self, reader: _ConnectReader) -> None:
        self._reader = reader

    async def list_events(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[CalendarEvent]:
        records = await self._reader.read(ctx, Capability.calendar, since=since, limit=limit)
        return [map_calendar_event(record) for record in records]


class SolerciaConnectMeetingNotesPort:
    """``MeetingNotesReaderPort`` over Connect's ``meeting.transcript.get``."""

    def __init__(self, reader: _ConnectReader) -> None:
        self._reader = reader

    async def list_notes(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MeetingNote]:
        records = await self._reader.read(ctx, Capability.meeting_notes, since=since, limit=limit)
        return [map_meeting_note(record) for record in records]


class SolerciaConnectHandshake:
    """``ApiTokenHandshake`` — validate a runtime and observe whose session it holds."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or default_settings

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        base_url = raw.get("base_url", "")
        api_key = raw.get("api_key", "")
        account = raw.get("account", "")
        target = raw.get("target", "")
        if not account.strip():
            raise SolerciaConnectConfigError("A Solercia Connect connector needs an account")
        if target not in _TARGETS:
            raise SolerciaConnectConfigError("A Solercia Connect connector needs a known target")

        client = SolerciaConnectClient(
            base_url=base_url,
            api_key=api_key,
            settings=self._settings,
        )
        # Health is unauthenticated and proves the runtime is reachable and
        # speaks this contract. It deliberately does not prove the provider
        # session: that is observed on the first read, against the identity
        # the provider itself reports.
        await client.health()
        return AccountRef(external_account_id=_canonical(account), display_name=None)


class SolerciaConnectAdapter:
    """``IntegrationAdapter`` for a local Solercia Connect runtime."""

    provider = PROVIDER
    capabilities = frozenset({Capability.mail, Capability.calendar, Capability.meeting_notes})
    credential_kind = CredentialKind.api_token
    credential_kinds = frozenset({CredentialKind.api_token})
    oauth: OAuthHandshake | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        reader = _ConnectReader(settings)
        self.api_token: ApiTokenHandshake | None = SolerciaConnectHandshake(settings)
        self._ports: dict[Capability, object] = {
            Capability.mail: SolerciaConnectMailPort(reader),
            Capability.calendar: SolerciaConnectCalendarPort(reader),
            Capability.meeting_notes: SolerciaConnectMeetingNotesPort(reader),
        }

    def port_for(self, capability: Capability) -> object | None:
        return self._ports.get(capability)
