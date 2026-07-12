"""Data-access layer for attachments."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.attachments.models import Attachment
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /tasks/{id}/attachments``. First entry is
# the default order when pagination is requested without an explicit ``sort``.
# Only the task-scoped list is paginable in this change; the comment-scoped
# list (``list_for_target(..., "comment", ...)``) is out of scope.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Attachment.created_at,
    "original_name": Attachment.original_name,
    "size_bytes": Attachment.size_bytes,
}


class AttachmentRepository:
    """Async repository encapsulating attachment persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_target(
        self,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Attachment], int]:
        """Return ``(attachments, total)`` for a target entity, newest first."""

        stmt = select(Attachment).where(
            Attachment.organization_id == organization_id,
            Attachment.target_type == target_type,
            Attachment.target_id == target_id,
            Attachment.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Attachment.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self,
        organization_id: uuid.UUID,
        attachment_id: uuid.UUID,
    ) -> Attachment | None:
        """Return a single active attachment scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.organization_id == organization_id,
                Attachment.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, attachment: Attachment) -> Attachment:
        """Persist a new attachment and return the refreshed instance."""

        self.db.add(attachment)
        await self.db.commit()
        await self.db.refresh(attachment)
        return attachment

    async def save(self, attachment: Attachment) -> Attachment:
        """Flush pending changes on an attached record and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(attachment)
        return attachment
