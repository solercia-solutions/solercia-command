"""Application ports for the organization theme and its version history.

The theme use cases (``OrganizationThemeService``) depend on these contracts
only; the SQLAlchemy adapter lives in ``theme_repository.py``. Every method
takes the ``organization_id`` scope explicitly: there is no way to read a
version, or to reference one as a restore source, across tenants.

The history is INSERT-ONLY by contract: the port can add and read versions and
has no operation to change or remove one.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OrganizationTheme:
    """Current ThemeFile of an organization (``None`` = bundled default theme)."""

    theme: dict | None


@dataclass(frozen=True, slots=True)
class ThemeVersionSummary:
    """Metadata of one recorded version (what the history list shows)."""

    id: int
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    user_name: str | None
    applied_at: datetime
    initial_capture: bool
    source_version_id: int | None


@dataclass(frozen=True, slots=True)
class ThemeVersionRecord(ThemeVersionSummary):
    """A recorded version with the ThemeFile that was applied."""

    theme: dict


class OrganizationThemePort(Protocol):
    """Theme of one organization plus its insert-only version history."""

    async def find_theme(
        self, organization_id: uuid.UUID
    ) -> OrganizationTheme | None:
        """Return the current theme, or ``None`` if the organization is not active."""
        ...

    async def lock_theme(
        self, organization_id: uuid.UUID
    ) -> OrganizationTheme | None:
        """Like :meth:`find_theme`, holding the organization until completion.

        Serializes theme changes of the same organization, so the initial
        capture happens once and versions are recorded in apply order.
        """
        ...

    async def replace_theme(
        self,
        organization_id: uuid.UUID,
        theme: dict | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Store ``theme`` (``None`` resets it) on an organization locked before."""
        ...

    async def has_versions(self, organization_id: uuid.UUID) -> bool:
        """Return whether the organization already has any recorded version."""
        ...

    async def add_version(
        self,
        organization_id: uuid.UUID,
        theme: dict,
        *,
        user_id: uuid.UUID | None,
        user_name: str | None,
        initial_capture: bool = False,
        source_version_id: int | None = None,
    ) -> ThemeVersionRecord:
        """Record a new version in the caller's transaction and return it."""
        ...

    async def find_version(
        self, organization_id: uuid.UUID, version_id: int
    ) -> ThemeVersionRecord | None:
        """Return a version of THIS organization, or ``None``."""
        ...

    async def list_versions(
        self, organization_id: uuid.UUID, *, before: int | None, limit: int
    ) -> list[ThemeVersionSummary]:
        """Return up to ``limit`` versions, newest first, older than ``before``."""
        ...


class OrganizationThemeTransaction(Protocol):
    """Transaction scope of a theme use case; the use case completes it once."""

    themes: OrganizationThemePort

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
