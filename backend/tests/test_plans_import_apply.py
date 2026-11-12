"""45b on real PostgreSQL: idempotent apply and a dry-run that writes nothing.

Synthetic sources only (builders shared with ``test_plans_importers``).
"""

import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.organizations.models import Organization
from app.modules.plans.importers.apply import SessionPlanImportUow, apply_bundle, build_bundle
from app.modules.plans.importers.pai import parse_pai
from app.modules.plans.importers.pspi import parse_pspi
from app.modules.plans.importers.ptr import parse_ptr
from app.modules.plans.models import Plan, PlanActivity, PlanActivityLink
from scripts.import_plans import (
    EXIT_OK,
    EXIT_ORGANIZATION_NOT_FOUND,
    build_parser,
    run,
)
from tests.conftest import skip_no_db
from tests.test_plans_importers import _pai, _pspi, _ptr

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


async def _counts(session: AsyncSession, organization_id: uuid.UUID) -> tuple[int, int, int]:
    plans = await session.scalar(
        select(func.count(Plan.id)).where(Plan.organization_id == organization_id)
    )
    activities = await session.scalar(
        select(func.count(PlanActivity.id))
        .join(Plan, Plan.id == PlanActivity.plan_id)
        .where(Plan.organization_id == organization_id)
    )
    links = await session.scalar(
        select(func.count(PlanActivityLink.id))
        .join(PlanActivity, PlanActivity.id == PlanActivityLink.from_activity_id)
        .join(Plan, Plan.id == PlanActivity.plan_id)
        .where(Plan.organization_id == organization_id)
    )
    return plans or 0, activities or 0, links or 0


async def test_apply_is_atomic_and_idempotent(session: AsyncSession, tenant, tmp_path: Path):
    plans = [
        parse_pspi(_pspi(tmp_path), period_year=2026),
        parse_ptr(_ptr(tmp_path), period_year=2026),
        parse_pai(_pai(tmp_path), period_year=2026),
    ]

    await apply_bundle(SessionPlanImportUow(session), tenant.id, build_bundle(plans))
    first = await _counts(session, tenant.id)
    await apply_bundle(SessionPlanImportUow(session), tenant.id, build_bundle(plans))

    assert first == (3, 4 + 5 + 3, 3)
    assert await _counts(session, tenant.id) == first
    resolutions = await session.execute(
        select(PlanActivityLink.resolution, PlanActivityLink.source_reference)
        .join(PlanActivity, PlanActivity.id == PlanActivityLink.from_activity_id)
        .join(Plan, Plan.id == PlanActivity.plan_id)
        .where(Plan.organization_id == tenant.id)
    )
    assert sorted(resolutions.tuples().all()) == [
        ("conflict", "2.2 (OM-03)"),
        ("exact", "1.1"),
        ("exact", "1.2"),
    ]


async def _committed_organization(engine: AsyncEngine) -> str:
    slug = f"plans-cli-{uuid.uuid4().hex[:10]}"
    async with engine.begin() as connection:
        await connection.execute(insert(Organization).values(name="Entidad sintética", slug=slug))
    return slug


async def test_cli_dry_run_writes_nothing_and_reports(engine: AsyncEngine, tmp_path: Path):
    slug = await _committed_organization(engine)
    report = tmp_path / "informe"
    args = build_parser().parse_args(
        [
            "--organization-slug", slug,
            "--pspi", str(_pspi(tmp_path)),
            "--ptr", str(_ptr(tmp_path)),
            "--report", str(report),
            "--database-url", os.environ["TEST_DATABASE_URL"],
        ]
    )  # fmt: skip

    assert await run(args) == EXIT_OK

    data = json.loads(report.with_name("informe.json").read_text(encoding="utf-8"))
    assert data["mode"] == "dry-run"
    assert [p["activity_count"] for p in data["plans"]] == [4, 5]
    assert len(data["conflicts"]) == 1 and len(data["review"]) == 1
    assert "## Conflictos registrados (1)" in report.with_name("informe.md").read_text("utf-8")
    async with AsyncSession(engine) as reader:
        organization_id = await reader.scalar(
            select(Organization.id).where(Organization.slug == slug)
        )
        assert await _counts(reader, organization_id) == (0, 0, 0)


async def test_cli_refuses_an_unknown_organization(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "--organization-slug", f"no-existe-{uuid.uuid4().hex[:8]}",
            "--pspi", str(_pspi(tmp_path)),
            "--report", str(tmp_path / "informe"),
            "--database-url", os.environ["TEST_DATABASE_URL"],
            "--apply",
        ]
    )  # fmt: skip

    assert await run(args) == EXIT_ORGANIZATION_NOT_FOUND
    assert not (tmp_path / "informe.json").exists()
