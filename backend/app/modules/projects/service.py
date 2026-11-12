"""Business logic for projects.

The service validates input through the methodology Strategy, attaches the
computed ``methodology_info`` payload and delegates persistence to the
repository.
"""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.methodology.board_aware import build_board_aware_strategy, resolve_board_strategy
from app.methodology.factory import get_strategy
from app.modules.boards.repository import BoardRepository
from app.modules.boards.service import BoardService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate
from app.modules.projects.system_project import (
    guard_system_project_update,
    reject_reserved_project_code,
)
from app.modules.tasks.service import TASK_YEAR_TIMEZONE, task_year_bounds
from app.shared.enums import ProjectKind, ProjectStatus
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

_CODE_STRIP_RE = re.compile(r"[^A-Z0-9]")


def _derive_code(name: str) -> str:
    """Generate a 2-10 char uppercase alphanumeric code from a project name.

    Multi-word names produce an initials-based code (e.g. "Plataforma Web" →
    "PW"). Single-word names are truncated to 6 chars. The result is always
    2-10 uppercase alphanumeric characters.
    """

    clean = re.sub(r"[^a-zA-Z0-9 ]", "", name).upper()
    words = clean.split()
    if not words:
        return "PRJ"
    code = "".join(w[0] for w in words if w) if len(words) >= 2 else words[0][:6]
    # Ensure at least 2 chars; if initials is just one letter, use first 3 of word.
    if len(code) < 2:
        code = (words[0] + code)[:4]
    return code[:10]


class ProjectService:
    """Orchestrates project use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ProjectRepository(db)

    async def list_projects(
        self,
        organization_id: uuid.UUID,
        pagination: PaginationParams | None = None,
        project_kind: ProjectKind | None = None,
        *,
        year: int | None = None,
    ) -> tuple[Sequence[Project], int]:
        """Return ``(projects, total)`` with methodology info and task counts.

        ``year`` (ODD S05) keeps only projects with active tasks created that
        calendar year in ``America/Bogota`` (same criterion as the task
        ``year`` filter). ``task_count``/``open_task_count`` are computed for
        that year, or for every year when ``year`` is ``None``, in one
        aggregate query for the whole page.

        Columns for every project's board are batch-preloaded in ONE call
        (two queries total, never N+1) instead of resolving each project's
        strategy individually — see
        ``BoardRepository.list_boards_with_columns_for_projects`` and
        design.md C1. ``project_kind`` (change 27-plantillas-idempotentes)
        is forwarded to the repository unchanged — ``None`` keeps every kind.
        """

        created_from, created_before = task_year_bounds(year)
        projects, total = await self.repo.list_by_org(
            organization_id,
            pagination,
            project_kind,
            tasks_created_from=created_from,
            tasks_created_before=created_before,
        )
        counts = await self.repo.task_counts(
            organization_id,
            [project.id for project in projects],
            created_from=created_from,
            created_before=created_before,
        )
        columns_by_project = await BoardRepository(
            self.repo.db
        ).list_boards_with_columns_for_projects([project.id for project in projects])
        for project in projects:
            status_keys = [
                column.status_key for column in columns_by_project.get(project.id, [])
            ]
            project.methodology_info = build_board_aware_strategy(
                project, status_keys
            ).to_info()
            project.task_count, project.open_task_count = counts.get(project.id, (0, 0))
        return projects, total

    async def list_task_years(self, organization_id: uuid.UUID) -> list[int]:
        """Return the years (Bogotá calendar) with active tasks in the
        organization's projects, newest first."""

        return await self.repo.list_task_created_years(
            organization_id, timezone=TASK_YEAR_TIMEZONE
        )

    async def create_project(
        self,
        organization_id: uuid.UUID,
        data: ProjectCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Project:
        """Validate the methodology, persist a new project and seed its board.

        Public contract UNCHANGED: this is still ONE call that both creates
        AND commits (``_create_project_unit()`` + :meth:`ProjectRepository.
        save`) — the extraction below (change 23-org-role-templates, design.md
        Decision 3) only splits WHERE the commit happens, never removes it
        from this path.

        ``data.lead_user_id`` is ALWAYS forced to ``None`` here: the plain
        ``POST /projects`` flow never validates that the submitted id is an
        active member of the caller's organization, so trusting it verbatim
        would let a member pin an arbitrary (even cross-org) user as lead.
        Only template instantiation may set ``lead_user_id`` — it validates
        membership first (``OrgRoleTemplateService.instantiate``) and calls
        :meth:`_create_project_unit` directly, bypassing this method.

        ``data.project_kind`` is ALWAYS forced to ``ProjectKind.proyecto``
        here (change 27-plantillas-idempotentes, same defensive pattern as
        ``lead_user_id`` above): only org-role-template instantiation may
        produce an ``area`` (a container node), so no client of the plain
        ``POST /projects`` flow can ever create one — specs/projects/spec.md
        (delta), "Creación directa con POST /projects es siempre proyecto".
        """

        data = data.model_copy(
            update={"lead_user_id": None, "project_kind": ProjectKind.proyecto}
        )

        project = await self._create_project_unit(
            organization_id, data, actor_id=actor_id
        )
        project = await self.repo.save(project)
        project.methodology_info = get_strategy(data.methodology).to_info()
        return project

    async def _create_project_unit(
        self,
        organization_id: uuid.UUID,
        data: ProjectCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Project:
        """Validate, persist (add+flush) and seed the board of a project — WITHOUT commit.

        Extracted from :meth:`create_project` (change 23-org-role-templates,
        design.md Decision 3) so a multi-project transaction — the org-role-
        template instantiation service, which must create an entire tree
        todo-o-nada — can call this once per node and commit ONCE at the end.
        ``create_project`` itself calls this then immediately
        :meth:`ProjectRepository.save` (commit), so its own contract stays a
        single atomic call — see boards.md, "Siembra del board al crear el
        proyecto".

        When ``data.code`` is omitted the service auto-generates one from the
        project name. A numeric suffix is appended (e.g. "PW2") when the
        derived code is already taken within the organization.

        When ``data.parent_project_id`` is given, :meth:`validate_parent` runs
        BEFORE anything is added to the session (change 21-project-hierarchy,
        R10): a rejected parent leaves NO project persisted — todo-o-nada.

        ``data.lead_user_id`` (change 23-org-role-templates) is fixed onto
        the project verbatim; ``None`` for the plain ``POST /projects`` flow
        keeps the compatibility scenario (specs/projects/spec.md delta).

        ``data.project_kind`` (change 27-plantillas-idempotentes) is fixed
        onto the project verbatim, defaulting to ``ProjectKind.proyecto``
        when omitted — only org-role-template instantiation passes an
        explicit ``area``/``proyecto`` per node; ``create_project`` already
        forces ``proyecto`` before reaching here.
        """

        reject_reserved_project_code(data.code)
        if data.parent_project_id is not None:
            await self.validate_parent(organization_id, data.parent_project_id)

        # Resolving the strategy validates the methodology (raises on invalid).
        strategy = get_strategy(data.methodology)

        # Resolve code: use explicit value or derive from name.
        if data.code:
            code = data.code.upper()
            if await self.repo.code_exists(organization_id, code):
                raise AppException(
                    f"El código '{code}' ya está en uso en tu organización.",
                    code="project_code_taken",
                    status_code=409,
                )
        else:
            code = await self._unique_code_for_org(
                organization_id, _derive_code(data.name)
            )

        reject_reserved_project_code(code)
        project = Project(
            name=data.name,
            description=data.description,
            methodology=data.methodology,
            status=ProjectStatus.active,
            organization_id=organization_id,
            code=code,
            task_counter=0,
            parent_project_id=data.parent_project_id,
            lead_user_id=data.lead_user_id,
            project_kind=data.project_kind or ProjectKind.proyecto,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.repo.db.add(project)
        await self.repo.db.flush()  # assign project.id for the board FK

        await BoardService(self.repo.db).seed_board(project.id, strategy)

        return project

    async def get_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        """Return a single project or raise a 404 ``AppException``."""

        project = await self.repo.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )
        await self._attach_methodology_info(project)
        return project

    async def update_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: ProjectUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Project:
        """Apply a partial update to a project's editable fields.

        Only fields present in the payload are applied
        (``model_dump(exclude_unset=True)``). ``methodology`` is NEVER
        editable — the seeded board and the task statuses derive from the
        Strategy — so its mere presence raises 422
        ``methodology_not_editable``. A changed ``code`` re-validates
        uniqueness within the organization EXCLUDING the project itself
        (``code_exists(exclude_id=...)``) and raises the same 409
        ``project_code_taken`` the create flow uses. Raises the usual 404
        ``project_not_found`` for missing/cross-org/soft-deleted projects.
        """

        project = await self.get_project(organization_id, project_id)

        changes = data.model_dump(exclude_unset=True)
        guard_system_project_update(project.is_system, changes)
        if "code" in changes:
            reject_reserved_project_code(changes["code"])

        if "methodology" in changes:
            raise AppException(
                "La metodología del proyecto no se puede editar: el board "
                "sembrado y los estados de las tareas dependen de ella.",
                code="methodology_not_editable",
                status_code=422,
            )

        if "code" in changes:
            code = changes["code"]
            if await self.repo.code_exists(
                organization_id, code, exclude_id=project.id
            ):
                raise AppException(
                    f"El código '{code}' ya está en uso en tu organización.",
                    code="project_code_taken",
                    status_code=409,
                )
            project.code = code

        for field in ("name", "description"):
            if field in changes:
                setattr(project, field, changes[field])

        project.updated_by = actor_id
        try:
            project = await self.repo.save(project)
        except IntegrityError as exc:
            # Two concurrent updates can BOTH pass the advisory code_exists
            # check above; the loser's commit then collides with
            # ``uq_project_code_per_org``. Translate to the SAME 409 the
            # advisory path produces instead of a bare 500 (same pattern as
            # ``OrgRoleTemplateService.instantiate``). ``changes`` is a plain
            # dict — safe to read after the rollback expires the ORM row.
            code_label = changes.get("code")
            await self.repo.db.rollback()
            detail = (
                f"El código '{code_label}' ya está en uso en tu organización."
                if code_label
                else "El código del proyecto ya está en uso en tu organización."
            )
            raise AppException(
                detail,
                code="project_code_taken",
                status_code=409,
            ) from exc
        await self._attach_methodology_info(project)
        return project

    # -- hierarchy (change 21-project-hierarchy) -----------------------------

    async def validate_parent(
        self,
        organization_id: uuid.UUID,
        parent_project_id: uuid.UUID,
        *,
        child_id: uuid.UUID | None = None,
    ) -> None:
        """Validate assigning ``parent_project_id`` as the parent of ``child_id``.

        ``child_id`` is ``None`` when validating a NEW project (creation);
        otherwise it is the id of the EXISTING project being reparented.
        Orchestrates every hierarchy invariant in the order design.md
        Decision 3 fixes: self-parent -> tenant/active -> cycle -> max depth.
        Raises :class:`AppException` with a distinct ``code`` per cause
        (``self_parent`` 422, ``parent_not_found`` 404, ``project_cycle`` 409,
        ``max_depth_exceeded`` 422) — never a generic error, so callers (and
        the API contract, R9) can distinguish the rejection reason.
        """

        if child_id is not None and child_id == parent_project_id:
            raise AppException(
                "Un proyecto no puede ser su propio padre.",
                code="self_parent",
                status_code=422,
            )

        parent = await self.repo.get(organization_id, parent_project_id)
        if parent is None:
            raise AppException(
                "El proyecto padre no existe, no está activo o no pertenece "
                "a tu organización.",
                code="parent_not_found",
                status_code=404,
            )

        parent_ancestor_ids = await self.repo.ancestor_ids(
            organization_id, parent_project_id
        )

        if child_id is not None and child_id in parent_ancestor_ids:
            # child_id already appears among the PARENT's own ancestors:
            # the parent is inside the child's subtree, so assigning it
            # would make the child its own (transitive) descendant.
            raise AppException(
                "Esa asignación crearía un ciclo en la jerarquía de proyectos.",
                code="project_cycle",
                status_code=409,
            )

        parent_depth = len(parent_ancestor_ids) + 1
        subtree_height = (
            await self.repo.subtree_height(organization_id, child_id)
            if child_id is not None
            else 0
        )
        new_depth = parent_depth + 1 + subtree_height
        if new_depth > settings.PROJECT_HIERARCHY_MAX_DEPTH:
            raise AppException(
                "Esa asignación excede la profundidad máxima permitida "
                f"({settings.PROJECT_HIERARCHY_MAX_DEPTH} niveles).",
                code="max_depth_exceeded",
                status_code=422,
            )

    async def reparent(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        parent_project_id: uuid.UUID | None,
    ) -> Project:
        """Change ``project_id``'s parent, or unlink it to root (``None``).

        Applies :meth:`validate_parent` when ``parent_project_id`` is given —
        unlinking to root never needs hierarchy validation, it can only
        SHORTEN the chain.

        When reparenting under a real parent, BOTH endpoints of the move
        (``project_id`` and ``parent_project_id``, locked in ascending-id
        order to avoid a lock-ordering deadlock between two concurrent
        reparents) are row-locked via ``ProjectRepository.get_for_update``
        BEFORE validation runs. This serializes two concurrent reparents
        that would otherwise both pass validation against a stale snapshot
        and persist a 2-node cycle (A->parent=B, B->parent=A under READ
        COMMITTED): the second transaction blocks on the lock and then
        re-validates against the first transaction's already-committed
        ``parent_project_id``.
        """

        if parent_project_id is not None:
            first_id, second_id = sorted((project_id, parent_project_id))
            await self.repo.get_for_update(organization_id, first_id)
            if second_id != first_id:
                await self.repo.get_for_update(organization_id, second_id)

        project = await self.get_project(organization_id, project_id)
        if parent_project_id is not None:
            await self.validate_parent(
                organization_id, parent_project_id, child_id=project_id
            )
        project.parent_project_id = parent_project_id
        return await self.repo.save(project)

    async def get_tree(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict:
        """Return ``project_id`` and its active descendants nested as a tree."""

        project = await self.get_project(organization_id, project_id)
        subtree = await self.repo.fetch_subtree(organization_id, project.id)
        return self._nest_tree(project_id, subtree)

    async def get_progress(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict:
        """Return the consolidated (roll-up) progress of ``project_id``'s subtree."""

        project = await self.get_project(organization_id, project_id)
        subtree = await self.repo.fetch_subtree(organization_id, project.id)
        rows = await self.repo.rollup_progress(organization_id, project.id)
        counts_by_project = {row[0]: (row[1], row[2]) for row in rows}
        return self._nest_progress(project_id, subtree, counts_by_project)

    @staticmethod
    def _nest_tree(root_id: uuid.UUID, subtree: Sequence[Project]) -> dict:
        """Build a nested ``ProjectTreeNode``-shaped dict from a flat subtree."""

        by_id = {project.id: project for project in subtree}
        children_by_parent: dict[uuid.UUID | None, list[Project]] = {}
        for project in subtree:
            children_by_parent.setdefault(project.parent_project_id, []).append(
                project
            )

        def _build(project: Project) -> dict:
            return {
                "id": project.id,
                "name": project.name,
                "code": project.code,
                "methodology": project.methodology,
                "status": project.status,
                "children": [
                    _build(child)
                    for child in children_by_parent.get(project.id, [])
                ],
            }

        return _build(by_id[root_id])

    @staticmethod
    def _nest_progress(
        root_id: uuid.UUID,
        subtree: Sequence[Project],
        counts_by_project: dict[uuid.UUID, tuple[int, int]],
    ) -> dict:
        """Build a nested ``ProjectProgressNode``-shaped dict from a flat subtree.

        Each node's ``self`` is ITS OWN counts; ``rollup`` is the sum of
        ``self`` across the node and every descendant in its own subtree
        (design.md, "el valor consolidado del proyecto raíz solicitado DEBE
        sumar done y total de él mismo más todos los proyectos activos de su
        subárbol").
        """

        by_id = {project.id: project for project in subtree}
        children_by_parent: dict[uuid.UUID | None, list[Project]] = {}
        for project in subtree:
            children_by_parent.setdefault(project.parent_project_id, []).append(
                project
            )

        def _counts(done: int, total: int) -> dict:
            percent_done = round(done / total * 100) if total else 0
            return {"done": done, "total": total, "percent_done": percent_done}

        def _build(project: Project) -> dict:
            own_done, own_total = counts_by_project.get(project.id, (0, 0))
            children = [
                _build(child) for child in children_by_parent.get(project.id, [])
            ]
            rollup_done = own_done + sum(child["rollup"]["done"] for child in children)
            rollup_total = own_total + sum(
                child["rollup"]["total"] for child in children
            )
            return {
                "project_id": project.id,
                "name": project.name,
                "self": _counts(own_done, own_total),
                "rollup": _counts(rollup_done, rollup_total),
                "children": children,
            }

        return _build(by_id[root_id])

    # -- helpers -----------------------------------------------------------

    async def _unique_code_for_org(
        self, organization_id: uuid.UUID, base: str
    ) -> str:
        """Return ``base`` or ``base+N`` so the code is unique within the org."""

        candidate = base
        suffix = 2
        while await self.repo.code_exists(organization_id, candidate):
            candidate = f"{base[:8]}{suffix}"
            suffix += 1
        return candidate

    async def _attach_methodology_info(self, project: Project) -> None:
        """Attach the transient ``methodology_info`` payload for serialization.

        Uses ``resolve_board_strategy`` (design.md C1) so a project fetched
        individually after its board was reconfigured reflects the CURRENT
        columns, not the stale hardcoded base strategy.
        """

        strategy = await resolve_board_strategy(project, self.repo.db)
        project.methodology_info = strategy.to_info()
