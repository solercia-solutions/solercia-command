"""Integration tests (real Postgres) for the cascading resolver of change
28-calendario-laboral (tasks.md T2.5/T2.8/T2.9/T2.10).

``WorkCalendarResolver.resolve(organization_id, project_id)`` implements the
cascade proyecto → override de la raíz del equipo → default de la empresa →
default global (design.md, "Data Flow"), and must NEVER cross
``organization_id`` (specs/work-calendar/spec.md, "Aislamiento de tenant en
la resolución").

Seeds data directly through the ORM (``session`` SAVEPOINT fixture), same
convention as ``test_project_hierarchy_repository.py`` — no HTTP layer here.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.work_calendar.repository import WorkCalendarRepository
from app.modules.work_calendar.resolver import WorkCalendarResolver
from app.modules.work_calendar.schemas import CalendarSource
from app.shared.enums import Methodology
from app.shared.exceptions import AppException
from tests.conftest import skip_no_db


async def _make_project(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    *,
    parent_project_id: uuid.UUID | None = None,
    working_hours_per_day: Decimal | None = None,
    working_days: list[int] | None = None,
) -> Project:
    project = Project(
        organization_id=organization_id,
        name=name,
        methodology=Methodology.planner,
        code=uuid.uuid4().hex[:8].upper(),
        task_counter=0,
        parent_project_id=parent_project_id,
        working_hours_per_day=working_hours_per_day,
        working_days=working_days,
    )
    session.add(project)
    await session.flush()
    return project


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_grandchild_inherits_root_override_with_weekend_days(
    session: AsyncSession, tenant: Organization
) -> None:
    """A root with a weekend override cascades all the way to its grandchild."""

    root = await _make_project(
        session,
        tenant.id,
        "Soporte",
        working_hours_per_day=Decimal("8"),
        working_days=[6, 7],
    )
    child = await _make_project(
        session, tenant.id, "Atención", parent_project_id=root.id
    )
    grandchild = await _make_project(
        session, tenant.id, "Turno noche", parent_project_id=child.id
    )

    resolver = WorkCalendarResolver(WorkCalendarRepository(session), None)
    resolved = await resolver.resolve(tenant.id, grandchild.id)

    assert resolved.working_hours_per_day == Decimal("8")
    assert resolved.working_days == [6, 7]
    assert resolved.source is CalendarSource.project_root_override


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_root_without_override_falls_back_to_organization_default(
    session: AsyncSession, tenant: Organization
) -> None:
    """A root with no override cascades to the organization's own calendar."""

    tenant.working_hours_per_day = Decimal("6")
    tenant.working_days = [1, 2, 3, 4]
    await session.flush()

    root = await _make_project(session, tenant.id, "Raíz sin override")
    child = await _make_project(
        session, tenant.id, "Hijo", parent_project_id=root.id
    )

    from app.modules.organizations.repository import OrganizationRepository

    resolver = WorkCalendarResolver(
        WorkCalendarRepository(session), OrganizationRepository(session)
    )
    resolved = await resolver.resolve(tenant.id, child.id)

    assert resolved.working_hours_per_day == Decimal("6")
    assert resolved.working_days == [1, 2, 3, 4]
    assert resolved.source is CalendarSource.organization_default


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_defaults_globally_when_the_organization_has_no_resolvable_calendar(
    session: AsyncSession, tenant: Organization
) -> None:
    """A double organizations repository with no resolvable default falls to global."""

    root = await _make_project(session, tenant.id, "Raíz")

    class _NoDefaultOrganizationRepository:
        async def get_by_id(self, organization_id: uuid.UUID):
            class _Blank:
                working_hours_per_day = None
                working_days = None

            return _Blank()

    resolver = WorkCalendarResolver(
        WorkCalendarRepository(session), _NoDefaultOrganizationRepository()
    )
    resolved = await resolver.resolve(tenant.id, root.id)

    assert resolved.working_hours_per_day == Decimal("8")
    assert resolved.working_days == [1, 2, 3, 4, 5]
    assert resolved.source is CalendarSource.global_default


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_never_crosses_organization_id(
    session: AsyncSession, tenant: Organization
) -> None:
    """Resolving a project of another organization raises project_not_found (404)."""

    from app.modules.organizations.models import Organization as OrganizationModel

    other_org = OrganizationModel(
        name="Other Org", slug=f"other-org-{uuid.uuid4().hex[:12]}"
    )
    session.add(other_org)
    await session.flush()
    other_project = await _make_project(session, other_org.id, "De la Org B")

    resolver = WorkCalendarResolver(WorkCalendarRepository(session), None)

    with pytest.raises(AppException) as exc_info:
        await resolver.resolve(tenant.id, other_project.id)

    assert exc_info.value.code == "project_not_found"
    assert exc_info.value.status_code == 404
