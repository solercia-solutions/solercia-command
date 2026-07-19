"""API tests for org-role-templates (change 23-org-role-templates).

R1 catálogo sembrado · R2 instanciación con responsable · R3 idempotencia por
reconciliación · R4 validaciones · R5 aislamiento multi-tenant
(specs/org-role-templates/spec.md). Also covers the roll-up (change
21-project-hierarchy) reporting correctly over an instantiated tree and the
SAVEPOINT-masking lesson (instantiate() commits for real, verified with two
independent sessions bound directly to the engine — same precedent as
``test_sso_service.py::test_resolve_commits_...``).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.org_role_templates.seeder import ensure_system_templates
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.shared.enums import MemberRole

try:
    from tests.conftest import TwoOrgs, skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _template_id_by_name(client: AsyncClient, token: str, name: str) -> str:
    response = await client.get("/org-role-templates", headers=_auth(token))
    row = next(row for row in response.json()["data"] if row["name"] == name)
    return row["id"]


async def _promote_to_admin(session: AsyncSession, user_id) -> None:
    """Promote the ``user`` fixture's default ``MemberRole.member`` to
    ``admin`` — ``require_role`` reads ``OrganizationMember.role``."""

    result = await session.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user_id)
    )
    membership = result.scalar_one()
    membership.role = MemberRole.admin
    await session.flush()


# ---------------------------------------------------------------------------
# R1 — catálogo sembrado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_templates_returns_the_five_system_templates(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    _, token = user

    response = await client.get("/org-role-templates", headers=_auth(token))

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 5
    assert all(row["is_system"] is True for row in rows)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_jefe_oap_ti_detail_exposes_umbrella_two_branches_and_eight_teams(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    _, token = user
    template_id = await _template_id_by_name(client, token, "Jefe OAP‑TI")

    response = await client.get(
        f"/org-role-templates/{template_id}", headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    tree = response.json()["data"]["tree"]
    assert tree["name"] == "OAP‑TI"
    assert {branch["name"] for branch in tree["children"]} == {
        "Planeación",
        "Tecnología",
    }
    total_teams = sum(len(branch["children"]) for branch in tree["children"])
    assert total_teams == 8


# ---------------------------------------------------------------------------
# R2 — instanciación genera el árbol de proyectos con responsable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_flat_template_creates_five_projects_with_lead_and_planner(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """"Jefe de Planeación" (plana): 1 sombrilla + 4 equipos = 5 proyectos."""

    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe de Planeación")

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 5
    assert all(row["lead_user_id"] == str(new_user.id) for row in rows)
    assert all(row["methodology"] == "planner" for row in rows)
    roots = [row for row in rows if row["parent_project_id"] is None]
    assert len(roots) == 1
    assert roots[0]["name"] == "Planeación"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_jefe_oap_ti_creates_eleven_projects_across_three_levels(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """"Jefe OAP‑TI": 1 sombrilla + 2 ramas + 8 equipos = 11 proyectos, 3 niveles."""

    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe OAP‑TI")

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 11
    assert all(row["lead_user_id"] == str(new_user.id) for row in rows)
    roots = [row for row in rows if row["parent_project_id"] is None]
    assert len(roots) == 1
    root_id = roots[0]["id"]
    branches = [row for row in rows if row["parent_project_id"] == root_id]
    assert len(branches) == 2
    branch_ids = {b["id"] for b in branches}
    teams = [row for row in rows if row["parent_project_id"] in branch_ids]
    assert len(teams) == 8


# ---------------------------------------------------------------------------
# R4 — validaciones de instanciación (rol)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_role_cannot_instantiate(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    new_user, member_token = user  # `user` fixture defaults to MemberRole.member
    template_id = await _template_id_by_name(
        client, member_token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(member_token),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_role_instantiates_successfully(
    client: AsyncClient, session: AsyncSession, tenant, make_member
) -> None:
    await ensure_system_templates(session)
    manager, manager_token = await make_member(session, tenant, MemberRole.manager)
    template_id = await _template_id_by_name(
        client, manager_token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(manager.id)},
        headers=_auth(manager_token),
    )

    assert response.status_code == 201, response.text
    rows = response.json()["data"]
    assert len(rows) == 1  # "Equipo de desarrollo" = solo sombrilla, sin equipos
    assert rows[0]["name"] == "Desarrollo"


# ---------------------------------------------------------------------------
# Roll-up (change 21-project-hierarchy) sobre el árbol instanciado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rollup_from_change_21_reports_correctly_over_instantiated_oap_ti_tree(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    """El roll-up del cambio 21 (``GET /projects/{id}/tree`` y
    ``/progress``) reporta correctamente sobre el árbol de 11 proyectos que
    genera la instanciación de "Jefe OAP‑TI"."""

    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe OAP‑TI")

    instantiate_response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )
    rows = instantiate_response.json()["data"]
    root_id = next(r["id"] for r in rows if r["parent_project_id"] is None)

    tree_response = await client.get(
        f"/projects/{root_id}/tree", headers=_auth(admin_token)
    )
    assert tree_response.status_code == 200, tree_response.text
    tree = tree_response.json()["data"]

    def _count_nodes(node: dict) -> int:
        return 1 + sum(_count_nodes(child) for child in node["children"])

    assert _count_nodes(tree) == 11

    progress_response = await client.get(
        f"/projects/{root_id}/progress", headers=_auth(admin_token)
    )
    assert progress_response.status_code == 200, progress_response.text
    progress = progress_response.json()["data"]
    assert progress["project_id"] == root_id
    # 11 proyectos recién creados, ninguna tarea todavía: el roll-up consolida
    # 0/0 en cada nivel sin fallar — prueba que la agregación recorrió las
    # 11 filas del subárbol (design.md 21, "consolidado del proyecto raíz").
    assert progress["rollup"]["total"] == 0
    assert progress["rollup"]["done"] == 0


# ---------------------------------------------------------------------------
# R3 — idempotencia por reconciliación (Lote 5, tasks.md T5.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reinstantiate_without_changes_creates_no_new_projects(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe de Planeación")

    first = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )
    second = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_ids = {row["id"] for row in first.json()["data"]}
    second_ids = {row["id"] for row in second.json()["data"]}
    assert first_ids == second_ids  # exactamente los mismos proyectos — ninguno nuevo


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reinstantiate_after_soft_deleting_piga_recreates_only_that_node(
    client: AsyncClient, session: AsyncSession, tenant, user
) -> None:
    await ensure_system_templates(session)
    new_user, admin_token = user
    await _promote_to_admin(session, new_user.id)
    template_id = await _template_id_by_name(client, admin_token, "Jefe de Planeación")

    first = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )
    first_rows = {row["name"]: row["id"] for row in first.json()["data"]}

    piga_result = await session.execute(
        select(Project).where(Project.id == uuid.UUID(first_rows["PIGA"]))
    )
    piga = piga_result.scalar_one()
    piga.is_active = False
    await session.flush()

    second = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(new_user.id)},
        headers=_auth(admin_token),
    )
    assert second.status_code == 201, second.text
    second_rows = {row["name"]: row["id"] for row in second.json()["data"]}

    assert len(second_rows) == 5
    assert second_rows["PIGA"] != first_rows["PIGA"]  # recreado — id NUEVO
    for name in (
        "Planeación",
        "MIPG",
        "Políticas, planes y proyectos",
        "Planeación presupuestal",
    ):
        assert second_rows[name] == first_rows[name]  # reusados — MISMO id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_forced_failure_on_fourth_of_five_projects_leaves_none_persisted(
    session: AsyncSession, tenant, user, monkeypatch
) -> None:
    """Fallo forzado al crear el cuarto de cinco proyectos ("Políticas,
    planes y proyectos", 4.º en el orden padre→hijo de "Jefe de
    Planeación") — DESPUÉS de un rollback explícito no queda NINGÚN
    proyecto de esta instanciación, incluidos los 3 anteriores ya
    flush()eados (transacción única, design.md Decisión 3)."""

    await ensure_system_templates(session)
    new_user, _ = user
    await _promote_to_admin(session, new_user.id)

    from app.modules.org_role_templates.models import OrgRoleTemplate
    from app.modules.org_role_templates.service import OrgRoleTemplateService
    from app.modules.projects.service import ProjectService

    template_result = await session.execute(
        select(OrgRoleTemplate).where(OrgRoleTemplate.name == "Jefe de Planeación")
    )
    template = template_result.scalar_one()

    original_create_unit = ProjectService._create_project_unit
    call_count = {"n": 0}

    async def _flaky_create_unit(self, organization_id, data, *, actor_id=None):
        call_count["n"] += 1
        if call_count["n"] == 4:
            raise RuntimeError("Fallo forzado — prueba de rollback transaccional.")
        return await original_create_unit(
            self, organization_id, data, actor_id=actor_id
        )

    monkeypatch.setattr(ProjectService, "_create_project_unit", _flaky_create_unit)

    service = OrgRoleTemplateService(session)
    with pytest.raises(RuntimeError):
        await service.instantiate(tenant.id, template.id, new_user.id)

    assert call_count["n"] == 4  # confirma que llegó justo al 4.º nodo

    await session.rollback()

    result = await session.execute(
        select(Project).where(
            Project.organization_id == tenant.id,
            Project.name.in_(
                [
                    "Planeación",
                    "MIPG",
                    "PIGA",
                    "Políticas, planes y proyectos",
                    "Planeación presupuestal",
                ]
            ),
        )
    )
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# R5 — aislamiento multi-tenant (Lote 5, tasks.md T5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_rejects_lead_from_another_org_with_zero_projects_created(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    await ensure_system_templates(session)
    template_id = await _template_id_by_name(
        client, two_orgs.a.token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(two_orgs.b.user.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "lead_not_member"

    result = await session.execute(
        select(Project).where(
            Project.organization_id == two_orgs.a.organization.id,
            Project.name == "Desarrollo",
        )
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_from_org_a_writes_only_in_org_a(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    await ensure_system_templates(session)
    template_id = await _template_id_by_name(
        client, two_orgs.a.token, "Equipo de desarrollo"
    )

    response = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(two_orgs.a.user.id)},
        headers=_auth(two_orgs.a.token),
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["data"][0]["id"]

    result = await session.execute(
        select(Project).where(Project.id == uuid.UUID(project_id))
    )
    project = result.scalar_one()
    assert project.organization_id == two_orgs.a.organization.id
    assert project.organization_id != two_orgs.b.organization.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_same_template_instantiated_by_two_orgs_does_not_leak_between_them(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    await ensure_system_templates(session)
    template_id = await _template_id_by_name(
        client, two_orgs.a.token, "Equipo de desarrollo"
    )

    response_a = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(two_orgs.a.user.id)},
        headers=_auth(two_orgs.a.token),
    )
    response_b = await client.post(
        f"/org-role-templates/{template_id}/instantiate",
        json={"lead_user_id": str(two_orgs.b.user.id)},
        headers=_auth(two_orgs.b.token),
    )
    assert response_a.status_code == 201, response_a.text
    assert response_b.status_code == 201, response_b.text
    project_a_id = response_a.json()["data"][0]["id"]
    project_b_id = response_b.json()["data"][0]["id"]
    assert project_a_id != project_b_id

    listing_a = await client.get("/projects", headers=_auth(two_orgs.a.token))
    ids_a = {row["id"] for row in listing_a.json()["data"]}
    assert project_a_id in ids_a
    assert project_b_id not in ids_a


# ---------------------------------------------------------------------------
# LECCIÓN SAVEPOINT — instantiate() commitea de verdad (dos sesiones reales)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_commits_so_a_new_session_sees_the_created_projects(
    engine: AsyncEngine,
) -> None:
    """Regresión: ``OrgRoleTemplateService.instantiate()`` DEBE confirmar
    (commit) sus escrituras — ``get_db()`` (app/database.py) abre una sesión
    nueva por request sin auto-commit, así que un flush sin commit se pierde
    al cerrarse la sesión. Usa sesiones ligadas DIRECTAMENTE al engine real
    (evitando el fixture ``session``, que envuelve en un SAVEPOINT y hace
    visible el flush sin necesitar commit, enmascarando este defecto) — mismo
    precedente que ``test_sso_service.py::test_resolve_commits_...``."""

    from sqlalchemy import delete

    from app.modules.org_role_templates.models import OrgRoleTemplate
    from app.modules.org_role_templates.service import OrgRoleTemplateService
    from app.modules.organizations.models import Organization
    from app.modules.users.models import User
    from app.shared.security import hash_password

    write_session = AsyncSession(bind=engine, expire_on_commit=False)
    organization_id = None
    lead_id = None
    created_project_id = None
    try:
        organization = Organization(
            name="Commit Templates Org", slug=f"commit-templates-{uuid.uuid4().hex[:12]}"
        )
        write_session.add(organization)
        await write_session.flush()
        organization_id = organization.id

        lead = User(
            email=f"commit-templates-lead-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Commit",
            primer_apellido="Lead",
            hashed_password=hash_password("Test123*"),
        )
        write_session.add(lead)
        await write_session.flush()
        lead_id = lead.id

        write_session.add(
            OrganizationMember(
                organization_id=organization.id, user_id=lead.id, role=MemberRole.admin
            )
        )
        await write_session.flush()
        await write_session.commit()

        await ensure_system_templates(write_session)
        await write_session.commit()

        template_result = await write_session.execute(
            select(OrgRoleTemplate).where(
                OrgRoleTemplate.name == "Equipo de desarrollo"
            )
        )
        template = template_result.scalar_one()

        service = OrgRoleTemplateService(write_session)
        projects = await service.instantiate(organization.id, template.id, lead.id)
        created_project_id = projects[0].id
    finally:
        await write_session.close()

    fresh_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        result = await fresh_session.execute(
            select(Project).where(Project.id == created_project_id)
        )
        project = result.scalar_one_or_none()
        assert project is not None
        assert project.name == "Desarrollo"
        assert project.lead_user_id == lead_id
        assert project.organization_id == organization_id
    finally:
        await fresh_session.execute(
            delete(Organization).where(Organization.id == organization_id)
        )
        await fresh_session.execute(delete(User).where(User.id == lead_id))
        await fresh_session.commit()
        await fresh_session.close()
