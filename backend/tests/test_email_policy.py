"""Tests for the email urgency classification (change 08, Fase A).

R3 Envío inmediato de tipos urgentes · R5 Alcance y marcado del digest
(specs/email-notifications/spec.md, D5 — mapeo puro ``email_class``).

Pure unit tests: ``email_class`` has zero side effects and zero dependencies
on the database, so no ``skip_no_db``/fixtures are needed here.
"""

from app.email.policy import EmailClass, email_class


def test_license_expired_is_immediate() -> None:
    """license_expired is the only urgent rule_type in the MVP (design.md D5)."""

    assert email_class("license_expired") == EmailClass.IMMEDIATE


def test_task_overdue_is_digestible() -> None:
    """A non-urgent rule_type waits for the digest instead of firing immediately."""

    assert email_class("task_overdue") == EmailClass.DIGESTIBLE


def test_sprint_at_risk_is_digestible() -> None:
    assert email_class("sprint_at_risk") == EmailClass.DIGESTIBLE


def test_license_expiring_is_digestible() -> None:
    """Distinct from license_expired: still approaching, not yet a compliance risk."""

    assert email_class("license_expiring") == EmailClass.DIGESTIBLE


def test_mention_is_digestible() -> None:
    assert email_class("mention") == EmailClass.DIGESTIBLE


def test_task_at_risk_is_digestible() -> None:
    assert email_class("task_at_risk") == EmailClass.DIGESTIBLE


def test_reminder_is_digestible() -> None:
    assert email_class("reminder") == EmailClass.DIGESTIBLE


def test_unknown_rule_type_defaults_to_digestible() -> None:
    """Any rule_type not explicitly classified as urgent stays DIGESTIBLE — the
    IMMEDIATE set is a strict allow-list, never a deny-list."""

    assert email_class("some_future_rule_type") == EmailClass.DIGESTIBLE
