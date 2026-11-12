"""The single definition of what "counts toward plan progress" (design.md D-E).

Change 44 replaces the status literal below with
``board_columns.excluded_from_progress`` plus ``tasks.context_group IS NULL``.
That criterion needs a LEFT JOIN this one does not, which is why the return
value carries joins together with the predicate.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement

from app.modules.tasks.models import Task


@dataclass(frozen=True)
class ProgressDenominator:
    """What "counts toward plan progress": predicate AND the joins it needs."""

    predicate: ColumnElement[bool]
    extra_joins: tuple[tuple[Any, ColumnElement[bool]], ...] = ()


def progress_denominator() -> ProgressDenominator:
    """THE single definition of a countable ``primary`` task.

    Current criterion, mirroring ``projects/repository.py`` at the time this
    module was written: a task counts unless its status is the literal
    ``'cancelled'``. Whoever applies change 44 edits THIS function and nothing
    else; ``test_progress_denominator_matches_the_current_criterion`` is the
    single test that must change with it.
    """

    return ProgressDenominator(predicate=Task.status != "cancelled")
