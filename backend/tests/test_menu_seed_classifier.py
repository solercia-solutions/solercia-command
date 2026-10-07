"""Seed contract for the C06 screens: «Bandeja de seguimiento» (top level,
ADMIN + MANAGER), «Sincronización» and «Inteligencia artificial» (children
of "Administración", ADMIN only through the ``"*"`` wildcard). The startup
seed only inserts missing rows, so asserting the seed content guards the
menu (same approach as ``test_menu_seed_appearance.py``).
"""

from app.db_init import _MENU_SEED, _ROLE_MENU_SEED


def _entry(name: str) -> tuple:
    entry = next((row for row in _MENU_SEED if row[0] == name), None)
    assert entry is not None, name
    return entry


def test_classifier_screens_are_seeded_with_their_paths() -> None:
    assert _entry("Bandeja de seguimiento")[1:] == ("envelope", "/intake/proposals", None, 8)
    assert _entry("Sincronización")[1:] == ("refresh", "/sync", "Administración", 5)
    assert _entry("Inteligencia artificial")[1:] == (
        "cpu-chip",
        "/settings/ai",
        "Administración",
        6,
    )


def test_orders_do_not_collide_with_siblings() -> None:
    for parent in (None, "Administración"):
        orders = [row[4] for row in _MENU_SEED if row[3] == parent]
        assert len(orders) == len(set(orders)), parent


def test_grants_follow_the_api_roles() -> None:
    assert _ROLE_MENU_SEED["ADMIN"] == "*"
    manager = _ROLE_MENU_SEED["MANAGER"]
    member = _ROLE_MENU_SEED["MEMBER"]
    assert isinstance(manager, list) and isinstance(member, list)
    assert "Bandeja de seguimiento" in manager
    for name in ("Sincronización", "Inteligencia artificial"):
        assert name not in manager
    for name in ("Bandeja de seguimiento", "Sincronización", "Inteligencia artificial"):
        assert name not in member
