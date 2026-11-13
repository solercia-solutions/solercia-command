"""Pydantic schemas for the jira_import module (change 18-adapter-jira,
specs/jira-import/spec.md "Superficie REST de import solo-lectura, con
permisos y multi-tenant"). ``NormalizedJiraIssueRead``/
``NormalizationReportRead`` mirror the adapter's frozen dataclasses
(``app/integrations/adapters/jira/dtos.py``) field-for-field — Pydantic's
``from_attributes=True`` reads them directly, no manual mapping needed.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class JiraImportRequest(BaseModel):
    """Payload to trigger an import via the API vía (design.md Data Flow,
    ``POST /connectors/{id}/jira/import {jql,since}``)."""

    jql: str
    since: datetime | None = None


class NormalizedJiraIssueRead(BaseModel):
    """API projection of ``NormalizedJiraIssue`` — never persisted, always
    a snapshot from THIS import run."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    title: str
    description: str | None = None
    issue_type: str
    status_raw: str
    status_bucket: str
    priority: str
    assignee_raw: str | None = None
    sprint_name: str | None = None
    sprint_state: str | None = None
    story_points: float | None = None
    labels: tuple[str, ...] = ()
    created_at: datetime | None = None
    source: str


class NormalizationReportRead(BaseModel):
    """API projection of ``NormalizationReport`` — the summary the
    superficie REST returns alongside the issues (specs/jira-import/
    spec.md "conteos totales, conteo de no homologados")."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    normalized: int
    unmapped_types: dict[str, int]
    unmapped_statuses: dict[str, int]
    unmapped_priorities: dict[str, int]
    story_points_field: str | None = None
    sprint_field: str | None = None
    source: str
    skipped_malformed: list[dict] = []


class JiraImportResponse(BaseModel):
    """The response contract BOTH vías (API/archivo) share (specs/
    jira-import/spec.md "Import por archivo devuelve el mismo contrato").
    ``truncated``/``truncation_reason`` default to ``false``/``None`` — set
    when a rate-limited API import still answers 200 with a partial result."""

    issues: list[NormalizedJiraIssueRead]
    report: NormalizationReportRead
    truncated: bool = False
    truncation_reason: str | None = None


# --------------------------------------------------------------------------
# User-driven project import: list -> preview -> import-project
# --------------------------------------------------------------------------

class ImportedProjectRef(BaseModel):
    """Local project already anchored to a Jira project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None = None


class JiraProjectRead(BaseModel):
    """A Jira project the connector's account can browse."""

    key: str
    name: str
    imported_project: ImportedProjectRef | None = None


class JiraPreviewRequest(BaseModel):
    """``POST /connectors/{id}/jira/preview``."""

    project_key: str = Field(max_length=50)


class SprintPreviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    jira_state: str | None = None
    status: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    issues: int


class StatusMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jira_status: str
    bucket: str
    target_status: str
    issues: int


class JiraPreviewResponse(BaseModel):
    """Counts and proposed mapping — nothing is persisted."""

    project_key: str
    suggested_code: str
    methodology: str
    existing_project: ImportedProjectRef | None = None
    total: int
    counts_by_type: dict[str, int]
    sprints: list[SprintPreviewRead]
    status_mapping: list[StatusMappingRead]
    target_statuses: list[str]
    estimated_hours: Decimal
    issues_with_estimate: int
    story_points: int
    issues_with_points: int
    unmapped_types: dict[str, int]
    unmapped_statuses: dict[str, int]
    unmapped_priorities: dict[str, int]
    skipped_malformed: int


class JiraImportProjectRequest(BaseModel):
    """``POST /connectors/{id}/jira/import-project``. ``project_name`` and
    ``project_code`` apply only when the local project is created."""

    project_key: str = Field(max_length=50)
    project_name: str | None = Field(default=None, max_length=160)
    project_code: str | None = Field(default=None, max_length=10)
    status_overrides: dict[str, str] = Field(default_factory=dict)


class EntityCountsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created: int
    updated: int
    unchanged: int


class ImportSummaryRead(BaseModel):
    """Final summary of one project import."""

    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    project_code: str | None = None
    project_name: str
    project_created: bool
    tasks: EntityCountsRead
    sprints: EntityCountsRead
    parents_linked: int
    orphans: list[str]
    unassigned: list[str]
    unmapped_types: dict[str, int]
    unmapped_statuses: dict[str, int]
    unmapped_priorities: dict[str, int]
    errors: list[str]
