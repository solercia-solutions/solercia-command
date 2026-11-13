"""External origin anchor on ``projects`` and ``sprints``.

``(source, external_key)`` lets the Jira importer find, on a re-import, the
project and sprints it created before instead of duplicating them. Projects
are unique per organization; sprints are unique per project (``project_id``
already implies the organization). Rows without ``external_key`` never
collide. Runs against the real PostgreSQL test database (partial indexes).
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.shared.enums import Methodology
from tests.conftest import skip_no_db


async def _org(session: AsyncSession) -> Organization:
    organization = Organization(name="Org anclas", slug=f"anclas-{uuid.uuid4().hex[:12]}")
    session.add(organization)
    await session.flush()
    return organization


def _project(organization: Organization, code: str, **anchor: str | None) -> Project:
    return Project(
        organization_id=organization.id,
        name=f"Proyecto {code}",
        methodology=Methodology.scrum,
        code=code,
        task_counter=0,
        **anchor,
    )


class TestProjectAnchor:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_same_anchor_twice_in_one_organization_is_rejected(
        self, session: AsyncSession
    ) -> None:
        organization = await _org(session)
        session.add(_project(organization, "AAA", source="jira", external_key="X"))
        await session.flush()

        session.add(_project(organization, "BBB", source="jira", external_key="X"))
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.flush()

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_projects_without_external_key_never_collide(
        self, session: AsyncSession
    ) -> None:
        organization = await _org(session)
        session.add(_project(organization, "AAA"))
        session.add(_project(organization, "BBB"))
        await session.flush()

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_same_anchor_in_two_organizations_is_allowed(
        self, session: AsyncSession
    ) -> None:
        first, second = await _org(session), await _org(session)
        session.add(_project(first, "AAA", source="jira", external_key="X"))
        session.add(_project(second, "AAA", source="jira", external_key="X"))
        await session.flush()


class TestSprintAnchor:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_same_anchor_twice_in_one_project_is_rejected(
        self, session: AsyncSession
    ) -> None:
        organization = await _org(session)
        project = _project(organization, "AAA")
        session.add(project)
        await session.flush()
        session.add(Sprint(project_id=project.id, name="S1", source="jira", external_key="S1"))
        await session.flush()

        session.add(Sprint(project_id=project.id, name="S1b", source="jira", external_key="S1"))
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.flush()

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_sprints_without_external_key_never_collide(
        self, session: AsyncSession
    ) -> None:
        organization = await _org(session)
        project = _project(organization, "AAA")
        session.add(project)
        await session.flush()
        session.add(Sprint(project_id=project.id, name="S1"))
        session.add(Sprint(project_id=project.id, name="S2"))
        await session.flush()

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_same_anchor_in_two_projects_is_allowed(self, session: AsyncSession) -> None:
        organization = await _org(session)
        first, second = _project(organization, "AAA"), _project(organization, "BBB")
        session.add_all([first, second])
        await session.flush()
        session.add(Sprint(project_id=first.id, name="S1", source="jira", external_key="S1"))
        session.add(Sprint(project_id=second.id, name="S1", source="jira", external_key="S1"))
        await session.flush()
