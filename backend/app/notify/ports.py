"""Delivery channel ports — the hub's extensibility contract (design.md D1/D2/D6).

Two DISJOINT protocols, one per :class:`DeliveryPolicy`, instead of one
protocol with optional methods: ``durable`` and ``best_effort`` channels
have disjoint lifecycles (a persisted, retried outbox row vs. an
in-process, post-commit buffer) that a single protocol with ``None``-checks
would blur into runtime branches. Modeling the policy as a TYPE (which
protocol a channel implements) keeps a half-implemented channel from ever
compiling, and lets the dispatcher/repository partition by ``.policy``
without inspecting channel internals.
"""

from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification


class DeliveryPolicy(StrEnum):
    """How a channel's delivery attempt is tracked.

    Plain ``enum.StrEnum`` (unlike the domain enums in ``app/shared/
    enums.py``, deliberately kept as ``(str, Enum)``): this policy is NEVER
    persisted via SQLAlchemy's ``Enum`` column type, so the
    ``ReprEnum``/f-string formatting difference ``StrEnum`` introduces has
    no storage implication here.
    """

    durable = "durable"
    best_effort = "best_effort"


class DeliveryChannel(Protocol):
    """Common shape every registered channel MUST implement."""

    name: str
    policy: DeliveryPolicy


class DurableChannel(DeliveryChannel, Protocol):
    """A channel whose attempts are persisted (store port) and dispatched
    generically, with claim/retry/terminal-failure semantics (D3)."""

    async def enqueue(self, db: AsyncSession, notification: Notification) -> None:
        """Applicability check + payload build + domain side-effects (e.g.
        ``notification.emailed_at``) + the store INSERT — all in ``db``'s
        active transaction. The row is inserted by the store port, never by
        the channel directly (D2): a channel stays decoupled from the table.
        """
        ...

    async def deliver(self, payload: dict[str, Any]) -> None:
        """Perform the actual send from a fully self-contained ``payload``.

        Called ONLY by the generic dispatcher (``app.notify.dispatcher``),
        never by ``enqueue`` — the dispatcher knows nothing channel-specific
        beyond this payload.
        """
        ...


class BestEffortChannel(DeliveryChannel, Protocol):
    """A channel that buffers in-process pre-commit and is flushed
    post-commit by the transaction owner — never persisted, never retried."""

    def buffer(self, db: AsyncSession, notification: Notification) -> None:
        """Queue ``notification`` on ``db`` for a later, external flush."""
        ...
