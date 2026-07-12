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

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
