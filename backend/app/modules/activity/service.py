"""Business logic for reading task history. Read-only: no create/update/delete
use-case exists here — rows are appended exclusively via ``recorder.record_task_history``
from the services that mutate tasks (activity-history.md, "Historial de solo lectura").
"""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activity.repository import ActivityRepository
from app.modules.activity.schemas import TaskHistoryResponse
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


class ActivityService:
    """Orchestrates task-history read use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ActivityRepository(db)
        self.tasks = TaskRepository(db)

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TaskHistoryResponse], int]:
        """Return ``(rows, total)`` — a task's history, newest first by default."""

        await self._require_task(organization_id, task_id)
        rows, total = await self.repo.list_for_task(organization_id, task_id, pagination)
        return [TaskHistoryResponse.model_validate(row) for row in rows], total

    async def list_for_actor(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        on_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TaskHistoryResponse], int]:
        """Return ``(rows, total)`` — changes an actor caused, optionally date-bounded."""

        rows, total = await self.repo.list_for_actor(
            organization_id,
            actor_id,
            on_date=on_date,
            date_from=date_from,
            date_to=date_to,
            pagination=pagination,
        )
        return [TaskHistoryResponse.model_validate(row) for row in rows], total

    async def _require_task(self, organization_id: uuid.UUID, task_id: uuid.UUID):
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task
