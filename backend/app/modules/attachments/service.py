"""Business logic for attachments.

Files are saved to the local filesystem under ``settings.UPLOAD_DIR``.  The
on-disk filename is a UUID (no extension) to prevent path-traversal attacks;
the original filename is stored in the DB and restored on download.
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.attachments.models import Attachment
from app.modules.attachments.repository import AttachmentRepository
from app.modules.attachments.schemas import AttachmentRead
from app.modules.comments.repository import CommentRepository
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException

# 10 MB maximum upload size.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# MIME types that are always rejected regardless of extension. Covers native
# executables/scripts plus active web content (HTML/JS/SVG) that could be used
# for stored XSS if a client ever renders a download inline. Downloads are
# additionally forced with Content-Disposition: attachment + X-Content-Type-Options.
_BLOCKED_TYPES = frozenset(
    {
        # Native executables / shell scripts
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-sh",
        "application/x-bat",
        "application/x-csh",
        "text/x-shellscript",
        "application/x-python",
        "application/x-python-code",
        "application/x-httpd-php",
        "application/java-archive",
        # Active web content (XSS vectors when rendered inline)
        "text/html",
        "application/xhtml+xml",
        "application/javascript",
        "text/javascript",
        "application/ecmascript",
        "text/ecmascript",
        "image/svg+xml",
        "application/xml",
        "text/xml",
    }
)


class AttachmentService:
    """Orchestrates file upload and download within a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = AttachmentRepository(db)
        self.tasks = TaskRepository(db)
        self.comments = CommentRepository(db)

    async def list_for_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[AttachmentRead]:
        """Return metadata for all active attachments on a task."""

        await self._require_task(organization_id, task_id)
        items = await self.repo.list_for_target(organization_id, "task", task_id)
        return [AttachmentRead.model_validate(a) for a in items]

    async def list_for_comment(
        self, organization_id: uuid.UUID, comment_id: uuid.UUID
    ) -> list[AttachmentRead]:
        """Return metadata for all active attachments on a comment."""

        await self._require_comment(organization_id, comment_id)
        items = await self.repo.list_for_target(organization_id, "comment", comment_id)
        return [AttachmentRead.model_validate(a) for a in items]

    async def create_task_attachment(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        uploader_id: uuid.UUID,
        file: UploadFile,
    ) -> AttachmentRead:
        """Upload and persist a file attachment for a task."""

        await self._require_task(organization_id, task_id)
        return await self._save_file(
            organization_id=organization_id,
            target_type="task",
            target_id=task_id,
            uploader_id=uploader_id,
            file=file,
        )

    async def create_comment_attachment(
        self,
        organization_id: uuid.UUID,
        comment_id: uuid.UUID,
        uploader_id: uuid.UUID,
        file: UploadFile,
    ) -> AttachmentRead:
        """Upload and persist a file attachment for a comment."""

        await self._require_comment(organization_id, comment_id)
        return await self._save_file(
            organization_id=organization_id,
            target_type="comment",
            target_id=comment_id,
            uploader_id=uploader_id,
            file=file,
        )

    async def get_attachment_for_download(
        self, organization_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> tuple[Attachment, Path]:
        """Return the ``Attachment`` record and the on-disk ``Path`` for serving.

        Raises ``AppException`` if the attachment does not exist, is deleted, or
        the on-disk file is missing (should not happen in normal operations).
        """

        attachment = await self.repo.get(organization_id, attachment_id)
        if attachment is None:
            raise AppException(
                "El archivo no existe o no tienes acceso a él.",
                code="attachment_not_found",
                status_code=404,
            )
        path = self._upload_dir() / attachment.stored_name
        if not path.exists():
            raise AppException(
                "El archivo no se encontró en el servidor.",
                code="attachment_missing_on_disk",
                status_code=404,
            )
        return attachment, path

    # -- helpers -----------------------------------------------------------

    async def _save_file(
        self,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        uploader_id: uuid.UUID,
        file: UploadFile,
    ) -> AttachmentRead:
        """Read, validate, store to disk and persist the Attachment record."""

        content = await file.read()

        # Size guard.
        if len(content) > _MAX_UPLOAD_BYTES:
            raise AppException(
                "El archivo excede el tamaño máximo permitido de 10 MB.",
                code="file_too_large",
                status_code=413,
            )

        if len(content) == 0:
            raise AppException(
                "No se puede subir un archivo vacío.",
                code="file_empty",
                status_code=422,
            )

        # Normalize content type; never trust the raw client value blindly.
        content_type = (file.content_type or "application/octet-stream").lower().split(";")[0].strip()
        if content_type in _BLOCKED_TYPES:
            raise AppException(
                "Este tipo de archivo no está permitido.",
                code="file_type_not_allowed",
                status_code=422,
            )

        # UUID-named file: safe against path traversal, collisions impossible.
        stored_name = str(uuid.uuid4())
        upload_path = self._upload_dir() / stored_name
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        # Off-load the blocking write so the event loop is not stalled on large files.
        await asyncio.to_thread(upload_path.write_bytes, content)

        attachment = Attachment(
            organization_id=organization_id,
            target_type=target_type,
            target_id=target_id,
            original_name=file.filename or "unnamed",
            stored_name=stored_name,
            content_type=content_type,
            size_bytes=len(content),
            uploaded_by=uploader_id,
        )
        try:
            attachment = await self.repo.create(attachment)
        except Exception:
            # Roll back the on-disk file so a failed DB write leaves no orphan.
            upload_path.unlink(missing_ok=True)
            raise
        return AttachmentRead.model_validate(attachment)

    @staticmethod
    def _upload_dir() -> Path:
        return Path(settings.UPLOAD_DIR).resolve()

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
    ) -> None:
        comment = await self.comments.get(organization_id, comment_id)
        if comment is None:
            raise AppException(
                "El comentario no existe o no tienes acceso a él.",
                code="comment_not_found",
                status_code=404,
            )
