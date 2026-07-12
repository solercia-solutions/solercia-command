"""Business logic for time logs.

Registering time is always for the caller themself. Editing/deleting is
strictly limited to the owner (no role exemption — design.md gate correction
#2). Reading another user's entries is allowed only for ``admin``/``manager``
(the "ver todos" exemption); a plain ``member``/``viewer`` may only read their
own — this mirrors the role check ``require_role(MemberRole.admin,
MemberRole.manager)`` would enforce, applied inline because the route also
has to allow unrestricted self-access, which a route-level dependency alone
cannot express.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.repository import TaskRepository
from app.modules.time_logs.models import TaskTimeLog
from app.modules.time_logs.repository import TimeLogRepository
from app.modules.time_logs.schemas import (
    DailyHoursEntry,
    TimeLogCreate,
    TimeLogResponse,
    TimeLogSummary,
    TimeLogUpdate,
    WeeklyHoursEntry,
)
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

# Roles allowed to read another user's time-log entries ("ver todos").
_SUPERVISOR_ROLES = (MemberRole.admin, MemberRole.manager)


class TimeLogService:
    """Orchestrates time-log use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = TimeLogRepository(db)
        self.tasks = TaskRepository(db)

    async def list_for_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TimeLogResponse], int]:
        """Return ``(entries, total)`` for a task's time logs."""

        await self._require_task(organization_id, task_id)
        rows, total = await self.repo.list_for_task(organization_id, task_id, pagination)
        return [TimeLogResponse.model_validate(row) for row in rows], total

    async def create_time_log(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        data: TimeLogCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TimeLogResponse:
        """Register time worked on a task for the authenticated caller."""

        await self._require_task(organization_id, task_id)
        log = TaskTimeLog(
            organization_id=organization_id,
            task_id=task_id,
            user_id=user_id,
            work_date=data.date,
            hours=data.hours,
            note=data.note,
            created_by=actor_id,
            updated_by=actor_id,
        )
        log = await self.repo.create(log)
        return TimeLogResponse.model_validate(log)

    async def update_time_log(
        self,
        organization_id: uuid.UUID,
        log_id: uuid.UUID,
        requester_id: uuid.UUID,
        data: TimeLogUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TimeLogResponse:
        """Edit a time-log entry. Only the owner may edit it (no role exemption)."""

        log = await self._require_owned_log(organization_id, log_id, requester_id, "editarlo")

        changes = data.model_dump(exclude_unset=True)
        if "date" in changes:
            log.work_date = changes["date"]
        if "hours" in changes:
            log.hours = changes["hours"]
        if "note" in changes:
            log.note = changes["note"]

        log.updated_by = actor_id
        log = await self.repo.save(log)
        return TimeLogResponse.model_validate(log)

    async def delete_time_log(
        self,
        organization_id: uuid.UUID,
        log_id: uuid.UUID,
        requester_id: uuid.UUID,
    ) -> None:
        """Soft-delete a time-log entry. Only the owner may delete it."""

        log = await self._require_owned_log(organization_id, log_id, requester_id, "eliminarlo")
        log.is_active = False
        log.deleted_at = datetime.now(UTC)
        await self.repo.save(log)

    async def list_for_user(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        requester_id: uuid.UUID,
        requester_role: MemberRole,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TimeLogResponse], int]:
        """Return ``(entries, total)`` for a user, honoring the propio-vs-todos rule."""

        self._require_visibility(target_user_id, requester_id, requester_role)
        rows, total = await self.repo.list_for_user(
            organization_id,
            target_user_id,
            date_from=date_from,
            date_to=date_to,
            pagination=pagination,
        )
        return [TimeLogResponse.model_validate(row) for row in rows], total

    async def summary_for_user(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        requester_id: uuid.UUID,
        requester_role: MemberRole,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> TimeLogSummary:
        """Return the daily/weekly hour aggregation for a user."""

        self._require_visibility(target_user_id, requester_id, requester_role)
        daily = await self.repo.daily_summary(
            organization_id, target_user_id, date_from=date_from, date_to=date_to
        )
        weekly = await self.repo.weekly_summary(
            organization_id, target_user_id, date_from=date_from, date_to=date_to
        )
        return TimeLogSummary(
            daily=[DailyHoursEntry(date=d, hours=h) for d, h in daily],
            weekly=[WeeklyHoursEntry(week_start=w, hours=h) for w, h in weekly],
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _require_visibility(
        target_user_id: uuid.UUID,
        requester_id: uuid.UUID,
        requester_role: MemberRole,
    ) -> None:
        """Enforce "propio vs. todos": self always allowed; others need admin/manager."""

        if target_user_id == requester_id:
            return
        if requester_role in _SUPERVISOR_ROLES:
            return
        raise AppException(
            "No tienes permisos para consultar el tiempo de otro usuario.",
            code="time_log_forbidden",
            status_code=403,
        )

    async def _require_task(self, organization_id: uuid.UUID, task_id: uuid.UUID):
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task

    async def _require_log(
        self, organization_id: uuid.UUID, log_id: uuid.UUID
    ) -> TaskTimeLog:
        log = await self.repo.get(organization_id, log_id)
        if log is None:
            raise AppException(
                "El registro de tiempo no existe o no tienes acceso a él.",
                code="time_log_not_found",
                status_code=404,
            )
        return log

    async def _require_owned_log(
        self,
        organization_id: uuid.UUID,
        log_id: uuid.UUID,
        requester_id: uuid.UUID,
        verb: str,
    ) -> TaskTimeLog:
        log = await self._require_log(organization_id, log_id)
        if log.user_id != requester_id:
            raise AppException(
                f"Solo el dueño del registro de tiempo puede {verb}.",
                code="time_log_forbidden",
                status_code=403,
            )
        return log
