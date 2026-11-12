"""SQLAlchemy adapter for the organization theme and its version history.

Implements ``theme_ports.OrganizationThemePort`` on the request session. The
repository only flushes: completion belongs to the use case through
``SessionThemeTransaction``. The row lock and the JSONB column stay in here.
"""

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationThemeVersion
from app.modules.organizations.theme_ports import (
    OrganizationTheme,
    ThemeVersionRecord,
    ThemeVersionSummary,
)

_Version = OrganizationThemeVersion

_SUMMARY_COLUMNS = (
    _Version.id,
    _Version.organization_id,
    _Version.user_id,
    _Version.user_name,
    _Version.applied_at,
    _Version.initial_capture,
    _Version.source_version_id,
)


class OrganizationThemeRepository:
    """Theme of an organization and its insert-only history; never commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _organization(
        self, organization_id: uuid.UUID, *, lock: bool
    ) -> Organization | None:
        stmt = select(Organization).where(
            Organization.id == organization_id,
            Organization.is_active.is_(True),
        )
        if lock:
            # ``populate_existing``: the value read under the lock must be the
            # committed one, not a copy this session loaded earlier.
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def find_theme(
        self, organization_id: uuid.UUID
    ) -> OrganizationTheme | None:
        organization = await self._organization(organization_id, lock=False)
        if organization is None:
            return None
        return OrganizationTheme(theme=organization.theme)

    async def lock_theme(
        self, organization_id: uuid.UUID
    ) -> OrganizationTheme | None:
        organization = await self._organization(organization_id, lock=True)
        if organization is None:
            return None
        return OrganizationTheme(theme=organization.theme)

    async def replace_theme(
        self,
        organization_id: uuid.UUID,
        theme: dict | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        organization = await self._organization(organization_id, lock=True)
        if organization is None:
            raise LookupError("replace_theme requires an active organization")
        organization.theme = theme
        organization.updated_by = actor_id
        await self._session.flush()

    async def has_versions(self, organization_id: uuid.UUID) -> bool:
        stmt = (
            select(_Version.id)
            .where(_Version.organization_id == organization_id)
            .limit(1)
        )
        return await self._session.scalar(stmt) is not None

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
        version = _Version(
            organization_id=organization_id,
            theme=theme,
            user_id=user_id,
            user_name=user_name,
            initial_capture=initial_capture,
            source_version_id=source_version_id,
        )
        self._session.add(version)
        # The flush returns the identity id and the server-side ``applied_at``.
        await self._session.flush()
        return ThemeVersionRecord(**_summary_fields(version), theme=version.theme)

    async def find_version(
        self, organization_id: uuid.UUID, version_id: int
    ) -> ThemeVersionRecord | None:
        stmt = select(*_SUMMARY_COLUMNS, _Version.theme).where(
            _Version.organization_id == organization_id,
            _Version.id == version_id,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return ThemeVersionRecord(**_summary_fields(row), theme=row.theme)

    async def list_versions(
        self, organization_id: uuid.UUID, *, before: int | None, limit: int
    ) -> list[ThemeVersionSummary]:
        # The ThemeFile is left out on purpose: a page only shows metadata.
        stmt = select(*_SUMMARY_COLUMNS).where(
            _Version.organization_id == organization_id
        )
        if before is not None:
            stmt = stmt.where(_Version.id < before)
        stmt = stmt.order_by(_Version.id.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [ThemeVersionSummary(**_summary_fields(row)) for row in rows]


def _summary_fields(source) -> dict:
    """Map a version (ORM instance or result row) to the summary fields."""

    return {
        "id": source.id,
        "organization_id": source.organization_id,
        "user_id": source.user_id,
        "user_name": source.user_name,
        "applied_at": source.applied_at.astimezone(UTC),
        "initial_capture": source.initial_capture,
        "source_version_id": source.source_version_id,
    }


class SessionThemeTransaction:
    """``OrganizationThemeTransaction`` over the caller-owned request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.themes = OrganizationThemeRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
