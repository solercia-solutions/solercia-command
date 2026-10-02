"""Checklist import + plan follow-up on real PostgreSQL (synthetic data only).

Proves the SQL adapters: org-scoped anchors (including soft-deleted rows),
project sequence allocation in the same transaction, board columns, the
45a seam upserts for reports/links, and idempotence of both feeds.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.plans.importers.followup import (
    FollowupBundle,
    LinkCandidate,
    ReportDraft,
)
from app.modules.plans.importers.followup_apply import (
    SessionFollowupUow,
    apply_followup,
    resolve_followup,
)
from app.modules.plans.models import PlanActivityReport, TaskPlanActivity
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert
from app.modules.projects.models import Project
from app.modules.task_import.checklist_apply import (
    CHECKLIST_SOURCE,
    ChecklistTargetError,
    SessionChecklistImportUow,
    SqlChecklistImportStore,
    apply_checklist_plan,
)
from app.modules.task_import.checklist_import import build_checklist_plan
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot
from app.modules.tasks.models import Task
from app.shared.enums import Methodology
from tests.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]

HEADER = (
    "ID;Estado;Vencido;Urgencia;Categoría;Tarea;Detalle;Fecha Límite;Solicitante;Apoyo IA;"
    "Observaciones"
)
ROWS = (
    "T-01;PENDIENTE;No;ALTA;Seguridad;Primera;Detalle;2026-05-15;Ana;No;",
    "T-82;EN CURSO;No;CRÍTICA;Plan Seguridad D612;[PSPI 1.1] Datos;;Sin fecha (por definir);x;No;",
)


def _plan(*rows: str):
    data = ("\n".join((HEADER, *rows)) + "\n").encode("utf-8")
    preview = parse_checklist(SourceSnapshot("c.csv", data), ChecklistProfile(), ParseLimits())
    return build_checklist_plan(preview, source_name="c.csv")


async def _sgsi(
    session: AsyncSession, organization_id: uuid.UUID, statuses=("Sin iniciar", "En curso")
):
    project = Project(
        organization_id=organization_id,
        name="SGSI",
        code="SGSI",
        methodology=Methodology.custom,
        task_counter=0,
    )
    session.add(project)
    await session.flush()
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()
    for order, status in enumerate(statuses):
        session.add(BoardColumn(board_id=board.id, name=status, status_key=status, order=order))
    await session.flush()
    return project


async def _tasks(session: AsyncSession, project_id: uuid.UUID) -> list[Task]:
    result = await session.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.task_number)
    )
    return list(result.scalars())


async def test_checklist_apply_is_idempotent_and_numbers_tasks(session, tenant):
    project = await _sgsi(session, tenant.id)
    first = await apply_checklist_plan(SessionChecklistImportUow(session), tenant.id, _plan(*ROWS))
    second = await apply_checklist_plan(SessionChecklistImportUow(session), tenant.id, _plan(*ROWS))
    assert (len(first.created), len(second.unchanged), second.created) == (2, 2, [])
    tasks = await _tasks(session, project.id)
    assert [(t.external_key, t.task_number, t.status) for t in tasks] == [
        ("CHECKLIST_TAREAS:T-01", 1, "Sin iniciar"),
        ("CHECKLIST_TAREAS:T-82", 2, "En curso"),
    ]
    assert all(t.source == CHECKLIST_SOURCE and t.board_column_id for t in tasks)
    assert tasks[0].due_date.date().isoformat() == "2026-05-15" and tasks[1].due_date is None
    await session.refresh(project)
    assert project.task_counter == 2


async def test_anchors_are_tenant_scoped_and_include_soft_deleted(session, tenant, second_tenant):
    await _sgsi(session, tenant.id)
    await apply_checklist_plan(SessionChecklistImportUow(session), tenant.id, _plan(ROWS[0]))
    store = SqlChecklistImportStore(session)
    keys = ["CHECKLIST_TAREAS:T-01"]
    assert await store.find_anchors(second_tenant.id, CHECKLIST_SOURCE, keys) == {}
    anchor = (await store.find_anchors(tenant.id, CHECKLIST_SOURCE, keys))[keys[0]]
    task = await session.get(Task, anchor.task_id)
    task.is_active = False
    await session.flush()
    result = await apply_checklist_plan(
        SessionChecklistImportUow(session), tenant.id, _plan(ROWS[0])
    )
    assert result.inactive == ["T-01"] and result.created == []


async def test_missing_column_writes_nothing(session, tenant):
    project = await _sgsi(session, tenant.id, statuses=("Sin iniciar",))
    with pytest.raises(ChecklistTargetError):
        await apply_checklist_plan(SessionChecklistImportUow(session), tenant.id, _plan(*ROWS))
    assert (
        await session.scalar(select(func.count(Task.id)).where(Task.project_id == project.id)) == 0
    )


async def test_followup_reports_and_links_are_idempotent(session, tenant):
    await _sgsi(session, tenant.id)
    await apply_checklist_plan(SessionChecklistImportUow(session), tenant.id, _plan(*ROWS))
    repo = PlansRepository(session)
    pspi = await repo.upsert_plan(
        tenant.id, PlanUpsert(code="PSPI-2026", name="PSPI", plan_type="pspi", period_year=2026)
    )
    pai = await repo.upsert_plan(
        tenant.id, PlanUpsert(code="PAI-2026", name="PAI", plan_type="pai", period_year=2026)
    )
    await session.flush()
    await repo.upsert_activity(
        pspi.id, PlanActivityUpsert(code="1.1", name="Datos", external_codes=["OM-05"])
    )
    await repo.upsert_activity(pai.id, PlanActivityUpsert(code="12.1", name="Sensibilizar"))
    await session.flush()
    bundle = FollowupBundle(
        reports=[
            ReportDraft(
                "PAI-2026/12.1",
                "II",
                Decimal("100.00"),
                "1",
                "Hecho",
                ["Lista"],
                True,
                True,
                "pai.xlsx, filas 9/10",
                "fracción",
            ),
            ReportDraft(
                "PAI-2026/99.9", "II", None, None, "x", None, None, None, "pai.xlsx", "sin cifra"
            ),
        ],
        links=[
            LinkCandidate("T-82", "PSPI-2026/1.1", None, "primary", "exact", "c.csv", "[PSPI 1.1]"),
            LinkCandidate(
                "T-01", None, "OM-05", "contributes", "by_external_code", "c.csv", "OM-05"
            ),
            LinkCandidate("T-77", "PSPI-2026/1.1", None, "contributes", "exact", "cruce", "T-77"),
        ],
    )
    codes = ["PSPI-2026", "PAI-2026"]
    resolved = await resolve_followup(
        SessionFollowupUow(session),
        tenant.id,
        bundle,
        plan_codes=codes,
        namespace="CHECKLIST_TAREAS",
    )
    assert [r.status for r in resolved.reports] == ["nuevo"]
    assert sorted(lk.candidate.source_id for lk in resolved.links) == ["T-01", "T-82"]
    assert {r.subject.split(" ")[0] for r in resolved.review} == {"PAI-2026/99.9", "T-77"}
    assert await apply_followup(SessionFollowupUow(session), resolved) == {
        "reports_written": 1,
        "links_written": 2,
    }

    again = await resolve_followup(
        SessionFollowupUow(session),
        tenant.id,
        bundle,
        plan_codes=codes,
        namespace="CHECKLIST_TAREAS",
    )
    assert {r.status for r in again.reports} | {lk.status for lk in again.links} == {"sin cambios"}
    assert await apply_followup(SessionFollowupUow(session), again) == {
        "reports_written": 0,
        "links_written": 0,
    }
    assert await session.scalar(select(func.count(TaskPlanActivity.id))) >= 2
    report = await session.scalar(
        select(PlanActivityReport).where(PlanActivityReport.period == "II")
    )
    assert report.reported_progress == Decimal("100.00") and report.evidence_refs == ["Lista"]
