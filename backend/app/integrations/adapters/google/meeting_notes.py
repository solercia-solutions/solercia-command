"""`MeetingNotesReaderPort` over the Google Drive API (change
16-adapter-google, design.md "meeting_notes.py"). Best-effort: Meet
transcripts land as Google Docs inside a "Meet Recordings" Drive folder
ONLY when the meeting's organizer enabled transcription — this port
degrades to an EMPTY LIST (never an error) whenever that folder/Doc simply
is not there, and reserves a raised :func:`errors.capability_unavailable`
for the DIFFERENT case of a real ``403`` (the connected account lacks
permission to see the organizer's Drive at all) — spec.md distinguishes
these two explicitly (GA-R6/GA-R7).
"""

from datetime import UTC, datetime
from typing import Any

from app.integrations.adapters.google.client import GoogleClient
from app.integrations.adapters.google.ports_base import _GooglePortBase
from app.integrations.dtos import MeetingNote
from app.integrations.ports import AccessContext

_RECORDINGS_FOLDER_NAME = "Meet Recordings"
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_DOC_MIME_TYPE = "application/vnd.google-apps.document"


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_meeting_note(raw: dict[str, Any], transcript_text: str) -> MeetingNote:
    """Map one Drive Doc resource (``id``/``name``/``modifiedTime``) + its
    already-exported plain-text content to a :class:`MeetingNote`.

    Drive's file resource carries no meeting attendee list — ``participants``
    stays empty, a documented simplification, never a crash (same
    convention the 15's ``map_meeting_note`` uses for Graph transcripts)."""

    return MeetingNote(
        external_id=str(raw["id"]),
        meeting_title=str(raw.get("name") or "Transcripción de reunión"),
        occurred_at=_parse_rfc3339(raw["modifiedTime"]),
        transcript=transcript_text,
        participants=(),
    )


class DriveMeetingNotesReader(_GooglePortBase):
    """``MeetingNotesReaderPort`` over the Google Drive API (scope
    ``drive.readonly``)."""

    _base_url_setting = "GOOGLE_DRIVE_BASE_URL"

    async def list_notes(
        self, ctx: AccessContext, *, since: datetime | None = None, limit: int | None = None
    ) -> list[MeetingNote]:
        bounded_limit = self._bounded_limit(limit)
        client = self._client(ctx)

        folder_id = await self._find_recordings_folder(client)
        if folder_id is None:
            return []

        doc_files = await self._find_transcript_docs(
            client, folder_id, since, bounded_limit
        )
        if not doc_files:
            return []

        notes: list[MeetingNote] = []
        for doc in doc_files:
            response = await client.get(
                f"/files/{doc['id']}/export", params={"mimeType": "text/plain"}
            )
            notes.append(map_meeting_note(doc, response.text))
        return notes

    async def _find_recordings_folder(self, client: GoogleClient) -> str | None:
        query = (
            f"name='{_RECORDINGS_FOLDER_NAME}' and mimeType='{_FOLDER_MIME_TYPE}' "
            "and trashed=false"
        )
        response = await client.get("/files", params={"q": query, "pageSize": "1"})
        files = response.json().get("files") or []
        return str(files[0]["id"]) if files else None

    async def _find_transcript_docs(
        self,
        client: GoogleClient,
        folder_id: str,
        since: datetime | None,
        bounded_limit: int,
    ) -> list[dict[str, Any]]:
        effective_since = self._since_or_default(since)
        query = (
            f"'{folder_id}' in parents and mimeType='{_DOC_MIME_TYPE}' "
            f"and trashed=false and modifiedTime > '{_rfc3339(effective_since)}'"
        )
        params = {
            "q": query,
            "pageSize": str(self._page_size(bounded_limit)),
            "fields": "nextPageToken, files(id, name, modifiedTime)",
        }
        return await client.paginate(
            "/files", params=params, items_key="files", limit=bounded_limit
        )
