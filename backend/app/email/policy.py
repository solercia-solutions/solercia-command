"""Email urgency classification — pure mapping, no side effects.

``email_class`` decides whether a notification's ``rule_type`` triggers an
immediate best-effort email (design.md D5) or waits for the user's digest.
Deliberately an in-process enum, NOT persisted anywhere: the classification
is a pure function of ``rule_type``, so callers (outbox, digest) never need a
column or a migration to know the urgency bucket.
"""

from enum import StrEnum


class EmailClass(StrEnum):
    """Urgency bucket for a notification's email delivery."""

    IMMEDIATE = "immediate"
    DIGESTIBLE = "digestible"


# rule_type values that MUST always trigger an immediate email regardless of
# the recipient's digest preference (design.md D5 — compliance risk). A
# strict allow-list: anything not listed here is DIGESTIBLE by default, so a
# future rule_type never becomes urgent by accident.
IMMEDIATE_RULE_TYPES: set[str] = {"license_expired"}


def email_class(rule_type: str) -> EmailClass:
    """Return the urgency bucket for ``rule_type``."""

    if rule_type in IMMEDIATE_RULE_TYPES:
        return EmailClass.IMMEDIATE
    return EmailClass.DIGESTIBLE
