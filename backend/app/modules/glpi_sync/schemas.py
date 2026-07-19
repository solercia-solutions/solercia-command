"""Pydantic schemas for the glpi_sync module (change 17-adapter-glpi,
UH-R3/UH-R4/UH-R5/UH-R6).

``UnmatchedAssigneeRead`` deliberately EXCLUDES ``glpi_document`` — the raw
national ID document of a person still PENDING homologation is sensitive
PII; it feeds the matching cascade internally (``service.py``) but is
never serialized in an API response (tasks.md T8.1, "nunca expone ...
documento en claro fuera de lo homologado"). Tokens are never exposed
anywhere in this module either (no schema here ever touches
``ConnectionCredentials``).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import MatchMethod, UnmatchedStatus


class RunSyncRequest(BaseModel):
    """Body of ``POST /glpi-sync/run`` — which connector to sync."""

    connector_id: uuid.UUID


class SyncRunResponse(BaseModel):
    """Summary of one ``run_sync`` execution — counts only, never raw
    ticket/person data (that lives in ``glpi_user_links``/
    ``glpi_unmatched_assignees`` and is read through their own endpoints).
    """

    tickets_processed: int
    links_created: int
    queue_updated: int


class CandidateRead(BaseModel):
    """One name-matching SUGGESTION (never an auto-confirmed match)."""

    user_id: uuid.UUID
    score: float
    reason: str


class UnmatchedCaseRead(BaseModel):
    """One GLPI case (detail row) affecting an unmatched person."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    glpi_ticket_id: str
    glpi_ticket_title: str | None = None
    glpi_ticket_status: str | None = None
    created_at: datetime


class UnmatchedAssigneeRead(BaseModel):
    """A queue HEADER — one row per unmatched GLPI person, with its
    affected cases nested (design.md "cola consolidada por persona")."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_id: uuid.UUID
    glpi_user_id: str
    glpi_username: str | None = None
    glpi_email: str | None = None
    candidates: list[CandidateRead] | None = None
    status: UnmatchedStatus
    resolved_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    cases: list[UnmatchedCaseRead] = []


class ResolveRequest(BaseModel):
    """Body of ``POST /glpi-sync/unmatched/{id}/resolve``."""

    user_id: uuid.UUID


class GlpiUserLinkRead(BaseModel):
    """A CONFIRMED GLPI person -> platform user mapping."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_id: uuid.UUID
    glpi_user_id: str
    user_id: uuid.UUID
    match_method: MatchMethod
    glpi_username: str | None = None
    glpi_email: str | None = None
    created_at: datetime
    updated_at: datetime
