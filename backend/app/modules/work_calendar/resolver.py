"""Cascading resolver: proyecto → override de la raíz → default de empresa →
default global (design.md, "Data Flow").
"""

import uuid

from app.modules.work_calendar.repository import WorkCalendarRepository
from app.modules.work_calendar.schemas import (
    DEFAULT_HOURS_PER_DAY,
    DEFAULT_WORKING_DAYS,
    CalendarSource,
    ResolvedCalendar,
)
from app.shared.exceptions import AppException


class WorkCalendarResolver:
    """Single seam ``resolve(organization_id, project_id) -> ResolvedCalendar``.

    No caching in this MVP (specs/work-calendar/spec.md, "Limitaciones y
    deuda conocida"); changes 34/35 wrap this in a cache keyed by
    ``(organization_id, root_project_id)`` when they need it hot.

    ``organizations`` is typed loosely (duck-typed to ``get_by_id(...) ->
    object with working_hours_per_day/working_days``) so tests can inject a
    stub without touching the real ``NOT NULL`` constraint (tasks.md T2.9).
    """

    def __init__(self, repository: WorkCalendarRepository, organizations) -> None:
        self.repository = repository
        self.organizations = organizations

    async def resolve(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> ResolvedCalendar:
        root = await self.repository.root_override(organization_id, project_id)
        if root is None:
            raise AppException(
                "El proyecto no existe o no pertenece a tu organización.",
                code="project_not_found",
                status_code=404,
            )

        hours, days = root
        if hours is not None and days is not None:
            return ResolvedCalendar(
                working_hours_per_day=hours,
                working_days=days,
                source=CalendarSource.project_root_override,
            )

        organization = await self.organizations.get_by_id(organization_id)
        if (
            organization is not None
            and organization.working_hours_per_day is not None
            and organization.working_days is not None
        ):
            return ResolvedCalendar(
                working_hours_per_day=organization.working_hours_per_day,
                working_days=organization.working_days,
                source=CalendarSource.organization_default,
            )

        # Defensivo: teóricamente inalcanzable una vez la Fase 1 garantiza
        # organizations.working_hours_per_day/working_days NOT NULL — cubre
        # únicamente un doble de pruebas o un dato corrupto preexistente.
        return ResolvedCalendar(
            working_hours_per_day=DEFAULT_HOURS_PER_DAY,
            working_days=DEFAULT_WORKING_DAYS,
            source=CalendarSource.global_default,
        )
