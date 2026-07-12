"""``EmailSender`` port + adapters (D1, D8) — the domain never talks SMTP.

``console`` (default backend, zero dependencies, captures in memory — the
test suite and local dev never touch the network unless ``EMAIL_BACKEND`` is
explicitly set to ``smtp``) and ``smtp`` (``aiosmtplib``, the ONLY module in
the codebase allowed to depend on it). Swapping ``EMAIL_BACKEND`` never
requires touching outbox/digest/preferences code — only ``get_email_sender``
changes which concrete adapter it returns. A future managed provider
(SES/SendGrid/Resend) is a new adapter implementing the same ``EmailSender``
protocol, zero changes elsewhere.
"""

import logging
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.config import settings

logger = logging.getLogger("solercia.email")


class EmailSender(Protocol):
    """Port every adapter implements — the domain depends on this, never a library."""

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None: ...


class ConsoleEmailSender:
    """Captures outgoing email in memory and logs it — zero network I/O.

    Used whenever ``EMAIL_BACKEND=console`` (the default): guarantees the
    test suite and local development never reach a real SMTP server unless
    ``smtp`` is configured explicitly (design.md, "EMAIL_BACKEND default
    console").
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


class SmtpEmailSender:
    """Sends real email via SMTP (``aiosmtplib``) — the only adapter with that dependency."""

    async def send(
        self, to: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        message = EmailMessage()
        message["From"] = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body is not None:
            message.add_alternative(html_body, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_USE_TLS,
        )


# Console adapter singleton (per-process): lets callers that only have access
# to ``get_email_sender()`` — jobs, tests — inspect ``.sent`` after a send
# happened elsewhere in the same process. The SMTP adapter is stateless, so it
# is instantiated fresh on every call; it always reads current ``settings``
# at send time regardless.
_console_sender = ConsoleEmailSender()


def get_email_sender() -> EmailSender:
    """Return the configured adapter, selected purely by ``settings.EMAIL_BACKEND``."""

    if settings.EMAIL_BACKEND == "smtp":
        return SmtpEmailSender()
    return _console_sender
