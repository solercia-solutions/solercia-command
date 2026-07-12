"""Business logic for assets, their licences and their task links.

``AssetService.delete_asset`` explicitly cascades the soft-delete to every
active licence of the asset (specs/assets/spec.md, "Licencias inaccesibles
tras el borrado soft del activo padre") — the propagation happens HERE, not
only in a downstream alert query, so a direct ``GET/PATCH/DELETE`` on a
licence of a soft-deleted asset already returns 404 via the repository's own
``is_active`` filter.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset, AssetLicense
from app.modules.assets.repository import (
    AssetLicenseRepository,
    AssetRepository,
    AssetTaskRepository,
)
from app.modules.assets.schemas import (
    AssetCreate,
    AssetLicenseCreate,
    AssetLicenseResponse,
    AssetLicenseUpdate,
    AssetResponse,
    AssetTaskResponse,
    AssetUpdate,
)
from app.modules.tasks.repository import TaskRepository
from app.shared.enums import AssetCriticality, AssetStatus, AssetType
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

_ASSET_UPDATABLE_FIELDS = (
    "name",
    "description",
    "asset_type",
    "category",
    "status",
    "criticality",
    "responsible_id",
    "acquisition_date",
    "location",
    "vendor",
)
_LICENSE_UPDATABLE_FIELDS = (
    "license_type",
    "license_key",
    "start_date",
    "expiration_date",
    "seats",
    "cost",
    "auto_renew",
)


class AssetService:
    """Orchestrates asset use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = AssetRepository(db)
        self.license_repo = AssetLicenseRepository(db)

    async def create_asset(
        self,
        organization_id: uuid.UUID,
        data: AssetCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> AssetResponse:
        """Create an information asset."""

        asset = Asset(
            organization_id=organization_id,
            name=data.name,
            description=data.description,
            asset_type=data.asset_type,
            category=data.category,
            status=data.status,
            criticality=data.criticality,
            responsible_id=data.responsible_id,
            acquisition_date=data.acquisition_date,
            location=data.location,
            vendor=data.vendor,
            created_by=actor_id,
            updated_by=actor_id,
        )
        asset = await self.repo.create(asset)
        return AssetResponse.model_validate(asset)

    async def get_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> AssetResponse:
        """Return a single asset scoped to the organization."""

        asset = await self._require_asset(organization_id, asset_id)
        return AssetResponse.model_validate(asset)

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
    ) -> tuple[list[AssetResponse], int]:
        """Return ``(assets, total)`` — the org's active assets, filtered."""

        rows, total = await self.repo.list_assets(
            organization_id,
            asset_type=asset_type,
            status=status,
            criticality=criticality,
            responsible_id=responsible_id,
            category=category,
            q=q,
            pagination=pagination,
        )
        return [AssetResponse.model_validate(row) for row in rows], total

    async def update_asset(
        self,
        organization_id: uuid.UUID,
        asset_id: uuid.UUID,
        data: AssetUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> AssetResponse:
        """Apply a partial update to an asset."""

        asset = await self._require_asset(organization_id, asset_id)
        changes = data.model_dump(exclude_unset=True)
        for field in _ASSET_UPDATABLE_FIELDS:
            if field in changes:
                setattr(asset, field, changes[field])

        asset.updated_by = actor_id
        asset = await self.repo.save(asset)
        return AssetResponse.model_validate(asset)

    async def delete_asset(self, organization_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        """Soft-delete an asset AND cascade the soft-delete to its licences."""

        asset = await self._require_asset(organization_id, asset_id)
        licenses = await self.license_repo.list_for_asset(organization_id, asset_id)
        now = datetime.now(UTC)
        for license_row in licenses:
            license_row.is_active = False
            license_row.deleted_at = now

        asset.is_active = False
        asset.deleted_at = now
        await self.repo.save(asset)

    # -- helpers -------------------------------------------------------------

    async def _require_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Asset:
        asset = await self.repo.get(organization_id, asset_id)
        if asset is None:
            raise AppException(
                "El activo no existe o no tienes acceso a él.",
                code="asset_not_found",
                status_code=404,
            )
        return asset


class AssetLicenseService:
    """Orchestrates licence use-cases scoped to their parent asset."""

    def __init__(self, db: AsyncSession) -> None:
        self.assets = AssetRepository(db)
        self.repo = AssetLicenseRepository(db)

    async def create_license(
        self,
        organization_id: uuid.UUID,
        asset_id: uuid.UUID,
        data: AssetLicenseCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> AssetLicenseResponse:
        """Create a licence under an existing, accessible asset."""

        await self._require_asset(organization_id, asset_id)
        license_row = AssetLicense(
            organization_id=organization_id,
            asset_id=asset_id,
            license_type=data.license_type,
            license_key=data.license_key,
            start_date=data.start_date,
            expiration_date=data.expiration_date,
            seats=data.seats,
            cost=data.cost,
            auto_renew=data.auto_renew,
            created_by=actor_id,
            updated_by=actor_id,
        )
        license_row = await self.repo.create(license_row)
        return AssetLicenseResponse.model_validate(license_row)

    async def list_licenses(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> list[AssetLicenseResponse]:
        """Return the active licences of an asset."""

        await self._require_asset(organization_id, asset_id)
        rows = await self.repo.list_for_asset(organization_id, asset_id)
        return [AssetLicenseResponse.model_validate(row) for row in rows]

    async def update_license(
        self,
        organization_id: uuid.UUID,
        license_id: uuid.UUID,
        data: AssetLicenseUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> AssetLicenseResponse:
        """Apply a partial update to a licence, re-checking date order."""

        license_row = await self._require_license(organization_id, license_id)
        changes = data.model_dump(exclude_unset=True)
        for field in _LICENSE_UPDATABLE_FIELDS:
            if field in changes:
                setattr(license_row, field, changes[field])

        if license_row.expiration_date <= license_row.start_date:
            raise AppException(
                "expiration_date debe ser posterior a start_date.",
                code="invalid_license_dates",
                status_code=422,
            )

        license_row.updated_by = actor_id
        license_row = await self.repo.save(license_row)
        return AssetLicenseResponse.model_validate(license_row)

    async def delete_license(
        self, organization_id: uuid.UUID, license_id: uuid.UUID
    ) -> None:
        """Soft-delete a licence."""

        license_row = await self._require_license(organization_id, license_id)
        license_row.is_active = False
        license_row.deleted_at = datetime.now(UTC)
        await self.repo.save(license_row)

    # -- helpers -------------------------------------------------------------

    async def _require_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Asset:
        asset = await self.assets.get(organization_id, asset_id)
        if asset is None:
            raise AppException(
                "El activo no existe o no tienes acceso a él.",
                code="asset_not_found",
                status_code=404,
            )
        return asset

    async def _require_license(
        self, organization_id: uuid.UUID, license_id: uuid.UUID
    ) -> AssetLicense:
        license_row = await self.repo.get(organization_id, license_id)
        if license_row is None:
            raise AppException(
                "La licencia no existe o no tienes acceso a ella.",
                code="asset_license_not_found",
                status_code=404,
            )
        return license_row


class AssetTaskService:
    """Orchestrates asset-task link use-cases (vínculo con tareas EXISTENTES)."""

    def __init__(self, db: AsyncSession) -> None:
        self.assets = AssetRepository(db)
        self.tasks = TaskRepository(db)
        self.repo = AssetTaskRepository(db)

    async def link_task(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID, task_id: uuid.UUID
    ) -> AssetTaskResponse:
        """Link an existing task of the same org to an asset (idempotent)."""

        await self._require_asset(organization_id, asset_id)
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )

        existing = await self.repo.get_link(asset_id, task_id)
        if existing is not None:
            return AssetTaskResponse.model_validate(existing)

        link = await self.repo.link(organization_id, asset_id, task_id)
        return AssetTaskResponse.model_validate(link)

    async def list_tasks(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> list[AssetTaskResponse]:
        """Return the tasks linked to an asset."""

        await self._require_asset(organization_id, asset_id)
        rows = await self.repo.list_for_asset(organization_id, asset_id)
        return [AssetTaskResponse.model_validate(row) for row in rows]

    async def unlink_task(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        """Unlink a task from an asset (no-op if it wasn't linked)."""

        await self._require_asset(organization_id, asset_id)
        await self.repo.unlink(asset_id, task_id)

    # -- helpers -------------------------------------------------------------

    async def _require_asset(
        self, organization_id: uuid.UUID, asset_id: uuid.UUID
    ) -> Asset:
        asset = await self.assets.get(organization_id, asset_id)
        if asset is None:
            raise AppException(
                "El activo no existe o no tienes acceso a él.",
                code="asset_not_found",
                status_code=404,
            )
        return asset
