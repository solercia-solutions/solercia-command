"""Seed contract for the "Conexiones" menu entry (Conexiones page): a
top-level item at ``/connections`` right after "Equipos", granted to
MANAGER (ADMIN already receives every menu via ``"*"``). Pure-unit tests —
``_ensure_menus``/``_ensure_role_menus`` insert any missing seed row on the
next startup, so asserting the seed content is what guards the feature.
"""

from app.db_init import _MENU_SEED, _ROLE_MENU_SEED


def test_menu_seed_has_top_level_connections_entry() -> None:
    entry = next((row for row in _MENU_SEED if row[0] == "Conexiones"), None)
    assert entry is not None
    name, icon, path, parent, order = entry
    assert path == "/connections"
    assert parent is None
    assert order == 6
    assert icon == "plug"


def test_manager_role_is_granted_connections_menu() -> None:
    manager_menus = _ROLE_MENU_SEED["MANAGER"]
    assert isinstance(manager_menus, list)
    assert "Conexiones" in manager_menus
    # ADMIN keeps the wildcard grant — no explicit entry needed.
    assert _ROLE_MENU_SEED["ADMIN"] == "*"
