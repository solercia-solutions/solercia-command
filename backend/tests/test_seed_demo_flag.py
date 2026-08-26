"""Tests for the demo-seed gate (change 42-purga-datos-demo, Fase 1).

Requirement «Compuerta de la semilla demo por SEED_DEMO_DATA»
(specs/data-maintenance/spec.md) + deltas `multi-tenancy` R4 and
`api-conventions` R4/R5. Design decision D5.

Every test calls the private helpers (`_ensure_demo_members`,
`_seed_demo_workitems`) directly against the SAVEPOINT ``session`` fixture,
never ``seed_default()`` for the flag-only assertions — precedent
``test_menu_seed.py`` (calls ``_ensure_roles``/``_ensure_menus`` directly)
and ``test_email_outbox.py:39`` (``monkeypatch.setattr(settings, ...)``).
``seed_default()`` opens its own ``AsyncSessionLocal`` OUTSIDE the SAVEPOINT
(``db_init.py:349``), so the one test that must exercise it end to end
(the restart scenario) reuses the SAVEPOINT session via a monkeypatched
``AsyncSessionLocal`` instead of letting it open a real connection to
``settings.DATABASE_URL`` (which would be the actual `solercia` database).
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db_init
from app.config import settings
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.modules.users.models import User
from tests.conftest import skip_no_db

_DEMO_EMAILS = ("ana@solercia.com", "carlos@solercia.com", "diana@solercia.com")


class _ReuseSessionContext:
    """Async context manager that hands back an ALREADY OPEN session.

    Used to monkeypatch ``db_init.AsyncSessionLocal`` so ``seed_default()``'s
    internal ``async with AsyncSessionLocal() as session:`` reuses the
    test's own SAVEPOINT-bound session instead of opening a brand-new
    connection to ``settings.DATABASE_URL``. Any ``session.commit()`` inside
    ``seed_default()`` then only releases/reopens the SAVEPOINT
    (``tests/conftest.py:88-110`` docstring), so nothing escapes the test's
    outer transaction — never the real `solercia` database.
    """

    def __init__(self, reused_session: AsyncSession) -> None:
        self._session = reused_session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ensure_demo_members_no_crea_usuarios_con_flag_apagado(
    session: AsyncSession, tenant: Organization
) -> None:
    """Con ``SEED_DEMO_DATA=False`` (valor por defecto) y BD vacía,
    ``_ensure_demo_members`` no crea usuarios demo."""

    dependencies = await db_init._ensure_dependencies(session, tenant)
    roles = await db_init._ensure_roles(session, tenant)

    members = await db_init._ensure_demo_members(session, tenant, dependencies, roles)

    assert members == []
    result = await session.execute(select(User).where(User.email.in_(_DEMO_EMAILS)))
    assert result.scalars().all() == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ensure_demo_members_crea_usuarios_con_flag_encendido(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con ``settings.SEED_DEMO_DATA = True``, ``_ensure_demo_members`` sigue
    creando ana/carlos/diana (sin regresión sobre el comportamiento previo)."""

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)
    dependencies = await db_init._ensure_dependencies(session, tenant)
    roles = await db_init._ensure_roles(session, tenant)

    members = await db_init._ensure_demo_members(session, tenant, dependencies, roles)

    assert {member.email for member in members} == set(_DEMO_EMAILS)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_seed_demo_workitems_no_crea_proyectos_con_flag_apagado(
    session: AsyncSession, tenant: Organization
) -> None:
    """Con el flag apagado, ``_seed_demo_workitems`` no crea proyectos ni tareas."""

    dependencies = await db_init._ensure_dependencies(session, tenant)
    roles = await db_init._ensure_roles(session, tenant)
    admin = await db_init._ensure_admin(session, tenant, dependencies)
    members = await db_init._ensure_demo_members(session, tenant, dependencies, roles)

    await db_init._seed_demo_workitems(session, tenant, members, admin)

    result = await session.execute(
        select(Project).where(Project.organization_id == tenant.id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_seed_demo_workitems_crea_proyectos_tareas_y_sprint_con_flag_encendido(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inclusión obligatoria #1 — con el flag encendido, ``_seed_demo_workitems``
    crea los proyectos demo, las tareas demo Y el sprint scrum (no solo miembros)."""

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)
    dependencies = await db_init._ensure_dependencies(session, tenant)
    roles = await db_init._ensure_roles(session, tenant)
    admin = await db_init._ensure_admin(session, tenant, dependencies)
    members = await db_init._ensure_demo_members(session, tenant, dependencies, roles)

    await db_init._seed_demo_workitems(session, tenant, members, admin)

    projects_count = await session.execute(
        select(func.count())
        .select_from(Project)
        .where(Project.organization_id == tenant.id)
    )
    assert projects_count.scalar_one() > 0

    tasks_count = await session.execute(
        select(func.count())
        .select_from(Task)
        .join(Project, Task.project_id == Project.id)
        .where(Project.organization_id == tenant.id)
    )
    assert tasks_count.scalar_one() > 0

    sprints_count = await session.execute(
        select(func.count())
        .select_from(Sprint)
        .join(Project, Sprint.project_id == Project.id)
        .where(Project.organization_id == tenant.id)
    )
    assert sprints_count.scalar_one() > 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_compuerta_se_lee_en_tiempo_de_llamada(
    session: AsyncSession, tenant: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El flag se lee en tiempo de llamada, nunca una constante capturada al
    importar: dos llamadas en el mismo test, con el valor cambiado entre
    ellas, respetan cada una el valor vigente en ese momento."""

    dependencies = await db_init._ensure_dependencies(session, tenant)
    roles = await db_init._ensure_roles(session, tenant)

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    first_call = await db_init._ensure_demo_members(session, tenant, dependencies, roles)
    assert first_call == []

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)
    second_call = await db_init._ensure_demo_members(session, tenant, dependencies, roles)
    assert {member.email for member in second_call} == set(_DEMO_EMAILS)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_restart_con_flag_apagado_no_revive_miembros_tras_purga(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con una base ya purgada (sin ana/carlos/diana) y el flag apagado, un
    reinicio (``seed_default()`` corriendo de nuevo) no revive miembros demo:
    la cuenta de usuarios de "Solercia" permanece en 1 (``admin@solercia.com``)."""

    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(db_init, "AsyncSessionLocal", lambda: _ReuseSessionContext(session))

    # First call establishes the "already purged" baseline: org "Solercia" +
    # admin only, since the flag was off from the very first boot.
    await db_init.seed_default()

    organization = (
        await session.execute(select(Organization).where(Organization.slug == "solercia"))
    ).scalar_one()

    member_count_before = await session.execute(
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization.id)
    )
    assert member_count_before.scalar_one() == 1

    # Second call simulates the restart under test.
    await db_init.seed_default()

    member_count_after = await session.execute(
        select(func.count())
        .select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization.id)
    )
    assert member_count_after.scalar_one() == 1

    demo_users = await session.execute(select(User).where(User.email.in_(_DEMO_EMAILS)))
    assert demo_users.scalars().all() == []
