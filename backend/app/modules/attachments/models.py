"""Attachment ORM model.

Attachments are polymorphic: one record covers files linked to tasks and files
linked to comments. ``target_type`` + ``target_id`` identify the owner without
a hard FK so a single table works for both targets.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Attachment(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A file attached to a task or comment."""

    __tablename__ = "attachments"

    # Discriminator: 'task' | 'comment'
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # UUID of the target entity (task.id or task_comment.id). No FK because
    # the target type varies — integrity is enforced at the service layer.
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    # Human-readable name provided by the uploader; never used as a file path.
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # UUID-based filename used on disk to prevent path-traversal attacks.
    stored_name: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    # MIME type reported by the client and normalized at upload time.
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
