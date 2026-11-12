"""Tests for the ``EmailSender`` port and its adapters (change 08, Fase A).

R1 Puerto EmailSender agnóstico al proveedor (specs/email-notifications/spec.md,
D8). Pure unit tests: ``ConsoleEmailSender`` never touches the network by
construction, and ``SmtpEmailSender`` is exercised with ``aiosmtplib.send``
mocked — this suite never reaches a real socket.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.email.sender import (
    ConsoleEmailSender,
    EmailApprovalRequiredError,
    SmtpEmailSender,
    get_email_sender,
)


@pytest.fixture(autouse=True)
def smtp_transport(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    transport = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr("aiosmtplib.send", transport)
    return transport


@pytest.mark.asyncio(loop_scope="session")
async def test_console_sender_captures_message_in_memory_without_network(
    smtp_transport: AsyncMock,
) -> None:
    sender = ConsoleEmailSender()

    await sender.send(
        to="ana@example.com",
        subject="Licencia vencida",
        text_body="La licencia venció.",
        html_body="<p>La licencia venció.</p>",
    )

    assert len(sender.sent) == 1
    captured = sender.sent[0]
    assert captured["to"] == "ana@example.com"
    assert captured["subject"] == "Licencia vencida"
    assert captured["text_body"] == "La licencia venció."
    assert captured["html_body"] == "<p>La licencia venció.</p>"
    smtp_transport.assert_not_called()


@pytest.mark.asyncio(loop_scope="session")
async def test_console_sender_captures_multiple_messages_in_order() -> None:
    """Triangulation: a second, DIFFERENT send is captured as a distinct entry —
    proves the capture is a real accumulating list, not a hardcoded single value."""

    sender = ConsoleEmailSender()

    await sender.send(to="a@example.com", subject="Uno", text_body="Cuerpo uno.")
    await sender.send(to="b@example.com", subject="Dos", text_body="Cuerpo dos.")

    assert len(sender.sent) == 2
    assert sender.sent[0]["subject"] == "Uno"
    assert sender.sent[1]["subject"] == "Dos"
    assert sender.sent[1]["to"] == "b@example.com"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("via_factory", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("credentials", ["", "synthetic-secret"])
@pytest.mark.parametrize("subject,html_body", [("Aviso", None), ("URGENTE", "<p>Privado</p>")])
async def test_smtp_denied_before_message_or_transport(
    monkeypatch: pytest.MonkeyPatch,
    smtp_transport: AsyncMock,
    via_factory: bool,
    enabled: bool,
    credentials: str,
    subject: str,
    html_body: str | None,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp" if via_factory else "console")
    monkeypatch.setattr(settings, "EMAIL_ENABLED", enabled)
    monkeypatch.setattr(settings, "SMTP_USER", credentials)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", credentials)
    message_builder = MagicMock()
    monkeypatch.setattr("email.message.EmailMessage", message_builder)
    monkeypatch.setattr("app.email.sender.EmailMessage", message_builder, raising=False)
    sender = get_email_sender() if via_factory else SmtpEmailSender()

    with pytest.raises(EmailApprovalRequiredError) as error:
        await sender.send("private@example.com", subject, "Cuerpo privado", html_body)

    assert str(error.value) == "Envío SMTP bloqueado: se requiere aprobación explícita."
    message_builder.assert_not_called()
    smtp_transport.assert_not_called()
    smtp_transport.assert_not_awaited()


def test_get_email_sender_returns_console_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "console")

    sender = get_email_sender()

    assert isinstance(sender, ConsoleEmailSender)


def test_get_email_sender_returns_smtp_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")

    sender = get_email_sender()

    assert isinstance(sender, SmtpEmailSender)
