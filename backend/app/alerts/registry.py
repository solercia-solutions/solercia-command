"""Alert strategy registry and factory."""
from app.alerts.base import AlertStrategy
from app.alerts.strategies.blocked_task import BlockedTaskStrategy
from app.alerts.strategies.license_expired import LicenseExpiredStrategy
from app.alerts.strategies.license_expiring import LicenseExpiringStrategy
from app.alerts.strategies.sprint_at_risk import SprintAtRiskStrategy
from app.alerts.strategies.task_at_risk import TaskAtRiskStrategy
from app.alerts.strategies.task_overdue import TaskOverdueStrategy
from app.alerts.strategies.workload_imbalance import WorkloadImbalanceStrategy

_STRATEGIES: dict[str, type[AlertStrategy]] = {
    "task_overdue": TaskOverdueStrategy,
    "task_at_risk": TaskAtRiskStrategy,
    "sprint_at_risk": SprintAtRiskStrategy,
    "workload_imbalance": WorkloadImbalanceStrategy,
    "blocked_task": BlockedTaskStrategy,
    "license_expiring": LicenseExpiringStrategy,
    "license_expired": LicenseExpiredStrategy,
}


def get_strategy(rule_type: str) -> AlertStrategy | None:
    cls = _STRATEGIES.get(rule_type)
    return cls() if cls else None


def registered_rule_types() -> list[str]:
    return list(_STRATEGIES.keys())
