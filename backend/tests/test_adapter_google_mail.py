"""RED tests for `app/integrations/adapters/google/mime.py` +
`.../mail.py` (change 16-adapter-google, specs/google-adapter/spec.md
GA-R4).

Every HTTP-touching test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/google/` — ZERO real network in CI.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.integrations.ports import AccessContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"
_GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1"


def _load_fixture(name: str) -> dict:
    """Load a Google API response fixture by filename from
    `tests/fixtures/google/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _ctx(**overrides) -> AccessContext:
    """Build an `AccessContext` for the adapter's tests, real access token."""

    defaults = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "scopes": (),
    }
    defaults.update(overrides)
    return AccessContext(**defaults)


def _settings(**overrides) -> Settings:
    """Build a real `Settings` instance with `GOOGLE_*` overrides for a test."""

    return Settings(**overrides)


# ---------------------------------------------------------------------------
# mime.py — decodificación MIME multiparte base64url
# ---------------------------------------------------------------------------


class TestMimeBodyText:
    def test_multipart_message_prefers_the_plain_text_part(self) -> None:
        """Scenario: Mensaje multiparte se decodifica a texto plano — con
        `text/plain` Y `text/html` presentes, `body_text` decodifica el
        `text/plain`, sin base64 ni MIME crudo."""

        from app.integrations.adapters.google import mime

        payload = _load_fixture("gmail_message_multipart.json")["payload"]

        text = mime.body_text(payload)

        assert "base64" not in text
        assert "<" not in text  # no residual MIME/HTML markup
        assert "Buenas tardes," in text
        assert "avance del proyecto" in text
        assert "Saludos," in text

    def test_html_only_message_falls_back_to_stripped_text(self) -> None:
        """Triangulation: SIN `text/plain`, solo `text/html`, `body_text`
        decodifica y quita las etiquetas — un camino de código distinto al
        multiparte de arriba."""

        from app.integrations.adapters.google import mime

        payload = _load_fixture("gmail_message_html_only.json")["payload"]

        text = mime.body_text(payload)

        assert "<html>" not in text
        assert "<b>" not in text
        assert "reunión de mañana" in text
        assert "9am" in text

    def test_message_without_any_readable_body_returns_empty_string_not_an_error(
        self,
    ) -> None:
        """Un mensaje solo con adjuntos (sin `text/plain` ni `text/html`)
        nunca lanza — `body_text` devuelve `""`."""

        from app.integrations.adapters.google import mime

        payload = _load_fixture("gmail_message_no_body.json")["payload"]

        text = mime.body_text(payload)

        assert text == ""


# ---------------------------------------------------------------------------
# mail.py — `MailReaderPort` sobre Gmail
# ---------------------------------------------------------------------------


class TestGmailMailReader:
    @pytest.mark.asyncio
    async def test_list_messages_fetches_full_content_for_every_listed_id(
        self,
    ) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página — Gmail's
        `messages.list` only returns ids; the port follows up with a
        `messages.get` per id and maps the FULL message to a
        `MailMessage`."""

        from app.integrations.adapters.google.mail import GmailMailReader
        from app.integrations.dtos import MailMessage

        list_page_1 = _load_fixture("gmail_messages_list_page1.json")
        list_page_2 = _load_fixture("gmail_messages_list_page2.json")
        message_1 = _load_fixture("gmail_message_multipart.json")
        message_2 = _load_fixture("gmail_message_html_only.json")
        message_3 = _load_fixture("gmail_message_no_body.json")
        get_calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/gmail/v1/users/me/messages":
                assert "q" in request.url.params
                assert request.url.params["q"].startswith("after:")
                if request.url.params.get("pageToken") == "gmail-page-2-token":
                    return httpx.Response(200, json=list_page_2)
                return httpx.Response(200, json=list_page_1)

            msg_id = request.url.path.rsplit("/", 1)[-1]
            get_calls.append(msg_id)
            assert request.url.params.get("format") == "full"
            by_id = {
                "gmail-msg-1": message_1,
                "gmail-msg-2": message_2,
                "gmail-msg-3": message_3,
            }
            return httpx.Response(200, json=by_id[msg_id])

        port = GmailMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert [m.external_id for m in messages] == [
            "gmail-msg-1",
            "gmail-msg-2",
            "gmail-msg-3",
        ]
        assert get_calls == ["gmail-msg-1", "gmail-msg-2", "gmail-msg-3"]
        assert all(isinstance(m, MailMessage) for m in messages)

    @pytest.mark.asyncio
    async def test_list_messages_returns_empty_list_without_error(self) -> None:
        """Sin resultados en la ventana — un `messages: []` nunca lanza,
        devuelve lista vacía."""

        from app.integrations.adapters.google.mail import GmailMailReader

        empty = _load_fixture("gmail_messages_list_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=empty)

        port = GmailMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert messages == []

    @pytest.mark.asyncio
    async def test_list_messages_maps_every_field_from_the_gmail_payload(
        self,
    ) -> None:
        """Triangulation: cada campo de `MailMessage` se puebla desde la
        forma REAL de un mensaje Gmail, no un stub fijo."""

        from app.integrations.adapters.google.mail import GmailMailReader

        single = {"messages": [{"id": "gmail-msg-1", "threadId": "gmail-thread-1"}]}
        message = _load_fixture("gmail_message_multipart.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/gmail/v1/users/me/messages":
                return httpx.Response(200, json=single)
            return httpx.Response(200, json=message)

        port = GmailMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert len(messages) == 1
        result = messages[0]
        assert result.external_id == "gmail-msg-1"
        assert result.subject == "Actualización del proyecto"
        assert result.sender == "ana.torres@example.com"
        assert result.recipients == (
            "equipo@example.com",
            "carlos.ruiz@example.com",
        )
        assert result.snippet == (
            "Buenas tardes, les comparto el avance del proyecto de esta semana."
        )
        assert result.body_text is not None
        assert "Buenas tardes," in result.body_text
        assert result.received_at.year == 2026
        assert result.received_at.month == 7
        assert result.received_at.day == 10

    @pytest.mark.asyncio
    async def test_since_and_limit_translate_to_q_after_epoch_and_max_results(
        self,
    ) -> None:
        """Scenario: since/limit acotan la consulta — `since` se traduce a
        `q=after:<epoch_segundos>` y `limit` a `maxResults` (design.md,
        tabla de traducción por puerto)."""

        from datetime import UTC, datetime

        from app.integrations.adapters.google.mail import GmailMailReader

        empty = _load_fixture("gmail_messages_list_empty.json")
        seen_params: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_params.update(dict(request.url.params))
            return httpx.Response(200, json=empty)

        port = GmailMailReader(transport=httpx.MockTransport(handler))
        since = datetime(2026, 6, 1, tzinfo=UTC)

        await port.list_messages(_ctx(), since=since, limit=5)

        expected_epoch = int(since.timestamp())
        assert seen_params["q"] == f"after:{expected_epoch}"
        assert seen_params["maxResults"] == "5"

    @pytest.mark.asyncio
    async def test_one_message_get_failure_is_skipped_and_the_rest_still_list(
        self,
    ) -> None:
        """WARNING 16-adapter-google: un mensaje que falle en `messages.get`
        (ej. borrado entre `list` y `get`, 404) se OMITE con un log warning
        — el listado sigue devolviendo el resto, nunca se pierde por
        completo por una falla puntual (aislamiento N+1)."""

        from app.integrations.adapters.google.mail import GmailMailReader

        listed = {
            "messages": [
                {"id": "gmail-msg-1"},
                {"id": "gmail-msg-2"},
                {"id": "gmail-msg-3"},
            ]
        }
        message_1 = _load_fixture("gmail_message_multipart.json")
        message_3 = _load_fixture("gmail_message_no_body.json")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/gmail/v1/users/me/messages":
                return httpx.Response(200, json=listed)
            msg_id = request.url.path.rsplit("/", 1)[-1]
            if msg_id == "gmail-msg-2":
                return httpx.Response(404, json={"error": {"message": "not found"}})
            by_id = {"gmail-msg-1": message_1, "gmail-msg-3": message_3}
            return httpx.Response(200, json=by_id[msg_id])

        port = GmailMailReader(transport=httpx.MockTransport(handler))

        messages = await port.list_messages(_ctx(), limit=10)

        assert [m.external_id for m in messages] == ["gmail-msg-1", "gmail-msg-3"]

    @pytest.mark.asyncio
    async def test_google_default_limit_setting_changes_the_effective_default(
        self,
    ) -> None:
        """`GOOGLE_DEFAULT_LIMIT` (config.py) es el default EFECTIVO cuando
        el caller no pasa `limit` — cambiar el setting cambia `maxResults`
        sin que el caller pida nada explícito."""

        from app.integrations.adapters.google.mail import GmailMailReader

        empty = _load_fixture("gmail_messages_list_empty.json")
        seen_params: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_params.update(dict(request.url.params))
            return httpx.Response(200, json=empty)

        port = GmailMailReader(
            settings=_settings(GOOGLE_DEFAULT_LIMIT=7),
            transport=httpx.MockTransport(handler),
        )

        await port.list_messages(_ctx())

        assert seen_params["maxResults"] == "7"

    def test_labels_are_never_exposed_as_a_folder_field_on_mail_message(self) -> None:
        """Scenario: Labels no se traducen a carpeta — `MailMessage` no
        declara NINGÚN campo de carpeta/label; las labels de Gmail quedan
        fuera del contrato común (divergencia frente a `mailFolders` de
        Graph)."""

        from app.integrations.dtos import MailMessage

        field_names = set(MailMessage.__dataclass_fields__)

        assert "label" not in field_names
        assert "labels" not in field_names
        assert "folder" not in field_names
        assert "thread_id" not in field_names
