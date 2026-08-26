"""Tests for ``app.maintenance.invariants`` (Fase 3 — Rebanada 2b).

Mandatory inclusion #2 (tasks.md 3.10): one failure case per invariant
I1-I8 injected onto an otherwise-green baseline, plus one all-green test.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.bootstrap import bootstrap_sdmujer
from app.maintenance.invariants import collect_invariants
from app.modules.attachments.models import Attachment
from app.modules.boards.models import Board, BoardColumn
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.intake.models import IntakeSettings
from app.modules.org_role_templates.models import (
    OrgRoleTemplateInstantiation,
    OrgRoleTemplateNode,
)
from app.modules.org_role_templates.seeder import ensure_system_templates
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.users.models import User
from app.shared.enums import AccountStatus
from app.shared.security import hash_password

try:
    from tests.conftest import skip_no_db
except ImportError:  # pragma: no cover - conftest always present in this suite
    skip_no_db = pytest.mark.skip(reason="conftest not found")


async def _seed_green_state(session: AsyncSession) -> tuple[Organization, User]:
    """Admin-only Solercia org, bootstrapped hierarchy, system templates and
    the 3 real connectors — every invariant PASSes from this baseline."""

    await ensure_system_templates(session)
    org = Organization(name="Solercia", slug=f"solercia-{uuid.uuid4().hex[:8]}")
    admin = User(
        email="admin@solercia.com",
        primer_nombre="Admin",
        primer_apellido="Solercia",
        hashed_password=hash_password("Demo123*"),
    )
    session.add_all([org, admin])
    await session.flush()

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    jira = Connector(organization_id=org.id, provider="jira")
    session.add_all(
        [jira, Connector(organization_id=org.id, provider="google"),
         Connector(organization_id=org.id, provider="microsoft365")]
    )
    await session.flush()
    session.add(
        ConnectedAccount(
            organization_id=org.id, connector_id=jira.id, user_id=admin.id,
            external_account_id="jira-real", display_name="Cuenta Jira real",
            status=AccountStatus.active,
        )
    )
    await session.flush()
    return org, admin


async def _assert_only_fails(session: AsyncSession, key: str) -> None:
    results = {result.key: result.passed for result in await collect_invariants(session)}
    assert results[key] is False, results


async def _project_by_code(session: AsyncSession, code: str) -> Project:
    return await session.scalar(select(Project).where(Project.code == code))  # type: ignore[return-value]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_todas_las_invariantes_pasan_tras_un_bootstrap_correcto(
    session: AsyncSession,
) -> None:
    await _seed_green_state(session)

    results = {result.key: result.passed for result in await collect_invariants(session)}

    assert all(results.values()), results
    assert set(results) == {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i1_falla_si_no_existe_admin(session: AsyncSession) -> None:
    _org, admin = await _seed_green_state(session)
    admin_row = await session.get(User, admin.id)
    assert admin_row is not None
    admin_row.email = "admin-renombrado@solercia.com"  # I1 checks the exact email
    await session.flush()

    await _assert_only_fails(session, "I1")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i2_falla_si_existe_acme_consultores(session: AsyncSession) -> None:
    await _seed_green_state(session)
    session.add(Organization(name="Acme Consultores", slug=f"acme-{uuid.uuid4().hex[:8]}"))
    await session.flush()

    await _assert_only_fails(session, "I2")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i3_falla_si_falta_codigo_o_padre_esperado(session: AsyncSession) -> None:
    await _seed_green_state(session)
    seg = await _project_by_code(session, "SEG")
    seg.parent_project_id = None  # SDM is the expected padre, per D6
    await session.flush()

    await _assert_only_fails(session, "I3")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i4_falla_si_completada_no_es_la_ultima_columna(
    session: AsyncSession,
) -> None:
    await _seed_green_state(session)
    seg = await _project_by_code(session, "SEG")
    board_id = await session.scalar(select(Board.id).where(Board.project_id == seg.id))
    columns = (
        await session.execute(
            select(BoardColumn).where(BoardColumn.board_id == board_id).order_by(BoardColumn.order)
        )
    ).scalars().all()
    completada = next(c for c in columns if c.status_key == "Completada")
    removida = next(c for c in columns if c.status_key == "Removida")
    completada.order, removida.order = removida.order, completada.order
    await session.flush()

    await _assert_only_fails(session, "I4")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i5_falla_si_default_project_id_no_apunta_a_seguridad(
    session: AsyncSession,
) -> None:
    org, _admin = await _seed_green_state(session)
    pan = await _project_by_code(session, "PAN")
    settings_row = await session.scalar(
        select(IntakeSettings).where(IntakeSettings.organization_id == org.id)
    )
    settings_row.default_project_id = pan.id
    await session.flush()

    await _assert_only_fails(session, "I5")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i6_falla_si_quedan_adjuntos_huerfanos(session: AsyncSession) -> None:
    org, admin = await _seed_green_state(session)
    session.add(
        Attachment(
            organization_id=org.id, target_type="task",
            target_id=uuid.uuid4(),  # points at nothing — never a real task
            original_name="huerfano.pdf", stored_name=str(uuid.uuid4()),
            content_type="application/pdf", size_bytes=1, uploaded_by=admin.id,
        )
    )
    await session.flush()

    await _assert_only_fails(session, "I6")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i7_falla_si_hay_instantiations_del_alcance_demo(
    session: AsyncSession,
) -> None:
    org, admin = await _seed_green_state(session)
    seg = await _project_by_code(session, "SEG")
    node = await session.scalar(select(OrgRoleTemplateNode).limit(1))
    session.add(
        OrgRoleTemplateInstantiation(
            organization_id=org.id, template_id=node.template_id, node_id=node.id,
            lead_user_id=admin.id, project_id=seg.id,
        )
    )
    await session.flush()

    await _assert_only_fails(session, "I7")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invariante_i8_falla_si_sobrevive_un_conector_fake(session: AsyncSession) -> None:
    org, _admin = await _seed_green_state(session)
    session.add(Connector(organization_id=org.id, provider="fake"))
    await session.flush()

    await _assert_only_fails(session, "I8")
