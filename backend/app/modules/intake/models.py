"""``IntakeItem``, ``IntakeRule``, ``IntakeRun`` and ``IntakeSettings`` ORM
models (change 22-intake-classifier, design.md "Tablas").

``IntakeItem`` persists every insumo read through the 14's read-only ports
(``app/integrations/ports.py``) with a traceable link to its origin —
idempotent by ``UNIQUE(organization_id, connector_id, external_id)``
(design.md Architecture Decisions, "Idempotencia"). ``IntakeRule`` is the
tema→respondiente configuration the pure ``classifier.py`` engine evaluates,
ordered by ``rule_order``. ``IntakeRun`` is the per-account bitácora of a
``POST /intake/pull`` execution — deliberately WITHOUT ``SoftDeleteMixin``:
an audit log is never "un-deleted", only queried. ``IntakeSettings`` holds
the organization's lazily-created default project — ``UNIQUE(organization_id)``
mirrors ``connection_credentials``' 1:1-per-parent shape, here 1:1-per-tenant.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
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
from app.shared.enums import IntakeItemStatus, IntakeItemType, IntakeRunStatus, Priority


class IntakeItem(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A single insumo (correo, evento, tarea externa, nota, ticket) stored
    from a connected account, with trazabilidad hacia la regla que lo
    clasificó y la tarea que generó (si aplica)."""

    __tablename__ = "intake_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connector_id",
            "external_id",
            name="uq_intake_items_org_connector_external",
        ),
        # Thread lookups are always tenant-scoped (C03).
        Index("ix_intake_items_org_conversation", "organization_id", "conversation_id"),
        Index("ix_intake_items_org_internet_message", "organization_id", "internet_message_id"),
    )

    source_provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    connector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: conectores sin cuenta individual (ej. GLPI a nivel de
    # servicio) no tienen un `ConnectedAccount` que enlazar.
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True
    )
    item_type: Mapped[IntakeItemType] = mapped_column(
        SAEnum(IntakeItemType, name="intake_item_type", native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_actor: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Original payload preserved for trazabilidad y reclasificación futura
    # (design.md, "el raw_payload original DEBE conservarse").
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[IntakeItemStatus] = mapped_column(
        SAEnum(IntakeItemStatus, name="intake_item_status", native_enum=False, length=20),
        default=IntakeItemStatus.pending,
        nullable=False,
        index=True,
    )
    matched_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("intake_rules.id", ondelete="SET NULL"), nullable=True
    )
    created_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Thread signals (C03, migration 0030). Mail only; NULL means "not
    # observed" — legacy rows stay NULL until a re-ingest refreshes them.
    # ``direction`` is relative to the account that ingested the item.
    conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    internet_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)


class IntakeRule(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A tema→respondiente rule evaluated by ``classifier.py`` in ascending
    ``rule_order`` — the FIRST active rule whose ``criteria`` match GANA
    (design.md, "primera regla por rule_order gana").

    ``is_active`` is DELIBERATELY not redeclared here: the spec's ``is_active
    Bool`` field IS ``SoftDeleteMixin.is_active`` — a deactivated rule
    (``PATCH is_active=false``) and a soft-deleted rule (``DELETE``) share
    the EXACT same exclusion contract (evaluation + listings), so a single
    column serves both instead of a second business flag that would collide
    with the mixin's own name.
    """

    __tablename__ = "intake_rules"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # List of {"field": ..., "operator": ..., "value": ...}, combined with
    # AND (design.md Interfaces/Contracts). Extensible without a migration
    # per criterio — the matcher in classifier.py is the only interpreter.
    criteria: Mapped[list] = mapped_column(JSONB, nullable=False)
    convert_to_task: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_priority: Mapped[Priority] = mapped_column(
        SAEnum(Priority, name="priority", native_enum=False, length=20),
        default=Priority.medium,
        nullable=False,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rule_order: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class IntakeRun(PkMixin, TimestampMixin, AuditMixin, TenantMixin, Base):
    """One row per connector/account processed by a ``POST /intake/pull``
    execution — bitácora, deliberately WITHOUT ``SoftDeleteMixin``: an audit
    log row is queried, never "un-deleted" (design.md "Tablas")."""

    __tablename__ = "intake_runs"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True
    )
    items_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_duplicated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_converted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[IntakeRunStatus] = mapped_column(
        SAEnum(IntakeRunStatus, name="intake_run_status", native_enum=False, length=20),
        default=IntakeRunStatus.running,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntakeSettings(PkMixin, TimestampMixin, TenantMixin, Base):
    """Per-organization intake configuration — ONE row per tenant
    (``UNIQUE(organization_id)``). ``default_project_id`` is resolved
    lazily by ``IntakeService._ensure_default_project`` on first use
    (design.md "Proyecto por defecto de la organización")."""

    __tablename__ = "intake_settings"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_intake_settings_organization"),)

    default_project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # NULL means "use app.config.settings.INTAKE_DEFAULT_PROJECT_NAME" — the
    # service resolves the fallback, never this column (keeps the migration
    # free of an environment-coupled server_default).
    default_project_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
