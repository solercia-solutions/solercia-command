"""RED tests for `app/integrations/adapters/google/calendar.py` (change
16-adapter-google, specs/google-adapter/spec.md GA-R5).

Every test runs against `httpx.MockTransport` fixtures under
`tests/fixtures/google/` — ZERO real network in CI.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.integrations.ports import AccessContext

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "google"


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


class TestGoogleCalendarReader:
    @pytest.mark.asyncio
    async def test_list_events_aggregates_dtos_from_two_pages_respecting_limit(
        self,
    ) -> None:
        """Scenario: Resultados dentro de la ventana, multi-página —
        `nextPageToken` is followed across a second page and every DTO is
        aggregated, respetando `limit`."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader
        from app.integrations.dtos import CalendarEvent

        page_1 = _load_fixture("calendar_events_page1.json")
        page_2 = _load_fixture("calendar_events_page2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/calendar/v3/calendars/primary/events"
            if request.url.params.get("pageToken") == "calendar-page-2-token":
                return httpx.Response(200, json=page_2)
            assert "timeMin" in request.url.params
            assert "timeMax" in request.url.params
            return httpx.Response(200, json=page_1)

        port = GoogleCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert [e.external_id for e in events] == ["gcal-event-1", "gcal-event-2"]
        assert all(isinstance(e, CalendarEvent) for e in events)

    @pytest.mark.asyncio
    async def test_list_events_returns_empty_list_without_error(self) -> None:
        """Sin resultados en la ventana — un `items: []` nunca lanza."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader

        empty = _load_fixture("calendar_events_empty.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=empty)

        port = GoogleCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert events == []

    @pytest.mark.asyncio
    async def test_list_events_maps_organizer_attendees_and_location(self) -> None:
        """Scenario (continuación): organizador, asistentes y horario
        mapean desde la forma REAL de un evento Calendar, incluyendo
        `location: null` → `None`, no un crash; `attendees: []` → `()`."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader

        page_1 = _load_fixture("calendar_events_page1.json")
        page_2 = _load_fixture("calendar_events_page2.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": page_1["items"] + page_2["items"]})

        port = GoogleCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert len(events) == 2
        first, second = events
        assert first.external_id == "gcal-event-1"
        assert first.title == "Reunión de seguimiento del proyecto"
        assert first.organizer == "ana.torres@example.com"
        assert first.attendees == ("carlos.ruiz@example.com",)
        assert first.location == "Sala virtual"
        assert first.starts_at.year == 2026
        assert first.starts_at.hour == 15

        assert second.attendees == ()
        assert second.location is None

    @pytest.mark.asyncio
    async def test_all_day_event_uses_the_date_field_instead_of_date_time(
        self,
    ) -> None:
        """Triangulation: un evento de día completo (`start.date`/`end.date`
        sin `dateTime`) mapea sin lanzar — un camino de código distinto al
        de arriba."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader

        all_day = _load_fixture("calendar_event_all_day.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=all_day)

        port = GoogleCalendarReader(transport=httpx.MockTransport(handler))

        events = await port.list_events(_ctx(), limit=10)

        assert len(events) == 1
        assert events[0].starts_at.year == 2026
        assert events[0].starts_at.month == 7
        assert events[0].starts_at.day == 20

    @pytest.mark.asyncio
    async def test_since_and_limit_translate_to_time_min_time_max_and_max_results(
        self,
    ) -> None:
        """Scenario: since/limit acotan la consulta — `since` se traduce a
        `timeMin`, `now` a `timeMax` y `limit` a `maxResults` (design.md
        tabla de traducción por puerto)."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader

        empty = _load_fixture("calendar_events_empty.json")
        seen_params: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_params.update(dict(request.url.params))
            return httpx.Response(200, json=empty)

        port = GoogleCalendarReader(transport=httpx.MockTransport(handler))
        since = datetime(2026, 6, 1, tzinfo=UTC)

        await port.list_events(_ctx(), since=since, limit=7)

        assert seen_params["timeMin"].startswith("2026-06-01T")
        assert seen_params["maxResults"] == "7"
        assert "timeMax" in seen_params
