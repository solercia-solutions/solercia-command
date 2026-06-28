"""Data-access layer for task comments."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import TaskComment


class CommentRepository:
    """Async repository encapsulating comment persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> Sequence[TaskComment]:
        """Return active comments for a task, oldest first."""

        result = await self.db.execute(
            select(TaskComment)
            .where(
                TaskComment.task_id == task_id,
                TaskComment.organization_id == organization_id,
                TaskComment.is_active.is_(True),
            )
            .order_by(TaskComment.created_at.asc())
        )
        return result.scalars().all()

    async def get(
        self,
        organization_id: uuid.UUID,
        comment_id: uuid.UUID,
    ) -> TaskComment | None:
        """Return a single active comment scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(TaskComment).where(
                TaskComment.id == comment_id,
                TaskComment.organization_id == organization_id,
                TaskComment.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, comment: TaskComment) -> TaskComment:
        """Persist a new comment and return the refreshed instance."""

        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def save(self, comment: TaskComment) -> TaskComment:
        """Flush pending changes on an attached comment and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(comment)
        return comment
