"""RED tests for `app/integrations/adapters/google/meeting_notes.py`
(change 16-adapter-google, specs/google-adapter/spec.md GA-R6/GA-R7).

Every test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/google/` — ZERO real network in CI.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.integrations.ports import AccessContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"


def _load_fixture(name: str) -> dict:
    """Load a Google API response fixture by filename from
    `tests/fixtures/google/`."""

    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding="utf-8")


def _ctx(**overrides) -> AccessContext:
    """Build an `AccessContext` for the adapter's tests, real access token."""

    defaults = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "scopes": (),
    }
    defaults.update(overrides)
    return AccessContext(**defaults)


class TestDriveMeetingNotesReader:
    @pytest.mark.asyncio
    async def test_transcript_available_is_exported_and_mapped(self) -> None:
        """Scenario: Transcripción disponible se exporta — la carpeta
        "Meet Recordings" existe, contiene un Doc, y el export de ese Doc
        se mapea a `MeetingNote.transcript`."""

        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )
        from app.integrations.dtos import MeetingNote

        folder_found = _load_fixture("drive_folder_found.json")
        docs_found = _load_fixture("drive_transcript_docs_found.json")
        transcript_text = _load_text_fixture("drive_transcript_export.txt")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/drive/v3/files" or request.url.path.endswith(
                "/export"
            )
            if request.url.path.endswith("/export"):
                assert "drive-doc-transcript-1" in request.url.path
                assert request.url.params.get("mimeType") == "text/plain"
                return httpx.Response(200, text=transcript_text)
            query = request.url.params.get("q", "")
            if "mimeType='application/vnd.google-apps.folder'" in query:
                return httpx.Response(200, json=folder_found)
            return httpx.Response(200, json=docs_found)

        port = DriveMeetingNotesReader(transport=httpx.MockTransport(handler))

        notes = await port.list_notes(_ctx(), limit=10)

        assert len(notes) == 1
        note = notes[0]
        assert isinstance(note, MeetingNote)
        assert note.external_id == "drive-doc-transcript-1"
        assert note.transcript == transcript_text
        assert note.occurred_at.year == 2026
        assert note.occurred_at.month == 7

    @pytest.mark.asyncio
    async def test_no_recordings_folder_degrades_to_empty_list_without_error(
        self,
    ) -> None:
        """Scenario: Sin transcripción del organizador, degrada sin error —
        cuando la carpeta "Meet Recordings" no existe (el organizador nunca
        activó transcripciones), la respuesta es `[]`, NUNCA una
        excepción."""

        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )

        folder_not_found = _load_fixture("drive_folder_not_found.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=folder_not_found)

        port = DriveMeetingNotesReader(transport=httpx.MockTransport(handler))

        notes = await port.list_notes(_ctx(), limit=10)

        assert notes == []

    @pytest.mark.asyncio
    async def test_folder_exists_but_no_docs_degrades_to_empty_list(self) -> None:
        """Triangulation: la carpeta SÍ existe pero está vacía (el
        organizador la creó pero ninguna reunión generó Doc todavía) —
        también `[]`, un camino de código distinto al de "sin carpeta"."""

        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )

        folder_found = _load_fixture("drive_folder_found.json")
        docs_empty = _load_fixture("drive_transcript_docs_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.params.get("q", "")
            if "mimeType='application/vnd.google-apps.folder'" in query:
                return httpx.Response(200, json=folder_found)
            return httpx.Response(200, json=docs_empty)

        port = DriveMeetingNotesReader(transport=httpx.MockTransport(handler))

        notes = await port.list_notes(_ctx(), limit=10)

        assert notes == []

    @pytest.mark.asyncio
    async def test_no_permission_on_the_organizer_drive_raises_capability_unavailable(
        self,
    ) -> None:
        """Scenario: Falta de permiso Drive se reporta como capacidad no
        disponible — un `403` REAL de Drive (sin acceso al Drive del
        organizador) se propaga como `capability_unavailable`, NUNCA como
        `[]` silencioso (distinto del "sin carpeta" de arriba: aquí SÍ hubo
        un error del proveedor, no una ausencia de datos)."""

        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )
        from app.shared.exceptions import AppException

        denied = _load_fixture("error_403_drive_permission.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json=denied)

        port = DriveMeetingNotesReader(transport=httpx.MockTransport(handler))

        with pytest.raises(AppException) as excinfo:
            await port.list_notes(_ctx(), limit=10)

        assert excinfo.value.code == "capability_unavailable"

    @pytest.mark.asyncio
    async def test_meeting_notes_failure_does_not_touch_mail_or_calendar_fixtures(
        self,
    ) -> None:
        """Scenario (continuación): la degradación/`capability_unavailable`
        de `meeting_notes` no interfiere con las OTRAS capacidades del
        MISMO adaptador — se prueba a nivel de puerto: el reader de
        `meeting_notes` es un objeto aislado, independiente de
        `GmailMailReader`/`GoogleCalendarReader`."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader
        from app.integrations.adapters.google.mail import GmailMailReader
        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )

        denied = _load_fixture("error_403_drive_permission.json")

        def failing_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json=denied)

        def ok_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [], "messages": []})

        notes_port = DriveMeetingNotesReader(
            transport=httpx.MockTransport(failing_handler)
        )
        mail_port = GmailMailReader(transport=httpx.MockTransport(ok_handler))
        calendar_port = GoogleCalendarReader(transport=httpx.MockTransport(ok_handler))

        from app.shared.exceptions import AppException

        with pytest.raises(AppException):
            await notes_port.list_notes(_ctx(), limit=10)

        assert await mail_port.list_messages(_ctx(), limit=10) == []
        assert await calendar_port.list_events(_ctx(), limit=10) == []
