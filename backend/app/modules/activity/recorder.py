"""Shared helper that appends ``TaskHistory`` rows within an existing transaction.

``record_task_history`` is called by every service that mutates a tracked
task field — ``TaskService.update_task`` (actor=user) and
``SprintService.close_sprint`` (actor=system) today. It only stages the rows
via ``add_all`` (NO commit): the caller's own ``repo.save()``/``create()``
seals the mutation and the history rows into ONE atomic transaction
(design.md, "Decisión: recorder compartido, no ligado a TaskService").

Defensive rule (design.md, "Correcciones de gate" #7): any FUTURE
system-originated task mutation (the alert engine included) MUST route
through this helper with ``actor_type=ACTOR_TYPE_SYSTEM`` and
``actor_id=None`` — today's alert strategies only create notifications, they
never mutate a task, so there is no call site to add yet.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activity.models import TaskHistory

ACTOR_TYPE_USER = "user"
ACTOR_TYPE_SYSTEM = "system"


async def record_task_history(
    db: AsyncSession,
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_type: str,
    changes: dict[str, tuple[str | None, str | None]],
) -> None:
    """Stage one ``TaskHistory`` row per entry of ``changes`` (field -> (old, new)).

    A no-op when ``changes`` is empty — callers pass the pre-filtered diff
    (only fields whose value actually changed), so this never creates a row
    for an untouched or no-op field.
    """

    if not changes:
        return

    rows = [
        TaskHistory(
            organization_id=organization_id,
            task_id=task_id,
            actor_id=actor_id,
            actor_type=actor_type,
            field=field,
            old_value=old_value,
            new_value=new_value,
        )
        for field, (old_value, new_value) in changes.items()
    ]
    db.add_all(rows)
