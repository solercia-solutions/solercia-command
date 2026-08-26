"""Tests for ``app.maintenance.purge`` (Fase 2 — Rebanada 2a).

7 of the 8 scenarios in design.md's Testing Strategy; the 8th
(``test_dry_run_no_deja_cambios_visibles``) needs ``runner.py`` and is a
deliberate carry-over to Fase 3 (tasks.md 3.14).

``_seed_demo_fixture`` mirrors the real production data verified
2026-08-26: org "Acme Consultores" (fully demo, incl. an OAP-TI tree), org
"Solercia" (protected) with 5 literal-named projects plus a non-literal
child (subtree closure), a 'fake' connector with a soft-deleted account,
real 'jira'/'google'/'microsoft365' connectors, an asset, and attachments/
notifications/reminders tied to one demo task — shape of ``_seed_org_data``
(``conftest.py:376-460``).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.purge import purge_demo_data
from app.maintenance.report import PurgeGuardError
from app.maintenance.scope import DemoScope
from app.modules.assets.models import Asset, AssetLicense
from app.modules.attachments.models import Attachment
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.notifications.models import Notification
from app.modules.org_role_templates.models import OrgRoleTemplate
from app.modules.org_role_templates.seeder import ensure_system_templates
from app.modules.org_role_templates.service import OrgRoleTemplateService
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.reminders.models import Reminder
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.notify.models import NotificationDelivery
from app.shared.enums import (
    AccountStatus,
    AssetCriticality,
    AssetStatus,
    AssetType,
    LicenseType,
    MemberRole,
    Methodology,
)
from app.shared.security import hash_password

try:
    from tests.conftest import skip_no_db
except ImportError:  # pragma: no cover - conftest always present in this suite
    skip_no_db = pytest.mark.skip(reason="conftest not found")

_LITERAL_PROJECT_NAMES = (
    "Plataforma Web",
    "Soporte Técnico",
    "Mejoras Internas 2026",
    "ACTUALIZACIÓN DE DOCUMENTOS",
    "Desarrollo",
)


@dataclass
class DemoFixture:
    solercia: Organization
    acme: Organization
    admin: User
    ana: User
    carlos: User
    diana: User
    verify_smoke: User
    solercia_projects: dict[str, Project]
    child_project: Project
    template_projects: list[Project]
    demo_task: Task
    fake_connector: Connector
    jira_connector: Connector
    asset: Asset


async def _exists(session: AsyncSession, model, entity_id: uuid.UUID) -> bool:
    """A fresh SELECT — never the ORM identity map, which a bulk ``DELETE``
    (``synchronize_session=False``) never expires."""

    result = await session.execute(select(model.id).where(model.id == entity_id))
    return result.scalar_one_or_none() is not None


async def _count(session: AsyncSession, model, *where) -> int:
    result = await session.execute(select(func.count()).select_from(model).where(*where))
    return result.scalar_one()


async def _make_user(
    session: AsyncSession, email: str, primer_nombre: str, primer_apellido: str
) -> User:
    user = User(
        email=email,
        primer_nombre=primer_nombre,
        primer_apellido=primer_apellido,
        hashed_password=hash_password("Demo123*"),
    )
    session.add(user)
    await session.flush()
    return user


async def _add_member(
    session: AsyncSession, org: Organization, user: User, role: MemberRole
) -> None:
    session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role))
    await session.flush()


async def _seed_demo_fixture(session: AsyncSession) -> DemoFixture:
    await ensure_system_templates(session)

    solercia = Organization(name="Solercia", slug=f"solercia-{uuid.uuid4().hex[:8]}")
    acme = Organization(name="Acme Consultores", slug=f"acme-{uuid.uuid4().hex[:8]}")
    session.add_all([solercia, acme])
    await session.flush()

    admin = await _make_user(session, "admin@solercia.com", "Admin", "Solercia")
    ana = await _make_user(session, "ana@solercia.com", "Ana", "Torres")
    carlos = await _make_user(session, "carlos@solercia.com", "Carlos", "Ruiz")
    diana = await _make_user(session, "diana@solercia.com", "Diana", "Páez")
    verify_smoke = await _make_user(session, "verify-smoke-11@solercia.com", "Verify", "Smoke")

    await _add_member(session, solercia, admin, MemberRole.admin)
    await _add_member(session, acme, ana, MemberRole.admin)
    await _add_member(session, acme, carlos, MemberRole.member)
    await _add_member(session, acme, diana, MemberRole.member)
    await _add_member(session, acme, verify_smoke, MemberRole.member)

    solercia_projects: dict[str, Project] = {}
    for name in _LITERAL_PROJECT_NAMES:
        project = Project(
            organization_id=solercia.id, name=name, methodology=Methodology.kanban, task_counter=0
        )
        session.add(project)
        await session.flush()
        solercia_projects[name] = project

    # Subtree closure (D3): a non-literal child reachable only via
    # parent_project_id — the CTE must still catch it.
    child_project = Project(
        organization_id=solercia.id,
        name="Plataforma Web - Módulo de pagos",
        methodology=Methodology.kanban,
        parent_project_id=solercia_projects["Plataforma Web"].id,
        task_counter=0,
    )
    session.add(child_project)
    await session.flush()

    demo_task = Task(
        project_id=solercia_projects["Plataforma Web"].id,
        title="Tarea demo con adjuntos y notificaciones",
        status="todo",
        assignee_id=ana.id,
    )
    session.add(demo_task)
    await session.flush()

    for index in range(2):
        session.add(
            Attachment(
                organization_id=solercia.id,
                target_type="task",
                target_id=demo_task.id,
                original_name=f"evidencia-{index}.pdf",
                stored_name=str(uuid.uuid4()),
                content_type="application/pdf",
                size_bytes=1024,
                uploaded_by=ana.id,
            )
        )
        notification = Notification(
            organization_id=solercia.id,
            recipient_user_id=ana.id,
            rule_type="task_overdue",
            title=f"Notificación demo {index}",
            body="Cuerpo de la notificación demo.",
            target_type="task",
            target_id=demo_task.id,
            dedup_key=f"task_overdue:{demo_task.id}:{index}",
        )
        session.add(notification)
        await session.flush()
        session.add(
            NotificationDelivery(
                organization_id=solercia.id,
                notification_id=notification.id,
                channel="email",
                dedup_key=f"immediate:{notification.id}",
                payload={"recipient": "ana@solercia.com"},
            )
        )
    session.add(
        Reminder(
            organization_id=solercia.id,
            user_id=ana.id,
            task_id=demo_task.id,
            remind_at=datetime.now(UTC),
            message="Recordatorio demo",
        )
    )
    await session.flush()

    # Instantiated OAP-TI tree under "Acme Consultores" — the org-role-
    # template ledger, not just literally-named projects.
    template_result = await session.execute(
        select(OrgRoleTemplate).where(
            OrgRoleTemplate.organization_id.is_(None),
            OrgRoleTemplate.name.ilike("Jefe OAP%TI"),
        )
    )
    oap_ti_template = template_result.scalar_one()
    template_projects = await OrgRoleTemplateService(session).instantiate(
        acme.id, oap_ti_template.id, ana.id, actor_id=admin.id
    )

    fake_connector = Connector(organization_id=solercia.id, provider="fake")
    jira_connector = Connector(organization_id=solercia.id, provider="jira")
    google_connector = Connector(organization_id=solercia.id, provider="google")
    microsoft_connector = Connector(organization_id=solercia.id, provider="microsoft365")
    session.add_all([fake_connector, jira_connector, google_connector, microsoft_connector])
    await session.flush()

    session.add(
        ConnectedAccount(
            organization_id=solercia.id,
            connector_id=fake_connector.id,
            user_id=admin.id,
            external_account_id="fake-account-1",
            display_name="Cuenta fake de prueba",
            status=AccountStatus.active,
            is_active=False,
        )
    )
    session.add(
        ConnectedAccount(
            organization_id=solercia.id,
            connector_id=jira_connector.id,
            user_id=admin.id,
            external_account_id="jira-account-real",
            display_name="Cuenta Jira real",
            status=AccountStatus.active,
        )
    )
    await session.flush()

    asset = Asset(
        organization_id=acme.id,
        name="Verify Test Asset",
        asset_type=AssetType.software,
        status=AssetStatus.active,
        criticality=AssetCriticality.medium,
    )
    session.add(asset)
    await session.flush()
    session.add(
        AssetLicense(
            organization_id=acme.id,
            asset_id=asset.id,
            license_type=LicenseType.subscription,
            start_date=date(2026, 1, 1),
            expiration_date=date(2027, 1, 1),
        )
    )
    await session.flush()

    return DemoFixture(
        solercia=solercia,
        acme=acme,
        admin=admin,
        ana=ana,
        carlos=carlos,
        diana=diana,
        verify_smoke=verify_smoke,
        solercia_projects=solercia_projects,
        child_project=child_project,
        template_projects=template_projects,
        demo_task=demo_task,
        fake_connector=fake_connector,
        jira_connector=jira_connector,
        asset=asset,
    )


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_borra_org_demo_usuarios_y_proyectos(session: AsyncSession) -> None:
    fixture = await _seed_demo_fixture(session)

    await purge_demo_data(session, DemoScope())

    assert not await _exists(session, Organization, fixture.acme.id)
    for user in (fixture.ana, fixture.carlos, fixture.diana, fixture.verify_smoke):
        assert not await _exists(session, User, user.id)
    assert not await _exists(session, Project, fixture.solercia_projects["Plataforma Web"].id)
    assert not await _exists(session, Project, fixture.template_projects[0].id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_conserva_admin_org_solercia_y_plantillas_de_sistema(
    session: AsyncSession,
) -> None:
    fixture = await _seed_demo_fixture(session)

    await purge_demo_data(session, DemoScope())

    assert await _exists(session, User, fixture.admin.id)
    assert await _exists(session, Organization, fixture.solercia.id)

    result = await session.execute(
        select(OrgRoleTemplate).where(OrgRoleTemplate.organization_id.is_(None))
    )
    system_templates = result.scalars().all()
    assert len(system_templates) == 5
    assert all(template.is_system for template in system_templates)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_borra_adjuntos_notificaciones_y_recordatorios_huerfanos(
    session: AsyncSession,
) -> None:
    fixture = await _seed_demo_fixture(session)
    task_id = fixture.demo_task.id

    assert await _count(session, Attachment, Attachment.target_id == task_id) == 2

    await purge_demo_data(session, DemoScope())

    assert await _count(session, Attachment, Attachment.target_id == task_id) == 0
    assert await _count(session, Notification, Notification.target_id == task_id) == 0
    assert await _count(session, NotificationDelivery) == 0
    assert await _count(session, Reminder, Reminder.task_id == task_id) == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_borra_subarbol_completo_de_hoja_a_raiz(session: AsyncSession) -> None:
    fixture = await _seed_demo_fixture(session)
    parent_id = fixture.solercia_projects["Plataforma Web"].id
    child_id = fixture.child_project.id

    await purge_demo_data(session, DemoScope())

    assert not await _exists(session, Project, parent_id)
    assert not await _exists(session, Project, child_id)
    assert await _count(session, Project, Project.parent_project_id == parent_id) == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_borra_conector_fake_y_conserva_los_reales(session: AsyncSession) -> None:
    fixture = await _seed_demo_fixture(session)

    await purge_demo_data(session, DemoScope())

    assert not await _exists(session, Connector, fixture.fake_connector.id)
    assert await _exists(session, Connector, fixture.jira_connector.id)

    remaining_providers = await session.execute(select(Connector.provider))
    assert {row[0] for row in remaining_providers.all()} == {"jira", "google", "microsoft365"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_falla_cerrado_si_una_cuenta_conectada_pertenece_a_un_usuario_demo(
    session: AsyncSession,
) -> None:
    fixture = await _seed_demo_fixture(session)

    # Reuses the fixture's "jira" connector (one per org/provider) with a
    # second account, this time owned by a demo user.
    session.add(
        ConnectedAccount(
            organization_id=fixture.solercia.id,
            connector_id=fixture.jira_connector.id,
            user_id=fixture.carlos.id,
            external_account_id="carlos-jira-account",
            display_name="Cuenta Jira de Carlos",
            status=AccountStatus.active,
        )
    )
    await session.flush()

    with pytest.raises(PurgeGuardError) as exc_info:
        await purge_demo_data(session, DemoScope())

    assert any(
        risk.owner_email == "carlos@solercia.com" and risk.provider == "jira"
        for risk in exc_info.value.risks
    )

    # The guard trips BEFORE any DELETE — nothing was touched.
    assert await _exists(session, User, fixture.carlos.id)
    assert await _exists(session, Organization, fixture.acme.id)
    assert await _exists(session, Project, fixture.solercia_projects["Plataforma Web"].id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_purga_es_idempotente_en_segunda_corrida(session: AsyncSession) -> None:
    await _seed_demo_fixture(session)

    first = await purge_demo_data(session, DemoScope())
    assert sum(result.deleted for result in first.deleted) > 0

    second = await purge_demo_data(session, DemoScope())

    for result in second.deleted:
        assert result.deleted == 0
