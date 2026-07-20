"""Unit tests for the org-role-templates service (change 23-org-role-templates).

R4 validaciones de instanciación (specs/org-role-templates/spec.md) at the
UNIT layer — no DB: parent→child traversal order, lead-membership rejection
BEFORE anything is created, and node→project mapping. R1 catálogo sembrado
(T3.4) uses a real DB via the ``session`` fixture (idempotent seeder).
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.org_role_templates.models import OrgRoleTemplate, OrgRoleTemplateNode
from app.modules.org_role_templates.seeder import ensure_system_templates
from app.modules.org_role_templates.service import (
    OrgRoleTemplateService,
    build_project_create,
    container_node_ids,
    order_parent_first,
    project_kind_for_node,
)
from app.shared.enums import Methodology, ProjectKind
from app.shared.exceptions import AppException

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")


def _node(
    *, template_id: uuid.UUID, parent_node_id: uuid.UUID | None, name: str, order: int
) -> OrgRoleTemplateNode:
    return OrgRoleTemplateNode(
        id=uuid.uuid4(),
        template_id=template_id,
        parent_node_id=parent_node_id,
        name=name,
        default_methodology=Methodology.planner,
        order=order,
    )


# ---------------------------------------------------------------------------
# order_parent_first — pure function, sin BD
# ---------------------------------------------------------------------------


def test_order_parent_first_orders_umbrella_before_branches_before_teams() -> None:
    """Jefe OAP‑TI shape: umbrella -> 2 branches -> 4 teams each. The umbrella
    MUST come first, both branches before any of their teams."""

    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="OAP‑TI", order=0
    )
    planeacion = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Planeación", order=0
    )
    tecnologia = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Tecnología", order=1
    )
    mipg = _node(
        template_id=template_id, parent_node_id=planeacion.id, name="MIPG", order=0
    )
    infraestructura = _node(
        template_id=template_id,
        parent_node_id=tecnologia.id,
        name="Infraestructura tecnológica",
        order=0,
    )

    # Deliberately shuffled input — the function must reconstruct the order.
    ordered = order_parent_first(
        [infraestructura, tecnologia, mipg, planeacion, umbrella]
    )

    assert [n.id for n in ordered] == [
        umbrella.id,
        planeacion.id,
        tecnologia.id,
        mipg.id,
        infraestructura.id,
    ]


def test_order_parent_first_orders_flat_template_by_sibling_order() -> None:
    """A flat template (e.g. "Jefe de Planeación"): umbrella first, then its
    4 teams in ``order`` — a DIFFERENT shape than the 3-level test above,
    forcing real sibling-ordering logic instead of a hardcoded 5-node path
    (triangulation)."""

    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="Planeación", order=0
    )
    piga = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="PIGA", order=1
    )
    mipg = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="MIPG", order=0
    )

    ordered = order_parent_first([piga, umbrella, mipg])

    assert [n.id for n in ordered] == [umbrella.id, mipg.id, piga.id]


# ---------------------------------------------------------------------------
# build_project_create — pure function, sin BD
# ---------------------------------------------------------------------------


def test_build_project_create_maps_node_lead_and_parent() -> None:
    template_id = uuid.uuid4()
    node = _node(
        template_id=template_id, parent_node_id=None, name="Tesorería", order=0
    )
    lead_user_id = uuid.uuid4()
    parent_project_id = uuid.uuid4()

    data = build_project_create(
        node,
        lead_user_id=lead_user_id,
        parent_project_id=parent_project_id,
        project_kind=ProjectKind.area,
    )

    assert data.name == "Tesorería"
    assert data.methodology == Methodology.planner
    assert data.lead_user_id == lead_user_id
    assert data.parent_project_id == parent_project_id
    assert data.project_kind == ProjectKind.area


def test_build_project_create_root_node_has_no_parent_project() -> None:
    """A DIFFERENT node (root, no parent) than the previous test — proves the
    mapping is not hardcoded to always attach a parent (triangulation)."""

    template_id = uuid.uuid4()
    node = _node(
        template_id=template_id,
        parent_node_id=None,
        name="Gestión Corporativa",
        order=0,
    )
    lead_user_id = uuid.uuid4()

    data = build_project_create(
        node,
        lead_user_id=lead_user_id,
        parent_project_id=None,
        project_kind=ProjectKind.proyecto,
    )

    assert data.name == "Gestión Corporativa"
    assert data.parent_project_id is None
    assert data.lead_user_id == lead_user_id
    assert data.project_kind == ProjectKind.proyecto


# ---------------------------------------------------------------------------
# container_node_ids / project_kind_for_node — pure functions, sin BD
# ---------------------------------------------------------------------------


def test_container_node_ids_returns_every_node_with_at_least_one_child() -> None:
    """Jefe OAP‑TI shape: umbrella + 2 branches son contenedores; los equipos
    (hojas) no."""

    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="OAP‑TI", order=0
    )
    planeacion = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Planeación", order=0
    )
    tecnologia = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Tecnología", order=1
    )
    mipg = _node(
        template_id=template_id, parent_node_id=planeacion.id, name="MIPG", order=0
    )

    containers = container_node_ids([umbrella, planeacion, tecnologia, mipg])

    assert containers == {umbrella.id, planeacion.id}


def test_container_node_ids_of_a_flat_template_is_only_the_umbrella() -> None:
    """A DIFFERENT shape (flat, one level) than the previous test —
    triangulation: only the umbrella has children, the 2 teams don't."""

    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="Planeación", order=0
    )
    mipg = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="MIPG", order=0
    )
    piga = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="PIGA", order=1
    )

    containers = container_node_ids([umbrella, mipg, piga])

    assert containers == {umbrella.id}


def test_project_kind_for_node_is_area_when_node_is_a_container() -> None:
    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="OAP‑TI", order=0
    )
    child = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Planeación", order=0
    )

    containers = container_node_ids([umbrella, child])

    assert project_kind_for_node(umbrella, containers) == ProjectKind.area


def test_project_kind_for_node_is_proyecto_when_node_is_a_leaf() -> None:
    template_id = uuid.uuid4()
    umbrella = _node(
        template_id=template_id, parent_node_id=None, name="OAP‑TI", order=0
    )
    child = _node(
        template_id=template_id, parent_node_id=umbrella.id, name="Planeación", order=0
    )

    containers = container_node_ids([umbrella, child])

    assert project_kind_for_node(child, containers) == ProjectKind.proyecto


def test_project_kind_for_node_of_a_single_node_template_is_proyecto() -> None:
    """Plantilla de un solo nodo (ej. "Equipo de desarrollo"): sin hijos ni
    padre -> proyecto."""

    template_id = uuid.uuid4()
    solo = _node(
        template_id=template_id, parent_node_id=None, name="Desarrollo", order=0
    )

    containers = container_node_ids([solo])

    assert project_kind_for_node(solo, containers) == ProjectKind.proyecto


# ---------------------------------------------------------------------------
# instantiate — lead membership validated BEFORE anything is created
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Stand-in for ``OrgRoleTemplateRepository`` — no DB, no session."""

    def __init__(self, *, template: OrgRoleTemplate | None, is_member: bool) -> None:
        self._template = template
        self._is_member = is_member
        self.nodes_for_template_called = False

    async def get_visible(
        self, organization_id: uuid.UUID, template_id: uuid.UUID
    ) -> OrgRoleTemplate | None:
        return self._template

    async def is_org_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return self._is_member

    async def nodes_for_template(self, template_id: uuid.UUID) -> list:
        # If instantiate() reaches this, membership rejection did NOT happen
        # before touching the tree — the RED assertion (below) catches it.
        self.nodes_for_template_called = True
        return []


@pytest.mark.asyncio
async def test_instantiate_rejects_non_member_lead_before_touching_the_tree() -> None:
    """R4: ``lead_user_id`` sin membresía activa rechaza la instanciación
    ANTES de tocar el árbol de nodos — ningún proyecto se crea."""

    organization_id = uuid.uuid4()
    template = OrgRoleTemplate(
        id=uuid.uuid4(), organization_id=None, name="Jefe de Planeación", is_system=True
    )
    service = OrgRoleTemplateService(db=None)  # type: ignore[arg-type]
    fake_repo = _FakeRepo(template=template, is_member=False)
    service.repo = fake_repo  # type: ignore[assignment]

    with pytest.raises(AppException) as exc_info:
        await service.instantiate(organization_id, template.id, uuid.uuid4())

    assert exc_info.value.code == "lead_not_member"
    assert exc_info.value.status_code == 422
    assert fake_repo.nodes_for_template_called is False


@pytest.mark.asyncio
async def test_instantiate_rejects_unknown_template_before_checking_membership() -> None:
    """A DIFFERENT rejection path (template not found, not lead) — proves the
    guard clause is not hardcoded to a single error shape (triangulation)."""

    organization_id = uuid.uuid4()
    service = OrgRoleTemplateService(db=None)  # type: ignore[arg-type]
    fake_repo = _FakeRepo(template=None, is_member=True)
    service.repo = fake_repo  # type: ignore[assignment]

    with pytest.raises(AppException) as exc_info:
        await service.instantiate(organization_id, uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.code == "template_not_found"
    assert exc_info.value.status_code == 404
    assert fake_repo.nodes_for_template_called is False


# ---------------------------------------------------------------------------
# ensure_system_templates — R1 catálogo sembrado (T3.4), real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ensure_system_templates_seeds_exactly_five_system_templates(
    session: AsyncSession,
) -> None:
    """R1: exactamente 5 plantillas de sistema, ``organization_id=NULL``,
    ``is_system=True``."""

    await ensure_system_templates(session)

    result = await session.execute(
        select(OrgRoleTemplate).where(OrgRoleTemplate.is_system.is_(True))
    )
    templates = result.scalars().all()

    assert len(templates) == 5
    assert all(t.organization_id is None for t in templates)
    names = {t.name for t in templates}
    assert names == {
        "Jefe OAP‑TI",
        "Jefe de Planeación",
        "Jefe de Tecnología",
        "Gerente de Gestión Corporativa",
        "Equipo de desarrollo",
    }


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ensure_system_templates_second_run_does_not_duplicate(
    session: AsyncSession,
) -> None:
    """Segunda corrida no duplica — ni plantillas ni nodos."""

    await ensure_system_templates(session)
    await ensure_system_templates(session)

    template_count = await session.execute(
        select(func.count())
        .select_from(OrgRoleTemplate)
        .where(OrgRoleTemplate.is_system.is_(True))
    )
    assert template_count.scalar_one() == 5

    node_count = await session.execute(
        select(func.count()).select_from(OrgRoleTemplateNode)
    )
    first_count = node_count.scalar_one()

    await ensure_system_templates(session)

    node_count_after_third_run = await session.execute(
        select(func.count()).select_from(OrgRoleTemplateNode)
    )
    assert node_count_after_third_run.scalar_one() == first_count


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_jefe_oap_ti_template_has_umbrella_two_branches_and_eight_teams(
    session: AsyncSession,
) -> None:
    """El árbol de "Jefe OAP‑TI" tiene 11 nodos: 1 sombrilla + 2 ramas + 8
    equipos (4 por rama) — forma de 3 niveles distinta de las plantillas
    planas (triangulación)."""

    await ensure_system_templates(session)

    template_result = await session.execute(
        select(OrgRoleTemplate).where(OrgRoleTemplate.name == "Jefe OAP‑TI")
    )
    template = template_result.scalar_one()

    nodes_result = await session.execute(
        select(OrgRoleTemplateNode).where(
            OrgRoleTemplateNode.template_id == template.id
        )
    )
    nodes = nodes_result.scalars().all()

    assert len(nodes) == 11
    umbrella = next(n for n in nodes if n.parent_node_id is None)
    assert umbrella.name == "OAP‑TI"
    branches = [n for n in nodes if n.parent_node_id == umbrella.id]
    assert {n.name for n in branches} == {"Planeación", "Tecnología"}
    teams = [n for n in nodes if n.parent_node_id in {b.id for b in branches}]
    assert len(teams) == 8


# ---------------------------------------------------------------------------
# instantiate — dos llamadas CONCURRENTES reconcilian, nunca 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_instantiate_concurrent_calls_reconcile_instead_of_500(
    engine: AsyncEngine,
) -> None:
    """Two REAL concurrent ``instantiate()`` calls for the SAME
    ``(organization, template, lead)`` collide (project ``code`` and/or the
    ledger's ``uq_org_role_template_instantiation``) — both must reconcile
    to the SAME tree, never surface a raw ``IntegrityError`` as a 500. Same
    real-connections pattern as ``test_move_to_column_wip_serializes_
    concurrent_movers_via_row_lock``.
    """

    import asyncio

    # Local imports: importing User/Organization before org_role_templates
    # .service's chain (which configures ALL mappers via projects.repository's
    # module-level SORTABLE_FIELDS) poisons the session if Role isn't loaded
    # yet — same lazy-import pattern as test_board_move_to_column.py.
    from app.modules.organizations.models import Organization, OrganizationMember
    from app.modules.users.models import User
    from app.shared.enums import MemberRole
    from app.shared.security import hash_password

    setup_session = AsyncSession(bind=engine, expire_on_commit=False)
    organization = Organization(
        name="Concurrency Org", slug=f"concurrency-{uuid.uuid4().hex[:12]}"
    )
    try:
        await ensure_system_templates(setup_session)
        template_result = await setup_session.execute(
            select(OrgRoleTemplate).where(
                OrgRoleTemplate.name == "Jefe de Planeación"
            )
        )
        template = template_result.scalar_one()

        setup_session.add(organization)
        await setup_session.flush()

        lead = User(
            email=f"lead-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Lead",
            primer_apellido="Responsable",
            hashed_password=hash_password("Test123*"),
        )
        setup_session.add(lead)
        await setup_session.flush()
        setup_session.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=lead.id,
                role=MemberRole.admin,
            )
        )
        await setup_session.commit()

        organization_id, template_id, lead_id = (
            organization.id,
            template.id,
            lead.id,
        )

        async def _instantiator() -> str:
            async with AsyncSession(
                bind=engine, expire_on_commit=False
            ) as inst_session:
                service = OrgRoleTemplateService(inst_session)
                try:
                    projects = await service.instantiate(
                        organization_id, template_id, lead_id
                    )
                    return f"ok:{len(projects)}"
                except Exception as exc:  # noqa: BLE001 — the RED assertion below
                    return f"error:{type(exc).__name__}"

        results = await asyncio.gather(_instantiator(), _instantiator())

        assert all(r.startswith("ok:") for r in results), results
        assert results[0] == results[1]  # both reconcile to the SAME tree size
    finally:
        await setup_session.execute(
            text("DELETE FROM organizations WHERE id = :id"),
            {"id": str(organization.id)},
        )
        await setup_session.commit()
        await setup_session.close()
