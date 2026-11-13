"""Use cases of the GitLab integration: list repositories, link them to a
Command project (S2) and read a task's development activity live (S3).

Credentials are the ones the connectors flow already validated and stored
encrypted in ``ConnectionCredentials``; they are decrypted only in memory,
handed to the adapter and never logged or returned. Every GitLab call is a
``GET``: nothing is written back to GitLab.
"""

import dataclasses
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.gitlab.adapter import GitlabAdapter
from app.integrations.registry import get_adapter
from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.gitlab_integration.repository import (
    GitlabMappingRepository,
    read_project_mapping,
)
from app.modules.gitlab_integration.schemas import (
    GitlabCommitRead,
    GitlabMergeRequestRead,
    GitlabRepositoryRead,
    ProjectRepositoriesRead,
    TaskDevelopmentActivityRead,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException

PROVIDER = "gitlab"


@dataclasses.dataclass(frozen=True)
class _Connection:
    connector: Connector
    raw: dict[str, Any]


class GitlabIntegrationService:
    """Org-scoped GitLab use cases; owns the transaction of the mapping write."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connectors = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)
        self.mapping = GitlabMappingRepository(db)
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)

    # -- S2 -----------------------------------------------------------------

    async def list_repositories(self, organization_id: uuid.UUID) -> list[GitlabRepositoryRead]:
        connection = await self._require_connection(organization_id)
        repositories = await self._adapter().list_repositories(connection.raw)
        return [GitlabRepositoryRead(**dataclasses.asdict(repo)) for repo in repositories]

    async def get_project_repositories(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> ProjectRepositoriesRead:
        await self._require_project(organization_id, project_id)
        connector = await self.connectors.get_by_provider(organization_id, PROVIDER)
        repositories = read_project_mapping(connector).get(str(project_id), []) if connector else []
        return ProjectRepositoriesRead(project_id=project_id, repositories=repositories)

    async def set_project_repositories(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        repositories: list[str],
        *,
        actor_id: uuid.UUID | None,
    ) -> ProjectRepositoriesRead:
        """Replace the project's linked repositories. Each path is checked
        live against GitLab first, so only repositories the token can read
        are stored; nothing is written when any of them fails."""

        await self._require_project(organization_id, project_id)
        connection = await self._require_connection(organization_id)

        adapter = self._adapter()
        canonical: list[str] = []
        for path in repositories:
            repo = await adapter.get_repository(connection.raw, path)
            if repo.path_with_namespace not in canonical:
                canonical.append(repo.path_with_namespace)

        try:
            await self.mapping.set_project_repositories(
                connection.connector, project_id, canonical, actor_id=actor_id
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return ProjectRepositoriesRead(project_id=project_id, repositories=canonical)

    # -- S3 -----------------------------------------------------------------

    async def get_task_activity(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskDevelopmentActivityRead:
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        project = await self.projects.get(organization_id, task.project_id)
        task_key = (
            f"{project.code}-{task.task_number}"
            if project is not None and project.code and task.task_number is not None
            else None
        )

        connection = await self._connection(organization_id)
        if connection is None:
            return TaskDevelopmentActivityRead(
                connected=False,
                task_key=task_key,
                repositories=[],
                merge_requests=[],
                commits=[],
            )

        repositories = read_project_mapping(connection.connector).get(str(task.project_id), [])
        if not repositories or task_key is None:
            return TaskDevelopmentActivityRead(
                connected=True,
                task_key=task_key,
                repositories=repositories,
                merge_requests=[],
                commits=[],
            )

        merge_requests, commits = await self._adapter().find_activity(
            connection.raw, repositories, task_key
        )
        return TaskDevelopmentActivityRead(
            connected=True,
            task_key=task_key,
            repositories=repositories,
            merge_requests=[
                GitlabMergeRequestRead(**dataclasses.asdict(mr)) for mr in merge_requests
            ],
            commits=[GitlabCommitRead(**dataclasses.asdict(c)) for c in commits],
        )

    # -- helpers ------------------------------------------------------------

    async def _connection(self, organization_id: uuid.UUID) -> _Connection | None:
        connector = await self.connectors.get_by_provider(organization_id, PROVIDER)
        if connector is None:
            return None
        accounts = await self.accounts.list_accounts(connector.id, organization_id)
        if not accounts:
            return None
        credentials = await self.accounts.get_credentials(accounts[0].id)
        if credentials is None:
            return None
        raw = json.loads(crypto.decrypt(credentials.access_token_enc))
        return _Connection(connector=connector, raw=raw)

    async def _require_connection(self, organization_id: uuid.UUID) -> _Connection:
        connection = await self._connection(organization_id)
        if connection is None:
            raise AppException(
                "La organización no tiene GitLab conectado. Registra un token en Conexiones.",
                code="gitlab_not_connected",
                status_code=422,
            )
        return connection

    async def _require_project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> None:
        if await self.projects.get(organization_id, project_id) is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )

    @staticmethod
    def _adapter() -> GitlabAdapter:
        adapter = get_adapter(PROVIDER)
        if not isinstance(adapter, GitlabAdapter):
            raise AppException(
                "El adaptador de GitLab no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )
        return adapter
