"""Business logic for projects.

The service validates input through the methodology Strategy, attaches the
computed ``methodology_info`` payload and delegates persistence to the
repository.
"""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.factory import get_strategy
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
        """Return ``(projects, total)`` with methodology info attached."""

        projects, total = await self.repo.list_by_org(organization_id, pagination)
        for project in projects:
            self._attach_methodology_info(project)
        return projects, total

    async def create_project(
        self,
        organization_id: uuid.UUID,
        data: ProjectCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Project:
        """Validate the methodology and persist a new project.

        When ``data.code`` is omitted the service auto-generates one from the
        project name. A numeric suffix is appended (e.g. "PW2") when the
        derived code is already taken within the organization.
        """

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
            created_by=actor_id,
            updated_by=actor_id,
        )
        project = await self.repo.create(project)
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
        self._attach_methodology_info(project)
        return project

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

    @staticmethod
    def _attach_methodology_info(project: Project) -> None:
        """Attach the transient ``methodology_info`` payload for serialization."""

        project.methodology_info = get_strategy(project.methodology).to_info()
