"""``GlpiUserLink``/``GlpiUnmatchedAssignee``/``GlpiUnmatchedCase`` ORM
models (change 17-adapter-glpi, design.md "Tablas nuevas").

Three tables:

- ``GlpiUserLink`` — a CONFIRMED mapping ``glpi_user_id`` (scoped by
  connector/organization) -> platform ``user_id``, with the ``match_method``
  that confirmed it. ``UNIQUE(connector_id, glpi_user_id)``: at most one
  link per GLPI person per connector.
- ``GlpiUnmatchedAssignee`` — the queue HEADER, one row per unmatched GLPI
  person (``UNIQUE(connector_id, glpi_user_id)``, same anchor as the link).
  Carries the candidate suggestions (``candidates`` JSONB) and the
  resolution outcome.
- ``GlpiUnmatchedCase`` — the queue DETAIL, one row per GLPI case affected
  by an unmatched person, 1:N off the header
  (``UNIQUE(unmatched_assignee_id, glpi_ticket_id)``, idempotent re-sync).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
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
from app.shared.enums import MatchMethod, UnmatchedStatus


class GlpiUserLink(
    PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base
):
    """A CONFIRMED GLPI person -> platform user mapping.

    Once created, every future sync for this ``glpi_user_id`` resolves
    directly against this row without re-running the matching cascade
    (user-homologation spec, "Sincronización repetida reutiliza el
    mapeo"). Revoking (soft-delete) sends the person back through the
    cascade on the next sync.
    """

    __tablename__ = "glpi_user_links"
    __table_args__ = (
        UniqueConstraint(
            "connector_id", "glpi_user_id", name="uq_glpi_user_links_connector_glpi_user"
        ),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    glpi_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_method: Mapped[MatchMethod] = mapped_column(
        SAEnum(MatchMethod, name="glpi_match_method", native_enum=False, length=20),
        nullable=False,
    )
    glpi_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    glpi_email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class GlpiUnmatchedAssignee(PkMixin, TimestampMixin, AuditMixin, TenantMixin, Base):
    """Queue HEADER: one row per GLPI person still unmatched for a connector.

    No :class:`~app.shared.base_model.SoftDeleteMixin` — ``status`` (via
    :class:`UnmatchedStatus`) IS the row's lifecycle; resolving/ignoring
    flips it in place instead of soft-deleting (design.md "Tablas nuevas").
    """

    __tablename__ = "glpi_unmatched_assignees"
    __table_args__ = (
        UniqueConstraint(
            "connector_id",
            "glpi_user_id",
            name="uq_glpi_unmatched_assignees_connector_glpi_user",
        ),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    glpi_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    glpi_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    glpi_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    glpi_document: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Suggested candidates from the name-matching level of the cascade:
    # [{"user_id": "...", "score": 0.87, "reason": "name"}], ordered desc by
    # score. Empty/None when the header exists only because a case landed
    # with no name candidates at all.
    candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[UnmatchedStatus] = mapped_column(
        SAEnum(UnmatchedStatus, name="glpi_unmatched_status", native_enum=False, length=20),
        default=UnmatchedStatus.pending,
        nullable=False,
        index=True,
    )
    resolved_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GlpiUnmatchedCase(PkMixin, TimestampMixin, Base):
    """Queue DETAIL: one row per GLPI case affected by an unmatched person.

    1:N off :class:`GlpiUnmatchedAssignee` — a second case for the SAME
    person is appended here, never duplicating the header (user-homologation
    spec, "Segundo caso sin homologar de la misma persona"). No Audit/Tenant
    mixin: scoped transitively via the header -> connector -> organization.
    """

    __tablename__ = "glpi_unmatched_cases"
    __table_args__ = (
        UniqueConstraint(
            "unmatched_assignee_id",
            "glpi_ticket_id",
            name="uq_glpi_unmatched_cases_assignee_ticket",
        ),
    )

    unmatched_assignee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("glpi_unmatched_assignees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    glpi_ticket_id: Mapped[str] = mapped_column(String(64), nullable=False)
    glpi_ticket_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    glpi_ticket_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
