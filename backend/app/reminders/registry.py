"""Reminder rule strategy registry and factory — mirrors app/alerts/registry.py."""
from app.reminders.base import ReminderRuleStrategy
from app.reminders.strategies.task_due_soon import TaskDueSoonStrategy

_STRATEGIES: dict[str, type[ReminderRuleStrategy]] = {
    "task_due_soon": TaskDueSoonStrategy,
}


def get_strategy(rule_type: str) -> ReminderRuleStrategy | None:
    cls = _STRATEGIES.get(rule_type)
    return cls() if cls else None


def registered_rule_types() -> list[str]:
    return list(_STRATEGIES.keys())
