"""Unit tests for BoardAwareStrategy (no DB) — Batch B, T10.

``allowed_statuses()`` must prefer the persisted ``status_key`` values and
fall back to the base strategy only when empty; every other flag always
delegates to the base (design.md D1).
"""

from app.methodology.base import MethodologyStrategy
from app.methodology.board_aware import BoardAwareStrategy


class _FakeStrategy(MethodologyStrategy):
    """A minimal concrete strategy standing in for a real methodology."""

    name = "fake"

    def default_columns(self) -> list[str]:
        return ["A", "B"]

    def allowed_statuses(self) -> list[str]:
        return ["A", "B"]

    @property
    def sprints_enabled(self) -> bool:
        return True

    @property
    def estimation_mode(self) -> str:
        return "points"

    @property
    def has_backlog(self) -> bool:
        return True


def test_allowed_statuses_uses_persisted_status_keys_when_present() -> None:
    wrapper = BoardAwareStrategy(_FakeStrategy(), ["todo", "doing"])
    assert wrapper.allowed_statuses() == ["todo", "doing"]


def test_allowed_statuses_falls_back_to_base_when_status_keys_empty() -> None:
    wrapper = BoardAwareStrategy(_FakeStrategy(), [])
    assert wrapper.allowed_statuses() == ["A", "B"]


def test_flags_and_default_columns_always_delegate_to_base() -> None:
    wrapper = BoardAwareStrategy(_FakeStrategy(), ["todo"])
    assert wrapper.sprints_enabled is True
    assert wrapper.estimation_mode == "points"
    assert wrapper.has_backlog is True
    assert wrapper.default_columns() == ["A", "B"]
    assert wrapper.name == "fake"


def test_to_info_reflects_status_keys_not_base_allowed_statuses() -> None:
    """to_info() composes allowed_statuses() — must show the persisted columns."""

    wrapper = BoardAwareStrategy(_FakeStrategy(), ["custom_todo", "custom_done"])
    info = wrapper.to_info()
    assert info["allowed_statuses"] == ["custom_todo", "custom_done"]
    assert info["default_columns"] == ["A", "B"]
    assert info["methodology"] == "fake"
