"""Real service methods with scoped fake repositories, no ORM instances.

Methodology enrichment is stubbed: its SQL adapter is not under test. All
imports are inside tests/fixtures to avoid collection-time mapper effects.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.fixture
def project_service(monkeypatch):
    import app.modules.projects.service as module
    from app.modules.projects.service import ProjectService

    monkeypatch.setattr(module, "Project", lambda **kw: SimpleNamespace(**kw))

    org, pid = uuid4(), uuid4()
    project = SimpleNamespace(id=pid, is_system=True, code="GENERALES", name="Generales")
    db = SimpleNamespace(add=lambda obj: None, flush=AsyncMock())
    repo = SimpleNamespace(db=db, save=AsyncMock(side_effect=lambda p: p),
                           code_exists=AsyncMock(return_value=False))

    async def get(scope, identity):
        return project if (scope, identity) == (org, pid) else None

    repo.get = get
    service = ProjectService(repo.db)
    service.repo = repo
    monkeypatch.setattr(service, "_attach_methodology_info", AsyncMock())
    return service, project, org, pid


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["GENERALES", "generales", "Generales "])
async def test_public_create_reserves_code_before_persistence(project_service, code):
    from app.modules.projects.schemas import ProjectCreate
    from app.shared.exceptions import AppException

    service, _, org, _ = project_service
    with pytest.raises(AppException) as error:
        await service.create_project(org, ProjectCreate(name="Synthetic", code=code, methodology="custom"))
    assert error.value.code == "reserved_project_code"
    service.repo.code_exists.assert_not_awaited()
    service.repo.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"code": "OTHER"}, {"methodology": "planner"}])
async def test_system_update_rejected_before_save(project_service, changes):
    from app.modules.projects.schemas import ProjectUpdate
    from app.shared.exceptions import AppException

    service, project, org, pid = project_service
    with pytest.raises(AppException) as error:
        await service.update_project(org, pid, ProjectUpdate(**changes))
    assert error.value.code == "system_project_protected"
    assert project.code == "GENERALES"
    service.repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_project_cannot_claim_reserved_code(project_service):
    from app.modules.projects.schemas import ProjectUpdate
    from app.shared.exceptions import AppException

    service, project, org, pid = project_service
    project.is_system = False
    with pytest.raises(AppException) as error:
        await service.update_project(org, pid, ProjectUpdate(code="generales"))
    assert error.value.code == "reserved_project_code"
    service.repo.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("system", [False, True])
async def test_name_edit_still_allowed(project_service, system):
    from app.modules.projects.schemas import ProjectUpdate

    service, project, org, pid = project_service
    project.is_system = system
    result = await service.update_project(org, pid, ProjectUpdate(name="Nuevo nombre"))
    assert result.name == "Nuevo nombre"
    service.repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_ordinary_custom_creation_stays_empty_and_non_system(project_service, monkeypatch):
    import app.modules.projects.service as module
    from app.modules.projects.schemas import ProjectCreate

    service, _, org, _ = project_service
    seeded = []

    def project_factory(**kwargs):
        return SimpleNamespace(id=uuid4(), is_system=False, **kwargs)

    async def seed(project_id, strategy):
        seeded.append(strategy.default_columns())

    monkeypatch.setattr(module, "Project", project_factory)
    monkeypatch.setattr(module, "BoardService", lambda db: SimpleNamespace(seed_board=seed))
    result = await service.create_project(org, ProjectCreate(name="Synthetic", methodology="custom"))
    assert result.code == "SYNTHE" and result.is_system is False
    assert result.organization_id == org
    assert seeded == [[]]
    service.repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_ordinary_update_and_methodology_error_unchanged(project_service):
    from app.modules.projects.schemas import ProjectUpdate
    from app.shared.exceptions import AppException

    service, project, org, pid = project_service
    project.is_system = False
    await service.update_project(org, pid, ProjectUpdate(code="OTHER"))
    assert project.code == "OTHER"
    with pytest.raises(AppException) as error:
        await service.update_project(org, pid, ProjectUpdate(methodology="planner"))
    assert error.value.code == "methodology_not_editable"
    assert service.repo.save.await_count == 1


@pytest.mark.asyncio
async def test_cross_tenant_update_stays_not_found(project_service):
    from app.modules.projects.schemas import ProjectUpdate
    from app.shared.exceptions import AppException

    service, _, _, pid = project_service
    with pytest.raises(AppException) as error:
        await service.update_project(uuid4(), pid, ProjectUpdate(code="OTHER"))
    assert error.value.code == "project_not_found"
    service.repo.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "reorder", "add", "remove"])
@pytest.mark.parametrize("system", [True, False])
async def test_board_configuration_guard_preserves_ordinary_custom(monkeypatch, operation, system):
    import app.modules.boards.service as module
    from app.shared.exceptions import AppException

    org, bid, pid = uuid4(), uuid4(), uuid4()
    columns = [SimpleNamespace(id=uuid4(), name=name, order=i, status_key=name)
               for i, name in enumerate(("One", "Two"))]
    board = SimpleNamespace(id=bid, project_id=pid)
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock(), add=lambda obj: None)

    async def scoped_board(scope, identity):
        assert (scope, identity) == (org, bid)
        return board

    async def scoped_project(scope, identity):
        assert (scope, identity) == (org, pid)
        return SimpleNamespace(is_system=system)

    monkeypatch.setattr(module, "ProjectRepository", lambda session: SimpleNamespace(get=scoped_project), raising=False)
    monkeypatch.setattr(module, "BoardColumn", lambda **kw: SimpleNamespace(**kw))
    service = module.BoardService(db)
    service.repo = SimpleNamespace(db=db, get_board_scoped=scoped_board,
        get_column=AsyncMock(return_value=columns[0]), list_columns=AsyncMock(return_value=columns),
        count_active_tasks_in_column=AsyncMock(return_value=0))
    calls = {
        "rename": lambda: service.rename_column(org, bid, columns[0].id, "Renamed", actor_id=None),
        "reorder": lambda: service.reorder_columns(org, bid, [c.id for c in reversed(columns)], actor_id=None),
        "add": lambda: service.add_column(org, bid, "Extra", None, actor_id=None),
        "remove": lambda: service.remove_column(org, bid, columns[0].id, None, actor_id=None),
    }
    if system:
        with pytest.raises(AppException) as error:
            await calls[operation]()
        assert error.value.code == "system_project_protected"
        assert columns[0].name == "One" and columns[0].order == 0
        db.commit.assert_not_awaited()
    else:
        await calls[operation]()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cross_tenant_board_does_not_reach_project_lookup(monkeypatch):
    import app.modules.boards.service as module
    from app.shared.exceptions import AppException

    def unexpected_lookup(db):
        raise AssertionError("Project lookup must follow board authorization")

    monkeypatch.setattr(module, "ProjectRepository", unexpected_lookup)
    service = module.BoardService(SimpleNamespace())
    service.repo = SimpleNamespace(get_board_scoped=AsyncMock(return_value=None))
    with pytest.raises(AppException) as error:
        await service.rename_column(uuid4(), uuid4(), uuid4(), "Other", actor_id=None)
    assert error.value.code == "board_not_found"
