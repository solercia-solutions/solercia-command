"""Tests for ``app.maintenance.bootstrap`` (Fase 3 — Rebanada 2b).

design.md's 6 Testing Strategy scenarios: hierarchy shape, SEGURIDAD's 7
columns/order, literal (never slugified) ``status_key``, PANDORA's kanban
defaults, idempotent reuse by ``code``, and the ``intake_settings`` upsert.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.bootstrap import SEGURIDAD_COLUMNS, bootstrap_sdmujer
from app.methodology.board_aware import resolve_board_strategy
from app.modules.boards.models import Board, BoardColumn
from app.modules.intake.models import IntakeSettings
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.users.models import User
from app.shared.enums import Methodology, ProjectKind
from app.shared.security import hash_password

try:
    from tests.conftest import skip_no_db
except ImportError:  # pragma: no cover - conftest always present in this suite
    skip_no_db = pytest.mark.skip(reason="conftest not found")


async def _seed_org(session: AsyncSession) -> tuple[Organization, User]:
    org = Organization(name="Solercia", slug=f"solercia-{uuid.uuid4().hex[:8]}")
    admin = User(
        email="admin@solercia.com", primer_nombre="Admin", primer_apellido="Solercia",
        hashed_password=hash_password("Demo123*"),
    )
    session.add_all([org, admin])
    await session.flush()
    return org, admin


async def _project_by_code(session: AsyncSession, code: str) -> Project:
    return await session.scalar(select(Project).where(Project.code == code))  # type: ignore[return-value]


async def _columns_of(session: AsyncSession, project_id: uuid.UUID) -> list[BoardColumn]:
    board_id = await session.scalar(
        select(Board.id).where(Board.project_id == project_id, Board.is_active.is_(True))
    )
    result = await session.execute(
        select(BoardColumn)
        .where(BoardColumn.board_id == board_id, BoardColumn.is_active.is_(True))
        .order_by(BoardColumn.order.asc())
    )
    return list(result.scalars().all())


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_bootstrap_crea_sdmujer_seguridad_pandora_con_codigos_y_metodologias(
    session: AsyncSession,
) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    sdm = await _project_by_code(session, "SDM")
    seg = await _project_by_code(session, "SEG")
    pan = await _project_by_code(session, "PAN")

    assert (sdm.project_kind, sdm.methodology, sdm.parent_project_id) == (
        ProjectKind.area, Methodology.planner, None,
    )
    assert (seg.project_kind, seg.methodology, seg.parent_project_id) == (
        ProjectKind.proyecto, Methodology.custom, sdm.id,
    )
    assert (pan.project_kind, pan.methodology, pan.parent_project_id) == (
        ProjectKind.proyecto, Methodology.kanban, sdm.id,
    )


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_seguridad_tiene_siete_columnas_y_completada_es_la_de_mayor_order(
    session: AsyncSession,
) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    seg = await _project_by_code(session, "SEG")
    columns = await _columns_of(session, seg.id)

    assert [column.name for column in columns] == list(SEGURIDAD_COLUMNS)
    assert [column.order for column in columns] == list(range(7))

    strategy = await resolve_board_strategy(seg, session)
    assert strategy.allowed_statuses()[-1] == "Completada"
    assert len(strategy.allowed_statuses()) == 7


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_key_de_las_columnas_es_literal_no_slug(session: AsyncSession) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    seg = await _project_by_code(session, "SEG")
    columns = await _columns_of(session, seg.id)

    # BoardService.add_column would slugify "Gestionada aparte" into
    # "gestionada_aparte" (boards/service.py:27-37) — ensure_board_columns
    # never does that.
    keys_by_name = {column.name: column.status_key for column in columns}
    assert keys_by_name["Gestionada aparte"] == "Gestionada aparte"
    assert keys_by_name["Sin iniciar"] == "Sin iniciar"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_pandora_recibe_las_columnas_por_defecto_de_kanban(session: AsyncSession) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    pan = await _project_by_code(session, "PAN")
    columns = await _columns_of(session, pan.id)

    assert [column.name for column in columns] == ["Backlog", "Doing", "Done"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_bootstrap_es_idempotente_y_reutiliza_proyectos_por_codigo(
    session: AsyncSession,
) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)
    seg_first = await _project_by_code(session, "SEG")
    columns_first = await _columns_of(session, seg_first.id)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)
    seg_second = await _project_by_code(session, "SEG")
    columns_second = await _columns_of(session, seg_second.id)

    assert seg_second.id == seg_first.id
    assert len(columns_second) == len(columns_first) == 7

    seg_rows = await session.scalars(
        select(Project).where(Project.organization_id == org.id, Project.code == "SEG")
    )
    assert len(seg_rows.all()) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_intake_settings_apunta_a_seguridad_sin_crear_tareas_outlook(
    session: AsyncSession,
) -> None:
    org, admin = await _seed_org(session)

    await bootstrap_sdmujer(session, organization_id=org.id, actor_id=admin.id)

    seg = await _project_by_code(session, "SEG")
    settings_row = await session.scalar(
        select(IntakeSettings).where(IntakeSettings.organization_id == org.id)
    )
    assert settings_row.default_project_id == seg.id

    tareas_outlook = await session.scalar(
        select(Project).where(Project.organization_id == org.id, Project.name == "Tareas Outlook")
    )
    assert tareas_outlook is None
