"""Tests for the `solercia_connect` adapter — read-only access to mail,
calendar and meeting notes through a local Solercia Connect runtime.

Everything runs against `httpx.MockTransport`: no real network, and no running
Connect runtime required in CI. The boundaries under test are the ones the
platform decision record makes normative
(`docs/decisions/2026-08-23-solercia-platform-decisions.md`):

    TestConnectClientBoundary   — §2.2 HTTP-only + anti-SSRF allowlist
    TestConnectDegradation      — §2.3 a Connect outage degrades, never breaks
    TestConnectAccountIdentity  — §4.1-4.3 one observed identity or zero reads
    TestConnectMapping          — §5.2 provider-neutral DTOs
    TestConnectReadOnly         — read-only surface
"""

import json
from typing import Any

import httpx
import pytest

from app.config import Settings

_BASE_URL = "http://127.0.0.1:8765"
_API_KEY = "local-runtime-key-not-a-provider-credential"
_ACCOUNT = "persona@entidad.example.gov.co"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "SOLERCIA_CONNECT_BASE_URL_ALLOWLIST": [_BASE_URL],
        "SOLERCIA_CONNECT_TIMEOUT_SECONDS": 5.0,
    }
    values.update(overrides)
    return Settings(**values)


def _envelope(records: list[dict[str, Any]], *, account: str = _ACCOUNT) -> dict[str, Any]:
    return {
        "schema": "solercia.connect/v1",
        "ok": True,
        "status": "success",
        "operation": "run",
        "account": account,
        "route": "browser",
        "data": {"records": records},
        "error": None,
    }


def _context(**overrides: Any) -> Any:
    from app.integrations.adapters.solercia_connect.adapter import encode_access_context
    from app.integrations.ports import AccessContext

    payload: dict[str, Any] = {
        "connector_id": "connector-1",
        "base_url": _BASE_URL,
        "api_key": _API_KEY,
        "account": _ACCOUNT,
        "target": "outlook",
    }
    payload.update(overrides)
    return AccessContext(
        access_token=encode_access_context(**payload),
        refresh_token=None,
        scopes=(),
    )


def _adapter(handler: Any, **settings_overrides: Any) -> Any:
    """Build the adapter with every HTTP call routed to `handler`."""
    from app.integrations.adapters.solercia_connect import adapter as module

    transport = httpx.MockTransport(handler)
    built = module.SolerciaConnectAdapter(_settings(**settings_overrides))
    original = module.SolerciaConnectClient

    def _client(**kwargs: Any) -> Any:
        return original(**kwargs, transport=transport)

    module.SolerciaConnectClient = _client  # type: ignore[assignment]
    built._restore = lambda: setattr(module, "SolerciaConnectClient", original)  # type: ignore[attr-defined]
    return built


class TestConnectClientBoundary:
    def test_rejects_a_base_url_outside_the_allowlist_before_any_request(self) -> None:
        from app.integrations.adapters.solercia_connect.client import SolerciaConnectClient
        from app.integrations.adapters.solercia_connect.errors import SolerciaConnectConfigError

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("a rejected base URL must never reach the network")

        with pytest.raises(SolerciaConnectConfigError):
            SolerciaConnectClient(
                base_url="http://evil.example.com",
                api_key=_API_KEY,
                settings=_settings(),
                transport=httpx.MockTransport(handler),
            )

    def test_rejects_an_empty_api_key_before_any_request(self) -> None:
        from app.integrations.adapters.solercia_connect.client import SolerciaConnectClient
        from app.integrations.adapters.solercia_connect.errors import SolerciaConnectConfigError

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("a rejected key must never reach the network")

        with pytest.raises(SolerciaConnectConfigError):
            SolerciaConnectClient(
                base_url=_BASE_URL,
                api_key="   ",
                settings=_settings(),
                transport=httpx.MockTransport(handler),
            )

    def test_the_allowlist_does_not_care_about_a_trailing_slash(self) -> None:
        from app.integrations.adapters.solercia_connect.client import SolerciaConnectClient

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("construction alone issues no request")

        SolerciaConnectClient(
            base_url=f"{_BASE_URL}/",
            api_key=_API_KEY,
            settings=_settings(),
            transport=httpx.MockTransport(handler),
        )

    @pytest.mark.asyncio
    async def test_the_api_key_travels_as_a_header_and_never_in_the_body(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["header"] = request.headers.get("X-Solercia-Connect-Key")
            seen["body"] = request.content.decode()
            return httpx.Response(200, json=_envelope([]))

        built = _adapter(handler)
        try:
            from app.integrations.ports import Capability

            port = built.port_for(Capability.mail)
            await port.list_messages(_context())
        finally:
            built._restore()

        assert seen["header"] == _API_KEY
        assert _API_KEY not in seen["body"]


class TestConnectDegradation:
    @pytest.mark.asyncio
    async def test_a_runtime_that_is_not_running_reports_unavailable(self) -> None:
        from app.integrations.adapters.solercia_connect.errors import (
            SolerciaConnectUnavailableError,
        )
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            with pytest.raises(SolerciaConnectUnavailableError):
                await port.list_messages(_context())
        finally:
            built._restore()

    @pytest.mark.asyncio
    async def test_a_rejected_key_is_an_auth_failure_not_an_outage(self) -> None:
        from app.integrations.adapters.solercia_connect.errors import SolerciaConnectAuthError
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"})

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            with pytest.raises(SolerciaConnectAuthError):
                await port.list_messages(_context())
        finally:
            built._restore()

    @pytest.mark.asyncio
    async def test_an_unknown_envelope_version_is_refused_rather_than_guessed(self) -> None:
        from app.integrations.adapters.solercia_connect.errors import SolerciaConnectProtocolError
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"schema": "solercia.connect/v9", "ok": True})

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            with pytest.raises(SolerciaConnectProtocolError):
                await port.list_messages(_context())
        finally:
            built._restore()


class TestConnectAccountIdentity:
    @pytest.mark.asyncio
    async def test_an_answer_for_another_account_yields_zero_records(self) -> None:
        from app.integrations.adapters.solercia_connect.errors import (
            SolerciaConnectAccountMismatchError,
        )
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    [
                        {
                            "id": "m-1",
                            "subject": "Asunto",
                            "sent_at": "2026-08-20T10:00:00+00:00",
                            "body": "cuerpo",
                            "body_format": "text",
                        }
                    ],
                    account="otra.persona@entidad.example.gov.co",
                ),
            )

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            with pytest.raises(SolerciaConnectAccountMismatchError):
                await port.list_messages(_context())
        finally:
            built._restore()

    @pytest.mark.asyncio
    async def test_identity_comparison_ignores_case(self) -> None:
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_envelope([], account=_ACCOUNT.upper()))

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            assert await port.list_messages(_context()) == []
        finally:
            built._restore()

    @pytest.mark.asyncio
    async def test_an_envelope_without_an_account_yields_zero_records(self) -> None:
        from app.integrations.adapters.solercia_connect.errors import (
            SolerciaConnectAccountMismatchError,
        )
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            body = _envelope([])
            del body["account"]
            return httpx.Response(200, json=body)

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            with pytest.raises(SolerciaConnectAccountMismatchError):
                await port.list_messages(_context())
        finally:
            built._restore()


class TestConnectMapping:
    @pytest.mark.asyncio
    async def test_a_mail_record_becomes_a_neutral_dto_with_text_only(self) -> None:
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    [
                        {
                            "id": "AAMk-1",
                            "subject": "Radicación de soporte",
                            "sent_at": "2026-08-20T15:31:00+00:00",
                            "sender": {"address": "persona@entidad.example.gov.co"},
                            "to": [{"address": "mesa@entidad.example.gov.co"}],
                            "body": "<p>Buenas <b>tardes</b></p>",
                            "body_format": "html",
                        }
                    ]
                ),
            )

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.mail)
            (message,) = await port.list_messages(_context())
        finally:
            built._restore()

        assert message.external_id == "AAMk-1"
        assert message.subject == "Radicación de soporte"
        assert message.sender == "persona@entidad.example.gov.co"
        assert message.recipients == ("mesa@entidad.example.gov.co",)
        # Markup is stripped once here so every reader does not do it its own way.
        assert message.body_text == "Buenas tardes"
        assert "<p>" not in message.snippet

    @pytest.mark.asyncio
    async def test_a_transcript_becomes_a_meeting_note_with_its_speakers(self) -> None:
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    [
                        {
                            "id": "t-1",
                            "display_name": "Revisión de historia de usuario",
                            "recorded_at": "2026-08-20T20:56:16+00:00",
                            "content": (
                                "WEBVTT\n\n1\n"
                                "00:00:01.000 --> 00:00:04.000\n"
                                "<v Persona Uno>Hola"
                            ),
                            "speakers": ["Persona Uno", "Persona Dos"],
                        }
                    ]
                ),
            )

        built = _adapter(handler, SOLERCIA_CONNECT_TIMEOUT_SECONDS=5.0)
        try:
            port = built.port_for(Capability.meeting_notes)
            (note,) = await port.list_notes(_context(target="teams"))
        finally:
            built._restore()

        assert note.external_id == "t-1"
        assert note.meeting_title == "Revisión de historia de usuario"
        assert note.participants == ("Persona Uno", "Persona Dos")
        assert note.transcript.startswith("WEBVTT")

    @pytest.mark.asyncio
    async def test_a_transcript_without_a_recording_timestamp_is_refused(self) -> None:
        """A note stamped "now" would claim to be from today when it is not."""
        from app.integrations.adapters.solercia_connect.errors import SolerciaConnectProtocolError
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    [{"id": "t-1", "display_name": "Sin fecha", "content": "WEBVTT\n"}]
                ),
            )

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.meeting_notes)
            with pytest.raises(SolerciaConnectProtocolError):
                await port.list_notes(_context(target="teams"))
        finally:
            built._restore()

    @pytest.mark.asyncio
    async def test_a_calendar_event_reports_no_location_rather_than_inventing_one(self) -> None:
        from app.integrations.ports import Capability

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_envelope(
                    [
                        {
                            "id": "e-1",
                            "title": "Seguimiento",
                            "start": "2026-08-20T14:00:00+00:00",
                            "end": "2026-08-20T15:00:00+00:00",
                            "organizer": {"address": "jefatura@entidad.example.gov.co"},
                            "attendees": [{"address": "persona@entidad.example.gov.co"}],
                        }
                    ]
                ),
            )

        built = _adapter(handler)
        try:
            port = built.port_for(Capability.calendar)
            (event,) = await port.list_events(_context())
        finally:
            built._restore()

        assert event.external_id == "e-1"
        assert event.organizer == "jefatura@entidad.example.gov.co"
        assert event.location is None


class TestConnectReadOnly:
    @pytest.mark.asyncio
    async def test_every_call_targets_the_run_endpoint_and_nothing_else(self) -> None:
        from app.integrations.ports import Capability

        seen: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            return httpx.Response(200, json=_envelope([]))

        built = _adapter(handler)
        try:
            await built.port_for(Capability.mail).list_messages(_context())
            await built.port_for(Capability.calendar).list_events(_context())
        finally:
            built._restore()

        assert seen == [("POST", "/v1/run"), ("POST", "/v1/run")]

    @pytest.mark.asyncio
    async def test_the_browser_fallback_is_off_unless_the_connector_asks_for_it(self) -> None:
        from app.integrations.ports import Capability

        bodies: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_envelope([]))

        built = _adapter(handler)
        try:
            await built.port_for(Capability.mail).list_messages(_context())
            await built.port_for(Capability.mail).list_messages(
                _context(allow_browser_fallback=True)
            )
        finally:
            built._restore()

        assert bodies[0]["allow_browser_fallback"] is False
        assert bodies[1]["allow_browser_fallback"] is True

    def test_the_adapter_declares_no_oauth_handshake(self) -> None:
        from app.integrations.adapters.solercia_connect.adapter import SolerciaConnectAdapter
        from app.integrations.ports import Capability, CredentialKind

        built = SolerciaConnectAdapter(_settings())
        assert built.credential_kind is CredentialKind.api_token
        assert built.oauth is None
        assert built.api_token is not None
        # A capability this adapter does not serve has no port, rather than a
        # port that raises when called.
        assert built.port_for(Capability.tickets) is None

    def test_the_adapter_registers_itself_under_its_provider_name(self) -> None:
        import app.integrations.adapters.solercia_connect  # noqa: F401
        from app.integrations.registry import get_adapter

        registered = get_adapter("solercia_connect")
        assert registered is not None
        assert registered.provider == "solercia_connect"
