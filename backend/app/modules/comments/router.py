"""Comment routes nested under tasks.

All endpoints require authentication and are scoped to the caller's
organization. Responses are wrapped in a ``{data, meta}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.comments.schemas import CommentCreate, CommentUpdate
from app.modules.comments.service import CommentService
from app.modules.organizations.models import OrganizationMember
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["comments"])


@router.get("/tasks/{task_id}/comments")
async def list_comments(
    task_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the comments of a task, oldest first.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = CommentService(db)
    comments, total = await service.list_comments(
        membership.organization_id, task_id, pagination
    )
    return {"data": comments, "meta": build_list_meta(pagination, total)}


@router.post(
    "/tasks/{task_id}/comments", status_code=status.HTTP_201_CREATED
)
async def create_comment(
    task_id: uuid.UUID,
    payload: CommentCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Post a comment on a task. Mentions are parsed from the body and stored."""

    service = CommentService(db)
    comment = await service.create_comment(
        membership.organization_id,
        task_id,
        membership.user_id,
        payload,
    )
    return {"data": comment}


@router.patch("/comments/{comment_id}")
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a comment body. Only the original author may edit their own comment."""

    service = CommentService(db)
    comment = await service.update_comment(
        membership.organization_id,
        comment_id,
        membership.user_id,
        payload,
    )
    return {"data": comment}


@router.delete(
    "/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment(
    comment_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a comment. Only the original author may delete their own comment."""

    service = CommentService(db)
    await service.delete_comment(
        membership.organization_id,
        comment_id,
        membership.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
