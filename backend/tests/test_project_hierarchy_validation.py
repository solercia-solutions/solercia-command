"""Tests for ``ProjectService.validate_parent`` (change 21-project-hierarchy,
tasks.md T2.3): the shared validation orchestrating self-parent, tenant/active,
cycle and max-depth checks for both project creation and reparenting.

R1 Relación padre-hijo y restricciones estructurales · R2 Prevención de ciclos
· R3 Profundidad máxima configurable · R9 Contrato de envelope y errores
(specs/project-hierarchy/spec.md).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project
from app.modules.projects.service import ProjectService
from app.shared.exceptions import AppException
from tests.conftest import skip_no_db


async def _make_project(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    *,
    parent_project_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> Project:
    project = Project(
        organization_id=organization_id,
        name=name,
        methodology="planner",
        code=uuid.uuid4().hex[:8].upper(),
        task_counter=0,
        parent_project_id=parent_project_id,
        is_active=is_active,
    )
    session.add(project)
    await session.flush()
    return project


# ---------------------------------------------------------------------------
# self_parent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_rejects_self_parent(
    session: AsyncSession, tenant
) -> None:
    project = await _make_project(session, tenant.id, "Self Parent Project")

    service = ProjectService(session)
    with pytest.raises(AppException) as exc_info:
        await service.validate_parent(tenant.id, project.id, child_id=project.id)

    assert exc_info.value.code == "self_parent"
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# tenant / active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_rejects_parent_from_another_organization(
    session: AsyncSession, tenant, second_tenant
) -> None:
    foreign_parent = await _make_project(session, second_tenant.id, "Foreign Parent")
    child = await _make_project(session, tenant.id, "Local Child")

    service = ProjectService(session)
    with pytest.raises(AppException) as exc_info:
        await service.validate_parent(tenant.id, foreign_parent.id, child_id=child.id)

    assert exc_info.value.code == "parent_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_rejects_inactive_parent(
    session: AsyncSession, tenant
) -> None:
    inactive_parent = await _make_project(
        session, tenant.id, "Inactive Parent", is_active=False
    )
    child = await _make_project(session, tenant.id, "Child Of Inactive")

    service = ProjectService(session)
    with pytest.raises(AppException) as exc_info:
        await service.validate_parent(tenant.id, inactive_parent.id, child_id=child.id)

    assert exc_info.value.code == "parent_not_found"
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_rejects_transitive_cycle(
    session: AsyncSession, tenant
) -> None:
    """A is parent of B, B is parent of C. Reparenting A under C is a cycle."""

    project_a = await _make_project(session, tenant.id, "Cycle Root A")
    project_b = await _make_project(
        session, tenant.id, "Cycle Middle B", parent_project_id=project_a.id
    )
    project_c = await _make_project(
        session, tenant.id, "Cycle Leaf C", parent_project_id=project_b.id
    )

    service = ProjectService(session)
    with pytest.raises(AppException) as exc_info:
        await service.validate_parent(tenant.id, project_c.id, child_id=project_a.id)

    assert exc_info.value.code == "project_cycle"
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# max depth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_accepts_depth_within_the_default_limit(
    session: AsyncSession, tenant
) -> None:
    """A chain reaching depth 5 (the default limit) is accepted for the 5th node."""

    service = ProjectService(session)

    level1 = await _make_project(session, tenant.id, "L1")
    level2 = await _make_project(session, tenant.id, "L2", parent_project_id=level1.id)
    level3 = await _make_project(session, tenant.id, "L3", parent_project_id=level2.id)
    level4 = await _make_project(session, tenant.id, "L4", parent_project_id=level3.id)

    # Creating a 5th-level project under level4 -> depth 5, within the limit.
    await service.validate_parent(tenant.id, level4.id, child_id=None)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_rejects_depth_exceeding_the_default_limit(
    session: AsyncSession, tenant
) -> None:
    """Triangulation: a chain already at depth 5 rejects a 6th level."""

    service = ProjectService(session)

    level1 = await _make_project(session, tenant.id, "D1")
    level2 = await _make_project(session, tenant.id, "D2", parent_project_id=level1.id)
    level3 = await _make_project(session, tenant.id, "D3", parent_project_id=level2.id)
    level4 = await _make_project(session, tenant.id, "D4", parent_project_id=level3.id)
    level5 = await _make_project(session, tenant.id, "D5", parent_project_id=level4.id)

    with pytest.raises(AppException) as exc_info:
        await service.validate_parent(tenant.id, level5.id, child_id=None)

    assert exc_info.value.code == "max_depth_exceeded"
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_validate_parent_accepts_a_valid_same_org_active_assignment(
    session: AsyncSession, tenant
) -> None:
    parent = await _make_project(session, tenant.id, "Valid Parent")
    child = await _make_project(session, tenant.id, "Valid Child")

    service = ProjectService(session)
    # Must not raise.
    await service.validate_parent(tenant.id, parent.id, child_id=child.id)
