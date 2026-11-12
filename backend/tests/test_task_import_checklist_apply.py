"""T05f use case with fakes: classification, idempotence, no silent overwrite, atomicity."""

import uuid
from dataclasses import replace

import pytest

import app.db_init  # noqa: F401  (Task() needs every mapper registered)
from app.modules.task_import.checklist_apply import (
    AnchorState,
    ChecklistTargetError,
    ProjectTarget,
    apply_checklist_plan,
)
from app.modules.task_import.checklist_import import (
    CHECKLIST_SOURCE,
    build_checklist_plan,
)
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot

pytestmark = pytest.mark.asyncio

HEADER = (
    "ID;Estado;Vencido;Urgencia;Categoría;Tarea;Detalle;Fecha Límite;Solicitante;Apoyo IA;"
    "Observaciones"
)
ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()


def _plan(*rows: str):
    data = ("\n".join((HEADER, *rows)) + "\n").encode("utf-8")
    preview = parse_checklist(SourceSnapshot("c.csv", data), ChecklistProfile(), ParseLimits())
    return build_checklist_plan(preview, source_name="c.csv")


class FakeStore:
    """Tenant-scoped in-memory store; anchors survive only after commit."""

    def __init__(self):
        sgsi = ProjectTarget(
            uuid.uuid4(), "SGSI", {"Sin iniciar": uuid.uuid4(), "En curso": uuid.uuid4()}
        )
        self.targets = {ORG: {"SGSI": sgsi}}
        self.tasks: dict[uuid.UUID, dict] = {}
        self.pending: dict[uuid.UUID, dict] = {}
        self.fail_on_create = False

    async def find_anchors(self, organization_id, source, keys):
        assert source == CHECKLIST_SOURCE
        result = {}
        for task_id, task in self.tasks.items():
            if task["org"] == organization_id and task["key"] in keys:
                result[task["key"]] = AnchorState(
                    task_id,
                    task["project_id"],
                    task["project_code"],
                    task["active"],
                    task["title"],
                    task["description"],
                    task["status"],
                    task["priority"],
                    task["due_date"],
                )
        return result

    async def project_targets(self, organization_id, codes):
        return {c: t for c, t in self.targets.get(organization_id, {}).items() if c in codes}

    async def find_member(self, organization_id, email):
        return None

    async def create_task(self, task):
        if self.fail_on_create:
            raise RuntimeError("boom")
        self.pending[task.id] = {
            "org": ORG,
            "key": task.external_key,
            "project_id": task.project_id,
            "project_code": "SGSI",
            "active": True,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority.value,
            "due_date": task.due_date,
        }
        return task

    async def update_task(self, organization_id, task_id, values):
        assert self.tasks[task_id]["org"] == organization_id
        self.pending[task_id] = {
            **self.tasks[task_id],
            **{
                k: (v.value if hasattr(v, "value") else v)
                for k, v in values.items()
                if k in ("title", "description", "status", "priority", "due_date")
            },
        }


class FakeUow:
    def __init__(self, store):
        self.store = store
        self.commits = self.rollbacks = 0

    async def commit(self):
        self.store.tasks.update(self.store.pending)
        self.store.pending = {}
        self.commits += 1

    async def rollback(self):
        self.store.pending = {}
        self.rollbacks += 1


ROW = "T-01;PENDIENTE;No;ALTA;Seguridad;Título;Detalle;2026-05-15;Ana;No;"


async def test_first_run_creates_and_rerun_is_unchanged():
    store = FakeStore()
    uow = FakeUow(store)
    first = await apply_checklist_plan(uow, ORG, _plan(ROW))
    second = await apply_checklist_plan(uow, ORG, _plan(ROW))
    assert (first.created, second.created, second.unchanged) == (["T-01"], [], ["T-01"])
    assert len(store.tasks) == 1 and uow.commits == 2


async def test_changed_row_is_reported_not_overwritten_by_default():
    store = FakeStore()
    uow = FakeUow(store)
    await apply_checklist_plan(uow, ORG, _plan(ROW))
    revised = _plan(ROW.replace("PENDIENTE", "EN CURSO"))
    result = await apply_checklist_plan(uow, ORG, revised)
    assert result.changed_not_applied == ["T-01"]
    assert next(iter(store.tasks.values()))["status"] == "Sin iniciar"
    result = await apply_checklist_plan(uow, ORG, revised, update_existing=True)
    assert result.updated == ["T-01"]
    assert next(iter(store.tasks.values()))["status"] == "En curso"


async def test_soft_deleted_anchor_is_neither_resurrected_nor_duplicated():
    store = FakeStore()
    uow = FakeUow(store)
    await apply_checklist_plan(uow, ORG, _plan(ROW))
    task = next(iter(store.tasks.values()))
    task["active"] = False
    result = await apply_checklist_plan(uow, ORG, _plan(ROW))
    assert result.inactive == ["T-01"] and len(store.tasks) == 1


async def test_anchor_in_another_project_is_not_moved():
    store = FakeStore()
    uow = FakeUow(store)
    await apply_checklist_plan(uow, ORG, _plan(ROW))
    next(iter(store.tasks.values()))["project_code"] = "GENERALES"
    result = await apply_checklist_plan(uow, ORG, _plan(ROW))
    assert result.project_mismatch == ["T-01"]


async def test_missing_project_aborts_before_any_write():
    store = FakeStore()
    uow = FakeUow(store)
    with pytest.raises(ChecklistTargetError):
        await apply_checklist_plan(uow, ORG, _plan("T-02;PENDIENTE;No;ALTA;MIPG;A;;;x;No;"))
    assert store.tasks == {} and uow.rollbacks == 1 and uow.commits == 0


async def test_missing_column_aborts_before_any_write():
    store = FakeStore()
    store.targets[ORG]["SGSI"] = replace(store.targets[ORG]["SGSI"], columns={})
    uow = FakeUow(store)
    with pytest.raises(ChecklistTargetError):
        await apply_checklist_plan(uow, ORG, _plan(ROW))
    assert store.tasks == {}


async def test_failure_mid_batch_rolls_back_everything():
    store = FakeStore()
    uow = FakeUow(store)
    store.fail_on_create = True
    with pytest.raises(RuntimeError):
        await apply_checklist_plan(uow, ORG, _plan(ROW, ROW.replace("T-01", "T-02")))
    assert store.tasks == {} and uow.rollbacks == 1


async def test_other_organization_cannot_see_the_anchor():
    store = FakeStore()
    uow = FakeUow(store)
    await apply_checklist_plan(uow, ORG, _plan(ROW))
    assert await store.find_anchors(OTHER_ORG, CHECKLIST_SOURCE, ["CHECKLIST_TAREAS:T-01"]) == {}
