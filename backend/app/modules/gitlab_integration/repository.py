"""Persistence of the GitLab project -> repositories mapping.

The mapping lives in the ``gitlab`` connector's ``settings`` JSONB (no own
table, no migration): ``settings["gitlab"]["project_repositories"]`` maps a
Command project id (str) to a list of ``path_with_namespace``. This
repository never commits — :class:`GitlabIntegrationService` owns the
transaction.
"""

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import Connector

_NAMESPACE = "gitlab"
_MAPPING_KEY = "project_repositories"


def read_project_mapping(connector: Connector) -> dict[str, list[str]]:
    """Return the whole mapping stored on ``connector`` (empty when absent)."""

    namespace = (connector.settings or {}).get(_NAMESPACE) or {}
    mapping = namespace.get(_MAPPING_KEY) or {}
    if not isinstance(mapping, Mapping):
        return {}
    return {
        str(key): [str(path) for path in value]
        for key, value in mapping.items()
        if isinstance(value, list)
    }


class GitlabMappingRepository:
    """Writes the mapping into the connector row (flush only, no commit)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def set_project_repositories(
        self,
        connector: Connector,
        project_id: uuid.UUID,
        repositories: list[str],
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        mapping = read_project_mapping(connector)
        if repositories:
            mapping[str(project_id)] = list(repositories)
        else:
            mapping.pop(str(project_id), None)

        settings = dict(connector.settings or {})
        namespace = dict(settings.get(_NAMESPACE) or {})
        namespace[_MAPPING_KEY] = mapping
        settings[_NAMESPACE] = namespace
        # Reassign a NEW dict: SQLAlchemy does not track in-place JSONB edits.
        connector.settings = settings
        connector.updated_by = actor_id
        await self.db.flush()
