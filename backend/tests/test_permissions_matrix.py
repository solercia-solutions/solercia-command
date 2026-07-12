"""Cross-cutting permission matrix: the gate REALLY implemented per endpoint,
not an idealized model (test-coverage-baseline/spec.md, "Matriz de permisos
por endpoint").

Two role systems coexist and are exercised separately:
- RBAC catalog (``Role.code == 'ADMIN'`` via ``require_admin``): rbac-catalog,
  users-admin, ``PATCH /alert-rules/{id}``, ``POST /alerts/evaluate``.
- Inline ownership/supervision checks (NOT ``require_role()``):
  ``GET /users/{id}/time-logs`` (admin/manager only for another user's data),
  ``PATCH``/``DELETE /time-logs/{id}`` (strict owner).
- No role gate at all: CRUD on projects/tasks — any ``MemberRole`` passes.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.shared.enums import MemberRole
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_alert_rule(session: AsyncSession, tenant: Organization):
    from app.modules.alert_rules.models import AlertRule

    rule = AlertRule(
        organization_id=tenant.id,
        rule_type="task_overdue",
        enabled=True,
        threshold_params={},
    )
    session.add(rule)
    await session.flush()
    return rule


async def _admin_family_request(
    case: str, client: AsyncClient, token: str, alert_rule_id: uuid.UUID
):
    if case == "roles_list":
        return await client.get("/admin/roles", headers=_auth(token))
    if case == "menus_list":
        return await client.get("/admin/menus", headers=_auth(token))
    if case == "dependencies_list":
        return await client.get("/admin/dependencies", headers=_auth(token))
    if case == "users_list":
        return await client.get("/admin/users", headers=_auth(token))
    if case == "alert_rules_patch":
        return await client.patch(
            f"/alert-rules/{alert_rule_id}",
            json={"enabled": False},
            headers=_auth(token),
        )
    if case == "alerts_evaluate":
        return await client.post("/alerts/evaluate", headers=_auth(token))
    raise ValueError(f"unknown case: {case}")


_ADMIN_FAMILY_CASES = [
    "roles_list",
    "menus_list",
    "dependencies_list",
    "users_list",
    "alert_rules_patch",
    "alerts_evaluate",
]


# ---------------------------------------------------------------------------
# Familia require_admin (RBAC ADMIN)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _ADMIN_FAMILY_CASES)
@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.manager])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_admin_family_rejects_member_and_manager_without_rbac(
    role: MemberRole,
    case: str,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """A ``member``/``manager`` MemberRole WITHOUT the RBAC ADMIN role gets 403."""

    alert_rule = await _seed_alert_rule(session, tenant)
    _, token = await make_member(session, tenant, role)

    response = await _admin_family_request(case, client, token, alert_rule.id)

    assert response.status_code == 403


@pytest.mark.parametrize("case", _ADMIN_FAMILY_CASES)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_require_admin_family_accepts_rbac_admin(
    case: str,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    rbac_admin,
) -> None:
    """A user WITH the RBAC ADMIN role passes every endpoint in the family (2xx)."""

    owner, token = user
    await rbac_admin(session, tenant, owner)
    alert_rule = await _seed_alert_rule(session, tenant)

    response = await _admin_family_request(case, client, token, alert_rule.id)

    assert 200 <= response.status_code < 300, response.text


# ---------------------------------------------------------------------------
# GET /users/{id}/time-logs de OTRO usuario: admin/manager sí, member/viewer no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,expected_status",
    [
        (MemberRole.member, 403),
        (MemberRole.viewer, 403),
        (MemberRole.admin, 200),
        (MemberRole.manager, 200),
    ],
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_time_logs_visibility_of_another_user_by_role(
    role: MemberRole,
    expected_status: int,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """``GET /users/{id}/time-logs`` of ANOTHER user: 403 for member/viewer,
    200 for admin/manager — the inline ``_require_visibility`` gate, not
    ``require_role()``.
    """

    owner, owner_token = user
    project = await client.post(
        "/projects",
        json={"name": "Matrix Project", "methodology": "kanban"},
        headers=_auth(owner_token),
    )
    project_id = project.json()["data"]["id"]
    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Matrix task"},
        headers=_auth(owner_token),
    )
    task_id = task.json()["data"]["id"]
    await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 2},
        headers=_auth(owner_token),
    )

    _, requester_token = await make_member(session, tenant, role)

    response = await client.get(
        f"/users/{owner.id}/time-logs", headers=_auth(requester_token)
    )

    assert response.status_code == expected_status


# ---------------------------------------------------------------------------
# PATCH/DELETE /time-logs/{id}: dueño estricto (ni admin ni manager exentos)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.manager, MemberRole.admin])
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_time_log_edit_delete_forbidden_to_non_owner_regardless_of_role(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user,
    make_member,
) -> None:
    """A non-owner gets 403 on PATCH/DELETE — even admin/manager get no exemption."""

    owner, owner_token = user
    project = await client.post(
        "/projects",
        json={"name": "Owner Project", "methodology": "kanban"},
        headers=_auth(owner_token),
    )
    project_id = project.json()["data"]["id"]
    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Owner task"},
        headers=_auth(owner_token),
    )
    task_id = task.json()["data"]["id"]
    log = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 2},
        headers=_auth(owner_token),
    )
    log_id = log.json()["data"]["id"]

    _, other_token = await make_member(session, tenant, role)

    patch_response = await client.patch(
        f"/time-logs/{log_id}", json={"hours": 5}, headers=_auth(other_token)
    )
    delete_response = await client.delete(
        f"/time-logs/{log_id}", headers=_auth(other_token)
    )

    assert patch_response.status_code == 403
    assert delete_response.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_time_log_edit_allowed_to_owner(
    client: AsyncClient, tenant: Organization, user
) -> None:
    """The owner CAN edit their own time-log entry (2xx)."""

    owner, token = user
    project = await client.post(
        "/projects",
        json={"name": "Self Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    project_id = project.json()["data"]["id"]
    task = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Self task"},
        headers=_auth(token),
    )
    task_id = task.json()["data"]["id"]
    log = await client.post(
        f"/tasks/{task_id}/time-logs",
        json={"date": "2026-02-10", "hours": 2},
        headers=_auth(token),
    )
    log_id = log.json()["data"]["id"]

    response = await client.patch(
        f"/time-logs/{log_id}", json={"hours": 5}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# CRUD projects/tasks: sin gate de rol — los 4 MemberRole reciben 2xx
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [MemberRole.admin, MemberRole.manager, MemberRole.member, MemberRole.viewer]
)
@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_projects_and_tasks_crud_has_no_role_gate(
    role: MemberRole,
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    make_member,
) -> None:
    """Every ``MemberRole`` — including ``viewer`` — can list/create projects
    and tasks: there is no ``require_role()`` gate on this domain CRUD, only
    authentication + membership (test-coverage-baseline/spec.md).
    """

    _, token = await make_member(session, tenant, role)

    list_response = await client.get("/projects", headers=_auth(token))
    assert list_response.status_code == 200, list_response.text

    create_response = await client.post(
        "/projects",
        json={"name": f"{role.value} Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert create_response.status_code == 201, create_response.text

    project_id = create_response.json()["data"]["id"]
    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": f"{role.value} task"},
        headers=_auth(token),
    )
    assert task_response.status_code == 201, task_response.text
