"""Data-access layer for attachments."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attachments.models import Attachment


class AttachmentRepository:
    """Async repository encapsulating attachment persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_target(
        self,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> Sequence[Attachment]:
        """Return active attachments for a target entity, newest first."""

        result = await self.db.execute(
            select(Attachment)
            .where(
                Attachment.organization_id == organization_id,
                Attachment.target_type == target_type,
                Attachment.target_id == target_id,
                Attachment.is_active.is_(True),
            )
            .order_by(Attachment.created_at.desc())
        )
        return result.scalars().all()

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
