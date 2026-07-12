"""Data-access layer for task comments."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.comments.models import TaskComment
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /tasks/{id}/comments``. First entry is
# the default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": TaskComment.created_at,
    "body": TaskComment.body,
}


class CommentRepository:
    """Async repository encapsulating comment persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[TaskComment], int]:
        """Return ``(comments, total)`` — active comments for a task, oldest first."""

        stmt = select(TaskComment).where(
            TaskComment.task_id == task_id,
            TaskComment.organization_id == organization_id,
            TaskComment.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(TaskComment.created_at.asc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

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
