"""String enums shared across the domain.

Each enum subclasses ``str`` so values serialize transparently to JSON and are
stored as their literal value in Postgres.
"""

from enum import Enum


class Methodology(str, Enum):
    """Project methodology that drives board behaviour via a Strategy."""

    planner = "planner"
    kanban = "kanban"
    scrum = "scrum"
    custom = "custom"


class ProjectStatus(str, Enum):
    """Lifecycle status of a project."""

    active = "active"
    archived = "archived"


class TaskStatus(str, Enum):
    """Generic task status used by board columns."""

    todo = "todo"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class TaskType(str, Enum):
    """Type of work item."""

    task = "task"
    bug = "bug"
    story = "story"
    epic = "epic"


class Priority(str, Enum):
    """Relative priority of a work item."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MemberRole(str, Enum):
    """Role of a user within an organization."""

    admin = "admin"
    manager = "manager"
    member = "member"
    viewer = "viewer"


class EstimationMode(str, Enum):
    """Supported estimation strategy for a methodology."""

    none = "none"
    points = "points"
    hours = "hours"
    both = "both"


class NotificationStatus(str, Enum):
    """Lifecycle status of an in-app notification."""

    active = "active"
    read = "read"
    resolved = "resolved"
    silenced = "silenced"


class ReminderStatus(str, Enum):
    """Lifecycle status of a manual reminder."""

    scheduled = "scheduled"
    fired = "fired"
    skipped = "skipped"
    cancelled = "cancelled"


class AssetType(str, Enum):
    """Category of an information asset (first axis of its taxonomy)."""

    hardware = "hardware"
    software = "software"
    saas_subscription = "saas_subscription"
    information = "information"
    service = "service"
    certificate = "certificate"


class AssetStatus(str, Enum):
    """Lifecycle status of an information asset."""

    active = "active"
    inactive = "inactive"
    retired = "retired"
    under_review = "under_review"


class AssetCriticality(str, Enum):
    """Criticality of an information asset.

    A dedicated enum, deliberately NOT reusing ``Priority`` (design.md,
    "Enums native_enum=False") — assets and tasks are separate domains even
    though the value sets happen to overlap.
    """

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class LicenseType(str, Enum):
    """Commercial type of an ``AssetLicense``."""

    perpetual = "perpetual"
    subscription = "subscription"
    trial = "trial"
