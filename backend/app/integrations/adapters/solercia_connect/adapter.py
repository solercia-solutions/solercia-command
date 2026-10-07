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
from datetime import UTC, datetime, timedelta
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
    Capability.calendar: "calendar.events.list",
    Capability.meeting_notes: "meeting.transcript.get",
}

# Which of this adapter's capabilities each target actually serves — mirrors
# Connect's ``/v1/providers``. The adapter declares the union so intake knows
# what it MAY read; a target that lacks one answers "nothing" locally, because
# asking Connect for it is a 422 on its side and an aborted run on ours.
_TARGET_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "outlook": frozenset({Capability.mail, Capability.calendar}),
    "teams": frozenset({Capability.meeting_notes}),
    "onedrive": frozenset(),
    "gmail": frozenset({Capability.mail}),
    "google_calendar": frozenset({Capability.calendar}),
}

_MAIL_SENT = "mail.sent.list"
_MAIL_INBOX = "mail.inbox.list"
# Outlook is the one target where a person's pending work lives in BOTH
# folders: what they received and what they promised in reply. Other targets
# keep the single sent-items read this adapter always did.
_MAIL_FOLDERS_BY_TARGET: dict[str, tuple[str, ...]] = {"outlook": (_MAIL_INBOX, _MAIL_SENT)}
_MAIL_FOLDERS_DEFAULT: tuple[str, ...] = (_MAIL_SENT,)
# Connect capability → the folder name its records carry (``inbox``/``sent``),
# kept so a merged read does not lose where each message came from.
_MAIL_FOLDER_NAMES: dict[str, str] = {_MAIL_INBOX: "inbox", _MAIL_SENT: "sent"}

# Connect error codes that mean "the person has to log in again", whichever
# route produced them. Exposed so the connector facade maps them the same way.
LOGIN_REQUIRED_CODES = frozenset(
    {
        "browser_identity_unavailable",
        "browser_login_required",
        "browser_mfa_required",
        "authorization_denied",
        "action_required",
    }
)


def _flag(value: Any) -> bool:
    """Read a boolean that may have travelled as text.

    The connectors service encrypts the credential mapping as ``dict[str,
    str]`` (``ApiTokenCredentials.as_mapping``), so ``allow_browser_fallback``
    arrives back as ``"true"``/``"false"`` on that path and as a real bool on
    the :func:`encode_access_context` path. Anything else is ``False``: the
    browser route is opt-in, never inferred.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes"}
    return False


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
            raise SolerciaConnectConfigError(f"Solercia Connect access context is missing {key!r}")
    if payload["target"] not in _TARGETS:
        raise SolerciaConnectConfigError("Solercia Connect access context names an unknown target")
    payload["allow_browser_fallback"] = _flag(payload.get("allow_browser_fallback"))
    return payload


def _canonical(account: str) -> str:
    return account.strip().casefold()


def _target_serves(payload: dict[str, Any], capability: Capability) -> bool:
    """``True`` when the connector's target can answer ``capability`` at all.

    A miss is the ordinary state of a mixed read (an Outlook connector has no
    transcripts), so it is logged at debug level and never reported as a
    failure of the account.
    """
    target = payload["target"]
    if capability in _TARGET_CAPABILITIES.get(target, frozenset()):
        return True
    logger.debug(
        "Solercia Connect target %r does not serve %s; answering with no records",
        target,
        capability.value,
    )
    return False


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
        if not _target_serves(payload, capability):
            return []
        return await self._read_records(
            payload, _CAPABILITY_TO_CONNECT[capability], since=since, limit=limit
        )

    async def read_mail(
        self, ctx: AccessContext, *, since: datetime | None, limit: int
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """Read every mail folder the connector's target calls for.

        Returns one ``(folder, records)`` pair per folder, in folder order, so
        the port can tell a single-folder target (records handed through
        untouched) from a multi-folder one (merged, de-duplicated and
        re-ordered) and still know which folder each record came from
        (``inbox`` or ``sent``). A target without mail returns no folders.
        """
        payload = _decode_access_context(ctx)
        if not _target_serves(payload, Capability.mail):
            return []
        folders = _MAIL_FOLDERS_BY_TARGET.get(payload["target"], _MAIL_FOLDERS_DEFAULT)
        return [
            (
                _MAIL_FOLDER_NAMES[folder],
                await self._read_records(payload, folder, since=since, limit=limit),
            )
            for folder in folders
        ]

    async def _read_records(
        self,
        payload: dict[str, Any],
        connect_capability: str,
        *,
        since: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        client = SolerciaConnectClient(
            base_url=payload["base_url"],
            api_key=payload["api_key"],
            settings=self._settings,
        )
        requested = payload["account"]
        body: dict[str, Any] = {
            "type": payload["target"],
            "account": requested,
            "capability": connect_capability,
            "limit": min(max(limit, 1), 1000),
            "allow_browser_fallback": payload["allow_browser_fallback"],
        }
        # Connect's windows are exact and end-exclusive and it rejects a read
        # without both bounds, so a first pull (no ``since``) sends the default
        # look-back window instead of an open one.
        end = datetime.now(UTC)
        if since is None:
            since = end - timedelta(days=self._settings.SOLERCIA_CONNECT_DEFAULT_LOOKBACK_DAYS)
        body["start"] = since.isoformat()
        body["end"] = end.astimezone(since.tzinfo).isoformat()

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
    known_code = code if isinstance(code, str) else None
    if known_code in LOGIN_REQUIRED_CODES:
        # Including `action_required`: Connect's non-interactive answer when
        # the person must log in through the supervised browser first. It is
        # an authentication state of the provider session, not a protocol
        # defect, and the connector facade tells them apart by `code`.
        return SolerciaConnectAuthError(detail, code=known_code)
    if known_code == "browser_account_mismatch":
        return SolerciaConnectAccountMismatchError(detail, code=known_code)
    return SolerciaConnectProtocolError(detail, code=known_code)


class SolerciaConnectMailPort:
    """``MailReaderPort`` over Connect's mail folders.

    ``outlook`` reads the inbox AND sent items, merges them, drops duplicates
    by external id and returns the newest ``limit`` messages; every other
    target reads sent items only, exactly as before.
    """

    def __init__(self, reader: _ConnectReader) -> None:
        self._reader = reader

    async def list_messages(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int = 50
    ) -> list[MailMessage]:
        folders = await self._reader.read_mail(ctx, since=since, limit=limit)
        if not folders:
            return []
        if len(folders) == 1:
            folder, records = folders[0]
            return [map_mail_message(record, listed_from=folder) for record in records]

        merged: dict[str, MailMessage] = {}
        for folder, records in folders:
            for record in records:
                message = map_mail_message(record, listed_from=folder)
                # A message present in both folders is one message: the first
                # folder listed wins so the read is deterministic.
                merged.setdefault(message.external_id, message)
        ordered = sorted(merged.values(), key=lambda message: message.received_at, reverse=True)
        return ordered[: max(limit, 1)]


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
