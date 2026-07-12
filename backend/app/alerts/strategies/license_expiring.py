"""LicenseExpiringStrategy — licences approaching their expiration_date.

Notifies the asset's ``responsible_id`` ONCE per run at the **smallest**
threshold band ``b`` (``threshold_params["lead_days"]``, default 30/7/1)
such that ``0 <= days_left <= b`` — never every band that matches at once
(design.md, "dedup_key con recipient y banda de umbral"): a licence
discovered at 5 days left only fires band 7 (never 30+7 together), and one
found at exactly 25 days fires band 30 (25<=30) without requiring the
evaluator to have run on day 30 sharp.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.assets.models import Asset, AssetLicense

#: Default threshold_params["lead_days"] when the AlertRule carries none.
_DEFAULT_LEAD_DAYS = [30, 7, 1]


class LicenseExpiringStrategy(AlertStrategy):
    rule_type = "license_expiring"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        leads: list[int] = threshold_params.get("lead_days", _DEFAULT_LEAD_DAYS)
        today = date.today()

        result = await db.execute(
            select(AssetLicense, Asset)
            .join(Asset, Asset.id == AssetLicense.asset_id)
            .where(
                Asset.organization_id == organization_id,
                Asset.is_active.is_(True),
                AssetLicense.is_active.is_(True),
                AssetLicense.auto_renew.is_(False),
            )
        )

        candidates = []
        for license_row, asset in result.all():
            if asset.responsible_id is None:
                continue

            days_left = (license_row.expiration_date - today).days
            if days_left < 0:
                # Already expired — covered by LicenseExpiredStrategy, not here.
                continue

            eligible_bands = [band for band in leads if days_left <= band]
            if not eligible_bands:
                continue
            band = min(eligible_bands)

            candidates.append(
                AlertCandidate(
                    organization_id=organization_id,
                    rule_type=self.rule_type,
                    recipient_user_id=asset.responsible_id,
                    title="Licencia próxima a vencer",
                    body=(
                        f'La licencia de "{asset.name}" vence en {days_left} '
                        f"día(s) ({license_row.expiration_date.isoformat()})."
                    ),
                    dedup_key=f"license_expiring:{license_row.id}:{band}",
                    target_type="asset_license",
                    target_id=license_row.id,
                )
            )
        return candidates
