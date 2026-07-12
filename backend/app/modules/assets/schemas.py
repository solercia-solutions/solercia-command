"""Pydantic schemas for the assets module (Asset + AssetLicense + AssetTask)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enums import AssetCriticality, AssetStatus, AssetType, LicenseType


class AssetCreate(BaseModel):
    """Payload to create an information asset."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    asset_type: AssetType
    category: str | None = Field(default=None, max_length=80)
    status: AssetStatus = AssetStatus.active
    criticality: AssetCriticality = AssetCriticality.medium
    responsible_id: uuid.UUID | None = None
    acquisition_date: date | None = None
    location: str | None = Field(default=None, max_length=200)
    vendor: str | None = Field(default=None, max_length=200)


class AssetUpdate(BaseModel):
    """Partial payload to edit an information asset."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    asset_type: AssetType | None = None
    category: str | None = Field(default=None, max_length=80)
    status: AssetStatus | None = None
    criticality: AssetCriticality | None = None
    responsible_id: uuid.UUID | None = None
    acquisition_date: date | None = None
    location: str | None = Field(default=None, max_length=200)
    vendor: str | None = Field(default=None, max_length=200)


class AssetResponse(BaseModel):
    """An information asset as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    asset_type: AssetType
    category: str | None = None
    status: AssetStatus
    criticality: AssetCriticality
    responsible_id: uuid.UUID | None = None
    acquisition_date: date | None = None
    location: str | None = None
    vendor: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


def _require_expiration_after_start(start_date: date, expiration_date: date) -> None:
    if expiration_date <= start_date:
        raise ValueError("expiration_date debe ser posterior a start_date.")


class AssetLicenseCreate(BaseModel):
    """Payload to create a licence attached to an asset."""

    license_type: LicenseType
    license_key: str | None = Field(default=None, max_length=200)
    start_date: date
    expiration_date: date
    seats: int | None = Field(default=None, gt=0)
    cost: Decimal | None = Field(default=None, ge=0)
    auto_renew: bool = False

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        _require_expiration_after_start(self.start_date, self.expiration_date)
        return self


class AssetLicenseUpdate(BaseModel):
    """Partial payload to edit a licence.

    When BOTH ``start_date`` and ``expiration_date`` are supplied together the
    order is validated here; a single-field update is re-checked against the
    persisted row by ``AssetLicenseService.update_license`` so the invariant
    always holds regardless of which field(s) the caller sends.
    """

    license_type: LicenseType | None = None
    license_key: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    expiration_date: date | None = None
    seats: int | None = Field(default=None, gt=0)
    cost: Decimal | None = Field(default=None, ge=0)
    auto_renew: bool | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if self.start_date is not None and self.expiration_date is not None:
            _require_expiration_after_start(self.start_date, self.expiration_date)
        return self


class AssetLicenseResponse(BaseModel):
    """A licence as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    license_type: LicenseType
    license_key: str | None = None
    start_date: date
    expiration_date: date
    seats: int | None = None
    cost: Decimal | None = None
    auto_renew: bool
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class AssetTaskLink(BaseModel):
    """Payload to link an EXISTING task to an asset."""

    task_id: uuid.UUID


class AssetTaskResponse(BaseModel):
    """An asset-task link as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    task_id: uuid.UUID
    created_at: datetime
