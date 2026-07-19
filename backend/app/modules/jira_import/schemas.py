"""Pydantic schemas for the jira_import module (change 18-adapter-jira,
specs/jira-import/spec.md "Superficie REST de import solo-lectura, con
permisos y multi-tenant"). ``NormalizedJiraIssueRead``/
``NormalizationReportRead`` mirror the adapter's frozen dataclasses
(``app/integrations/adapters/jira/dtos.py``) field-for-field — Pydantic's
``from_attributes=True`` reads them directly, no manual mapping needed.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
