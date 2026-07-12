"""Guard test for the shared pytest fixtures (R2, R3).

Exercises ``engine``/``session``/``client``/``tenant``/``user`` end to end: a
new test file should be able to declare them as parameters and get a working
authenticated client plus tenant/user data, with no bootstrap of its own and
no leakage between tests (SAVEPOINT + rollback per test).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")

from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.users.models import User


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tenant_fixture_returns_a_persisted_organization(
    tenant: Organization,
) -> None:
    """``tenant`` yields a real, queryable ``Organization`` row."""

    assert tenant.id is not None
    assert tenant.slug.startswith("test-org-")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_user_fixture_authenticates_via_client(
    client: AsyncClient, user: tuple[User, str]
) -> None:
    """``client`` + ``user`` round-trip: the issued bearer token authenticates."""

    created_user, token = user
    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == created_user.email


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_client_rejects_missing_token(client: AsyncClient) -> None:
    """``client`` with no bearer token behaves like a real unauthenticated call."""

    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_writes_are_isolated_step_a(
    session: AsyncSession, tenant: Organization
) -> None:
    """Insert a project in one test; a sibling test must not see it (SAVEPOINT)."""

    session.add(
        Project(
            organization_id=tenant.id,
            name="Isolation Probe",
            methodology="kanban",
            status="active",
        )
    )
    await session.flush()

    count = await session.execute(
        select(func.count()).select_from(Project).where(Project.organization_id == tenant.id)
    )
    assert count.scalar_one() == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_writes_are_isolated_step_b(session: AsyncSession) -> None:
    """A fresh ``session`` never sees the project inserted by the sibling test."""

    count = await session.execute(
        select(func.count()).select_from(Project).where(Project.name == "Isolation Probe")
    )
    assert count.scalar_one() == 0
