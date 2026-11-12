"""Tests for the pure sprint auto-naming function (change 29-sprint-borrador).

``next_sprint_name`` is a pure function (no DB, no I/O) that computes the
suggested name for the next sprint given the previous sprint's name (or
``None``) and the project's ``code`` (or ``None``). Design.md D1 truth table.
"""

from app.modules.sprints.naming import next_sprint_name

# ---------------------------------------------------------------------------
# Full truth table (design.md D1 / tasks.md 1.1)
# ---------------------------------------------------------------------------


def test_next_name_increments_trailing_run_with_separator() -> None:
    """``PANDORA 2026-1`` -> ``PANDORA 2026-2`` — last digit run incremented,
    preserving the ``-`` separator. ``project_code`` is ignored when there is
    a previous name."""

    assert next_sprint_name("PANDORA 2026-1", None) == "PANDORA 2026-2"
    assert next_sprint_name("PANDORA 2026-1", "PANDORA") == "PANDORA 2026-2"


def test_next_name_increments_simple_trailing_number() -> None:
    """``Sprint 9`` -> ``Sprint 10``."""

    assert next_sprint_name("Sprint 9", None) == "Sprint 10"


def test_next_name_without_trailing_number_suffixes_two() -> None:
    """``Velocidad`` (no digits) -> ``Velocidad 2``."""

    assert next_sprint_name("Velocidad", None) == "Velocidad 2"


def test_next_name_preserves_zero_padding() -> None:
    """``S-09`` -> ``S-10`` — left-zero padding and the ``-`` separator are
    preserved when incrementing."""

    assert next_sprint_name("S-09", None) == "S-10"


def test_next_name_without_previous_uses_project_code() -> None:
    """No previous sprint, ``project_code="SDM"`` -> ``SDM Sprint 1``."""

    assert next_sprint_name(None, "SDM") == "SDM Sprint 1"


def test_next_name_without_previous_and_without_code_defaults_to_sprint_one() -> None:
    """No previous sprint, no ``project_code`` -> ``Sprint 1``."""

    assert next_sprint_name(None, None) == "Sprint 1"


# ---------------------------------------------------------------------------
# Additional edge-case widths (tasks.md 1.3)
# ---------------------------------------------------------------------------


def test_next_name_multi_word_without_digits_suffixes_two() -> None:
    """``Sprint Kickoff`` (no digits) -> ``Sprint Kickoff 2``."""

    assert next_sprint_name("Sprint Kickoff", None) == "Sprint Kickoff 2"


def test_next_name_two_digit_run_preserves_width() -> None:
    """``PANDORA 2026-09`` -> ``PANDORA 2026-10`` — two-digit run, same width
    preserved on increment."""

    assert next_sprint_name("PANDORA 2026-09", None) == "PANDORA 2026-10"


def test_next_name_single_digit_run_has_no_artificial_padding() -> None:
    """``Sprint 2`` -> ``Sprint 3`` — single digit, no padding added."""

    assert next_sprint_name("Sprint 2", None) == "Sprint 3"
