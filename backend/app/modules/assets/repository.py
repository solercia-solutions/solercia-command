"""Data-access layer for assets, their licences and their task links.

Assets and licences are tenant-scoped directly via ``organization_id``
(``TenantMixin``); a licence's own ``is_active`` flag is what the propagated
soft-delete of its parent asset flips (``AssetService.delete_asset``), so
every licence query here only needs to filter its own ``is_active`` — no
join to ``Asset`` required (design.md, "FK y borrado de las entidades
hijas").
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.assets.models import Asset, AssetLicense, AssetTask
from app.shared.enums import AssetCriticality, AssetStatus, AssetType
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /assets``. First entry is the default
# order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Asset.created_at,
    "name": Asset.name,
    "status": Asset.status,
    "criticality": Asset.criticality,
}


class AssetRepository:
    """Async repository encapsulating asset persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_assets(
        self,
        organization_id: uuid.UUID,
        *,
        asset_type: AssetType | None = None,
        status: AssetStatus | None = None,
        criticality: AssetCriticality | None = None,
        responsible_id: uuid.UUID | None = None,
        category: str | None = None,
        q: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Asset], int]:
        """Return ``(assets, total)`` — active assets of the org, filtered."""

        stmt = select(Asset).where(
            Asset.organization_id == organization_id,
            Asset.is_active.is_(True),
        )
        if asset_type is not None:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if status is not None:
            stmt = stmt.where(Asset.status == status)
        if criticality is not None:
            stmt = stmt.where(Asset.criticality == criticality)
        if responsible_id is not None:
            stmt = stmt.where(Asset.responsible_id == responsible_id)
        if category is not None:
            stmt = stmt.where(Asset.category == category)
        if q is not None:
            stmt = stmt.where(Asset.name.ilike(f"%{q}%"))

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Asset.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(self, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset | None:
        """Return a single active asset scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.organization_id == organization_id,
                Asset.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, asset: Asset) -> Asset:
        """Persist a new asset and return the refreshed instance."""

        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def save(self, asset: Asset) -> Asset:
        """Flush pending changes on an attached asset and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(asset)
        return asset


class AssetLicenseRepository:
    """Async repository encapsulating licence persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Sequence[AssetLicense]:
        """Return the active licences of ``asset_id``, soonest to expire first."""

        result = await self.db.execute(
            select(AssetLicense)
            .where(
                AssetLicense.asset_id == asset_id,
                AssetLicense.organization_id == organization_id,
                AssetLicense.is_active.is_(True),
            )
            .order_by(AssetLicense.expiration_date.asc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, license_id: uuid.UUID
    ) -> AssetLicense | None:
        """Return a single active licence scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(AssetLicense).where(
                AssetLicense.id == license_id,
                AssetLicense.organization_id == organization_id,
                AssetLicense.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, license_row: AssetLicense) -> AssetLicense:
        """Persist a new licence and return the refreshed instance."""

        self.db.add(license_row)
        await self.db.commit()
        await self.db.refresh(license_row)
        return license_row

    async def save(self, license_row: AssetLicense) -> AssetLicense:
        """Flush pending changes on an attached licence and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(license_row)
        return license_row


class AssetTaskRepository:
    """Async repository encapsulating asset-task link persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Sequence[AssetTask]:
        """Return the task links of ``asset_id``, oldest first."""

        result = await self.db.execute(
            select(AssetTask)
            .where(
                AssetTask.asset_id == asset_id,
                AssetTask.organization_id == organization_id,
            )
            .order_by(AssetTask.created_at.asc())
        )
        return result.scalars().all()

    async def get_link(
        self, asset_id: uuid.UUID, task_id: uuid.UUID
    ) -> AssetTask | None:
        """Return the ``AssetTask`` row for an asset/task pair, or ``None``."""

        result = await self.db.execute(
            select(AssetTask).where(
                AssetTask.asset_id == asset_id, AssetTask.task_id == task_id
            )
        )
        return result.scalar_one_or_none()

    async def link(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID, task_id: uuid.UUID
    ) -> AssetTask:
        """Create an ``AssetTask`` row, linking ``task_id`` to ``asset_id``."""

        link_row = AssetTask(
            organization_id=organization_id, asset_id=asset_id, task_id=task_id
        )
        self.db.add(link_row)
        await self.db.commit()
        await self.db.refresh(link_row)
        return link_row

    async def unlink(self, asset_id: uuid.UUID, task_id: uuid.UUID) -> None:
        """Hard-delete the ``AssetTask`` row for an asset/task pair, if any."""

        await self.db.execute(
            delete(AssetTask).where(
                AssetTask.asset_id == asset_id, AssetTask.task_id == task_id
            )
        )
        await self.db.commit()
