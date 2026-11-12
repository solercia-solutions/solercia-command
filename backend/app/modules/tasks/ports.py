"""Application-facing task creation contract."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.tasks.models import Task


class TaskCreationPort(Protocol):
    """Create an already validated aggregate in the caller-owned transaction.

    Task is deliberately the existing product-local aggregate. Before calling,
    the use case must authorize the tenant and validate that task.project_id
    and all related identifiers belong to that context. This port performs no
    lookups and is not an authorization boundary. Number allocation and domain
    validation remain the caller's responsibility.

    Implementations participate in the injected session, flush and refresh the
    same instance, and propagate failures. The caller alone owns transaction
    completion and session lifetime; a returned task is not yet committed.
    """

    async def create(self, task: "Task") -> "Task": ...
