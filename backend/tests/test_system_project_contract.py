"""Pure domain contract; no ORM construction or database fixtures."""

import pytest


def test_generales_definition_is_immutable_and_done_last():
    from app.modules.projects.system_project import GENERALES

    assert GENERALES.code == "GENERALES"
    assert GENERALES.methodology == "custom"
    assert GENERALES.statuses == (
        "PENDIENTE", "EN CURSO", "DIFERIDA", "RECURRENTE",
        "GESTIONADA APARTE", "REMOVIDA", "COMPLETADA",
    )
    with pytest.raises(AttributeError):
        GENERALES.code = "OTHER"


@pytest.mark.parametrize("field,value", [
    ("code", "OTHER"), ("methodology", "planner"), ("status", "archived"),
    ("is_active", False), ("deleted_at", "synthetic"), ("is_system", False),
])
def test_system_identity_and_lifecycle_guard(field, value):
    from app.modules.projects.system_project import guard_system_project_update
    from app.shared.exceptions import AppException

    with pytest.raises(AppException) as error:
        guard_system_project_update(True, {field: value})
    assert error.value.code == "system_project_protected"
    guard_system_project_update(False, {field: value})
