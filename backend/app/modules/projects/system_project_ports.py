"""Application projections and caller-transaction-bound provisioning port."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ProjectSnapshot:
    id: UUID
    organization_id: UUID
    code: str | None
    is_system: bool
    methodology: str
    status: str
    is_active: bool
    deleted_at: datetime | None


@dataclass(frozen=True)
class ColumnSnapshot:
    name: str
    status_key: str
    order: int
    is_active: bool
    deleted_at: datetime | None


@dataclass(frozen=True)
class BoardSnapshot:
    is_active: bool
    deleted_at: datetime | None
    columns: tuple[ColumnSnapshot, ...]


class SystemProjectPort(Protocol):
    """All operations share the caller's transaction; no completion methods."""

    async def lock_organization(self, organization_id: UUID) -> bool: ...

    async def find_reserved(self, organization_id: UUID) -> ProjectSnapshot | None: ...

    async def read_board(
        self, organization_id: UUID, project_id: UUID
    ) -> BoardSnapshot | None: ...

    async def create_generales(
        self, organization_id: UUID, actor_id: UUID, parent_id: UUID | None
    ) -> ProjectSnapshot: ...
