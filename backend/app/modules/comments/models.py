"""TaskComment ORM model."""

import uuid

from sqlalchemy import JSON, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class TaskComment(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A comment posted on a task, with optional @-mention tracking."""

    __tablename__ = "task_comments"
    __table_args__ = (
        # Trigram GIN index backing GET /search (change 10-busqueda-global,
        # design.md "Índices GIN"); accelerates ILIKE '%q%' + similarity().
        Index(
            "ix_task_comments_body_trgm",
            "body",
            postgresql_using="gin",
            postgresql_ops={"body": "gin_trgm_ops"},
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    # Rich text / HTML body. Max ~100k chars.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON array of UUID strings parsed from ``@mention`` patterns in ``body``.
    # Stored for future notification dispatch; no notifications are sent yet.
    mentioned_user_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
