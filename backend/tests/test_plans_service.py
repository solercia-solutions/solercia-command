"""Unit tests of the plans module (change 45a-planes-modelo-api).

Pure units: NO database, NO network. Slice B guards (scope/boundary) plus
slice D service tests that use an in-memory fake of ``PlansRepository``
(agents/rules/solercia-persistence.md: services are tested with fakes).
"""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.plans.models import PlanActivity, PlanActivityReport
from app.modules.plans.schemas import PlanActivityReportUpsert
from app.shared.exceptions import AppException

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PLANS_DIR = BACKEND_DIR / "app" / "modules" / "plans"


# ---------------------------------------------------------------------------
# Slice B — scope and boundary guards (scenarios 30, 31, 32)
# ---------------------------------------------------------------------------


def test_plans_module_has_no_importer_or_cli() -> None:
    """Scenario 31: seven modules without counting ``__init__.py`` (eight
    ``.py`` files) and zero document-reader or CLI imports."""

    files = {p.name for p in PLANS_DIR.glob("*.py")}
    assert files == {
        "__init__.py",
        "models.py",
        "vocabularies.py",
        "progress.py",
        "schemas.py",
        "repository.py",
        "service.py",
        "router.py",
    }

    forbidden = re.compile(
        r"^\s*(?:import|from)\s+(zipfile|openpyxl|docx|argparse)\b", re.MULTILINE
    )
    for path in PLANS_DIR.glob("*.py"):
        assert not forbidden.search(path.read_text()), path.name


# Scenario 32 (no «Planes» menu entry and no ``/plans`` route) was a 45a-only
# guard (design.md D13): change 45c delivers both, and its positive contract
# lives in ``test_menu_seed_plans.py``.


def test_report_schema_has_no_second_or_third_line_fields() -> None:
    """Scenario 30 (ADR 0009): exactly the five first-line fields."""

    assert set(PlanActivityReportUpsert.model_fields) == {
        "reported_progress",
        "qualitative_summary",
        "evidence_refs",
        "is_met",
        "met_on_time",
    }

    columns = set(PlanActivityReport.__table__.columns.keys())
    business = columns - {
        "id",
        "plan_activity_id",
        "period",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }
    assert business == {
        "reported_progress",
        "qualitative_summary",
        "evidence_refs",
        "is_met",
        "met_on_time",
    }
    for name in columns:
        assert not any(word in name for word in ("monitor", "evaluat", "observ", "recommend")), name


def test_progress_denominator_matches_the_current_criterion() -> None:
    """Pins the criterion in force (design.md D-E): a task counts unless its
    status is ``'cancelled'``. The ONLY test that changes when change 44 moves
    the definition."""

    from app.modules.plans.progress import progress_denominator

    denominator = progress_denominator()
    sql = str(
        denominator.predicate.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert sql == "tasks.status != 'cancelled'"
    assert denominator.extra_joins == ()


def test_vocabularies_are_closed_frozensets() -> None:
    from app.modules.plans import vocabularies as v

    assert v.PLAN_TYPES == {"pspi", "ptr", "pai", "ptep"}
    assert v.PLAN_STATUSES == {"active", "archived"}
    assert v.REPORT_PERIODS == {"I", "II", "III", "ANUAL"}
    assert v.TASK_LINK_ROLES == {"primary", "contributes"}
    assert v.ACTIVITY_LINK_TYPES == {"contributes_to", "derives_from", "duplicates"}
    assert v.LINK_RESOLUTIONS == {"exact", "by_external_code", "conflict", "manual"}
    for bad, fn, code in (
        ("x", v.validate_period, "plan_period_invalid"),
        ("x", v.validate_plan_type, "plan_type_invalid"),
        ("x", v.validate_plan_status, "plan_status_invalid"),
        ("x", v.validate_task_link_role, "plan_task_link_role_invalid"),
        ("x", v.validate_activity_link_type, "plan_activity_link_type_invalid"),
        ("x", v.validate_resolution, "plan_resolution_invalid"),
    ):
        with pytest.raises(AppException) as exc:
            fn(bad)
        assert exc.value.code == code
        assert exc.value.status_code == 422

    v.validate_reported_progress(None)
    v.validate_reported_progress(Decimal("0"))
    v.validate_reported_progress(Decimal("100"))
    for out_of_range in (Decimal("-0.01"), Decimal("150")):
        with pytest.raises(AppException) as exc:
            v.validate_reported_progress(out_of_range)
        assert exc.value.code == "plan_progress_out_of_range"


# ---------------------------------------------------------------------------
# Slice D — PlansService with a fake repository (scenarios 7, 8, 11, 15)
# ---------------------------------------------------------------------------

ORG_ID = uuid.uuid4()


class _FakeDb:
    """Stand-in for AsyncSession: records commit/rollback intent."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _activity(code: str = "12.4", plan_id: uuid.UUID | None = None) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=plan_id or uuid.uuid4(),
        code=code,
        group_code=None,
        group_name=None,
        name="Actividad",
        deliverable=None,
        evidence_expected=None,
        responsible=None,
        is_mine=True,
        due_date=None,
        target_from=None,
        target_to=None,
        iso_controls=None,
        external_codes=["OM-05", "OM-08"],
        scheduled_periods=None,
        sort_order=0,
        created_at=now,
        created_by=None,
        updated_by=None,
    )


class _FakePlansRepository:
    """In-memory port: enforces tenant scope (org) and returns canned roll-ups."""

    def __init__(self) -> None:
        self.activities: dict[uuid.UUID, tuple[uuid.UUID, Any, str]] = {}
        self.rollup: dict[uuid.UUID, tuple[int, int, int]] = {}
        self.reports: dict[uuid.UUID, tuple[Decimal | None, str]] = {}
        self.upserted_links: list[dict[str, Any]] = []

    def add(self, organization_id: uuid.UUID, activity: Any, plan_code: str) -> None:
        self.activities[activity.id] = (organization_id, activity, plan_code)

    async def get_activity(self, organization_id, activity_id):
        entry = self.activities.get(activity_id)
        if entry is None or entry[0] != organization_id:
            return None
        return entry[1]

    async def plan_codes(self, organization_id, plan_ids):
        return {
            activity.plan_id: code
            for org, activity, code in self.activities.values()
            if org == organization_id and activity.plan_id in set(plan_ids)
        }

    async def rollup_activity_progress(self, organization_id, activity_ids):
        return {a: self.rollup[a] for a in activity_ids if a in self.rollup}

    async def list_reports_for_period(self, organization_id, activity_ids, period):
        return {
            a: value for a, (value, p) in self.reports.items() if p == period and a in activity_ids
        }

    async def find_activity_link(self, from_activity_id, to_activity_id, link_type):
        return None

    async def upsert_activity_link(self, **kwargs):
        self.upserted_links.append(kwargs)
        return SimpleNamespace(
            id=uuid.uuid4(),
            from_activity_id=kwargs["from_activity_id"],
            to_activity_id=kwargs["to_activity_id"],
            link_type=kwargs["link_type"],
            source_reference=kwargs.get("source_reference"),
            resolution=kwargs["resolution"],
        )


def _service(repo: _FakePlansRepository):
    from app.modules.plans.service import PlansService

    return PlansService(_FakeDb(), repository=repo)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_self_link_is_rejected_with_plan_activity_self_link() -> None:
    from app.modules.plans.schemas import ActivityLinkCreate

    repo = _FakePlansRepository()
    activity = _activity()
    repo.add(ORG_ID, activity, "PSPI-2026")
    service = _service(repo)

    with pytest.raises(AppException) as exc:
        await service.create_activity_link(
            ORG_ID,
            activity.id,
            ActivityLinkCreate(to_activity_id=activity.id),
            actor_id=None,
        )
    assert exc.value.code == "plan_activity_self_link"
    assert exc.value.status_code == 422
    assert repo.upserted_links == []


@pytest.mark.asyncio
async def test_conflict_link_serializes_is_confirmed_false() -> None:
    from app.modules.plans.service import PlansService

    def _link(resolution: str) -> Any:
        return SimpleNamespace(
            id=uuid.uuid4(),
            from_activity_id=uuid.uuid4(),
            to_activity_id=uuid.uuid4(),
            link_type="contributes_to",
            source_reference="4.5 (OM-03)",
            resolution=resolution,
        )

    assert PlansService.link_to_read(_link("conflict")).is_confirmed is False
    for resolution in ("exact", "by_external_code", "manual"):
        assert PlansService.link_to_read(_link(resolution)).is_confirmed is True


def test_activity_key_is_derived_and_is_not_a_column() -> None:
    from app.modules.plans.service import PlansService

    columns = PlanActivity.__table__.columns
    assert "code" in columns
    assert "activity_key" not in columns

    read = PlansService.activity_to_read(
        _activity("12.4"), "PAI-2026", rollup=None, reported=None, period=None
    )
    assert read.activity_key == "PAI-2026/12.4"


def test_calculated_progress_uses_a_single_null_rule() -> None:
    """``primary_task_count == 0 => None`` (never 0); otherwise done/total."""

    from app.modules.plans.service import PlansService

    def _read(rollup: tuple[int, int, int] | None):
        return PlansService.activity_to_read(
            _activity(), "PSPI-2026", rollup=rollup, reported=None, period=None
        )

    assert _read(None).calculated_progress is None
    assert _read((0, 0, 4)).calculated_progress is None
    assert _read((0, 4, 0)).calculated_progress == 0.0
    assert _read((1, 4, 3)).calculated_progress == 0.25
    assert _read((1, 4, 3)).contributing_task_count == 3
    assert _read((1, 4, 3)).primary_task_count == 4


@pytest.mark.asyncio
async def test_reported_progress_is_none_for_a_period_without_report() -> None:
    repo = _FakePlansRepository()
    activity = _activity()
    repo.add(ORG_ID, activity, "PSPI-2026")
    repo.reports[activity.id] = (Decimal("40"), "I")
    service = _service(repo)

    # Period WITHOUT a report: ausencia de dato.
    (for_ii,) = await service.build_activity_reads(ORG_ID, [activity], "II")
    assert for_ii.reported_progress is None
    assert for_ii.reported_period == "II"

    # No ?period= at all: the system never picks one for the user (D-F).
    (no_period,) = await service.build_activity_reads(ORG_ID, [activity], None)
    assert no_period.reported_progress is None
    assert no_period.reported_period is None

    (for_i,) = await service.build_activity_reads(ORG_ID, [activity], "I")
    assert for_i.reported_progress == Decimal("40")
    assert for_i.reported_period == "I"
    assert for_i.activity_key == "PSPI-2026/12.4"


@pytest.mark.asyncio
async def test_activity_link_created_through_the_service_is_always_manual() -> None:
    from app.modules.plans.schemas import ActivityLinkCreate

    repo = _FakePlansRepository()
    source, target = _activity("1.1"), _activity("1.2")
    repo.add(ORG_ID, source, "PSPI-2026")
    repo.add(ORG_ID, target, "PSPI-2026")
    db = _FakeDb()
    from app.modules.plans.service import PlansService

    service = PlansService(db, repository=repo)  # type: ignore[arg-type]

    # A client-supplied `resolution` is ignored structurally by the schema.
    body = ActivityLinkCreate.model_validate(
        {"to_activity_id": str(target.id), "resolution": "exact"}
    )
    read = await service.create_activity_link(ORG_ID, source.id, body, actor_id=None)

    assert read.resolution == "manual"
    assert read.is_confirmed is True
    assert repo.upserted_links[0]["resolution"] == "manual"
    assert db.commits == 1, "the service (not the repository) owns the commit"


@pytest.mark.asyncio
async def test_activity_of_another_organization_is_reported_as_not_found() -> None:
    from app.modules.plans.schemas import ActivityLinkCreate

    repo = _FakePlansRepository()
    mine, foreign = _activity("1.1"), _activity("9.9")
    repo.add(ORG_ID, mine, "PSPI-2026")
    repo.add(uuid.uuid4(), foreign, "OTHER-2026")
    service = _service(repo)

    with pytest.raises(AppException) as exc:
        await service.create_activity_link(
            ORG_ID,
            mine.id,
            ActivityLinkCreate(to_activity_id=foreign.id),
            actor_id=None,
        )
    assert exc.value.code == "plan_activity_not_found"
    assert exc.value.status_code == 404
    assert repo.upserted_links == []
