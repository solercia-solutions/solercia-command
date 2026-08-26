"""Typed report shapes for the maintenance package (design.md Decision D8).

Pure data — no I/O.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryRow:
    """Row count for one table, resolved once before any ``DELETE`` runs."""

    table: str
    before: int
    after: int


@dataclass(frozen=True)
class PlannedDeletion:
    """The exact ids the purge is about to delete from ``table`` and why —
    printed by the CLI (Fase 4) before ``--execute`` touches anything."""

    table: str
    ids: tuple[uuid.UUID, ...]
    reason: str


@dataclass(frozen=True)
class DeletionResult:
    """Rows actually removed from ``table`` by this purge run."""

    table: str
    deleted: int


@dataclass(frozen=True)
class PurgeOutcome:
    """The full result of one ``purge_demo_data`` call."""

    inventory: tuple[InventoryRow, ...]
    planned: tuple[PlannedDeletion, ...]
    deleted: tuple[DeletionResult, ...]
    # Corrección 2 (I6): PRE-EXISTING orphans swept independently of this
    # run's demo scope — reported separately so the dry-run stays honest.
    orphans_swept: tuple[DeletionResult, ...] = ()


@dataclass(frozen=True)
class ConnectedAccountRisk:
    """A ``connected_account`` blocking the purge because its owner is a
    user in the demo scope."""

    provider: str
    display_name: str | None
    owner_email: str


class PurgeGuardError(Exception):
    """Raised BEFORE any ``DELETE`` when a fail-closed guard trips — the
    caller never sees a partially-applied purge."""

    def __init__(self, message: str, *, risks: tuple[ConnectedAccountRisk, ...] = ()) -> None:
        super().__init__(message)
        self.risks = risks


@dataclass(frozen=True)
class InvariantResult:
    """One post-execution check (design.md D8, I1-I8) — read-only, never
    raises; ``runner.py`` gates the ``commit()`` on ``passed``."""

    key: str
    description: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class MaintenanceReport:
    """The full result of one ``run_maintenance`` call — purge + bootstrap +
    invariants (design.md D8)."""

    mode: str
    inventory: tuple[InventoryRow, ...]
    planned: tuple[PlannedDeletion, ...]
    deleted: tuple[DeletionResult, ...]
    bootstrap: tuple[str, ...]
    invariants: tuple[InvariantResult, ...]
    orphans_swept: tuple[DeletionResult, ...] = ()

    @property
    def ok(self) -> bool:
        return all(result.passed for result in self.invariants)
