"""Pure auto-naming logic for sprints (change 29-sprint-borrador).

No SQLAlchemy, no I/O — testable in isolation without a database, the same
reuse boundary as ``work_calendar/estimation.py`` (change 34). The service
layer fetches the previous sprint by ``created_at`` and calls
``next_sprint_name``; this module only decides the string.
"""

import re


def next_sprint_name(previous: str | None, project_code: str | None) -> str:
    """Return the suggested name for the next sprint.

    - No previous sprint: ``f"{project_code} Sprint 1"`` when ``project_code``
      (stripped) is non-empty, otherwise ``"Sprint 1"``.
    - With a previous name: increment the LAST run of digits, preserving its
      width (left-zero padding) and the surrounding prefix/separator
      (e.g. the ``-`` in ``S-09`` -> ``S-10``).
    - With a previous name but no digits at all: suffix ``" 2"`` (the
      existing name counts as the implicit "1").

    The result is a SUGGESTION only — it is never persisted here and there is
    no uniqueness constraint on sprint names.
    """

    if previous is None or not previous.strip():
        code = (project_code or "").strip()
        return f"{code} Sprint 1" if code else "Sprint 1"

    matches = list(re.finditer(r"\d+", previous))
    if not matches:
        return f"{previous} 2"

    last = matches[-1]
    incremented = str(int(last.group()) + 1).zfill(len(last.group()))
    return previous[: last.start()] + incremented + previous[last.end() :]
