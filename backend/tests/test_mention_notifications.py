"""Unit tests for @-mention notification dispatch wired into CommentService.

These tests run WITHOUT a database. All repositories and the AsyncSession are
mocked so the suite stays fast and dependency-free.

Strategy
--------
- ``_dispatch_mention_notifications`` is tested directly because it contains
  all the business rules (skip self-mentions, non-members, dedup). This avoids
  the SQLAlchemy mapper-configuration cascade triggered by ``TaskComment(...)``.
- Wiring tests for ``create_comment`` and ``update_comment`` patch
  ``TaskComment`` as well so no real ORM object is ever instantiated.

Scenarios covered
-----------------
1. Notification created for a valid mention on create.
2. No duplicate when dedup_key is already active.
3. Self-mention is silently skipped.
4. Non-member mention is silently skipped.
5. update_comment notifies only the newly added mentions.
6. update_comment sends nothing when no new mentions were added.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(author_full_name: str = "Ana García") -> AsyncMock:
    """Return a mock AsyncSession whose execute() resolves to a User."""
    user = MagicMock()
    user.full_name = author_full_name
    user.is_active = True

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    db = AsyncMock()
    db.execute = AsyncMock(return_value=user_result)
    db.commit = AsyncMock()
    # Real dict, not an auto-mocked attribute: `flush_pending` (change
    # 09-websocket-realtime) reads/pops `db.info["realtime_pending"]`, same
    # as the production `AsyncSession.info` it stands in for here.
    db.info = {}
    return db


def _make_comment_mock(
    comment_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    mentioned_ids: list[str] | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = comment_id or uuid.uuid4()
    c.task_id = task_id or uuid.uuid4()
    c.author_id = author_id or uuid.uuid4()
    c.mentioned_user_ids = list(mentioned_ids or [])
    c.body = ""
    return c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def author_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def task_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mentioned_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Direct tests of _dispatch_mention_notifications
# ---------------------------------------------------------------------------


class TestDispatchMentionNotifications:
    """Tests that exercise _dispatch_mention_notifications directly.

    This avoids instantiating any real ORM models so no DB connection is
    needed and no SQLAlchemy mapper configuration is triggered.
    """

    async def _make_service(self, db: AsyncMock) -> "CommentService":  # type: ignore[name-defined]  # noqa: F821
        """Build a CommentService with fully mocked sub-repositories."""
        with (
            patch("app.modules.comments.service.CommentRepository"),
            patch("app.modules.comments.service.TaskRepository"),
        ):
            from app.modules.comments.service import CommentService
            return CommentService(db)

    @pytest.mark.asyncio
    async def test_creates_notification_for_valid_mention(
        self, org_id, author_id, task_id, mentioned_id
    ):
        db = _make_db("Carlos López")
        service = await self._make_service(db)
        comment_id = uuid.uuid4()

        with patch("app.modules.comments.service.NotificationRepository") as MockNR:
            task_repo = service.tasks
            task_repo.is_org_member = AsyncMock(return_value=True)

            notif_repo = MockNR.return_value
            notif_repo.exists_active = AsyncMock(return_value=False)
            notif_repo.create = AsyncMock(return_value=MagicMock())

            await service._dispatch_mention_notifications(
                org_id=org_id,
                comment_id=comment_id,
                task_id=task_id,
                task_title="Revisar PR",
                author_id=author_id,
                mentioned_ids=[str(mentioned_id)],
            )

        notif_repo.create.assert_called_once()
        kw = notif_repo.create.call_args.kwargs
        assert kw["recipient_user_id"] == mentioned_id
        assert kw["rule_type"] == "mention"
        assert kw["target_type"] == "task"
        assert kw["target_id"] == task_id
        assert kw["dedup_key"] == f"mention:{comment_id}:{mentioned_id}"
        assert "Carlos López" in kw["body"]
        assert "Revisar PR" in kw["body"]
        assert kw["title"] == "Te mencionaron en un comentario"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_self_mention(self, org_id, author_id, task_id):
        db = _make_db()
        service = await self._make_service(db)

        with patch("app.modules.comments.service.NotificationRepository") as MockNR:
            task_repo = service.tasks
            task_repo.is_org_member = AsyncMock(return_value=True)

            notif_repo = MockNR.return_value
            notif_repo.exists_active = AsyncMock(return_value=False)
            notif_repo.create = AsyncMock()

            await service._dispatch_mention_notifications(
                org_id=org_id,
                comment_id=uuid.uuid4(),
                task_id=task_id,
                task_title="Tarea X",
                author_id=author_id,
                mentioned_ids=[str(author_id)],  # self-mention
            )

        notif_repo.create.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_org_member(self, org_id, author_id, task_id, mentioned_id):
        db = _make_db()
        service = await self._make_service(db)

        with patch("app.modules.comments.service.NotificationRepository") as MockNR:
            task_repo = service.tasks
            task_repo.is_org_member = AsyncMock(return_value=False)  # not a member

            notif_repo = MockNR.return_value
            notif_repo.create = AsyncMock()

            await service._dispatch_mention_notifications(
                org_id=org_id,
                comment_id=uuid.uuid4(),
                task_id=task_id,
                task_title="Tarea X",
                author_id=author_id,
                mentioned_ids=[str(mentioned_id)],
            )

        notif_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_when_already_active(
        self, org_id, author_id, task_id, mentioned_id
    ):
        db = _make_db()
        service = await self._make_service(db)

        with patch("app.modules.comments.service.NotificationRepository") as MockNR:
            task_repo = service.tasks
            task_repo.is_org_member = AsyncMock(return_value=True)

            notif_repo = MockNR.return_value
            notif_repo.exists_active = AsyncMock(return_value=True)  # already active
            notif_repo.create = AsyncMock()

            await service._dispatch_mention_notifications(
                org_id=org_id,
                comment_id=uuid.uuid4(),
                task_id=task_id,
                task_title="Tarea X",
                author_id=author_id,
                mentioned_ids=[str(mentioned_id)],
            )

        notif_repo.create.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_mentioned_ids_is_noop(self, org_id, author_id, task_id):
        db = _make_db()
        service = await self._make_service(db)

        with patch("app.modules.comments.service.NotificationRepository") as MockNR:
            notif_repo = MockNR.return_value
            notif_repo.create = AsyncMock()

            await service._dispatch_mention_notifications(
                org_id=org_id,
                comment_id=uuid.uuid4(),
                task_id=task_id,
                task_title="Tarea X",
                author_id=author_id,
                mentioned_ids=[],
            )

        notif_repo.create.assert_not_called()
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Wiring tests: create_comment and update_comment call dispatch correctly
# ---------------------------------------------------------------------------


class TestUpdateCommentMentionDiff:
    """Update-specific logic: only NEW mentions trigger notifications."""

    @pytest.mark.asyncio
    async def test_update_notifies_only_new_mentions(self, org_id, author_id, task_id):
        """Pre-existing mention is not re-notified; only the newly added one is."""
        db = _make_db("Laura Gómez")
        existing_uid = uuid.uuid4()
        new_uid = uuid.uuid4()
        comment_id = uuid.uuid4()

        # State BEFORE the edit: existing_uid already mentioned
        original_comment = _make_comment_mock(
            comment_id=comment_id,
            task_id=task_id,
            author_id=author_id,
            mentioned_ids=[str(existing_uid)],
        )
        saved_comment = _make_comment_mock(
            comment_id=comment_id,
            task_id=task_id,
            author_id=author_id,
            mentioned_ids=[str(existing_uid), str(new_uid)],
        )

        task_mock = MagicMock()
        task_mock.title = "Diseño de base de datos"

        with (
            patch("app.modules.comments.service.CommentRepository") as MockCR,
            patch("app.modules.comments.service.TaskRepository") as MockTR,
            patch("app.modules.comments.service.NotificationRepository") as MockNR,
            patch("app.modules.comments.service.CommentRead") as MockCommentRead,
        ):
            MockCommentRead.model_validate.return_value = MagicMock()

            comment_repo = MockCR.return_value
            comment_repo.get = AsyncMock(return_value=original_comment)
            comment_repo.save = AsyncMock(return_value=saved_comment)

            task_repo = MockTR.return_value
            task_repo.get = AsyncMock(return_value=task_mock)
            task_repo.is_org_member = AsyncMock(return_value=True)

            notif_repo = MockNR.return_value
            notif_repo.exists_active = AsyncMock(return_value=False)
            notif_repo.create = AsyncMock(return_value=MagicMock())

            # Simulate User execute returning author name
            user_mock = MagicMock()
            user_mock.full_name = "Laura Gómez"
            user_result = MagicMock()
            user_result.scalar_one_or_none.return_value = user_mock
            db.execute = AsyncMock(return_value=user_result)

            from app.modules.comments.schemas import CommentUpdate
            from app.modules.comments.service import CommentService

            service = CommentService(db)
            await service.update_comment(
                organization_id=org_id,
                comment_id=comment_id,
                author_id=author_id,
                data=CommentUpdate(
                    body=f"@{existing_uid} y además @{new_uid} revisen por favor"
                ),
            )

        # Only the newly added user should receive a notification
        notif_repo.create.assert_called_once()
        kw = notif_repo.create.call_args.kwargs
        assert kw["recipient_user_id"] == new_uid
        assert "Diseño de base de datos" in kw["body"]
        assert "Laura Gómez" in kw["body"]

    @pytest.mark.asyncio
    async def test_update_with_no_new_mentions_sends_nothing(
        self, org_id, author_id, task_id, mentioned_id
    ):
        """Re-saving a comment without new mentions must not create notifications."""
        db = _make_db()
        comment_id = uuid.uuid4()

        # Same mention existed before AND after edit
        comment = _make_comment_mock(
            comment_id=comment_id,
            task_id=task_id,
            author_id=author_id,
            mentioned_ids=[str(mentioned_id)],
        )
        saved_comment = _make_comment_mock(
            comment_id=comment_id,
            task_id=task_id,
            author_id=author_id,
            mentioned_ids=[str(mentioned_id)],
        )
        task_mock = MagicMock()
        task_mock.title = "Tarea"

        with (
            patch("app.modules.comments.service.CommentRepository") as MockCR,
            patch("app.modules.comments.service.TaskRepository") as MockTR,
            patch("app.modules.comments.service.NotificationRepository") as MockNR,
            patch("app.modules.comments.service.CommentRead") as MockCommentRead,
        ):
            MockCommentRead.model_validate.return_value = MagicMock()
            MockCR.return_value.get = AsyncMock(return_value=comment)
            MockCR.return_value.save = AsyncMock(return_value=saved_comment)
            MockTR.return_value.get = AsyncMock(return_value=task_mock)

            notif_repo = MockNR.return_value
            notif_repo.create = AsyncMock()

            from app.modules.comments.schemas import CommentUpdate
            from app.modules.comments.service import CommentService

            service = CommentService(db)
            await service.update_comment(
                organization_id=org_id,
                comment_id=comment_id,
                author_id=author_id,
                data=CommentUpdate(
                    body=f"Texto diferente, misma mención @{mentioned_id}"
                ),
            )

        notif_repo.create.assert_not_called()
        db.commit.assert_not_called()
