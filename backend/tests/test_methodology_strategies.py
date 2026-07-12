"""Tests for the methodology Strategy pattern (app/methodology/).

R1 estados validados por la strategy · R2 factory 422 ante metodología
inválida · R3 sprints solo si ``sprints_enabled`` · R4 ``to_info()`` expone
el contrato completo (openspec/specs/methodology-strategies/spec.md).

Unit puro (sin BD) para R1/R2/R4; integración mínima para R3 (requiere el
endpoint de sprints). ``custom`` solo se prueba en su parte estática — su
``allowed_statuses()`` board-aware ya está cubierto por
``test_board_aware_strategy.py``/``test_board_column_config.py``.
"""

import pytest
from httpx import AsyncClient

from app.shared.exceptions import AppException
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1/R4 — Contrato fijo de planner/kanban/scrum
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected_columns,sprints_enabled,estimation_mode,has_backlog",
    [
        (
            "planner",
            ["Sin iniciar", "En curso", "Completada"],
            False,
            "none",
            False,
        ),
        ("kanban", ["Backlog", "Doing", "Done"], False, "hours", False),
        (
            "scrum",
            ["To Do", "In Progress", "In Review", "Done"],
            True,
            "points",
            True,
        ),
    ],
)
def test_fixed_methodology_contract(
    name: str,
    expected_columns: list[str],
    sprints_enabled: bool,
    estimation_mode: str,
    has_backlog: bool,
) -> None:
    """Each fixed methodology exposes its documented columns/statuses/flags,
    and ``allowed_statuses()`` equals ``default_columns()`` (no board yet).
    """

    from app.methodology.factory import get_strategy

    strategy = get_strategy(name)

    assert strategy.default_columns() == expected_columns
    assert strategy.allowed_statuses() == expected_columns
    assert strategy.sprints_enabled is sprints_enabled
    assert strategy.estimation_mode == estimation_mode
    assert strategy.has_backlog is has_backlog


@pytest.mark.parametrize("name", ["planner", "kanban", "scrum", "custom"])
def test_to_info_exposes_full_contract_shape(name: str) -> None:
    """``to_info()`` returns every field the frontend needs, keyed correctly."""

    from app.methodology.factory import get_strategy

    strategy = get_strategy(name)

    info = strategy.to_info()

    assert info == {
        "methodology": name,
        "default_columns": strategy.default_columns(),
        "allowed_statuses": strategy.allowed_statuses(),
        "sprints_enabled": strategy.sprints_enabled,
        "estimation_mode": strategy.estimation_mode,
        "has_backlog": strategy.has_backlog,
    }


# ---------------------------------------------------------------------------
# custom — solo la parte ESTÁTICA (su allowed_statuses() board-aware no se duplica)
# ---------------------------------------------------------------------------


def test_custom_strategy_static_contract() -> None:
    """``custom`` starts with empty columns/statuses and every flag off."""

    from app.methodology.factory import get_strategy

    strategy = get_strategy("custom")

    assert strategy.default_columns() == []
    assert strategy.allowed_statuses() == []
    assert strategy.sprints_enabled is False
    assert strategy.estimation_mode == "none"
    assert strategy.has_backlog is False


# ---------------------------------------------------------------------------
# R2 — Factory 422 ante metodología inválida
# ---------------------------------------------------------------------------


def test_get_strategy_rejects_unknown_methodology() -> None:
    """``get_strategy("xp")`` raises ``AppException`` with ``status_code=422``."""

    from app.methodology.factory import get_strategy

    with pytest.raises(AppException) as exc_info:
        get_strategy("xp")

    assert exc_info.value.status_code == 422


def test_get_strategy_accepts_the_methodology_enum_member() -> None:
    """``get_strategy`` also accepts a ``Methodology`` enum member directly."""

    from app.methodology.factory import get_strategy
    from app.shared.enums import Methodology

    strategy = get_strategy(Methodology.scrum)

    assert strategy.name == "scrum"


# ---------------------------------------------------------------------------
# R3 — Sprint rechazado si sprints_enabled=False (kanban)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sprint_creation_rejected_when_methodology_disables_sprints(
    client: AsyncClient, tenant, user
) -> None:
    """Creating a sprint on a ``kanban`` project (``sprints_enabled=False``)
    is rejected with 422.
    """

    _, token = user
    project = await client.post(
        "/projects",
        json={"name": "Kanban Project", "methodology": "kanban"},
        headers=_auth(token),
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Sprint 1"},
        headers=_auth(token),
    )

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sprint_creation_allowed_when_methodology_enables_sprints(
    client: AsyncClient, tenant, user
) -> None:
    """Creating a sprint on a ``scrum`` project (``sprints_enabled=True``) succeeds."""

    _, token = user
    project = await client.post(
        "/projects",
        json={"name": "Scrum Project", "methodology": "scrum"},
        headers=_auth(token),
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]

    response = await client.post(
        f"/projects/{project_id}/sprints",
        json={"name": "Sprint 1"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
