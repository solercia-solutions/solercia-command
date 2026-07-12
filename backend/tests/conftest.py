"""Pytest configuration and shared fixtures.

Integration tests require a running Postgres DB configured via the environment
variable ``TEST_DATABASE_URL``. When the variable is absent the tests that need
DB access are automatically skipped.

Install test dependencies:
    pip install pytest pytest-asyncio httpx

Run all tests:
    cd backend && pytest tests/ -v

Shared fixtures (``engine``/``session``/``client``/``tenant``/``user``) are
ADDITIVE: the 43 pre-existing tests are black-box HTTP tests against a live
server (``API_BASE_URL`` + ``TEST_AUTH_TOKEN``) and are not rewritten to use
them. New tests (from this file onward) should prefer the in-process ASGI
``client`` fixture instead of a live server.
"""

import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Mark all tests in the suite as async by default.
pytest_plugins = ("pytest_asyncio",)

# Skip DB-dependent tests gracefully when no test database is configured.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL not set — skipping integration tests",
)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine bound to ``TEST_DATABASE_URL``.

    Builds the schema once per test session via ``Base.metadata.create_all``
    (the migrations path — ``alembic upgrade head`` — is verified separately
    by ``test_migrations_baseline.py``; see design.md, "Brecha residual
    aceptada").

    ``poolclass=NullPool`` is required together with
    ``asyncio_default_fixture_loop_scope = "session"`` in
    ``pyproject.toml``: a session-scoped engine that pools connections would
    bind its first asyncpg connection to the event loop of whichever test
    acquires it first, and every other test — running on a different
    per-test loop — would then fail intermittently ("Future attached to a
    different loop" / "another operation is in progress"). With
    ``NullPool`` every checkout opens a fresh connection on the loop that is
    actually running, so there is no cross-test loop affinity to break.
    """

    if TEST_DATABASE_URL is None:  # pragma: no cover - guarded by skip_no_db
        pytest.skip("TEST_DATABASE_URL not set — skipping integration tests")

    # Import after the guard: pulls in every ORM model so Base.metadata is
    # fully populated before create_all runs.
    import app.db_init  # noqa: F401
    from app.database import Base

    test_engine = create_async_engine(
        TEST_DATABASE_URL, poolclass=NullPool, future=True
    )
    async with test_engine.begin() as conn:
        # Required before create_all: the ORM models declare GIN indexes with
        # the `gin_trgm_ops` opclass (change 10-busqueda-global, design.md
        # Decision 2) — without the extension, create_all fails building
        # those indexes and `similarity()` is unavailable to tests.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped session isolated by a SAVEPOINT, rolled back on teardown.

    Binds the session to a single connection with an externally-managed
    transaction (``join_transaction_mode="create_savepoint"``): whatever the
    code under test does — including calling ``session.commit()`` — only
    releases/reopens the SAVEPOINT. The outer transaction is never committed,
    so rolling it back at teardown erases every write the test made,
    regardless of how many internal commits happened.
    """

    async with engine.connect() as connection:
        await connection.begin()
        async_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield async_session
        finally:
            await async_session.close()
            await connection.rollback()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """In-process ASGI client (no live server) with ``get_db`` overridden.

    Every request made through this client is served by the FastAPI app
    directly (``httpx.ASGITransport``) and reuses the test's ``session``, so
    data created via ``tenant``/``user``/``session`` in the same test is
    visible to the request without any commit crossing the SAVEPOINT
    boundary.
    """

    from app.database import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver/api/v1"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def tenant(session: AsyncSession):
    """A persisted ``Organization`` with a unique slug, scoped to the test."""

    from app.modules.organizations.models import Organization

    organization = Organization(
        name="Test Org", slug=f"test-org-{uuid.uuid4().hex[:12]}"
    )
    session.add(organization)
    await session.flush()
    return organization


@pytest_asyncio.fixture
async def user(session: AsyncSession, tenant):
    """A persisted ``User`` member of ``tenant``, plus a valid bearer token.

    Returns ``(user, token)`` so tests can assert on the ORM row and
    authenticate the ``client`` fixture in the same step.
    """

    from app.modules.organizations.models import OrganizationMember
    from app.modules.users.models import User
    from app.shared.enums import MemberRole
    from app.shared.security import create_access_token, hash_password

    new_user = User(
        email=f"test-{uuid.uuid4().hex[:12]}@example.com",
        primer_nombre="Test",
        primer_apellido="User",
        hashed_password=hash_password("Test123*"),
    )
    session.add(new_user)
    await session.flush()

    session.add(
        OrganizationMember(
            organization_id=tenant.id,
            user_id=new_user.id,
            role=MemberRole.member,
        )
    )
    await session.flush()

    token = create_access_token(str(new_user.id))
    return new_user, token


@pytest_asyncio.fixture
async def second_tenant(session: AsyncSession):
    """A second persisted ``Organization``, distinct from ``tenant``."""

    from app.modules.organizations.models import Organization

    organization = Organization(
        name="Second Org", slug=f"second-org-{uuid.uuid4().hex[:12]}"
    )
    session.add(organization)
    await session.flush()
    return organization


@pytest.fixture
def make_member():
    """Factory fixture: ``await make_member(session, org, role) -> (User, token)``.

    Unlike the ``user`` fixture (always ``MemberRole.member``), this factory
    builds a member of any ``MemberRole`` for a given organization. The email
    is generated internally (``uuid.uuid4().hex[:12]``, same scheme as
    ``user``) — no ``suffix`` parameter — so it is safe to call repeatedly
    within the same org/test.
    """

    async def _make_member(session: AsyncSession, org, role):
        from app.modules.organizations.models import OrganizationMember
        from app.modules.users.models import User
        from app.shared.security import create_access_token, hash_password

        role_label = str(role.value if hasattr(role, "value") else role)
        new_user = User(
            email=f"member-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Member",
            primer_apellido=role_label.capitalize(),
            hashed_password=hash_password("Test123*"),
        )
        session.add(new_user)
        await session.flush()

        session.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=new_user.id,
                role=role,
            )
        )
        await session.flush()

        token = create_access_token(str(new_user.id))
        return new_user, token

    return _make_member


@pytest.fixture
def rbac_admin():
    """Factory fixture: ``await rbac_admin(session, org, user) -> None``.

    Grants ``user`` the RBAC ``ADMIN`` role in ``org`` (satisfies
    ``require_admin``). ``MemberRole`` (used by ``require_role``) is a
    SEPARATE system from the RBAC catalog (used by ``require_admin``) — see
    multi-tenancy/rbac-catalog specs. This creates the RBAC ``Role``/
    ``UserRole`` link directly; it does NOT touch the user's
    ``OrganizationMember.role``.
    """

    async def _rbac_admin(session: AsyncSession, org, user) -> None:
        from app.modules.roles.models import Role, UserRole

        role = Role(organization_id=org.id, code="ADMIN", name="Administrator")
        session.add(role)
        await session.flush()

        session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.flush()

    return _rbac_admin


@dataclass
class OrgData:
    """One organization's worth of seeded tenant-scoped data."""

    organization: object
    user: object
    token: str
    project: object
    task: object
    alert_rule: object
    notification: object


@dataclass
class TwoOrgs:
    """Two fully-seeded organizations (A/B) for cross-tenant isolation tests."""

    a: OrgData
    b: OrgData


async def _seed_org_data(session: AsyncSession, *, name: str, code: str) -> OrgData:
    """Create one organization with a user, project, task, alert_rule and notification."""

    from app.modules.alert_rules.models import AlertRule
    from app.modules.notifications.models import Notification
    from app.modules.organizations.models import Organization, OrganizationMember
    from app.modules.projects.models import Project
    from app.modules.tasks.models import Task
    from app.modules.users.models import User
    from app.shared.enums import MemberRole, Methodology
    from app.shared.security import create_access_token, hash_password

    organization = Organization(name=name, slug=f"{code.lower()}-{uuid.uuid4().hex[:12]}")
    session.add(organization)
    await session.flush()

    owner = User(
        email=f"owner-{uuid.uuid4().hex[:12]}@example.com",
        primer_nombre="Owner",
        primer_apellido=code,
        hashed_password=hash_password("Test123*"),
    )
    session.add(owner)
    await session.flush()

    session.add(
        OrganizationMember(
            organization_id=organization.id,
            user_id=owner.id,
            role=MemberRole.admin,
        )
    )
    await session.flush()

    project = Project(
        organization_id=organization.id,
        name=f"{name} Project",
        methodology=Methodology.kanban,
        code=code,
        task_counter=0,
    )
    session.add(project)
    await session.flush()

    task = Task(
        project_id=project.id,
        title=f"{name} Task",
        status="Backlog",
        assignee_id=owner.id,
    )
    session.add(task)
    await session.flush()

    alert_rule = AlertRule(
        organization_id=organization.id,
        rule_type="task_overdue",
        enabled=True,
        threshold_params={},
    )
    session.add(alert_rule)
    await session.flush()

    notification = Notification(
        organization_id=organization.id,
        recipient_user_id=owner.id,
        rule_type="task_overdue",
        title=f"{name} notification",
        body="Seed notification for isolation tests.",
        target_type="task",
        target_id=task.id,
        dedup_key=f"task_overdue:{task.id}",
    )
    session.add(notification)
    await session.flush()

    token = create_access_token(str(owner.id))
    return OrgData(
        organization=organization,
        user=owner,
        token=token,
        project=project,
        task=task,
        alert_rule=alert_rule,
        notification=notification,
    )


@pytest_asyncio.fixture
async def two_orgs(session: AsyncSession) -> TwoOrgs:
    """Two organizations (A/B), each with its own user/project/task/alert_rule/notification.

    Mandatory fixture for every tenant-scoped suite (design.md, "fixtures de
    dos organizaciones para aislamiento"): asserts that a member of A never
    lists/reads/edits/deletes a resource whose ``organization_id`` — own or
    inherited (e.g. Task -> Project) — belongs to B.
    """

    org_a = await _seed_org_data(session, name="Org A", code="ORGA")
    org_b = await _seed_org_data(session, name="Org B", code="ORGB")
    return TwoOrgs(a=org_a, b=org_b)
