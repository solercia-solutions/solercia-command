"""Business logic for checklists, items and their aggregated progress."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checklists.models import ChecklistItem, TaskChecklist
from app.modules.checklists.repository import ChecklistRepository
from app.modules.checklists.schemas import (
    ChecklistItemCreate,
    ChecklistItemRead,
    ChecklistItemUpdate,
    TaskChecklistCreate,
    TaskChecklistRead,
    TaskChecklistUpdate,
)
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException


class ChecklistService:
    """Orchestrates checklist/item use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ChecklistRepository(db)
        self.tasks = TaskRepository(db)

    # -- TaskChecklist ---------------------------------------------------

    async def list_checklists(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[TaskChecklistRead]:
        """Return the task's active checklists, each with its progress embedded.

        One extra query total (the grouped progress aggregate) regardless of
        how many checklists the task has — never N+1.
        """

        await self._require_task(organization_id, task_id)
        checklists = await self.repo.list_for_task(organization_id, task_id)
        progress = dict.fromkeys(
            (c.id for c in checklists), (0, 0)
        )
        progress.update(
            {
                checklist_id: (done, total)
                for checklist_id, done, total in await self.repo.get_progress_for_task(
                    task_id
                )
            }
        )
        return [
            self._to_read(checklist, *progress[checklist.id])
            for checklist in checklists
        ]

    async def create_checklist(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        data: TaskChecklistCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaskChecklistRead:
        """Create a checklist on a task. Starts with no items (0/0 progress)."""

        await self._require_task(organization_id, task_id)
        checklist = TaskChecklist(
            organization_id=organization_id,
            task_id=task_id,
            title=data.title,
            order=data.order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        checklist = await self.repo.create_checklist(checklist)
        return self._to_read(checklist, 0, 0)

    async def update_checklist(
        self,
        organization_id: uuid.UUID,
        checklist_id: uuid.UUID,
        data: TaskChecklistUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaskChecklistRead:
        """Apply a partial update (rename/reorder) to a checklist."""

        checklist = await self._require_checklist(organization_id, checklist_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("title", "order"):
            if field in changes:
                setattr(checklist, field, changes[field])
        checklist.updated_by = actor_id
        checklist = await self.repo.save_checklist(checklist)
        done, total = await self.repo.get_progress_for_checklist(checklist.id)
        return self._to_read(checklist, done, total)

    async def delete_checklist(
        self, organization_id: uuid.UUID, checklist_id: uuid.UUID
    ) -> None:
        """Soft-delete a checklist. Its items stop counting toward progress."""

        checklist = await self._require_checklist(organization_id, checklist_id)
        checklist.is_active = False
        checklist.deleted_at = datetime.now(UTC)
        await self.repo.save_checklist(checklist)

    # -- ChecklistItem -----------------------------------------------------

    async def list_items(
        self, organization_id: uuid.UUID, checklist_id: uuid.UUID
    ) -> list[ChecklistItemRead]:
        """Return the active items of a checklist, ordered for display."""

        await self._require_checklist(organization_id, checklist_id)
        items = await self.repo.list_items(checklist_id)
        return [ChecklistItemRead.model_validate(item) for item in items]

    async def create_item(
        self,
        organization_id: uuid.UUID,
        checklist_id: uuid.UUID,
        data: ChecklistItemCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ChecklistItemRead:
        """Create an item within a checklist."""

        checklist = await self._require_checklist(organization_id, checklist_id)
        item = ChecklistItem(
            organization_id=organization_id,
            checklist_id=checklist.id,
            text=data.text,
            order=data.order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        item = await self.repo.create_item(item)
        return ChecklistItemRead.model_validate(item)

    async def update_item(
        self,
        organization_id: uuid.UUID,
        item_id: uuid.UUID,
        data: ChecklistItemUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ChecklistItemRead:
        """Apply a partial update (edit text / reorder) to an item."""

        item = await self._require_item(organization_id, item_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("text", "order"):
            if field in changes:
                setattr(item, field, changes[field])
        item.updated_by = actor_id
        item = await self.repo.save_item(item)
        return ChecklistItemRead.model_validate(item)

    async def toggle_item(
        self,
        organization_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ChecklistItemRead:
        """Flip an item's ``is_done`` flag."""

        item = await self._require_item(organization_id, item_id)
        item.is_done = not item.is_done
        item.updated_by = actor_id
        item = await self.repo.save_item(item)
        return ChecklistItemRead.model_validate(item)

    async def delete_item(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> None:
        """Soft-delete an item."""

        item = await self._require_item(organization_id, item_id)
        item.is_active = False
        item.deleted_at = datetime.now(UTC)
        await self.repo.save_item(item)

    # -- Aggregate progress (Batch E: TaskRead.checklist_progress) ---------

    async def get_checklist_progress(self, task_id: uuid.UUID) -> tuple[int, int]:
        """Return ``(done, total)`` aggregated across every active checklist of a task.

        Mirrors ``TaskRepository.get_subtask_counts`` in shape (design.md
        T09) — one grouped query, then a Python-side sum. Feeds
        ``TaskRead.checklist_progress`` (design.md Interfaces/Contracts).
        """

        rows = await self.repo.get_progress_for_task(task_id)
        done = sum(row[1] for row in rows)
        total = sum(row[2] for row in rows)
        return done, total

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _to_read(checklist: TaskChecklist, done: int, total: int) -> TaskChecklistRead:
        read = TaskChecklistRead.model_validate(checklist)
        read.done = done
        read.total = total
        return read

    async def _require_task(self, organization_id: uuid.UUID, task_id: uuid.UUID):
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task

    async def _require_checklist(
        self, organization_id: uuid.UUID, checklist_id: uuid.UUID
    ) -> TaskChecklist:
        checklist = await self.repo.get_checklist(organization_id, checklist_id)
        if checklist is None:
            raise AppException(
                "El checklist no existe o no tienes acceso a él.",
                code="checklist_not_found",
                status_code=404,
            )
        return checklist

    async def _require_item(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> ChecklistItem:
        item = await self.repo.get_item(organization_id, item_id)
        if item is None:
            raise AppException(
                "El ítem no existe o no tienes acceso a él.",
                code="checklist_item_not_found",
                status_code=404,
            )
        return item
