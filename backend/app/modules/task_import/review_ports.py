"""Read-only tenant-scoped facts; implementations must return active records only.

These facts are not permissions or an import authorization. No production adapter
is provided by this domain unit.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProjectFacts:
    tenant_id: str
    project_id: str
    supported_statuses: frozenset[str]


class ReviewFacts(Protocol):
    def active_project(self, tenant_id: str, project_id: str) -> ProjectFacts | None: ...

    def active_member(self, tenant_id: str, user_id: str) -> bool: ...
