"""Data-access layer for checklists, items and their aggregated progress."""

import uuid
from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checklists.models import ChecklistItem, TaskChecklist


class ChecklistRepository:
    """Async repository encapsulating checklist and item persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- TaskChecklist ---------------------------------------------------

    async def list_for_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Sequence[TaskChecklist]:
        """Return the active checklists of a task, ordered for display."""

        result = await self.db.execute(
            select(TaskChecklist)
            .where(
                TaskChecklist.task_id == task_id,
                TaskChecklist.organization_id == organization_id,
                TaskChecklist.is_active.is_(True),
            )
            .order_by(TaskChecklist.order.asc(), TaskChecklist.created_at.asc())
        )
        return result.scalars().all()

    async def get_checklist(
        self, organization_id: uuid.UUID, checklist_id: uuid.UUID
    ) -> TaskChecklist | None:
        """Return a single active checklist scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(TaskChecklist).where(
                TaskChecklist.id == checklist_id,
                TaskChecklist.organization_id == organization_id,
                TaskChecklist.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_checklist(self, checklist: TaskChecklist) -> TaskChecklist:
        """Persist a new checklist and return the refreshed instance."""

        self.db.add(checklist)
        await self.db.commit()
        await self.db.refresh(checklist)
        return checklist

    async def save_checklist(self, checklist: TaskChecklist) -> TaskChecklist:
        """Flush pending changes on an attached checklist and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(checklist)
        return checklist

    # -- ChecklistItem -----------------------------------------------------

    async def list_items(self, checklist_id: uuid.UUID) -> Sequence[ChecklistItem]:
        """Return the active items of a checklist, ordered for display."""

        result = await self.db.execute(
            select(ChecklistItem)
            .where(
                ChecklistItem.checklist_id == checklist_id,
                ChecklistItem.is_active.is_(True),
            )
            .order_by(ChecklistItem.order.asc(), ChecklistItem.created_at.asc())
        )
        return result.scalars().all()

    async def get_item(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> ChecklistItem | None:
        """Return a single active item scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(ChecklistItem).where(
                ChecklistItem.id == item_id,
                ChecklistItem.organization_id == organization_id,
                ChecklistItem.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_item(self, item: ChecklistItem) -> ChecklistItem:
        """Persist a new item and return the refreshed instance."""

        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def save_item(self, item: ChecklistItem) -> ChecklistItem:
        """Flush pending changes on an attached item and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(item)
        return item

    # -- Progress ------------------------------------------------------------

    async def get_progress_for_checklist(
        self, checklist_id: uuid.UUID
    ) -> tuple[int, int]:
        """Return ``(done, total)`` item counts for a single checklist.

        Mirrors ``TaskRepository.get_subtask_counts`` (two simple ``COUNT``
        queries), design.md T09.
        """

        total_result = await self.db.execute(
            select(func.count()).select_from(ChecklistItem).where(
                ChecklistItem.checklist_id == checklist_id,
                ChecklistItem.is_active.is_(True),
            )
        )
        total = total_result.scalar_one() or 0

        done_result = await self.db.execute(
            select(func.count()).select_from(ChecklistItem).where(
                ChecklistItem.checklist_id == checklist_id,
                ChecklistItem.is_active.is_(True),
                ChecklistItem.is_done.is_(True),
            )
        )
        done = done_result.scalar_one() or 0
        return done, total

    async def get_progress_for_task(
        self, task_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, int, int]]:
        """Return ``[(checklist_id, done, total), ...]`` for every active checklist of a task.

        A single grouped query, regardless of how many checklists the task
        has — used to embed per-checklist progress when listing (no N+1) and
        to compute the task-level aggregate (design.md, "Enriquecer el
        detalle sin N+1").
        """

        result = await self.db.execute(
            select(
                ChecklistItem.checklist_id,
                func.count().label("total"),
                func.sum(case((ChecklistItem.is_done.is_(True), 1), else_=0)).label(
                    "done"
                ),
            )
            .join(TaskChecklist, TaskChecklist.id == ChecklistItem.checklist_id)
            .where(
                TaskChecklist.task_id == task_id,
                TaskChecklist.is_active.is_(True),
                ChecklistItem.is_active.is_(True),
            )
            .group_by(ChecklistItem.checklist_id)
        )
        return [
            (row.checklist_id, int(row.done or 0), int(row.total or 0))
            for row in result
        ]
