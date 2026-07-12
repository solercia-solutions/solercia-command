"""Reusable declarative mixins shared across ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class PkMixin:
    """Primary key as a UUID generated on the application side."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Automatically managed creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Logical deletion flags so rows can be hidden instead of removed."""

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class TenantMixin:
    """Multi-tenant scoping by organization."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class AuditMixin:
    """Tracks which user created/last-updated a row.

    Both columns are nullable UUID foreign keys to ``users.id`` with
    ``ON DELETE SET NULL`` — deleting the actor user never blocks or cascades
    into the audited row, it just clears the reference. Populated explicitly
    by the service layer from the authenticated actor (see
    ``app/dependencies.py::get_actor_id``); NEVER accepted as direct client
    input. Rows written outside a request context (e.g. the startup seed in
    ``db_init.py``) or created before this column existed keep both fields
    ``NULL`` permanently — no backfill.
    """

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
