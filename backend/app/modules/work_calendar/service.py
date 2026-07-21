"""Business logic for the work-calendar module: company calendar, root
override, resolved calendar. Orchestrates ``OrganizationRepository``,
``ProjectRepository``, ``WorkCalendarRepository`` and ``WorkCalendarResolver``
— the service NEVER touches SQLAlchemy directly (project convention).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.work_calendar.repository import WorkCalendarRepository
from app.modules.work_calendar.resolver import WorkCalendarResolver
from app.modules.work_calendar.schemas import (
    ResolvedCalendar,
    WorkCalendarConfig,
    WorkCalendarOverride,
)
from app.shared.exceptions import AppException


class WorkCalendarService:
    """Read/write company calendar + root-project override, and resolution."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.organizations = OrganizationRepository(db)
        self.projects = ProjectRepository(db)
        self.calendars = WorkCalendarRepository(db)
        self.resolver = WorkCalendarResolver(self.calendars, self.organizations)

    async def get_organization_calendar(
        self, organization_id: uuid.UUID
    ) -> WorkCalendarConfig:
        """Return the caller's organization calendar (default 8/[1..5])."""

        organization = await self._get_organization(organization_id)
        return WorkCalendarConfig(
            working_hours_per_day=organization.working_hours_per_day,
            working_days=organization.working_days,
        )

    async def set_organization_calendar(
        self,
        organization_id: uuid.UUID,
        payload: WorkCalendarConfig,
        *,
        actor_id: uuid.UUID | None,
    ) -> WorkCalendarConfig:
        """Persist the company calendar — caller already ``require_admin``-gated."""

        organization = await self._get_organization(organization_id)
        organization.working_hours_per_day = payload.working_hours_per_day
        organization.working_days = payload.working_days
        organization.updated_by = actor_id
        organization = await self.organizations.save(organization)
        return WorkCalendarConfig(
            working_hours_per_day=organization.working_hours_per_day,
            working_days=organization.working_days,
        )

    async def get_project_override(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> WorkCalendarOverride:
        """Return the RAW override of ``project_id`` (``null`` if non-root/unset)."""

        project = await self._get_project(organization_id, project_id)
        return WorkCalendarOverride(
            working_hours_per_day=project.working_hours_per_day,
            working_days=project.working_days,
        )

    async def set_project_override(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        payload: WorkCalendarOverride,
        *,
        actor_id: uuid.UUID | None,
    ) -> WorkCalendarOverride:
        """Set (or clear with ``null``) the root project's override.

        Rejects with ``override_requires_root`` (422) when ``project_id`` is
        NOT a root project (``parent_project_id is not None``) — caller must
        already be gated to ``admin``/``manager`` (specs/work-calendar/spec.md).
        """

        project = await self._get_project(organization_id, project_id)
        if project.parent_project_id is not None:
            raise AppException(
                "Solo el proyecto raíz de un equipo puede tener su propio "
                "calendario laboral.",
                code="override_requires_root",
                status_code=422,
            )

        project.working_hours_per_day = payload.working_hours_per_day
        project.working_days = payload.working_days
        project.updated_by = actor_id
        project = await self.projects.save(project)
        return WorkCalendarOverride(
            working_hours_per_day=project.working_hours_per_day,
            working_days=project.working_days,
        )

    async def get_resolved(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> ResolvedCalendar:
        """Return the effective calendar of ``project_id`` at any depth."""

        return await self.resolver.resolve(organization_id, project_id)

    async def _get_organization(self, organization_id: uuid.UUID) -> Organization:
        organization = await self.organizations.get_by_id(organization_id)
        if organization is None:
            raise AppException(
                "La organización no existe o está inactiva.",
                code="organization_not_found",
                status_code=404,
            )
        return organization

    async def _get_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        project = await self.projects.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no pertenece a tu organización.",
                code="project_not_found",
                status_code=404,
            )
        return project
