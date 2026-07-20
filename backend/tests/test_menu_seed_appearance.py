"""Seed contract for the "Apariencia" menu entry (feat/org-theme): a child
of "Administración" at ``/settings/appearance``, granted ONLY to ADMIN (via
the ``"*"`` wildcard — deliberately absent from MANAGER/MEMBER). Pure-unit
tests — ``_ensure_menus``/``_ensure_role_menus`` insert any missing seed row
on the next startup, so asserting the seed content is what guards the feature.
"""

from app.db_init import _MENU_SEED, _ROLE_MENU_SEED


def test_menu_seed_has_appearance_entry_under_administracion() -> None:
    entry = next((row for row in _MENU_SEED if row[0] == "Apariencia"), None)
    assert entry is not None
    name, icon, path, parent, order = entry
    assert path == "/settings/appearance"
    assert parent == "Administración"
    assert order == 4
    assert icon == "palette"


def test_appearance_menu_is_granted_only_to_admin() -> None:
    # ADMIN receives every menu via the wildcard grant.
    assert _ROLE_MENU_SEED["ADMIN"] == "*"
    # MANAGER/MEMBER must NOT see the theme editor entry.
    for role_code in ("MANAGER", "MEMBER"):
        grants = _ROLE_MENU_SEED[role_code]
        assert isinstance(grants, list)
        assert "Apariencia" not in grants
