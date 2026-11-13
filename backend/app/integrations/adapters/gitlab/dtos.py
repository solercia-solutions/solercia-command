"""Provider-normalized DTOs of the GitLab adapter (frozen snapshots)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GitlabRepository:
    """A GitLab project the token can read."""

    path_with_namespace: str
    name: str
    web_url: str | None


@dataclass(frozen=True)
class GitlabMergeRequest:
    """A merge request that mentions a task key in its title."""

    repository: str
    iid: int
    title: str
    state: str
    author: str | None
    source_branch: str | None
    updated_at: datetime | None
    web_url: str | None


@dataclass(frozen=True)
class GitlabCommit:
    """A commit whose message mentions a task key."""

    repository: str
    short_id: str
    title: str
    author_name: str | None
    authored_at: datetime | None
    web_url: str | None
