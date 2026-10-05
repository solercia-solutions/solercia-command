"""HTTP tests of the institutional plans API (change 45a-planes-modelo-api).

Real API in-process (``httpx.AsyncClient`` over the ASGI app) on PostgreSQL.
Plans and activities are seeded through the repository WRITE SEAM (design.md
D10/D-M), never by raw INSERT: the tests exercise the same path the importer of
a later change will use.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans.models import PlanActivityLink, PlanActivityReport, TaskPlanActivity
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.enums import MemberRole, Methodology
from tests.conftest import TwoOrgs, skip_no_db

pytestmark = [pytest.mark.asyncio(loop_scope="session"), skip_no_db]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_plan(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    plan_code: str = "PSPI-2026",
    activity_codes: tuple[str, ...] = ("1.1",),
) -> tuple[Any, list[Any]]:
    repo = PlansRepository(session)
    plan = await repo.upsert_plan(
        organization_id,
        PlanUpsert(
            code=plan_code,
            name="Plan de seguridad",
            plan_type="pspi",
            period_year=2026,
        ),
    )
    activities = [
        await repo.upsert_activity(
            plan.id,
            PlanActivityUpsert(
                code=code,
                name=f"Actividad {code}",
                group_code=code.split(".")[0],
                group_name=f"Grupo {code.split('.')[0]}",
                is_mine=True,
                sort_order=index,
            ),
        )
        for index, code in enumerate(activity_codes)
    ]
    # The service commits (releases the SAVEPOINT): persist the seed so a
    # service-side rollback never discards it.
    await session.commit()
    return plan, activities


async def _seed_task(session: AsyncSession, organization_id: uuid.UUID, code: str = "TSK") -> Task:
    project = Project(
        organization_id=organization_id,
        name=f"Proyecto {code}",
        methodology=Methodology.kanban,
        code=code,
        task_counter=0,
    )
    session.add(project)
    await session.flush()
    task = Task(project_id=project.id, title=f"Tarea {code}", status="To Do")
    session.add(task)
    await session.commit()
    return task


async def _link_task(
    session: AsyncSession, task: Task, activity: Any, role: str = "primary"
) -> None:
    await PlansRepository(session).upsert_task_link(task.id, activity.id, role)
    await session.commit()


# ---------------------------------------------------------------------------
# Reads (slice E)
# ---------------------------------------------------------------------------


async def test_plan_detail_exposes_code_type_year_and_group_counts(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    plan, _ = await _seed_plan(session, tenant.id, activity_codes=("1.1", "1.2", "2.1"))

    response = await client.get(f"/plans/{plan.id}", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert (data["code"], data["plan_type"], data["period_year"]) == (
        "PSPI-2026",
        "pspi",
        2026,
    )
    assert data["activity_count"] == 3
    assert {(g["group_code"], g["activity_count"]) for g in data["groups"]} == {
        ("1", 2),
        ("2", 1),
    }


async def test_activity_without_primary_links_serializes_calculated_progress_as_null(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    _, (activity,) = await _seed_plan(session, tenant.id)

    response = await client.get("/plans/activities", headers=_auth(token))

    assert response.status_code == 200, response.text
    (row,) = response.json()["data"]
    assert "calculated_progress" in row
    assert row["calculated_progress"] is None  # literal null, never 0
    assert row["activity_key"] == "PSPI-2026/1.1"
    assert row["primary_task_count"] == 0
    assert row["reported_progress"] is None and row["reported_period"] is None


async def test_activity_of_another_organization_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    _, (foreign,) = await _seed_plan(session, two_orgs.b.organization.id)

    response = await client.get(f"/plans/activities/{foreign.id}", headers=_auth(two_orgs.a.token))

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "plan_activity_not_found"


@pytest.mark.parametrize(
    ("template", "expects_list"),
    [
        ("/plans", True),
        ("/plans/activities", True),
        ("/plans/activities/{activity_id}", False),
        ("/plans/activities/{activity_id}/tasks", False),
        ("/plans/{plan_id}", False),
    ],
)
async def test_no_read_endpoint_ever_returns_rows_of_another_organization(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    template: str,
    expects_list: bool,
) -> None:
    plan, (activity,) = await _seed_plan(session, two_orgs.b.organization.id)
    path = template.format(activity_id=activity.id, plan_id=plan.id)

    response = await client.get(path, headers=_auth(two_orgs.a.token))

    if expects_list:
        assert response.status_code == 200, response.text
        assert response.json()["data"] == []
    else:
        assert response.status_code == 404, response.text


async def test_member_can_read_every_plans_endpoint(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    plan, (activity,) = await _seed_plan(session, tenant.id)

    for path in (
        "/plans",
        f"/plans/{plan.id}",
        "/plans/activities",
        f"/plans/activities/{activity.id}",
        f"/plans/activities/{activity.id}/tasks",
    ):
        response = await client.get(path, headers=_auth(token))
        assert response.status_code == 200, (path, response.text)


async def test_activities_filtered_by_task_id_return_both_links(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    _, (a, b, other) = await _seed_plan(session, tenant.id, activity_codes=("2.5", "5.3", "9.9"))
    task = await _seed_task(session, tenant.id)
    await _link_task(session, task, a)
    await _link_task(session, task, b)

    response = await client.get(
        "/plans/activities", params={"task_id": str(task.id)}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    keys = {row["activity_key"] for row in response.json()["data"]}
    assert keys == {"PSPI-2026/2.5", "PSPI-2026/5.3"}
    assert other.code not in {k.split("/")[1] for k in keys}


async def test_activity_tasks_expose_the_source_external_key(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """The plans page shows the business code the entity knows («T-07» of the
    checklist) next to the Command key, so each linked task carries the
    origin's ``source`` and ``external_key`` (null for native tasks)."""

    _, token = user
    _, (activity,) = await _seed_plan(session, tenant.id)
    imported = await _seed_task(session, tenant.id, code="CHK")
    imported.source = "checklist_xlsx"
    imported.external_key = "CHECKLIST_TAREAS:T-07"
    native = await _seed_task(session, tenant.id, code="NAT")
    await session.commit()
    await _link_task(session, imported, activity)
    await _link_task(session, native, activity, role="contributes")

    response = await client.get(f"/plans/activities/{activity.id}/tasks", headers=_auth(token))

    assert response.status_code == 200, response.text
    rows = {row["title"]: row for row in response.json()["data"]}
    assert rows["Tarea CHK"]["source"] == "checklist_xlsx"
    assert rows["Tarea CHK"]["external_key"] == "CHECKLIST_TAREAS:T-07"
    assert rows["Tarea NAT"]["source"] is None
    assert rows["Tarea NAT"]["external_key"] is None


def test_task_read_declares_no_plan_field() -> None:
    from app.modules.tasks.schemas import TaskRead

    assert not [name for name in TaskRead.model_fields if "plan" in name.lower()]


async def test_activities_route_is_declared_before_plan_detail(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    from app.main import app

    _, token = user
    await _seed_plan(session, tenant.id)
    paths = [getattr(r, "path", "") for r in app.routes]
    assert paths.index("/api/v1/plans/activities") < paths.index("/api/v1/plans/{plan_id}")

    response = await client.get("/plans/activities", headers=_auth(token))

    assert response.status_code == 200, response.text  # not 422 from UUID parsing
    assert isinstance(response.json()["data"], list)


def test_no_registered_route_creates_a_plan_or_an_activity() -> None:
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/plans"):
            continue
        if "POST" in getattr(route, "methods", set()):
            assert not path.endswith("/plans"), path
            assert not path.endswith("/activities"), path


async def test_pagination_is_opt_in_on_the_activity_list(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    await _seed_plan(session, tenant.id, activity_codes=("1.1", "1.2", "1.3"))

    plain = await client.get("/plans/activities", headers=_auth(token))
    paged = await client.get(
        "/plans/activities", params={"page": 1, "size": 2}, headers=_auth(token)
    )

    assert plain.json()["meta"] == {"total": 3}
    assert len(plain.json()["data"]) == 3
    assert paged.json()["meta"] == {"page": 1, "size": 2, "total": 3}
    assert len(paged.json()["data"]) == 2


async def test_activity_detail_lists_reports_and_conflict_link_as_unconfirmed(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    _, token = user
    _, (a, b) = await _seed_plan(session, tenant.id, activity_codes=("1.1", "1.2"))
    repo = PlansRepository(session)
    await repo.upsert_activity_link(
        a.id, b.id, "contributes_to", "conflict", source_reference="4.5 (OM-03)"
    )
    await session.commit()

    response = await client.get(f"/plans/activities/{a.id}", headers=_auth(token))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["reports"] == []  # a period without report has no row
    (link,) = data["links_out"]
    assert link["resolution"] == "conflict"
    assert link["is_confirmed"] is False
    assert link["source_reference"] == "4.5 (OM-03)"
    incoming = await client.get(f"/plans/activities/{b.id}", headers=_auth(token))
    assert incoming.json()["data"]["links_in"][0]["is_confirmed"] is False


# ---------------------------------------------------------------------------
# Writes (slice F)
# ---------------------------------------------------------------------------


async def _manager(make_member, session: AsyncSession, tenant) -> str:
    _, token = await make_member(session, tenant, MemberRole.manager)
    return token


async def test_duplicate_task_link_returns_409_plan_task_link_duplicate(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)
    task = await _seed_task(session, tenant.id)
    body = {"task_id": str(task.id), "role": "contributes"}

    first = await client.post(
        f"/plans/activities/{activity.id}/tasks", json=body, headers=_auth(token)
    )
    second = await client.post(
        f"/plans/activities/{activity.id}/tasks", json=body, headers=_auth(token)
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "plan_task_link_duplicate"
    count = (await session.execute(select(func.count()).select_from(TaskPlanActivity))).scalar_one()
    assert count == 1


async def test_cross_tenant_task_link_is_rejected(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    _, (mine,) = await _seed_plan(session, two_orgs.a.organization.id)
    _, (foreign,) = await _seed_plan(session, two_orgs.b.organization.id, plan_code="PSPI-B")

    foreign_activity = await client.post(
        f"/plans/activities/{foreign.id}/tasks",
        json={"task_id": str(two_orgs.a.task.id), "role": "primary"},
        headers=_auth(two_orgs.a.token),
    )
    foreign_task = await client.post(
        f"/plans/activities/{mine.id}/tasks",
        json={"task_id": str(two_orgs.b.task.id), "role": "primary"},
        headers=_auth(two_orgs.a.token),
    )

    assert foreign_activity.status_code == 404
    assert foreign_activity.json()["code"] == "plan_activity_not_found"
    assert foreign_task.status_code == 404
    assert foreign_task.json()["code"] == "plan_task_not_found"


async def test_two_consecutive_puts_leave_one_report_row_with_the_second_value(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)
    url = f"/plans/activities/{activity.id}/reports/I"

    first = await client.put(
        url, json={"reported_progress": 10, "is_met": False}, headers=_auth(token)
    )
    second = await client.put(
        url,
        json={"reported_progress": 80, "qualitative_summary": "Avance"},
        headers=_auth(token),
    )

    assert first.status_code == 200 and second.status_code == 200, second.text
    rows = (
        (
            await session.execute(
                select(PlanActivityReport).where(PlanActivityReport.plan_activity_id == activity.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert float(rows[0].reported_progress) == 80.0
    assert rows[0].qualitative_summary == "Avance"
    assert rows[0].is_met is None  # PUT replaces the whole period report


async def test_reported_progress_out_of_range_is_rejected(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)

    response = await client.put(
        f"/plans/activities/{activity.id}/reports/II",
        json={"reported_progress": 150},
        headers=_auth(token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "plan_progress_out_of_range"
    count = (
        await session.execute(select(func.count()).select_from(PlanActivityReport))
    ).scalar_one()
    assert count == 0


async def test_invalid_period_is_rejected(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)

    response = await client.put(
        f"/plans/activities/{activity.id}/reports/IV",
        json={"reported_progress": 5},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "plan_period_invalid"


async def test_api_forces_resolution_manual_whatever_the_client_sends(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    _, (a, b) = await _seed_plan(session, two_orgs.a.organization.id, activity_codes=("1.1", "1.2"))
    _, (foreign,) = await _seed_plan(session, two_orgs.b.organization.id, plan_code="PSPI-B")
    token = two_orgs.a.token

    created = await client.post(
        f"/plans/activities/{a.id}/links",
        json={
            "to_activity_id": str(b.id),
            "link_type": "contributes_to",
            "resolution": "exact",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["resolution"] == "manual"
    row = (
        await session.execute(
            select(PlanActivityLink).where(PlanActivityLink.from_activity_id == a.id)
        )
    ).scalar_one()
    assert row.resolution == "manual"

    before = (
        await session.execute(select(func.count()).select_from(PlanActivityLink))
    ).scalar_one()
    foreign_target = await client.post(
        f"/plans/activities/{a.id}/links",
        json={"to_activity_id": str(foreign.id)},
        headers=_auth(token),
    )
    after = (await session.execute(select(func.count()).select_from(PlanActivityLink))).scalar_one()
    assert foreign_target.status_code == 404
    assert foreign_target.json()["code"] == "plan_activity_not_found"
    assert before == after

    self_link = await client.post(
        f"/plans/activities/{a.id}/links",
        json={"to_activity_id": str(a.id)},
        headers=_auth(token),
    )
    assert self_link.status_code == 422
    assert self_link.json()["code"] == "plan_activity_self_link"


async def test_duplicate_task_link_conflicts_and_deleting_a_missing_link_returns_404(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)
    task = await _seed_task(session, tenant.id)
    base = f"/plans/activities/{activity.id}/tasks"

    assert (
        await client.post(base, json={"task_id": str(task.id)}, headers=_auth(token))
    ).status_code == 201
    assert (
        await client.post(base, json={"task_id": str(task.id)}, headers=_auth(token))
    ).status_code == 409

    deleted = await client.delete(f"{base}/{task.id}", headers=_auth(token))
    assert deleted.status_code == 204
    missing = await client.delete(f"{base}/{task.id}", headers=_auth(token))
    assert missing.status_code == 404
    assert missing.json()["code"] == "plan_task_link_not_found"
    # After a DELETE the same pair can be linked again (no retained unique).
    relink = await client.post(base, json={"task_id": str(task.id)}, headers=_auth(token))
    assert relink.status_code == 201

    no_link = await client.delete(
        f"/plans/activities/{activity.id}/links/{uuid.uuid4()}", headers=_auth(token)
    )
    assert no_link.status_code == 404
    assert no_link.json()["code"] == "plan_activity_link_not_found"


@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.viewer])
async def test_member_is_forbidden_on_every_write_endpoint(
    client: AsyncClient, session: AsyncSession, tenant, make_member, role
) -> None:
    _, token = await make_member(session, tenant, role)
    _, (activity,) = await _seed_plan(session, tenant.id)
    base = f"/plans/activities/{activity.id}"
    calls = [
        ("PUT", f"{base}/reports/I", {"reported_progress": 10}),
        ("POST", f"{base}/tasks", {"task_id": str(uuid.uuid4())}),
        ("DELETE", f"{base}/tasks/{uuid.uuid4()}", None),
        ("POST", f"{base}/links", {"to_activity_id": str(uuid.uuid4())}),
        ("DELETE", f"{base}/links/{uuid.uuid4()}", None),
    ]

    for method, url, body in calls:
        response = await client.request(method, url, json=body, headers=_auth(token))
        assert response.status_code == 403, (method, url, response.text)


async def test_manager_can_write_a_period_report(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)

    response = await client.put(
        f"/plans/activities/{activity.id}/reports/ANUAL",
        json={"reported_progress": 55.5, "evidence_refs": ["DOC-1"]},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["period"] == "ANUAL"
    assert float(data["reported_progress"]) == 55.5
    assert data["evidence_refs"] == ["DOC-1"]


async def test_reported_progress_reaches_the_activity_row_only_for_the_asked_period(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)
    await client.put(
        f"/plans/activities/{activity.id}/reports/I",
        json={"reported_progress": 30},
        headers=_auth(token),
    )

    for_i = await client.get("/plans/activities", params={"period": "I"}, headers=_auth(token))
    for_ii = await client.get("/plans/activities", params={"period": "II"}, headers=_auth(token))

    (row_i,) = for_i.json()["data"]
    (row_ii,) = for_ii.json()["data"]
    assert float(row_i["reported_progress"]) == 30.0
    assert row_i["reported_period"] == "I"
    assert row_ii["reported_progress"] is None
    assert row_ii["reported_period"] == "II"


async def test_concurrent_duplicate_link_surfaces_409_not_500(
    client: AsyncClient, session: AsyncSession, tenant, make_member, monkeypatch
) -> None:
    """Simulates losing the race: the row already exists but the lookups made
    before the INSERT see nothing, so the INSERT hits the unique and the
    service must translate the ``IntegrityError`` into the domain 409."""

    token = await _manager(make_member, session, tenant)
    _, (activity,) = await _seed_plan(session, tenant.id)
    task = await _seed_task(session, tenant.id)
    await _link_task(session, task, activity)

    async def _stale_lookup(self, activity_id, task_id):
        return None

    monkeypatch.setattr(PlansRepository, "_find_task_link", _stale_lookup)

    response = await client.post(
        f"/plans/activities/{activity.id}/tasks",
        json={"task_id": str(task.id), "role": "primary"},
        headers=_auth(token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "plan_task_link_duplicate"
