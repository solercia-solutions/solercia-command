"""Request/response schemas of the GitLab integration module."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# `group/subgroup/repo`: at least one slash, GitLab path characters only, no
# dot-only segments (never `..`), so a path can never escape `/projects/:id`.
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MAX_REPOSITORIES_PER_PROJECT = 20


def _valid_repository_path(value: str) -> bool:
    segments = value.split("/")
    return (
        len(value) <= 255
        and len(segments) >= 2
        and all(_PATH_SEGMENT.match(segment) for segment in segments)
    )


class GitlabRepositoryRead(BaseModel):
    path_with_namespace: str
    name: str
    web_url: str | None = None


class ProjectRepositoriesUpdate(BaseModel):
    """Full replacement of a project's linked repositories (empty clears)."""

    repositories: list[str] = Field(default_factory=list, max_length=MAX_REPOSITORIES_PER_PROJECT)

    @field_validator("repositories")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            path = raw.strip().strip("/")
            if not _valid_repository_path(path):
                raise ValueError(
                    "Cada repositorio debe tener la forma grupo/repositorio de GitLab."
                )
            if path not in cleaned:
                cleaned.append(path)
        return cleaned


class ProjectRepositoriesRead(BaseModel):
    project_id: uuid.UUID
    repositories: list[str]


class GitlabMergeRequestRead(BaseModel):
    repository: str
    iid: int
    title: str
    state: str
    author: str | None = None
    source_branch: str | None = None
    updated_at: datetime | None = None
    web_url: str | None = None


class GitlabCommitRead(BaseModel):
    repository: str
    short_id: str
    title: str
    author_name: str | None = None
    authored_at: datetime | None = None
    web_url: str | None = None


class TaskDevelopmentActivityRead(BaseModel):
    """Live, read-only development activity of a task.

    ``connected=False`` means the organization has no GitLab credentials;
    an empty ``repositories`` list means the task's project has no linked
    repository. Both are legitimate empty states, not errors.
    """

    connected: bool
    task_key: str | None
    repositories: list[str]
    merge_requests: list[GitlabMergeRequestRead]
    commits: list[GitlabCommitRead]
