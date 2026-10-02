"""Seed contract for the «Planes» menu entry (change 45c, design.md D13 of 45a).

A top-level item at ``/plans`` with the free ``order`` 7 (after «Conexiones»),
granted to MANAGER and MEMBER (read-only: every ``GET /plans...`` route is open
to any member; writes stay admin/manager in the backend RBAC). ADMIN keeps the
``"*"`` wildcard. Pure-unit tests: no database.
"""

import re
from pathlib import Path

from app.db_init import _MENU_SEED, _ROLE_MENU_SEED

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_menu_seed_has_top_level_plans_entry() -> None:
    entry = next((row for row in _MENU_SEED if row[0] == "Planes"), None)
    assert entry is not None
    _name, icon, path, parent, order = entry
    assert path == "/plans"
    assert parent is None
    assert order == 7
    assert icon == "clipboard-list"
    # The free slot: no other top-level entry shares order 7.
    assert [row[0] for row in _MENU_SEED if row[3] is None and row[4] == 7] == ["Planes"]


def test_plans_menu_is_granted_to_manager_and_member() -> None:
    assert _ROLE_MENU_SEED["ADMIN"] == "*"
    for role_code in ("MANAGER", "MEMBER"):
        grants = _ROLE_MENU_SEED[role_code]
        assert isinstance(grants, list)
        assert "Planes" in grants


def test_plans_menu_points_to_an_existing_frontend_route() -> None:
    """The sidebar never links to a route the SPA does not declare (D13)."""

    routes = (REPO_ROOT / "frontend" / "src" / "app" / "app.routes.ts").read_text()
    assert re.search(r"""path:\s*['"]plans['"]""", routes)


def test_plans_menu_icon_has_a_sidebar_alias() -> None:
    icons = (
        REPO_ROOT / "frontend" / "src" / "widgets" / "sidebar" / "ui" / "sidebar-icons.ts"
    ).read_text()
    assert "'clipboard-list': 'clipboard'" in icons
