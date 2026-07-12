"""Attachment routes for tasks and comments.

All endpoints require authentication and are scoped to the caller's
organization.  Upload endpoints accept ``multipart/form-data``; the download
endpoint returns the raw file with the original filename.
"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership
from app.modules.attachments.service import AttachmentService
from app.modules.organizations.models import OrganizationMember
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["attachments"])


@router.get("/tasks/{task_id}/attachments")
async def list_task_attachments(
    task_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List metadata of all attachments on a task.

    Supports opt-in pagination (``page``/``size``/``sort``/``order``); without
    those params the full collection is returned unchanged.
    """

    service = AttachmentService(db)
    items, total = await service.list_for_task(
        membership.organization_id, task_id, pagination
    )
    return {"data": items, "meta": build_list_meta(pagination, total)}


@router.post(
    "/tasks/{task_id}/attachments",
    status_code=status.HTTP_201_CREATED,
)
async def upload_task_attachment(
    task_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a file and attach it to a task.

    - Maximum file size: 10 MB.
    - The original filename is preserved for download; the on-disk path uses a
      UUID to prevent path-traversal attacks.
    """

    service = AttachmentService(db)
    attachment = await service.create_task_attachment(
        organization_id=membership.organization_id,
        task_id=task_id,
        uploader_id=membership.user_id,
        file=file,
        actor_id=actor_id,
    )
    return {"data": attachment}


@router.get("/comments/{comment_id}/attachments")
async def list_comment_attachments(
    comment_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List metadata of all attachments on a comment."""

    service = AttachmentService(db)
    items = await service.list_for_comment(membership.organization_id, comment_id)
    return {"data": items, "meta": {"total": len(items)}}


@router.post(
    "/comments/{comment_id}/attachments",
    status_code=status.HTTP_201_CREATED,
)
async def upload_comment_attachment(
    comment_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a file and attach it to a comment.

    - Maximum file size: 10 MB.
    - The original filename is preserved for download; the on-disk path uses a
      UUID to prevent path-traversal attacks.
    """

    service = AttachmentService(db)
    attachment = await service.create_comment_attachment(
        organization_id=membership.organization_id,
        comment_id=comment_id,
        uploader_id=membership.user_id,
        file=file,
        actor_id=actor_id,
    )
    return {"data": attachment}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download an attachment with auth enforcement.

    The response sets ``Content-Disposition: attachment`` with the original
    filename so browsers prompt a save dialog.
    """

    service = AttachmentService(db)
    attachment, path = await service.get_attachment_for_download(
        membership.organization_id, attachment_id
    )
    return FileResponse(
        path=str(path),
        media_type=attachment.content_type,
        filename=attachment.original_name,
        # Defense-in-depth: stop browsers from MIME-sniffing the payload and
        # rendering it inline. Combined with the attachment disposition above,
        # this neutralizes stored-XSS via uploaded active content.
        headers={"X-Content-Type-Options": "nosniff"},
    )
