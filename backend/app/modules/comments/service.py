"""Business logic for task comments."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import TaskComment
from app.modules.comments.repository import CommentRepository
from app.modules.comments.schemas import CommentCreate, CommentRead, CommentUpdate
from app.modules.notifications.repository import NotificationRepository
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.users.models import User
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

# Matches standard UUID v4 strings embedded in comment bodies.
# The frontend typically inlines mentioned user IDs as UUIDs within @-mention
# markup (e.g. data attributes or plain @uuid references in HTML).
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _parse_mentioned_ids(body: str) -> list[str]:
    """Extract all UUID strings present in the comment body (deduplicated)."""

    return list({m.lower() for m in _UUID_RE.findall(body)})


class CommentService:
    """Orchestrates comment use-cases within a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self.repo = CommentRepository(db)
        self.tasks = TaskRepository(db)

    async def list_comments(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[CommentRead], int]:
        """Return ``(comments, total)`` — the active comments of a task."""

        await self._require_task(organization_id, task_id)
        comments, total = await self.repo.list_for_task(
            organization_id, task_id, pagination
        )
        reads = [CommentRead.model_validate(c) for c in comments]
        return reads, total

    async def create_comment(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        author_id: uuid.UUID,
        data: CommentCreate,
    ) -> CommentRead:
        """Persist a comment and dispatch in-app notifications for @-mentions.

        Mentioned UUIDs are extracted from the body, validated as org members,
        and notified via the notification engine (in-app channel). Email is a
        future extension — see :meth:`_dispatch_mention_notifications`.
        """

        task = await self._require_task(organization_id, task_id)
        # Extract title now; the task object expires after repo.create() commits.
        task_title = task.title

        comment = TaskComment(
            organization_id=organization_id,
            task_id=task_id,
            author_id=author_id,
            body=data.body,
            mentioned_user_ids=_parse_mentioned_ids(data.body),
        )
        comment = await self.repo.create(comment)

        await self._dispatch_mention_notifications(
            org_id=organization_id,
            comment_id=comment.id,
            task_id=task_id,
            task_title=task_title,
            author_id=author_id,
            mentioned_ids=comment.mentioned_user_ids,
        )

        return CommentRead.model_validate(comment)

    async def update_comment(
        self,
        organization_id: uuid.UUID,
        comment_id: uuid.UUID,
        author_id: uuid.UUID,
        data: CommentUpdate,
    ) -> CommentRead:
        """Edit a comment body. Only the original author may edit.

        Only mentions that are NEW in this edit (not present in the previous
        body) receive notifications, preventing duplicate alerts.
        """

        comment = await self._require_comment(organization_id, comment_id)
        if comment.author_id != author_id:
            raise AppException(
                "Solo el autor del comentario puede editarlo.",
                code="comment_forbidden",
                status_code=403,
            )

        previous_mentioned: set[str] = set(comment.mentioned_user_ids)
        comment_task_id = comment.task_id

        comment.body = data.body
        comment.mentioned_user_ids = _parse_mentioned_ids(data.body)
        new_mentioned: set[str] = set(comment.mentioned_user_ids)
        newly_added: list[str] = list(new_mentioned - previous_mentioned)

        # Fetch task title before repo.save() commits (object expires after commit).
        task = await self.tasks.get(organization_id, comment_task_id)
        task_title = task.title if task is not None else ""

        comment = await self.repo.save(comment)

        if newly_added:
            await self._dispatch_mention_notifications(
                org_id=organization_id,
                comment_id=comment.id,
                task_id=comment_task_id,
                task_title=task_title,
                author_id=author_id,
                mentioned_ids=newly_added,
            )

        return CommentRead.model_validate(comment)

    async def delete_comment(
        self,
        organization_id: uuid.UUID,
        comment_id: uuid.UUID,
        author_id: uuid.UUID,
    ) -> None:
        """Soft-delete a comment. Only the original author may delete."""

        comment = await self._require_comment(organization_id, comment_id)
        if comment.author_id != author_id:
            raise AppException(
                "Solo el autor del comentario puede eliminarlo.",
                code="comment_forbidden",
                status_code=403,
            )
        comment.is_active = False
        comment.deleted_at = datetime.now(UTC)
        await self.repo.save(comment)

    # -- helpers -----------------------------------------------------------

    async def _require_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task:
        """Return the task or raise 404 if it doesn't exist in this org."""
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task

    async def _require_comment(
        self, organization_id: uuid.UUID, comment_id: uuid.UUID
    ) -> TaskComment:
        comment = await self.repo.get(organization_id, comment_id)
        if comment is None:
            raise AppException(
                "El comentario no existe o no tienes acceso a él.",
                code="comment_not_found",
                status_code=404,
            )
        return comment

    async def _get_author_name(self, author_id: uuid.UUID) -> str:
        """Resolve the author's display name for the notification body.

        Falls back to the UUID string when the user record is not found.
        """
        result = await self._db.execute(
            select(User).where(User.id == author_id, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        return user.full_name if user is not None else str(author_id)

    async def _dispatch_mention_notifications(
        self,
        org_id: uuid.UUID,
        comment_id: uuid.UUID,
        task_id: uuid.UUID,
        task_title: str,
        author_id: uuid.UUID,
        mentioned_ids: list[str],
    ) -> None:
        """Create in-app notifications for each newly mentioned org member.

        Skips:
        - self-mentions (author_id == mentioned user)
        - users that are not members of this organization (multi-tenant guard)
        - duplicate notifications (same dedup_key already active in the DB)

        TODO(email): When the email channel is implemented, add a call after
        each in-app notification is persisted:
            await email_service.send_mention(
                recipient_id=user_id,
                task_title=task_title,
                author_name=author_name,
                comment_url=f"/tasks/{task_id}#comment-{comment_id}",
            )
        The email_service can be injected into CommentService alongside
        NotificationRepository.
        """
        if not mentioned_ids:
            return

        author_name = await self._get_author_name(author_id)
        notif_repo = NotificationRepository(self._db)
        created_any = False

        for uid_str in mentioned_ids:
            try:
                user_id = uuid.UUID(uid_str)
            except ValueError:
                continue

            # Skip self-mentions
            if user_id == author_id:
                continue

            # Multi-tenant guard: only notify actual org members
            if not await self.tasks.is_org_member(org_id, user_id):
                continue

            dedup_key = f"mention:{comment_id}:{user_id}"

            # Idempotency: skip if the same notification is already active
            if await notif_repo.exists_active(org_id, dedup_key):
                continue

            await notif_repo.create(
                organization_id=org_id,
                recipient_user_id=user_id,
                rule_type="mention",
                title="Te mencionaron en un comentario",
                body=f'{author_name} te mencionó en la tarea "{task_title}"',
                target_type="task",
                target_id=task_id,
                dedup_key=dedup_key,
            )
            created_any = True

        if created_any:
            await self._db.commit()
