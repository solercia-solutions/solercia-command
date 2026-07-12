"""LicenseExpiredStrategy — licences already past their expiration_date.

Notifies the asset's ``responsible_id`` **AND** every organization admin,
with EACH recipient treated as an INDEPENDENT candidate
(``dedup_key`` includes ``recipient_id``, design.md "dedup_key con
recipient y banda de umbral"). Deliberately does NOT copy
``workload_imbalance``'s ``if not admins: return []`` early-return: there the
early return is safe because every recipient IS an admin, but here it would
wrongly suppress the responsible person's notification in an organization
with zero admins.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.assets.models import Asset, AssetLicense
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole


class LicenseExpiredStrategy(AlertStrategy):
    rule_type = "license_expired"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        today = date.today()

        result = await db.execute(
            select(AssetLicense, Asset)
            .join(Asset, Asset.id == AssetLicense.asset_id)
            .where(
                Asset.organization_id == organization_id,
                Asset.is_active.is_(True),
                AssetLicense.is_active.is_(True),
                AssetLicense.expiration_date < today,
            )
        )
        expired = result.all()
        if not expired:
            return []

        admins_result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == MemberRole.admin,
            )
        )
        admin_ids = {admin.user_id for admin in admins_result.scalars().all()}

        candidates = []
        for license_row, asset in expired:
            # A set: an organization without admins still notifies the
            # responsible person (never suppressed); if the responsible
            # person IS also an admin, they get exactly one notification.
            recipients = set(admin_ids)
            if asset.responsible_id is not None:
                recipients.add(asset.responsible_id)

            for recipient_id in recipients:
                candidates.append(
                    AlertCandidate(
                        organization_id=organization_id,
                        rule_type=self.rule_type,
                        recipient_user_id=recipient_id,
                        title="Licencia vencida",
                        body=(
                            f'La licencia de "{asset.name}" venció el '
                            f"{license_row.expiration_date.isoformat()}."
                        ),
                        dedup_key=f"license_expired:{license_row.id}:{recipient_id}",
                        target_type="asset_license",
                        target_id=license_row.id,
                    )
                )
        return candidates
