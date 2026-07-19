"""RED tests for automatic classification wired into `POST /intake/pull`
(change 22-intake-classifier, tasks.md T4.4/T4.5) plus the lazy default
project (`TestDefaultProject`) and manual triage (`TestManualTriage`,
tasks.md T5.4).

The REAL-conversion scenarios (``TestAutoConversion::
test_matching_rule_creates_real_task_with_assignee`` and the whole
``TestDefaultProject`` class) use TWO INDEPENDENT ``AsyncSession`` instances
bound to the shared ``engine`` fixture — never the SAVEPOINT-scoped
``session``/``client`` combo — to prove ``TaskService.create_task``/
``ProjectService.create_project``'s commits are REAL, durable writes
(lección savepoint, ratified for change 22's write flows: ingesta
idempotente, conversión a tarea, sink).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.integrations import crypto
from app.integrations.ports import CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.intake.models import IntakeItem, IntakeRule, IntakeSettings
from app.modules.intake.service import IntakeService
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import AccountStatus, ConnectorStatus, MemberRole
from app.shared.security import hash_password
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_fake_connector(
    session: AsyncSession, organization_id: uuid.UUID, owner_id: uuid.UUID
) -> Connector:
    connector = Connector(
        organization_id=organization_id,
        provider="fake",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )
    session.add(connector)
    await session.flush()

    account = ConnectedAccount(
        organization_id=organization_id,
        connector_id=connector.id,
        user_id=owner_id,
        external_account_id="fake-account-classifier",
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    session.add(
        ConnectionCredentials(
            organization_id=organization_id,
            connected_account_id=account.id,
            access_token_enc=crypto.encrypt("fake-access-token"),
            refresh_token_enc=crypto.encrypt("fake-refresh-token"),
            token_type="Bearer",
            scopes=["mail"],
        )
    )
    await session.flush()
    return connector


# ---------------------------------------------------------------------------
# TestAutoConversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_pull_classifies_new_items_without_extra_call(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: El pull dispara la clasificación automáticamente — los 5
    ítems nuevos (fake adapter: 5 capacidades) se evalúan sin llamada extra."""

    await _seed_fake_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id)
    session.add(
        IntakeRule(
            organization_id=two_orgs.a.organization.id,
            name="Regla catch-all",
            criteria=[{"field": "source_provider", "operator": "equals", "value": "fake"}],
            convert_to_task=False,
            rule_order=1,
        )
    )
    await session.flush()

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    assert response.status_code == 200, response.text

    items_response = await client.get("/intake/items", headers=_auth(two_orgs.a.token))
    items = items_response.json()["data"]
    assert len(items) == 5
    assert all(item["status"] == "ignored" for item in items)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_convert_to_task_false_marks_ignored_without_task(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Regla con convert_to_task=false no crea tarea — el ítem
    queda `ignored`, sin pasar a la cola de triage."""

    await _seed_fake_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id)
    session.add(
        IntakeRule(
            organization_id=two_orgs.a.organization.id,
            name="Ignorar todo",
            criteria=[{"field": "source_provider", "operator": "equals", "value": "fake"}],
            convert_to_task=False,
            rule_order=1,
        )
    )
    await session.flush()

    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    pending_response = await client.get(
        "/intake/items", params={"status": "pending"}, headers=_auth(two_orgs.a.token)
    )
    assert pending_response.json()["data"] == []

    ignored_response = await client.get(
        "/intake/items", params={"status": "ignored"}, headers=_auth(two_orgs.a.token)
    )
    assert len(ignored_response.json()["data"]) == 5


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_matching_rule_stays_pending_without_matched_rule_id(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Ítem sin regla coincidente queda pendiente — sin `Task`
    creada ni `matched_rule_id`."""

    await _seed_fake_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id)
    session.add(
        IntakeRule(
            organization_id=two_orgs.a.organization.id,
            name="Nunca casa",
            criteria=[
                {"field": "source_provider", "operator": "equals", "value": "no-existe"}
            ],
            convert_to_task=True,
            task_priority="medium",
            rule_order=1,
        )
    )
    await session.flush()

    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    items_response = await client.get("/intake/items", headers=_auth(two_orgs.a.token))
    items = items_response.json()["data"]
    assert len(items) == 5
    assert all(item["status"] == "pending" for item in items)
    assert all(item["matched_rule_id"] is None for item in items)
    assert all(item["created_task_id"] is None for item in items)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ineligible_assignee_rejects_without_creating_membership(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Asignado no elegible bloquea la conversión — el ítem queda
    `pending` en triage, `matched_rule_id` registrado como motivo, y NUNCA
    se crea membresía nueva para el usuario no elegible."""

    await _seed_fake_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id)

    outsider = User(
        email=f"outsider-{uuid.uuid4().hex[:12]}@example.com",
        primer_nombre="Outsider",
        primer_apellido="User",
        hashed_password=hash_password("Test123*"),
    )
    session.add(outsider)
    await session.flush()

    session.add(
        IntakeRule(
            organization_id=two_orgs.a.organization.id,
            name="Asigna a foraneo",
            criteria=[{"field": "source_provider", "operator": "equals", "value": "fake"}],
            convert_to_task=True,
            task_priority="high",
            assignee_id=outsider.id,
            rule_order=1,
        )
    )
    await session.flush()

    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    items_response = await client.get("/intake/items", headers=_auth(two_orgs.a.token))
    items = items_response.json()["data"]
    assert len(items) == 5
    assert all(item["status"] == "pending" for item in items)
    assert all(item["matched_rule_id"] is not None for item in items)
    assert all(item["created_task_id"] is None for item in items)

    membership_result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == two_orgs.a.organization.id,
            OrganizationMember.user_id == outsider.id,
        )
    )
    assert membership_result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_matching_rule_creates_real_task_with_assignee(engine: AsyncEngine) -> None:
    """Scenario: Correo con dominio conocido se convierte en tarea asignada —
    crea una `Task` REAL en el proyecto/prioridad/asignado de la regla, y el
    ítem queda `converted` con `matched_rule_id`/`created_task_id` —
    verificado con sesiones REALMENTE independientes (lección savepoint)."""

    session_a = AsyncSession(engine, expire_on_commit=False)
    organization_id: uuid.UUID | None = None
    try:
        organization = Organization(
            name="Auto Conversion Org", slug=f"auto-conv-{uuid.uuid4().hex[:12]}"
        )
        session_a.add(organization)
        await session_a.flush()
        organization_id = organization.id

        admin = User(
            email=f"auto-admin-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Auto",
            primer_apellido="Admin",
            hashed_password=hash_password("Test123*"),
        )
        session_a.add(admin)
        await session_a.flush()
        session_a.add(
            OrganizationMember(
                organization_id=organization.id, user_id=admin.id, role=MemberRole.admin
            )
        )

        assignee = User(
            email=f"auto-assignee-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Auto",
            primer_apellido="Assignee",
            hashed_password=hash_password("Test123*"),
        )
        session_a.add(assignee)
        await session_a.flush()
        session_a.add(
            OrganizationMember(
                organization_id=organization.id, user_id=assignee.id, role=MemberRole.member
            )
        )
        await session_a.flush()

        target_project = Project(
            organization_id=organization.id,
            name="Seguridad",
            methodology="planner",
            code="SEG",
            task_counter=0,
        )
        session_a.add(target_project)
        await session_a.flush()
        # Seed the board so TaskService.create_task can resolve a default
        # column (mirrors ProjectService's own board-seeding on create).
        from app.methodology.factory import get_strategy
        from app.modules.boards.service import BoardService
        from app.shared.enums import Methodology

        await BoardService(session_a).seed_board(
            target_project.id, get_strategy(Methodology.planner)
        )

        await _seed_fake_connector(session_a, organization.id, admin.id)
        session_a.add(
            IntakeRule(
                organization_id=organization.id,
                name="Seguridad a asignado",
                criteria=[
                    {"field": "source_provider", "operator": "equals", "value": "fake"}
                ],
                convert_to_task=True,
                target_project_id=target_project.id,
                task_priority="high",
                assignee_id=assignee.id,
                rule_order=1,
            )
        )
        await session_a.commit()

        service_a = IntakeService(session_a)
        await service_a.pull(organization.id)
        await session_a.close()

        session_b = AsyncSession(engine, expire_on_commit=False)
        try:
            items_result = await session_b.execute(
                select(IntakeItem).where(IntakeItem.organization_id == organization.id)
            )
            items = items_result.scalars().all()
            assert len(items) == 5
            for item in items:
                assert item.status == "converted"
                assert item.matched_rule_id is not None
                assert item.created_task_id is not None

            tasks_result = await session_b.execute(
                select(Task).where(Task.project_id == target_project.id)
            )
            tasks = tasks_result.scalars().all()
            assert len(tasks) == 5
            for task in tasks:
                assert task.priority == "high"
                assert task.assignee_id == assignee.id
        finally:
            await session_b.close()
    finally:
        if organization_id is not None:
            cleanup_session = AsyncSession(engine, expire_on_commit=False)
            try:
                await cleanup_session.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
                await cleanup_session.commit()
            finally:
                await cleanup_session.close()


# ---------------------------------------------------------------------------
# TestDefaultProject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_first_use_creates_default_project_and_second_use_reuses_it(
    engine: AsyncEngine,
) -> None:
    """Scenario: Primer uso crea el proyecto por defecto "Tareas Outlook";
    usos posteriores reutilizan el mismo proyecto — sesiones independientes."""

    session_a = AsyncSession(engine, expire_on_commit=False)
    organization_id: uuid.UUID | None = None
    try:
        organization = Organization(
            name="Default Project Org", slug=f"default-proj-{uuid.uuid4().hex[:12]}"
        )
        session_a.add(organization)
        await session_a.flush()
        organization_id = organization.id

        admin = User(
            email=f"default-admin-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Default",
            primer_apellido="Admin",
            hashed_password=hash_password("Test123*"),
        )
        session_a.add(admin)
        await session_a.flush()
        session_a.add(
            OrganizationMember(
                organization_id=organization.id, user_id=admin.id, role=MemberRole.admin
            )
        )
        await session_a.flush()

        await _seed_fake_connector(session_a, organization.id, admin.id)
        session_a.add(
            IntakeRule(
                organization_id=organization.id,
                name="Sin proyecto destino",
                criteria=[
                    {"field": "source_provider", "operator": "equals", "value": "fake"}
                ],
                convert_to_task=True,
                target_project_id=None,
                task_priority="medium",
                rule_order=1,
            )
        )
        await session_a.commit()

        service_a = IntakeService(session_a)
        await service_a.pull(organization.id)
        await session_a.close()

        session_b = AsyncSession(engine, expire_on_commit=False)
        first_project_id: uuid.UUID | None = None
        try:
            settings_result = await session_b.execute(
                select(IntakeSettings).where(IntakeSettings.organization_id == organization.id)
            )
            settings_row = settings_result.scalar_one()
            first_project_id = settings_row.default_project_id
            assert first_project_id is not None

            project_result = await session_b.execute(
                select(Project).where(Project.id == first_project_id)
            )
            project = project_result.scalar_one()
            assert project.name == "Tareas Outlook"
            assert project.methodology == "planner"
        finally:
            await session_b.close()

        # Second pull (different rule, still no target_project_id) — reuses
        # the SAME default project instead of creating a new one.
        session_c = AsyncSession(engine, expire_on_commit=False)
        try:
            result = await session_c.execute(
                select(ConnectedAccount).where(
                    ConnectedAccount.organization_id == organization.id
                )
            )
            account = result.scalars().first()
            assert account is not None
            account.external_account_id = "fake-account-classifier-2"

            rule_result = await session_c.execute(
                select(IntakeRule).where(IntakeRule.organization_id == organization.id)
            )
            rule = rule_result.scalar_one()
            rule.rule_order = 2
            await session_c.commit()
        finally:
            await session_c.close()

        session_d = AsyncSession(engine, expire_on_commit=False)
        try:
            service_d = IntakeService(session_d)
            await service_d.pull(organization.id)
        finally:
            await session_d.close()

        session_e = AsyncSession(engine, expire_on_commit=False)
        try:
            projects_result = await session_e.execute(
                select(Project).where(
                    Project.organization_id == organization.id, Project.name == "Tareas Outlook"
                )
            )
            projects = projects_result.scalars().all()
            assert len(projects) == 1  # no new project created — reused
            assert projects[0].id == first_project_id
        finally:
            await session_e.close()
    finally:
        if organization_id is not None:
            cleanup_session = AsyncSession(engine, expire_on_commit=False)
            try:
                await cleanup_session.execute(
                    delete(Organization).where(Organization.id == organization_id)
                )
                await cleanup_session.commit()
            finally:
                await cleanup_session.close()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_configured_name_before_first_use_is_respected(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Nombre configurado antes del primer uso — el proyecto se
    llama "Bandeja de Entrada", no "Tareas Outlook"."""

    session.add(
        IntakeSettings(
            organization_id=two_orgs.a.organization.id,
            default_project_name="Bandeja de Entrada",
        )
    )
    await _seed_fake_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id)
    session.add(
        IntakeRule(
            organization_id=two_orgs.a.organization.id,
            name="Sin destino",
            criteria=[{"field": "source_provider", "operator": "equals", "value": "fake"}],
            convert_to_task=True,
            target_project_id=None,
            task_priority="medium",
            rule_order=1,
        )
    )
    await session.flush()

    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    result = await session.execute(
        select(Project).where(
            Project.organization_id == two_orgs.a.organization.id,
            Project.name == "Bandeja de Entrada",
        )
    )
    project = result.scalar_one_or_none()
    assert project is not None
    assert project.methodology == "planner"


# ---------------------------------------------------------------------------
# TestManualTriage
# ---------------------------------------------------------------------------


async def _seed_pending_item_without_matching_rule(
    session: AsyncSession, organization_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    await _seed_fake_connector(session, organization_id, owner_id)
    session.add(
        IntakeRule(
            organization_id=organization_id,
            name="Nunca casa",
            criteria=[{"field": "source_provider", "operator": "equals", "value": "no-existe"}],
            convert_to_task=True,
            task_priority="medium",
            rule_order=1,
        )
    )
    await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manual_conversion_creates_task_with_null_matched_rule(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Usuario convierte manualmente un ítem en triage — crea la
    `Task` en el proyecto por defecto, `matched_rule_id` nulo."""

    await _seed_pending_item_without_matching_rule(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    items_response = await client.get(
        "/intake/items", params={"status": "pending"}, headers=_auth(two_orgs.a.token)
    )
    item_id = items_response.json()["data"][0]["id"]

    response = await client.post(
        f"/intake/items/{item_id}/convert",
        json={"priority": "high", "assignee_id": str(two_orgs.a.user.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "converted"
    assert body["matched_rule_id"] is None
    assert body["created_task_id"] is not None

    project_result = await session.execute(
        select(Project).where(
            Project.organization_id == two_orgs.a.organization.id,
            Project.name == "Tareas Outlook",
        )
    )
    assert project_result.scalar_one_or_none() is not None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reconverting_an_already_converted_item_is_rejected(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: No se puede reconvertir un ítem ya convertido — error de
    validación, sin segunda `Task`."""

    await _seed_pending_item_without_matching_rule(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    items_response = await client.get(
        "/intake/items", params={"status": "pending"}, headers=_auth(two_orgs.a.token)
    )
    item_id = items_response.json()["data"][0]["id"]

    first = await client.post(
        f"/intake/items/{item_id}/convert", json={"priority": "medium"},
        headers=_auth(two_orgs.a.token),
    )
    assert first.status_code == 200, first.text
    first_task_id = first.json()["data"]["created_task_id"]

    second = await client.post(
        f"/intake/items/{item_id}/convert", json={"priority": "medium"},
        headers=_auth(two_orgs.a.token),
    )
    assert second.status_code == 422, second.text

    get_response = await client.get(f"/intake/items/{item_id}", headers=_auth(two_orgs.a.token))
    assert get_response.json()["data"]["created_task_id"] == first_task_id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reassigning_task_does_not_break_intake_traceability(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Reasignar la tarea no rompe la trazabilidad — mover/
    reasignar la `Task` vía el endpoint vigente de `tasks` NO altera
    `IntakeItem.created_task_id`/`matched_rule_id`."""

    await _seed_pending_item_without_matching_rule(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    items_response = await client.get(
        "/intake/items", params={"status": "pending"}, headers=_auth(two_orgs.a.token)
    )
    item_id = items_response.json()["data"][0]["id"]

    convert_response = await client.post(
        f"/intake/items/{item_id}/convert", json={"priority": "medium"},
        headers=_auth(two_orgs.a.token),
    )
    task_id = convert_response.json()["data"]["created_task_id"]

    new_assignee, _new_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    reassign_response = await client.patch(
        f"/tasks/{task_id}",
        json={"assignee_id": str(new_assignee.id)},
        headers=_auth(two_orgs.a.token),
    )
    assert reassign_response.status_code == 200, reassign_response.text

    get_response = await client.get(f"/intake/items/{item_id}", headers=_auth(two_orgs.a.token))
    body = get_response.json()["data"]
    assert body["created_task_id"] == task_id
    assert body["matched_rule_id"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_settings_member_forbidden_admin_manager_allowed(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Member no puede configurar el nombre del proyecto por
    defecto — `PATCH /intake/settings` → member 403, admin/manager 200."""

    _member, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    member_response = await client.patch(
        "/intake/settings",
        json={"default_project_name": "Bandeja de Entrada"},
        headers=_auth(member_token),
    )
    assert member_response.status_code == 403, member_response.text

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    manager_response = await client.patch(
        "/intake/settings",
        json={"default_project_name": "Bandeja de Entrada"},
        headers=_auth(manager_token),
    )
    assert manager_response.status_code == 200, manager_response.text
    assert manager_response.json()["data"]["default_project_name"] == "Bandeja de Entrada"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_intake_settings_isolated_by_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """`IntakeSettings` es único por organización y no visible entre
    organizaciones."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    await client.patch(
        "/intake/settings",
        json={"default_project_name": "Solo Org A"},
        headers=_auth(manager_token),
    )

    org_a_settings = await client.get("/intake/settings", headers=_auth(two_orgs.a.token))
    assert org_a_settings.json()["data"]["default_project_name"] == "Solo Org A"

    org_b_settings = await client.get("/intake/settings", headers=_auth(two_orgs.b.token))
    assert org_b_settings.json()["data"]["default_project_name"] is None
