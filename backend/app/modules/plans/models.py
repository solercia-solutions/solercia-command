"""Institutional plans ORM models (change 45a-planes-modelo-api).

Decreto 612 plans (PSPI, PTR, PAI, PTEP) as a cross-cutting commitment
dimension. Five tables, mirrored LITERALLY in ``__table_args__`` against
migration ``0027`` because the test harness builds the schema with
``Base.metadata.create_all`` and NOT with Alembic (design.md D-B).

Rules that run through every model here:

* ``plan_activities`` has NO ``organization_id`` (design.md P7/D-D): its tenant
  is transitive through ``plan_id -> plans.organization_id``, exactly like
  ``tasks`` reaches it through ``project_id``.
* The three child tables (reports, activity links, task links) carry no
  ``SoftDeleteMixin`` (D-C): unlinking removes the row, same convention as
  ``TaskLabel`` (labels/models.py). With soft delete, the unique would keep
  holding the pair after an unlink and the next legitimate link would raise
  ``UniqueViolation`` -> 500.
* Zero ``relationship()`` (D-H): every navigation is an explicit JOIN in the
  repository, and the tenant JOIN is never optional.
* Closed vocabularies are plain ``String(n)`` validated at the service layer
  (D12/D-J), deliberately NOT PostgreSQL enums.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Plan(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """One institutional plan, e.g. ``PSPI-2026``. ``code`` is unique per org."""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_plans_org_code"),
        Index("ix_plans_org_type_year", "organization_id", "plan_type", "period_year"),
    )

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # `pspi` | `ptr` | `pai` | `ptep` — validated by the service (D12/D-J).
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # `active` | `archived`.
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class PlanActivity(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """One activity of a plan. NO ``organization_id``: tenant via ``plans``."""

    __tablename__ = "plan_activities"
    __table_args__ = (
        UniqueConstraint("plan_id", "code", name="uq_plan_activities_plan_code"),
        Index("ix_plan_activities_plan_is_mine", "plan_id", "is_mine"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Unique within the plan. The readable ``activity_key`` ("PSPI-2026/1.1")
    # is DERIVED by the service and is never a column (design.md D1).
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    deliverable: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_mine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_from: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    target_to: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    iso_controls: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    # PLURAL: one activity may carry more than one external code (OM-05 AND
    # OM-08 in PSPI 2.4, design.md D2).
    external_codes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    scheduled_periods: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlanActivityReport(PkMixin, TimestampMixin, AuditMixin, Base):
    """First-line self-report of one activity for one period.

    Exactly the five business fields ADR 0009 allows Command to keep
    (design.md D-N). Second and third line of defence (qualitative monitoring,
    independent evaluation, observations-recommendations) belong to Solercia
    Security and MUST NOT get a column here.
    """

    __tablename__ = "plan_activity_reports"
    __table_args__ = (
        UniqueConstraint(
            "plan_activity_id",
            "period",
            name="uq_plan_activity_reports_activity_period",
        ),
    )

    plan_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `I` | `II` | `III` | `ANUAL`.
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    reported_progress: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    qualitative_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    is_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    met_on_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class PlanActivityLink(PkMixin, TimestampMixin, AuditMixin, Base):
    """Link between two plan activities, with its resolution kept traceable.

    No ``SoftDeleteMixin`` (design.md D-C), same convention as ``TaskLabel``:
    unlinking removes the row outright.
    """

    __tablename__ = "plan_activity_links"
    __table_args__ = (
        # Declared HERE and not only in migration 0027 because the test
        # harness builds the schema with `Base.metadata.create_all`. KEPT
        # BYTE-IDENTICAL to the migration: `alembic check` does NOT compare
        # CheckConstraints, so the equality is asserted by
        # test_migration_institutional_plans.py comparing pg_get_constraintdef
        # (design.md D-B).
        UniqueConstraint(
            "from_activity_id",
            "to_activity_id",
            "link_type",
            name="uq_plan_activity_links_from_to_type",
        ),
        CheckConstraint(
            "from_activity_id <> to_activity_id",
            name="ck_plan_activity_links_no_self",
        ),
    )

    from_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `contributes_to` | `derives_from` | `duplicates` — service-validated.
    link_type: Mapped[str] = mapped_column(String(20), default="contributes_to", nullable=False)
    # Literal text of the source that produced the link, e.g. "4.5 (OM-03)".
    source_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # `exact` | `by_external_code` | `conflict` | `manual`. The API NEVER
    # accepts this from a client: every HTTP-created link is `manual`
    # (design.md D14/D-I). Only the importer seam may emit the others.
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)


class TaskPlanActivity(PkMixin, TimestampMixin, AuditMixin, Base):
    """N:N link between a task and a plan activity, with a role.

    The ONLY touch point of this aggregate with ``tasks`` (FK). A task may be
    ``primary`` of more than one activity; a (task, activity) pair never
    repeats.
    """

    __tablename__ = "task_plan_activities"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "plan_activity_id",
            name="uq_task_plan_activities_task_activity",
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `primary` | `contributes` — service-validated.
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
