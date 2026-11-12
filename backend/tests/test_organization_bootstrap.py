"""Offline bootstrap contracts; no ambient database or application fixtures."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.organizations.bootstrap import bootstrap_organization
from app.modules.organizations.schemas import OrganizationCreate, OrganizationRead
from app.shared.exceptions import AppException


class FakeUow:
    def __init__(self, *, duplicate=False, failure=None):
        self.calls = []
        self.duplicate = duplicate
        self.failure = failure
        self.organizations = self
        self.rbac = self
        self.projects = self
        self.organization = OrganizationRead(
            id=uuid4(), name="Synthetic", slug="synthetic", is_active=True,
            created_at=datetime.now(UTC),
        )

    def record(self, event):
        self.calls.append(event)
        if event[0] == self.failure:
            raise RuntimeError(event[0])

    async def slug_exists(self, slug):
        self.record(("lookup", slug))
        return self.duplicate

    async def create_with_admin(self, data, *, creator_id, actor_id):
        self.record(("create", data, creator_id, actor_id))
        return self.organization

    async def provision_default_roles(self, org, *, admin_user_id, actor_id):
        self.record(("rbac", org, admin_user_id, actor_id))

    async def lock_organization(self, org):
        self.record(("lock", org))
        return True

    async def find_reserved(self, org):
        self.record(("reserved", org))
        return None

    async def create_generales(self, org, actor, parent):
        self.record(("provision", org, actor, parent))

    async def commit(self):
        self.record(("commit",))

    async def rollback(self):
        self.record(("rollback",))


@pytest.mark.asyncio
@pytest.mark.parametrize("null_actor", [False, True])
async def test_order_identity_audit_explicit_root_and_return(null_actor):
    uow = FakeUow()
    creator, actor = uuid4(), None if null_actor else uuid4()
    data = OrganizationCreate(name="Synthetic", slug="synthetic")
    result = await bootstrap_organization(uow, data, creator_id=creator, actor_id=actor)
    assert result is uow.organization
    assert uow.calls == [
        ("lookup", data.slug), ("create", data, creator, actor),
        ("rbac", result.id, creator, actor), ("lock", result.id), ("reserved", result.id),
        ("provision", result.id, actor, None), ("commit",),
    ]


@pytest.mark.asyncio
async def test_duplicate_slug_returns_409_without_creation():
    uow = FakeUow(duplicate=True)
    with pytest.raises(AppException) as error:
        await bootstrap_organization(uow, OrganizationCreate(name="X", slug="synthetic"),
                                     creator_id=uuid4(), actor_id=uuid4())
    assert error.value.status_code == 409
    assert error.value.code == "organization_slug_taken"
    assert uow.calls == [("lookup", "synthetic"), ("rollback",)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["lookup", "create", "rbac", "lock", "reserved", "provision", "commit"]
)
async def test_any_failure_including_completion_rolls_back(failure):
    uow = FakeUow(failure=failure)
    with pytest.raises(RuntimeError, match=failure):
        await bootstrap_organization(uow, OrganizationCreate(name="X", slug="x"),
                                     creator_id=uuid4(), actor_id=uuid4())
    assert uow.calls[-1] == ("rollback",)
    assert sum(c == ("commit",) for c in uow.calls) == (failure == "commit")


@pytest.mark.asyncio
async def test_compatibility_facade_delegates_and_returns_projection(monkeypatch):
    from app.modules.organizations import service

    db = object()
    uow = object()
    result = FakeUow().organization
    factory = lambda session: uow if session is db else None
    delegate = AsyncMock(return_value=result)
    monkeypatch.setattr(service, "OrganizationBootstrapUow", factory)
    monkeypatch.setattr(service, "bootstrap_organization", delegate)
    data = OrganizationCreate(name="X", slug="x")
    creator, actor = uuid4(), uuid4()
    assert await service.OrganizationService(db).create_bootstrap(
        data, creator_id=creator, actor_id=actor,
    ) is result
    delegate.assert_awaited_once_with(uow, data, creator_id=creator, actor_id=actor)


@pytest.mark.asyncio
async def test_concurrent_slug_constraint_is_409_and_rolled_back():
    import app.modules.dependencies.models  # noqa: F401
    import app.modules.menus.models  # noqa: F401
    import app.modules.roles.models  # noqa: F401
    from sqlalchemy.exc import IntegrityError
    from app.modules.organizations.bootstrap_uow import OrganizationBootstrapUow

    class CollisionSession(Session):
        async def flush(self):
            original = RuntimeError("synthetic collision")
            original.diag = SimpleNamespace(constraint_name="ix_organizations_slug")
            raise IntegrityError("synthetic", {}, original)

    session = CollisionSession()
    with pytest.raises(AppException) as error:
        await bootstrap_organization(
            OrganizationBootstrapUow(session), OrganizationCreate(name="X", slug="x"),
            creator_id=uuid4(), actor_id=uuid4(),
        )
    assert error.value.status_code == 409
    assert error.value.code == "organization_slug_taken"
    assert session.calls[-1] == ("rollback",)
    assert ("commit",) not in session.calls


class Session:
    """Records transaction intent only, not PostgreSQL behavior."""
    def __init__(self, fail_flush=None):
        self.calls = []
        self.rows = []
        self.fail_flush = fail_flush
        self.flushes = 0

    def add(self, row):
        self.rows.append(row)
        self.calls.append(("add", type(row).__name__))

    async def flush(self):
        self.flushes += 1
        self.calls.append(("flush", self.flushes))
        if self.fail_flush == self.flushes:
            raise RuntimeError("flush")
        for row in self.rows:
            row.id = row.id or uuid4()
            row.created_at = datetime.now(UTC)
            if hasattr(row, "is_active"):
                row.is_active = True

    async def commit(self):
        self.calls.append(("commit",))

    async def rollback(self):
        self.calls.append(("rollback",))

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def begin(self):
        pytest.fail("must reuse the injected session, not begin a transaction")

    begin_nested = begin


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_flush", [None, 1, 2])
async def test_session_adapter_flushes_both_rows_before_provision_and_owns_completion(fail_flush):
    # Register only relationships needed by ORM construction, not db_init/main.
    import app.modules.dependencies.models  # noqa: F401
    import app.modules.menus.models  # noqa: F401
    import app.modules.roles.models  # noqa: F401
    from app.modules.organizations.bootstrap_uow import OrganizationBootstrapUow
    from app.shared.enums import MemberRole

    session = Session(fail_flush)
    uow = OrganizationBootstrapUow(session)
    assert uow.projects.session is session
    creator, actor = uuid4(), uuid4()
    data = OrganizationCreate(name="Synthetic", slug="synthetic")
    projects = FakeUow()
    async def lock_after_flush(org):
        assert session.flushes == 2
        assert ("commit",) not in session.calls
        return await projects.lock_organization(org)

    uow.rbac = projects
    uow.projects = SimpleNamespace(
        lock_organization=lock_after_flush,
        find_reserved=projects.find_reserved,
        create_generales=projects.create_generales,
    )
    if fail_flush:
        with pytest.raises(RuntimeError, match="flush"):
            await bootstrap_organization(uow, data, creator_id=creator, actor_id=actor)
        assert session.calls[-1] == ("rollback",)
        assert not projects.calls
    else:
        result = await bootstrap_organization(uow, data, creator_id=creator, actor_id=actor)
        assert session.calls == [("add", "Organization"), ("flush", 1),
                                 ("add", "OrganizationMember"), ("flush", 2), ("commit",)]
        org, member = session.rows
        assert org.id == result.id == member.organization_id
        assert (org.created_by, org.updated_by) == (actor, actor)
        assert (member.user_id, member.role) == (creator, MemberRole.admin)
        assert projects.calls == [("rbac", org.id, creator, actor), ("lock", org.id),
                                  ("reserved", org.id), ("provision", org.id, actor, None)]
