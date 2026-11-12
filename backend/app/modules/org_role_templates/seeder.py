"""Idempotent seed of the 5 system org-role-templates (change
23-org-role-templates, design.md Decision 1).

Same ``_ensure_*`` pattern as the RBAC catalog in ``app/db_init.py``: keyed by
a natural key (here, the template ``name``, scoped to ``organization_id IS
NULL``) so re-running on every startup never duplicates. Templates are NEVER
seeded via a migration (``bulk_insert`` is not used anywhere in this repo) —
they are data, not schema.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org_role_templates.models import OrgRoleTemplate, OrgRoleTemplateNode
from app.shared.enums import Methodology

# (node name, children) — a template's tree is (umbrella name, its children).
_NodeSpec = tuple[str, list["_NodeSpec"]]

_PLANEACION_TEAMS: list[_NodeSpec] = [
    ("MIPG", []),
    ("PIGA", []),
    ("Políticas, planes y proyectos", []),
    ("Planeación presupuestal", []),
]

_TECNOLOGIA_TEAMS: list[_NodeSpec] = [
    ("Infraestructura tecnológica", []),
    ("Desarrollo de software", []),
    ("Gobierno digital", []),
    ("Seguridad de la información", []),
]

# (template name, umbrella node name, umbrella's children) — the exact 5
# system templates of specs/org-role-templates/spec.md, "Catálogo de
# plantillas de sistema".
_TEMPLATE_CATALOG: list[tuple[str, str, list[_NodeSpec]]] = [
    (
        "Jefe OAP‑TI",
        "OAP‑TI",
        [
            ("Planeación", _PLANEACION_TEAMS),
            ("Tecnología", _TECNOLOGIA_TEAMS),
        ],
    ),
    ("Jefe de Planeación", "Planeación", _PLANEACION_TEAMS),
    ("Jefe de Tecnología", "Tecnología", _TECNOLOGIA_TEAMS),
    (
        "Gerente de Gestión Corporativa",
        "Gestión Corporativa",
        [
            ("Tesorería", []),
            ("Subdirección administrativa y financiera", []),
            ("Mantenimiento", []),
        ],
    ),
    ("Equipo de desarrollo", "Desarrollo", []),
]


async def _create_node(
    session: AsyncSession,
    template_id: uuid.UUID,
    parent_node_id: uuid.UUID | None,
    name: str,
    children: Sequence[_NodeSpec],
    *,
    order: int,
) -> None:
    """Recursively create ``name`` and every entry of ``children`` beneath it."""

    node = OrgRoleTemplateNode(
        template_id=template_id,
        parent_node_id=parent_node_id,
        name=name,
        default_methodology=Methodology.planner,
        order=order,
    )
    session.add(node)
    await session.flush()  # assign node.id for its own children's FK

    for child_order, (child_name, grandchildren) in enumerate(children):
        await _create_node(
            session, template_id, node.id, child_name, grandchildren, order=child_order
        )


async def ensure_system_templates(session: AsyncSession) -> None:
    """Create each of the 5 system templates (and their tree) when missing.

    Idempotent per template: if a system template with the SAME ``name``
    already exists, this function does nothing for it — its tree is assumed
    already seeded (created atomically the first time), so it is never
    re-checked node-by-node.
    """

    for template_name, umbrella_name, children in _TEMPLATE_CATALOG:
        existing = await session.execute(
            select(OrgRoleTemplate).where(
                OrgRoleTemplate.organization_id.is_(None),
                OrgRoleTemplate.name == template_name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        template = OrgRoleTemplate(
            organization_id=None, name=template_name, is_system=True
        )
        session.add(template)
        await session.flush()  # assign template.id for the umbrella node's FK

        await _create_node(
            session, template.id, None, umbrella_name, children, order=0
        )
