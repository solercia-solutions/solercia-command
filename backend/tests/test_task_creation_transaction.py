"""Recording-session control flow only; no database or rollback guarantees."""

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.tasks.models import Task
else:
    # Identity sentinels avoid ORM construction; imports stay out of collection.
    Task = object


class RecordingSession:
    def __init__(self, failure: str | None = None):
        self.events = []
        self.failure = failure
        self.error = RuntimeError("synthetic persistence failure")

    def record(self, operation, task=None):
        self.events.append((operation, task))
        if operation == self.failure:
            raise self.error

    def add(self, task):
        self.record("add", task)

    async def commit(self):
        self.record("commit")

    async def flush(self):
        self.record("flush")

    async def refresh(self, task):
        self.record("refresh", task)

    async def rollback(self):
        self.record("rollback")


@pytest.mark.asyncio
async def test_legacy_create_returns_same_instance_after_commit_then_refresh():
    from app.modules.tasks.repository import TaskRepository

    db = RecordingSession()
    task = cast(Task, object())
    result = await TaskRepository(cast(AsyncSession, db)).create(task)
    assert result is task
    assert db.events == [("add", task), ("commit", None), ("refresh", task)]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["add", "commit", "refresh"])
async def test_legacy_create_propagates_original_failure_without_cleanup(failure):
    from app.modules.tasks.repository import TaskRepository

    db = RecordingSession(failure)
    task = cast(Task, object())
    with pytest.raises(RuntimeError) as caught:
        await TaskRepository(cast(AsyncSession, db)).create(task)
    assert caught.value is db.error
    expected = [("add", task), ("commit", None), ("refresh", task)]
    assert db.events == expected[:["add", "commit", "refresh"].index(failure) + 1]


@pytest.mark.asyncio
async def test_transactional_create_returns_same_instance_without_completion():
    from app.modules.tasks.ports import TaskCreationPort
    from app.modules.tasks.repository import TransactionalTaskCreationRepository

    db = RecordingSession()
    task = cast(Task, object())
    creator: TaskCreationPort = TransactionalTaskCreationRepository(cast(AsyncSession, db))
    result = await creator.create(task)
    assert result is task
    assert db.events == [("add", task), ("flush", None), ("refresh", task)]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["add", "flush", "refresh"])
async def test_transactional_create_propagates_original_failure_without_cleanup(failure):
    from app.modules.tasks.repository import TransactionalTaskCreationRepository

    db = RecordingSession(failure)
    task = cast(Task, object())
    with pytest.raises(RuntimeError) as caught:
        await TransactionalTaskCreationRepository(cast(AsyncSession, db)).create(task)
    assert caught.value is db.error
    expected = [("add", task), ("flush", None), ("refresh", task)]
    assert db.events == expected[:["add", "flush", "refresh"].index(failure) + 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "flush", "refresh", "later_step"])
async def test_caller_alone_decides_completion_on_shared_session(failure):
    from app.modules.tasks.ports import TaskCreationPort
    from app.modules.tasks.repository import TransactionalTaskCreationRepository

    db = RecordingSession(failure)
    task = cast(Task, object())
    creator: TaskCreationPort = TransactionalTaskCreationRepository(cast(AsyncSession, db))

    async def caller():
        try:
            result = await creator.create(task)
            db.record("later_step")
            await db.commit()
            return result
        except RuntimeError:
            await db.rollback()
            raise

    if failure is None:
        assert await caller() is task
    else:
        with pytest.raises(RuntimeError) as caught:
            await caller()
        assert caught.value is db.error

    expected = [("add", task), ("flush", None), ("refresh", task), ("later_step", None)]
    if failure is None:
        expected.append(("commit", None))
    else:
        expected = expected[:["add", "flush", "refresh", "later_step"].index(failure) + 1]
        expected.append(("rollback", None))
    assert db.events == expected
