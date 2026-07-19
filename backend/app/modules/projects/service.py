"""Business logic for projects.

The service validates input through the methodology Strategy, attaches the
computed ``methodology_info`` payload and delegates persistence to the
repository.
"""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.methodology.board_aware import build_board_aware_strategy, resolve_board_strategy
from app.methodology.factory import get_strategy
from app.modules.boards.repository import BoardRepository
from app.modules.boards.service import BoardService
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate
from app.shared.enums import ProjectStatus
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
    ) -> tuple[Sequence[Project], int]:
        """Return ``(projects, total)`` with methodology info attached.

        Columns for every project's board are batch-preloaded in ONE call
        (two queries total, never N+1) instead of resolving each project's
        strategy individually — see
        ``BoardRepository.list_boards_with_columns_for_projects`` and
        design.md C1.
        """

        projects, total = await self.repo.list_by_org(organization_id, pagination)
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
        return projects, total

    async def create_project(
        self,
        organization_id: uuid.UUID,
        data: ProjectCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Project:
        """Validate the methodology, persist a new project and seed its board.

        When ``data.code`` is omitted the service auto-generates one from the
        project name. A numeric suffix is appended (e.g. "PW2") when the
        derived code is already taken within the organization.

        The board (and its columns, from ``strategy.default_columns()``) is
        seeded in the SAME transaction as the project: the project is flushed
        first to obtain its id, the board is added against that id, and both
        are committed together — see boards.md, "Siembra del board al crear
        el proyecto".

        When ``data.parent_project_id`` is given, :meth:`validate_parent` runs
        BEFORE anything is added to the session (change 21-project-hierarchy,
        R10): a rejected parent leaves NO project persisted — todo-o-nada.
        """

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

        project = Project(
            name=data.name,
            description=data.description,
            methodology=data.methodology,
            status=ProjectStatus.active,
            organization_id=organization_id,
            code=code,
            task_counter=0,
            parent_project_id=data.parent_project_id,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.repo.db.add(project)
        await self.repo.db.flush()  # assign project.id for the board FK

        await BoardService(self.repo.db).seed_board(project.id, strategy)

        project = await self.repo.save(project)
        project.methodology_info = strategy.to_info()
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
        """

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
