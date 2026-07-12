"""Tests for the license_expiring/license_expired alert strategies (change 07).

R7 Alerta escalonada license_expiring · R8 Alerta license_expired
(specs/assets/spec.md). Siembra ``expiration_date`` relativa a
``date.today()`` e invoca ``strategy.evaluate``/``evaluate_organization``
directo, mismo patrón que ``test_blocked_task_alert.py``.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from tests.conftest import skip_no_db


async def _seed_asset_with_license(
    session: AsyncSession,
    tenant: Organization,
    *,
    responsible_id=None,
    days_left: int,
    auto_renew: bool = False,
):
    """Create an Asset + AssetLicense expiring ``days_left`` days from today."""

    from app.modules.assets.models import Asset, AssetLicense

    asset = Asset(
        organization_id=tenant.id,
        name="Antivirus Corporativo",
        asset_type="software",
        responsible_id=responsible_id,
    )
    session.add(asset)
    await session.flush()

    license_row = AssetLicense(
        organization_id=tenant.id,
        asset_id=asset.id,
        license_type="subscription",
        start_date=date.today() - timedelta(days=300),
        expiration_date=date.today() + timedelta(days=days_left),
        auto_renew=auto_renew,
    )
    session.add(license_row)
    await session.flush()
    return asset, license_row


# ---------------------------------------------------------------------------
# R7 — Alerta escalonada license_expiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_evaluate_notifies_responsible_at_30_days(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A licence 30 days from expiring, threshold 30/7/1, notifies its responsible once."""

    from app.alerts.strategies.license_expiring import LicenseExpiringStrategy

    owner, _ = user
    _, license_row = await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=30
    )

    strategy = LicenseExpiringStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"lead_days": [30, 7, 1]})

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.recipient_user_id == owner.id
    assert candidate.dedup_key == f"license_expiring:{license_row.id}:30"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repeated_evaluation_does_not_duplicate_notification(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the full evaluator twice at the same band creates exactly ONE notification."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.alert_rules.models import AlertRule

    owner, _ = user
    await _seed_asset_with_license(session, tenant, responsible_id=owner.id, days_left=30)

    session.add(
        AlertRule(
            organization_id=tenant.id,
            rule_type="license_expiring",
            enabled=True,
            threshold_params={"lead_days": [30, 7, 1]},
        )
    )
    await session.flush()

    created_first = await evaluate_organization(session, tenant.id)
    assert created_first == 1

    created_second = await evaluate_organization(session, tenant.id)
    assert created_second == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_crossing_to_a_new_band_notifies_again(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """After the 30-day notice, the licence reaching 7 days left fires a NEW notification."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.alert_rules.models import AlertRule

    owner, _ = user
    _, license_row = await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=30
    )

    session.add(
        AlertRule(
            organization_id=tenant.id,
            rule_type="license_expiring",
            enabled=True,
            threshold_params={"lead_days": [30, 7, 1]},
        )
    )
    await session.flush()

    assert await evaluate_organization(session, tenant.id) == 1

    # Simulate time passing: the licence now has 7 days left.
    license_row.expiration_date = date.today() + timedelta(days=7)
    session.add(license_row)
    await session.flush()

    assert await evaluate_organization(session, tenant.id) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_auto_renew_license_never_alerts(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A licence with auto_renew=True 7 days from expiring produces no candidate."""

    from app.alerts.strategies.license_expiring import LicenseExpiringStrategy

    owner, _ = user
    await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=7, auto_renew=True
    )

    strategy = LicenseExpiringStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"lead_days": [30, 7, 1]})

    assert candidates == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_late_discovery_at_5_days_fires_only_band_7(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A licence discovered at 5 days left fires ONLY band 7, never 30 and 7 together."""

    from app.alerts.strategies.license_expiring import LicenseExpiringStrategy

    owner, _ = user
    _, license_row = await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=5
    )

    strategy = LicenseExpiringStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"lead_days": [30, 7, 1]})

    assert len(candidates) == 1
    assert candidates[0].dedup_key == f"license_expiring:{license_row.id}:7"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_threshold_skip_at_25_days_still_fires_band_30(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """A licence found at 25 days left (evaluator missed day 30 exactly) fires band 30."""

    from app.alerts.strategies.license_expiring import LicenseExpiringStrategy

    owner, _ = user
    _, license_row = await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=25
    )

    strategy = LicenseExpiringStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {"lead_days": [30, 7, 1]})

    assert len(candidates) == 1
    assert candidates[0].dedup_key == f"license_expiring:{license_row.id}:30"


# ---------------------------------------------------------------------------
# R8 — Alerta license_expired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_expired_license_notifies_responsible_and_admins(
    session: AsyncSession, tenant: Organization, user, make_member
) -> None:
    """An expired licence notifies the responsible AND every org admin."""

    from app.alerts.strategies.license_expired import LicenseExpiredStrategy
    from app.shared.enums import MemberRole

    owner, _ = user
    admin, _ = await make_member(session, tenant, MemberRole.admin)
    _, license_row = await _seed_asset_with_license(
        session, tenant, responsible_id=owner.id, days_left=-1
    )

    strategy = LicenseExpiredStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {})

    recipients = {c.recipient_user_id for c in candidates}
    assert recipients == {owner.id, admin.id}
    assert all(
        c.dedup_key == f"license_expired:{license_row.id}:{c.recipient_user_id}"
        for c in candidates
    )


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_expired_license_without_admins_still_notifies_responsible(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """An organization WITHOUT any admin still notifies the responsible person.

    Regression guard: the strategy must NOT copy workload_imbalance's
    ``if not admins: return []`` early-return.
    """

    from app.alerts.strategies.license_expired import LicenseExpiredStrategy

    owner, _ = user
    await _seed_asset_with_license(session, tenant, responsible_id=owner.id, days_left=-3)

    strategy = LicenseExpiredStrategy()
    candidates = await strategy.evaluate(session, tenant.id, {})

    assert len(candidates) == 1
    assert candidates[0].recipient_user_id == owner.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repeated_expired_evaluation_does_not_duplicate(
    session: AsyncSession, tenant: Organization, user
) -> None:
    """Running the full evaluator twice creates exactly ONE notification per recipient."""

    from app.alerts.evaluator import evaluate_organization
    from app.modules.alert_rules.models import AlertRule

    owner, _ = user
    await _seed_asset_with_license(session, tenant, responsible_id=owner.id, days_left=-1)

    session.add(
        AlertRule(
            organization_id=tenant.id,
            rule_type="license_expired",
            enabled=True,
            threshold_params={},
        )
    )
    await session.flush()

    created_first = await evaluate_organization(session, tenant.id)
    assert created_first == 1

    created_second = await evaluate_organization(session, tenant.id)
    assert created_second == 0


# ---------------------------------------------------------------------------
# Registry + seed idempotente
# ---------------------------------------------------------------------------


def test_license_strategies_are_registered() -> None:
    """The registry exposes both license rule types among the registered ones."""

    from app.alerts.registry import get_strategy, registered_rule_types

    assert {"license_expiring", "license_expired"} <= set(registered_rule_types())
    assert get_strategy("license_expiring").rule_type == "license_expiring"
    assert get_strategy("license_expired").rule_type == "license_expired"
