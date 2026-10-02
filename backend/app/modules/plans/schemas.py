"""Pydantic schemas of the plans module (change 45a, design.md D-I/D-N).

Read schemas use ``from_attributes`` and are built with ``model_validate``;
derived fields (``activity_key``, progress, ``is_confirmed``) are assigned
transiently by ``PlansService`` afterwards — same pattern as
``TaskRead.task_key``. No relation is embedded in list responses.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class PlanRead(BaseModel):
    """One institutional plan as the API exposes it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    plan_type: str
    period_year: int
    version: str | None = None
    source_document: str | None = None
    status: str
    created_at: datetime


class PlanActivityGroupCount(BaseModel):
    """Activity count of ONE group inside a plan."""

    group_code: str | None = None
    group_name: str | None = None
    activity_count: int


class PlanDetailRead(PlanRead):
    """``GET /plans/{plan_id}``: the plan plus its per-group activity counts."""

    activity_count: int = 0
    groups: list[PlanActivityGroupCount] = []


class PlanActivityReportRead(BaseModel):
    """One period self-report of an activity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period: str
    reported_progress: Decimal | None = None
    qualitative_summary: str | None = None
    evidence_refs: list[str] | None = None
    is_met: bool | None = None
    met_on_time: bool | None = None
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    updated_at: datetime | None = None


class PlanActivityLinkRead(BaseModel):
    """One activity<->activity link, with its resolution kept readable."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID
    link_type: str
    source_reference: str | None = None
    resolution: str

    # Derived, NEVER a column: ``is_confirmed = resolution != "conflict"``.
    # Assigned by PlansService right after ``model_validate`` (D-I/H3).
    is_confirmed: bool = True


class PlanActivityRead(BaseModel):
    """One plan activity as the API exposes it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    code: str
    group_code: str | None = None
    group_name: str | None = None
    name: str
    deliverable: str | None = None
    evidence_expected: str | None = None
    responsible: str | None = None
    is_mine: bool = False
    due_date: date | None = None
    target_from: Decimal | None = None
    target_to: Decimal | None = None
    iso_controls: list[str] | None = None
    external_codes: list[str] | None = None  # PLURAL (D2)
    scheduled_periods: list[str] | None = None
    sort_order: int = 0
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None

    # --- Derived, NEVER columns. Set transiently by PlansService. ---------
    activity_key: str | None = None  # "PSPI-2026/1.1" (D1)
    calculated_progress: float | None = None  # None != 0 (D3, D-F)
    primary_task_count: int = 0
    contributing_task_count: int = 0
    reported_progress: Decimal | None = None  # of `reported_period`
    reported_period: str | None = None


class PlanActivityDetailRead(PlanActivityRead):
    """``GET /plans/activities/{id}``: the activity plus reports and links."""

    reports: list[PlanActivityReportRead] = []
    links_out: list[PlanActivityLinkRead] = []
    links_in: list[PlanActivityLinkRead] = []


class ActivityTaskRead(BaseModel):
    """One task linked to a plan activity, as ``GET .../tasks`` exposes it."""

    model_config = ConfigDict(from_attributes=True)

    task_id: uuid.UUID
    task_key: str | None = None  # "SDM-7"
    title: str | None = None
    project_code: str | None = None
    project_name: str
    status: str
    role: str  # `primary` | `contributes`
    note: str | None = None
    # True when this task is `primary` AND satisfies progress_denominator():
    # one of the rows the ratio of D-F actually counts.
    counts_toward_progress: bool = False


class ActivityConflictCountRead(BaseModel):
    """``GET /plans/activities/conflict-counts``: one row per activity that
    has at least one ``conflict`` link (either end)."""

    activity_id: uuid.UUID
    conflict_count: int


# ---------------------------------------------------------------------------
# Write (HTTP)
# ---------------------------------------------------------------------------


class PlanActivityReportUpsert(BaseModel):
    """Body of ``PUT /plans/activities/{id}/reports/{period}``.

    EXACTLY the five business fields ADR 0009 lets Command keep (design.md
    D-N). No monitoring, independent-evaluation or recommendations fields:
    those are second/third line of defence and belong to Solercia Security.
    """

    reported_progress: Decimal | None = None
    qualitative_summary: str | None = None
    evidence_refs: list[str] | None = None
    is_met: bool | None = None
    met_on_time: bool | None = None


class TaskLinkCreate(BaseModel):
    """Body of ``POST /plans/activities/{id}/tasks``."""

    task_id: uuid.UUID
    role: str = "contributes"
    note: str | None = None


class ActivityLinkCreate(BaseModel):
    """Body of ``POST /plans/activities/{id}/links``.

    Declares NO ``resolution`` (D14): Pydantic ignores unknown fields, so a
    client sending one never reaches the service; every link created through
    HTTP is ``manual`` by construction.
    """

    to_activity_id: uuid.UUID
    link_type: str = "contributes_to"
    source_reference: str | None = None


# ---------------------------------------------------------------------------
# Write seam (repository only, NO HTTP route — D10)
# ---------------------------------------------------------------------------


class PlanUpsert(BaseModel):
    """Seam payload: create-or-update a plan by ``(organization_id, code)``."""

    code: str
    name: str
    plan_type: str
    period_year: int
    version: str | None = None
    source_document: str | None = None
    status: str = "active"


class PlanActivityUpsert(BaseModel):
    """Seam payload: create-or-update an activity by ``(plan_id, code)``."""

    code: str
    name: str
    group_code: str | None = None
    group_name: str | None = None
    deliverable: str | None = None
    evidence_expected: str | None = None
    responsible: str | None = None
    is_mine: bool = False
    due_date: date | None = None
    target_from: Decimal | None = None
    target_to: Decimal | None = None
    iso_controls: list[str] | None = None
    external_codes: list[str] | None = None
    scheduled_periods: list[str] | None = None
    sort_order: int = 0
