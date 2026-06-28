"""Business logic for projects.

The service validates input through the methodology Strategy, attaches the
computed ``methodology_info`` payload and delegates persistence to the
repository.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.factory import get_strategy
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate
from app.shared.enums import ProjectStatus
from app.shared.exceptions import AppException


class ProjectService:
    """Orchestrates project use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ProjectRepository(db)

    async def list_projects(self, organization_id: uuid.UUID) -> Sequence[Project]:
        """Return the organization's projects with methodology info attached."""

        projects = await self.repo.list_by_org(organization_id)
        for project in projects:
            self._attach_methodology_info(project)
        return projects

    async def create_project(
        self, organization_id: uuid.UUID, data: ProjectCreate
    ) -> Project:
        """Validate the methodology and persist a new project."""

        # Resolving the strategy validates the methodology (raises on invalid).
        strategy = get_strategy(data.methodology)

        project = Project(
            name=data.name,
            description=data.description,
            methodology=data.methodology,
            status=ProjectStatus.active,
            organization_id=organization_id,
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

    @staticmethod
    def _attach_methodology_info(project: Project) -> None:
        """Attach the transient ``methodology_info`` payload for serialization."""

        project.methodology_info = get_strategy(project.methodology).to_info()
