"""Tests for the optional ``?project_kind=`` filter on ``GET /projects``
(change 27-plantillas-idempotentes, specs/projects/spec.md delta, "Filtro
opcional project_kind en el listado").
"""

import pytest
from httpx import AsyncClient

from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_by_area_returns_only_area_projects(
    client: AsyncClient, session, tenant, user
) -> None:
    """``GET /projects?project_kind=area`` incluye ÚNICAMENTE los proyectos
    ``area`` de la organización — spec 'Filtro por area devuelve solo
    contenedores'. Sembrado directo (sin plantilla) via ORM ya que
    ``POST /projects`` siempre fuerza ``proyecto`` (Fase 1/4.6)."""

    from app.modules.projects.models import Project
    from app.shared.enums import Methodology, ProjectKind

    _, token = user

    area_project = Project(
        organization_id=tenant.id,
        name="Area Sembrada",
        methodology=Methodology.planner,
        code="AREA0",
        task_counter=0,
        project_kind=ProjectKind.area,
    )
    session.add(area_project)
    await session.flush()

    created = await client.post(
        "/projects",
        json={"name": "Proyecto Normal", "methodology": "planner"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text

    response = await client.get(
        "/projects", params={"project_kind": "area"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert ids == {str(area_project.id)}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_by_proyecto_returns_only_proyecto_projects(
    client: AsyncClient, session, tenant, user
) -> None:
    """``GET /projects?project_kind=proyecto`` incluye únicamente los
    ``proyecto`` — spec 'Filtro por proyecto devuelve solo trabajo real'."""

    from app.modules.projects.models import Project
    from app.shared.enums import Methodology, ProjectKind

    _, token = user

    area_project = Project(
        organization_id=tenant.id,
        name="Area Sembrada",
        methodology=Methodology.planner,
        code="AREA1",
        task_counter=0,
        project_kind=ProjectKind.area,
    )
    session.add(area_project)
    await session.flush()

    created = await client.post(
        "/projects",
        json={"name": "Proyecto Normal", "methodology": "planner"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    proyecto_id = created.json()["data"]["id"]

    response = await client.get(
        "/projects", params={"project_kind": "proyecto"}, headers=_auth(token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert proyecto_id in ids
    assert str(area_project.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_parameter_returns_every_kind_unchanged(
    client: AsyncClient, session, tenant, user
) -> None:
    """``GET /projects`` sin `project_kind` devuelve TODOS los tipos — spec
    'Sin parámetro el comportamiento no cambia' (no-regresión)."""

    from app.modules.projects.models import Project
    from app.shared.enums import Methodology, ProjectKind

    _, token = user

    area_project = Project(
        organization_id=tenant.id,
        name="Area Sembrada Dos",
        methodology=Methodology.planner,
        code="AREA2",
        task_counter=0,
        project_kind=ProjectKind.area,
    )
    session.add(area_project)
    await session.flush()

    created = await client.post(
        "/projects",
        json={"name": "Proyecto Normal Dos", "methodology": "planner"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    proyecto_id = created.json()["data"]["id"]

    response = await client.get("/projects", headers=_auth(token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert proyecto_id in ids
    assert str(area_project.id) in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invalid_project_kind_value_is_rejected_with_422(
    client: AsyncClient, tenant, user
) -> None:
    """``GET /projects?project_kind=invalido`` responde 422 y no ejecuta el
    listado — spec 'Valor inválido de project_kind se rechaza'."""

    _, token = user

    response = await client.get(
        "/projects", params={"project_kind": "invalido"}, headers=_auth(token)
    )

    assert response.status_code == 422
