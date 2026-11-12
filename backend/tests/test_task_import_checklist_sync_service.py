"""C01: reusable checklist sync service (extracted from scripts.import_sdm_tasks), with fakes."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.db_init  # noqa: F401  (Task() needs every mapper registered)
from app.modules.task_import.checklist_apply import ChecklistTargetError
from app.modules.task_import.checklist_sync_service import (
    ChecklistMemberError,
    ChecklistOrganizationError,
    ChecklistSourceError,
    ChecklistSyncConfig,
    ChecklistSyncOptions,
    load_checklist_plan,
    run_checklist_sync,
)
from tests.test_task_import_checklist_apply import HEADER, ORG, ROW, FakeStore, FakeUow


class FakeSyncUow(FakeUow):
    """FakeUow plus the organization lookup and the read-only marker."""

    def __init__(self, store, *, active=True, members=None):
        super().__init__(store)
        self.organization = SimpleNamespace(id=ORG, slug="sdmujer", is_active=active)
        self.read_only = False
        members = members or {}
        store.find_member = self._find_member(members)

    @staticmethod
    def _find_member(members):
        async def find_member(organization_id, email):
            return members.get(email) if organization_id == ORG else None

        return find_member

    async def find_organization(self, slug):
        return self.organization if slug == self.organization.slug else None

    async def begin_read_only(self):
        self.read_only = True


def _csv(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "CHECKLIST_TAREAS.csv"
    path.write_text("\n".join((HEADER, *rows)) + "\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_dry_run_classifies_without_writing(tmp_path):
    store = FakeStore()
    uow = FakeSyncUow(store)
    plan = load_checklist_plan(_csv(tmp_path, ROW))
    result = await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions())
    assert result.mode == "dry-run" and uow.read_only and uow.commits == 0
    assert result.counts["outcomes"] == {"create": 1} and result.applied is None
    assert store.tasks == {} and uow.rollbacks == 1
    assert result.organization == {"slug": "sdmujer", "id": str(ORG)}


@pytest.mark.asyncio
async def test_apply_writes_and_reports_typed_counts(tmp_path):
    store = FakeStore()
    uow = FakeSyncUow(store)
    plan = load_checklist_plan(_csv(tmp_path, ROW))
    result = await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions(apply=True))
    assert result.mode == "apply" and not uow.read_only
    assert result.counts["applied"]["created"] == 1 and len(store.tasks) == 1
    again = await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions(apply=True))
    assert again.counts["applied"]["unchanged"] == 1 and again.counts["applied"]["created"] == 0


@pytest.mark.asyncio
async def test_update_existing_overwrites_changed_rows(tmp_path):
    store = FakeStore()
    uow = FakeSyncUow(store)
    await run_checklist_sync(
        uow, "sdmujer", load_checklist_plan(_csv(tmp_path, ROW)), ChecklistSyncOptions(apply=True)
    )
    revised = load_checklist_plan(_csv(tmp_path, ROW.replace("PENDIENTE", "EN CURSO")))
    result = await run_checklist_sync(
        uow, "sdmujer", revised, ChecklistSyncOptions(apply=True, update_existing=True)
    )
    assert result.counts["applied"]["updated"] == 1


@pytest.mark.asyncio
async def test_report_keeps_the_cli_shape(tmp_path):
    uow = FakeSyncUow(FakeStore())
    plan = load_checklist_plan(_csv(tmp_path, ROW))
    result = await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions())
    report = result.report(database="127.0.0.1:55432/x")
    assert report["mode"] == "dry-run" and report["database"] == "127.0.0.1:55432/x"
    assert report["counts"]["outcomes"] == {"create": 1}
    assert report["tasks"][0]["id"] == "T-01"


@pytest.mark.asyncio
async def test_unknown_or_inactive_organization_is_rejected(tmp_path):
    plan = load_checklist_plan(_csv(tmp_path, ROW))
    with pytest.raises(ChecklistOrganizationError):
        await run_checklist_sync(FakeSyncUow(FakeStore()), "otra", plan, ChecklistSyncOptions())
    inactive = FakeSyncUow(FakeStore(), active=False)
    with pytest.raises(ChecklistOrganizationError):
        await run_checklist_sync(inactive, "sdmujer", plan, ChecklistSyncOptions())
    assert inactive.rollbacks == 1


@pytest.mark.asyncio
async def test_actor_must_be_an_active_member(tmp_path):
    plan = load_checklist_plan(_csv(tmp_path, ROW))
    with pytest.raises(ChecklistMemberError) as caught:
        await run_checklist_sync(
            FakeSyncUow(FakeStore()),
            "sdmujer",
            plan,
            ChecklistSyncOptions(apply=True, actor_email="nadie@x.co"),
        )
    assert caught.value.email == "nadie@x.co"
    actor = uuid.uuid4()
    store = FakeStore()
    uow = FakeSyncUow(store, members={"ana@x.co": actor})
    await run_checklist_sync(
        uow, "sdmujer", plan, ChecklistSyncOptions(apply=True, actor_email="ana@x.co")
    )
    assert len(store.tasks) == 1


@pytest.mark.asyncio
async def test_apply_with_missing_target_raises_before_writing(tmp_path):
    plan = load_checklist_plan(_csv(tmp_path, "T-02;PENDIENTE;No;ALTA;MIPG;A;;;x;No;"))
    store = FakeStore()
    uow = FakeSyncUow(store)
    dry = await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions())
    assert dry.missing and store.tasks == {}
    with pytest.raises(ChecklistTargetError):
        await run_checklist_sync(uow, "sdmujer", plan, ChecklistSyncOptions(apply=True))
    assert store.tasks == {}


@pytest.mark.asyncio
async def test_unreadable_source_raises_source_error(tmp_path):
    bad = tmp_path / "vacío.csv"
    bad.write_bytes(b"")
    with pytest.raises(ChecklistSourceError):
        load_checklist_plan(bad)
    with pytest.raises(ChecklistSourceError):
        load_checklist_plan(tmp_path / "no-existe.csv")


@pytest.mark.asyncio
async def test_tareas_root_only_lists_work_folders(tmp_path):
    root = tmp_path / "TAREAS"
    (root / "T-01_Algo").mkdir(parents=True)
    plan = load_checklist_plan(_csv(tmp_path, ROW), tareas_root=root)
    assert plan.drafts[0].work_folder


def test_config_from_settings_is_disabled_when_empty():
    empty = SimpleNamespace(
        CHECKLIST_SYNC_PATH="",
        CHECKLIST_SYNC_TAREAS_ROOT="",
        CHECKLIST_SYNC_ORG_SLUG="",
        CHECKLIST_SYNC_ACTOR_EMAIL="",
        CHECKLIST_SYNC_UPDATE_EXISTING=True,
    )
    assert ChecklistSyncConfig.from_settings(empty) is None
    full = SimpleNamespace(
        **{**vars(empty), "CHECKLIST_SYNC_PATH": "/x/c.csv", "CHECKLIST_SYNC_ORG_SLUG": "sdmujer"}
    )
    config = ChecklistSyncConfig.from_settings(full)
    assert config.organization_slug == "sdmujer" and config.path == Path("/x/c.csv")
    assert config.tareas_root is None and config.actor_email is None
    assert config.update_existing is True


def test_settings_expose_checklist_sync_defaults():
    from app.config import Settings

    current = Settings(_env_file=None)
    assert current.CHECKLIST_SYNC_PATH == "" and current.CHECKLIST_SYNC_ORG_SLUG == ""
    assert current.CHECKLIST_SYNC_TAREAS_ROOT == "" and current.CHECKLIST_SYNC_ACTOR_EMAIL == ""
    assert current.CHECKLIST_SYNC_UPDATE_EXISTING is True
