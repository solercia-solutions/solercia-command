"""Business logic for task comments."""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import TaskComment
from app.modules.comments.repository import CommentRepository
from app.modules.comments.schemas import CommentCreate, CommentRead, CommentUpdate
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException

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
        self.repo = CommentRepository(db)
        self.tasks = TaskRepository(db)

    async def list_comments(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[CommentRead]:
        """Return the active comments of a task, oldest first."""

        await self._require_task(organization_id, task_id)
        comments = await self.repo.list_for_task(organization_id, task_id)
        return [CommentRead.model_validate(c) for c in comments]

    async def create_comment(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        author_id: uuid.UUID,
        data: CommentCreate,
    ) -> CommentRead:
        """Persist a comment, extracting @-mention UUIDs from the body.

        Mentions are stored in ``mentioned_user_ids`` for future notification
        dispatch. No notifications are sent at this stage.
        """

        await self._require_task(organization_id, task_id)

        comment = TaskComment(
            organization_id=organization_id,
            task_id=task_id,
            author_id=author_id,
            body=data.body,
            mentioned_user_ids=_parse_mentioned_ids(data.body),
        )
        comment = await self.repo.create(comment)
        return CommentRead.model_validate(comment)

    async def update_comment(
        self,
        organization_id: uuid.UUID,
        comment_id: uuid.UUID,
        author_id: uuid.UUID,
        data: CommentUpdate,
    ) -> CommentRead:
        """Edit a comment body. Only the original author may edit."""

        comment = await self._require_comment(organization_id, comment_id)
        if comment.author_id != author_id:
            raise AppException(
                "Solo el autor del comentario puede editarlo.",
                code="comment_forbidden",
                status_code=403,
            )
        comment.body = data.body
        comment.mentioned_user_ids = _parse_mentioned_ids(data.body)
        comment = await self.repo.save(comment)
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
        comment.deleted_at = datetime.now(timezone.utc)
        await self.repo.save(comment)

    # -- helpers -----------------------------------------------------------

    async def _require_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )

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
