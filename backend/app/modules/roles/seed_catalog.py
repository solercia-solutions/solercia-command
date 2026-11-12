"""Default RBAC catalog: roles, global menus and the menus each role grants.

Single source of truth shared by the startup seed (``app.db_init``, which
re-exports these as ``_ROLE_SEED``/``_MENU_SEED``/``_ROLE_MENU_SEED``) and by
the new-organization bootstrap (O5). Kept dependency-free so the bootstrap
does not import ``db_init`` and, with it, every adapter of the app.
"""

# RBAC roles: (code, display name).
ROLE_SEED: list[tuple[str, str]] = [
    ("ADMIN", "Administrador"),
    ("MANAGER", "Líder"),
    ("MEMBER", "Colaborador"),
]

# App-level activities (menus): (name, icon, path, parent_name, order).
# Parents appear before their children so the parent id is available.
#
# `_ensure_menus` (and `_ensure_role_menus`) run on every startup and only
# INSERT rows that are still missing, so an already-seeded backend picks up
# new entries (like "Jerarquía" below) automatically on its next restart —
# no data migration needed for existing organizations.
MENU_SEED: list[tuple[str, str, str | None, str | None, int]] = [
    ("Proyectos", "folder-kanban", "/projects", None, 0),
    ("Jerarquía", "list-tree", "/hierarchy", None, 1),
    ("Vista de jefe", "bar-chart-3", "/executive", None, 2),
    ("Rendimiento", "trending-up", "/performance", None, 3),
    ("Administración", "settings", None, None, 4),
    ("Equipos", "users", "/teams", None, 5),
    ("Conexiones", "plug", "/connections", None, 6),
    # Planes institucionales (cambio 45c, D13): toma el `order` libre 7 porque
    # renumerar la semilla no afecta a una base ya sembrada. Lectura para
    # MEMBER (la API de planes permite GET a cualquier miembro); la escritura
    # la sigue decidiendo el RBAC del backend (admin/manager).
    ("Planes", "clipboard-list", "/plans", None, 7),
    ("Usuarios", "users", "/admin/users", "Administración", 0),
    ("Roles", "shield", "/admin/roles", "Administración", 1),
    ("Actividades", "list", "/admin/menus", "Administración", 2),
    ("Dependencias", "building-2", "/admin/dependencies", "Administración", 3),
    # Editor del tema por organización (feat/org-theme). Solo lo ve ADMIN:
    # `ROLE_MENU_SEED["ADMIN"] = "*"` lo cubre y NO se agrega a las listas
    # de MANAGER/MEMBER a propósito.
    ("Apariencia", "palette", "/settings/appearance", "Administración", 4),
    # Clasificador de correo (C06). La bandeja la usan ADMIN y MANAGER (el API
    # de propuestas admite ambos). Sincronización e IA cuelgan de
    # "Administración" y solo los ve ADMIN por el comodín: el API de /sync es
    # solo admin y el manager lee /settings/ai por URL, sin escribir.
    ("Bandeja de seguimiento", "envelope", "/intake/proposals", None, 8),
    ("Sincronización", "refresh", "/sync", "Administración", 5),
    ("Inteligencia artificial", "cpu-chip", "/settings/ai", "Administración", 6),
]

# Menu grants per role. "*" grants every menu.
ROLE_MENU_SEED: dict[str, str | list[str]] = {
    "ADMIN": "*",
    "MANAGER": [
        "Proyectos",
        "Jerarquía",
        "Vista de jefe",
        "Rendimiento",
        "Equipos",
        "Conexiones",
        "Planes",
        "Bandeja de seguimiento",
    ],
    "MEMBER": ["Proyectos", "Jerarquía", "Planes"],
}

#: Role assigned to the creator of a new organization.
ADMIN_ROLE_CODE = "ADMIN"
