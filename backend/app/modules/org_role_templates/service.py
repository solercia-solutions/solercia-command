"""Business logic for org role templates: idempotent instantiation of the
project tree with a responsible person (change 23-org-role-templates).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.org_role_templates.models import (
    OrgRoleTemplate,
    OrgRoleTemplateInstantiation,
    OrgRoleTemplateNode,
)
from app.modules.org_role_templates.repository import OrgRoleTemplateRepository
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.shared.enums import ProjectKind
from app.shared.exceptions import AppException


def order_parent_first(
    nodes: Sequence[OrgRoleTemplateNode],
) -> list[OrgRoleTemplateNode]:
    """Return ``nodes`` ordered parent-before-child (BFS from the root(s)),
    siblings tie-broken by ``order`` — pure function, no DB. This is the
    traversal order instantiation creates projects in, so a child's
    ``parent_project_id`` always resolves to an already-created parent
    (design.md, "recorre el árbol y crea cada proyecto").
    """

    by_parent: dict[uuid.UUID | None, list[OrgRoleTemplateNode]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_node_id, []).append(node)
    for siblings in by_parent.values():
        siblings.sort(key=lambda n: n.order)

    ordered: list[OrgRoleTemplateNode] = []
    queue: list[OrgRoleTemplateNode] = list(by_parent.get(None, []))
    while queue:
        node = queue.pop(0)
        ordered.append(node)
        queue.extend(by_parent.get(node.id, []))
    return ordered


def build_project_create(
    node: OrgRoleTemplateNode,
    *,
    lead_user_id: uuid.UUID,
    parent_project_id: uuid.UUID | None,
    project_kind: ProjectKind,
) -> ProjectCreate:
    """Map one template node to the ``ProjectCreate`` payload instantiation
    feeds into ``ProjectService._create_project_unit`` — pure function, no
    DB. ``code`` is omitted on purpose: ``_create_project_unit`` derives a
    unique one from ``node.name``, same as the plain ``POST /projects`` flow.
    ``project_kind`` (change 27-plantillas-idempotentes) is decided by the
    caller via :func:`project_kind_for_node` — container node -> ``area``,
    leaf -> ``proyecto``.
    """

    return ProjectCreate(
        name=node.name,
        methodology=node.default_methodology,
        parent_project_id=parent_project_id,
        lead_user_id=lead_user_id,
        project_kind=project_kind,
    )


def container_node_ids(
    nodes: Sequence[OrgRoleTemplateNode],
) -> set[uuid.UUID]:
    """Return every node id that is some OTHER node's ``parent_node_id`` —
    i.e. every CONTAINER node of the template (design.md Decisión 2,
    "nodo con hijos -> area"). Pure function, no DB."""

    return {node.parent_node_id for node in nodes if node.parent_node_id is not None}


def project_kind_for_node(
    node: OrgRoleTemplateNode, containers: set[uuid.UUID]
) -> ProjectKind:
    """``area`` when ``node`` has at least one child in the template,
    ``proyecto`` otherwise (a leaf, or the single node of a one-node
    template) — design.md Decisión 2. Pure function, no DB."""

    return ProjectKind.area if node.id in containers else ProjectKind.proyecto


class OrgRoleTemplateService:
    """Orchestrates org-role-template instantiation for a single organization."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrgRoleTemplateRepository(db)

    async def list_templates(
        self, organization_id: uuid.UUID
    ) -> Sequence[OrgRoleTemplate]:
        """Return every template visible to ``organization_id``."""

        return await self.repo.list_visible(organization_id)

    async def get_template_tree(
        self, organization_id: uuid.UUID, template_id: uuid.UUID
    ) -> tuple[OrgRoleTemplate, dict]:
        """Return ``(template, tree)`` — ``tree`` is the nested umbrella node
        with its descendants, shaped like ``OrgRoleTemplateNodeRead``."""

        template = await self.repo.get_visible(organization_id, template_id)
        if template is None:
            raise AppException(
                "La plantilla no existe o no está disponible para tu organización.",
                code="template_not_found",
                status_code=404,
            )
        nodes = await self.repo.nodes_for_template(template_id)
        return template, self._nest_nodes(nodes)

    @staticmethod
    def _nest_nodes(nodes: Sequence[OrgRoleTemplateNode]) -> dict:
        """Build a nested ``OrgRoleTemplateNodeRead``-shaped dict from a flat
        node list — same nesting pattern as ``ProjectService._nest_tree``."""

        children_by_parent: dict[uuid.UUID | None, list[OrgRoleTemplateNode]] = {}
        for node in nodes:
            children_by_parent.setdefault(node.parent_node_id, []).append(node)
        for siblings in children_by_parent.values():
            siblings.sort(key=lambda n: n.order)

        def _build(node: OrgRoleTemplateNode) -> dict:
            return {
                "id": node.id,
                "name": node.name,
                "default_methodology": node.default_methodology,
                "children": [
                    _build(child) for child in children_by_parent.get(node.id, [])
                ],
            }

        roots = children_by_parent.get(None, [])
        return _build(roots[0]) if roots else {}

    async def instantiate(
        self,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
        lead_user_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> list[Project]:
        """Create (or reconcile) the project tree of ``template_id`` with
        ``lead_user_id`` as the responsible of every generated project.

        Guard order (design.md Data Flow): template visible to the caller's
        org -> ``lead_user_id`` is an active member of that SAME org ->
        THEN (and only then) the node tree/ledger are read and any project
        touched. A rejection at either guard leaves the tree untouched.

        Idempotent by reconciliation against the ``org_role_template_
        instantiations`` ledger, keyed by ``(organization_id, template_id,
        node_id)`` — WITHOUT ``lead_user_id`` (change 27-plantillas-
        idempotentes, design.md Decision 1): a node whose ledger row still
        points to an ``is_active`` project is REUSED (one query via
        ``ProjectRepository.get``, which already filters ``is_active``) and
        its responsible is RECONCILED to ``lead_user_id`` (on both the
        ``Project`` and the ledger row) whenever it differs from the caller's
        — never a duplicate tree. A missing or soft-deleted node is
        (re)created via ``ProjectService._create_project_unit`` (no commit)
        and the ledger row is inserted or UPDATED — NEVER re-inserted,
        preserving ``UNIQUE(organization_id, template_id, node_id)``. ONE
        commit closes the whole operation (design.md Decision 3): a failure
        partway through leaves NO project persisted.

        Two concurrent calls for the SAME ``(organization_id, template_id)``
        build the SAME tree; the loser's flush/commit collides
        (``uq_project_code_per_org`` and/or ``uq_org_role_template_
        instantiation``) and raises ``IntegrityError`` — instead of a bare
        500, the loser rolls back and retries ONCE against the now-committed
        ledger, reusing every node the winner already created (judgment-day
        fix, "doble clic da 500").

        Irreconcilable conflict (change 27-plantillas-idempotentes,
        post-verify correction, ``AppException`` code ``template_tree_
        conflict``, HTTP 409): a CONTAINER node's ledger row points to a
        project that no longer exists or was soft-deleted WHILE at least one
        of its children is still an active, reused project — recreating the
        container would orphan those children's ``parent_project_id`` from
        a dead project. Detected read-only, before any write, by
        ``_raise_if_irreconcilable_conflict``; the whole call is rejected,
        the tree stays untouched. A soft-deleted LEAF is not a conflict — it
        is simply recreated in place, same as any other missing node.
        """

        template = await self.repo.get_visible(organization_id, template_id)
        if template is None:
            raise AppException(
                "La plantilla no existe o no está disponible para tu organización.",
                code="template_not_found",
                status_code=404,
            )

        if not await self.repo.is_org_member(organization_id, lead_user_id):
            raise AppException(
                "El responsable indicado no es miembro activo de tu organización.",
                code="lead_not_member",
                status_code=422,
            )

        nodes = order_parent_first(await self.repo.nodes_for_template(template_id))
        if not nodes:
            return []

        try:
            return await self._reconcile_and_commit(
                organization_id, template_id, lead_user_id, nodes, actor_id=actor_id
            )
        except IntegrityError:
            await self.db.rollback()
            # Re-read ``nodes``: rollback expires every attached ORM
            # instance, and touching an expired attribute outside an
            # awaited context raises ``MissingGreenlet``.
            nodes = order_parent_first(await self.repo.nodes_for_template(template_id))
            return await self._reconcile_and_commit(
                organization_id, template_id, lead_user_id, nodes, actor_id=actor_id
            )

    async def _reconcile_and_commit(
        self,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
        lead_user_id: uuid.UUID,
        nodes: Sequence[OrgRoleTemplateNode],
        *,
        actor_id: uuid.UUID | None,
    ) -> list[Project]:
        """Read the ledger, reuse/create each node's project and commit once.

        Extracted so :meth:`instantiate` can retry it with a FRESH ledger
        read after a concurrency collision.
        """

        ledger = await self.repo.ledger_for(organization_id, template_id)
        containers = container_node_ids(nodes)

        project_service = ProjectService(self.db)

        # One read-only lookup per existing ledger row, done UP FRONT (before
        # any write): shared by the conflict check right below and by the
        # reuse-vs-recreate decision in the main loop further down — never
        # two queries for the same node.
        active_by_node: dict[uuid.UUID, Project | None] = {}
        for node in nodes:
            ledger_row = ledger.get(node.id)
            if ledger_row is not None:
                active_by_node[node.id] = await project_service.repo.get(
                    organization_id, ledger_row.project_id
                )

        self._raise_if_irreconcilable_conflict(nodes, containers, ledger, active_by_node)

        projects_by_node: dict[uuid.UUID, Project] = {}
        result: list[Project] = []

        for node in nodes:
            ledger_row = ledger.get(node.id)
            reused = active_by_node.get(node.id)

            if reused is not None:
                # Reconcile the responsible instead of duplicating the tree
                # (design.md Decision 1): the node is the SAME node
                # regardless of who instantiates it with a different lead.
                if reused.lead_user_id != lead_user_id:
                    reused.lead_user_id = lead_user_id
                    ledger_row.lead_user_id = lead_user_id
                projects_by_node[node.id] = reused
                result.append(reused)
                continue

            parent_project_id = (
                projects_by_node[node.parent_node_id].id
                if node.parent_node_id is not None
                else None
            )
            data = build_project_create(
                node,
                lead_user_id=lead_user_id,
                parent_project_id=parent_project_id,
                project_kind=project_kind_for_node(node, containers),
            )
            project = await project_service._create_project_unit(  # noqa: SLF001
                organization_id, data, actor_id=actor_id
            )
            projects_by_node[node.id] = project
            result.append(project)

            if ledger_row is not None:
                # Node was missing/soft-deleted: repoint the EXISTING ledger
                # row to the freshly created project — never a new row.
                ledger_row.project_id = project.id
            else:
                self.db.add(
                    OrgRoleTemplateInstantiation(
                        organization_id=organization_id,
                        template_id=template_id,
                        node_id=node.id,
                        lead_user_id=lead_user_id,
                        project_id=project.id,
                    )
                )

        await self.db.commit()
        for project in result:
            await self.db.refresh(project)
        return result

    @staticmethod
    def _raise_if_irreconcilable_conflict(
        nodes: Sequence[OrgRoleTemplateNode],
        containers: set[uuid.UUID],
        ledger: dict[uuid.UUID, OrgRoleTemplateInstantiation],
        active_by_node: dict[uuid.UUID, Project | None],
    ) -> None:
        """Reject the WHOLE instantiation, read-only, before a single write
        happens, when the ledger's history is incompatible with the tree it
        is about to (re)build (spec.md, Requirement MODIFIED "Idempotencia
        por reconciliación": *"Conflicto irreconciliable ... DEBE rechazarse
        con mensaje claro, sin modificar el árbol existente"*).

        The concrete, reachable case (change 27-plantillas-idempotentes,
        post-verify correction): a CONTAINER node (``area``, i.e. it has at
        least one child in the template) whose ledger row points to a
        project that no longer exists or was soft-deleted, while at least
        one of its children is STILL an active, reused project. Silently
        recreating the container would hand it a brand-new id while its
        still-active children keep ``parent_project_id`` pointing at the
        dead one — an inconsistent tree no later step repairs.

        A soft-deleted LEAF (no children, or a childless container) is NOT
        a conflict: it is simply missing and gets recreated in place by the
        main loop below, exactly like every other reconciled node — see
        ``test_reinstantiate_after_soft_deleting_piga_recreates_only_that_node``.
        """

        children_by_parent: dict[uuid.UUID, list[OrgRoleTemplateNode]] = {}
        for node in nodes:
            if node.parent_node_id is not None:
                children_by_parent.setdefault(node.parent_node_id, []).append(node)

        for node in nodes:
            if node.id not in containers:
                continue
            if ledger.get(node.id) is None:
                continue  # never instantiated before — nothing to conflict with
            if active_by_node.get(node.id) is not None:
                continue  # container itself still alive — no conflict here
            has_active_child = any(
                active_by_node.get(child.id) is not None
                for child in children_by_parent.get(node.id, [])
            )
            if has_active_child:
                raise AppException(
                    "No es posible re-aplicar la plantilla: el proyecto "
                    f"'{node.name}' creado por una aplicación anterior fue "
                    "eliminado. Restaura ese proyecto o contacta al "
                    "administrador.",
                    code="template_tree_conflict",
                    status_code=409,
                )
