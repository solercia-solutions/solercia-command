"""``EmailSender`` port + adapters (D1, D8) — the domain never talks SMTP.

``console`` is a network-free fake that captures messages in memory.
``smtp`` is temporarily blocked unconditionally, including direct adapter use.
No configuration or credentials enable delivery; approval is not implemented.
"""

import logging
from typing import Protocol

from app.config import settings

logger = logging.getLogger("solercia.email")


class EmailSender(Protocol):
    """Port every adapter implements — the domain depends on this, never a library."""

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None: ...


class ConsoleEmailSender:
    """Captures outgoing email in memory and logs it — zero network I/O.

    This fake never delivers email, regardless of SMTP configuration.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, str | None]] = []

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        self.sent.append(
            {"to": to, "subject": subject, "text_body": text_body, "html_body": html_body}
        )
        logger.info("Correo capturado (console backend): para=%s asunto=%s", to, subject)


class EmailApprovalRequiredError(RuntimeError):
    """Real email is blocked pending an explicit approval workflow."""

    def __init__(self) -> None:
        super().__init__("Envío SMTP bloqueado: se requiere aprobación explícita.")


class SmtpEmailSender:
    """Temporary unconditional barrier, not an approval workflow."""

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        raise EmailApprovalRequiredError()


# Console adapter singleton (per-process): lets callers that only have access
# to ``get_email_sender()`` — jobs, tests — inspect ``.sent`` after a send
# happened elsewhere in the same process. SMTP instances always deny delivery.
_console_sender = ConsoleEmailSender()


def get_email_sender() -> EmailSender:
    """Return the configured adapter, selected purely by ``settings.EMAIL_BACKEND``."""

    if settings.EMAIL_BACKEND == "smtp":
        return SmtpEmailSender()
    return _console_sender
