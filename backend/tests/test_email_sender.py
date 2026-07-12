"""Tests for the ``EmailSender`` port and its adapters (change 08, Fase A).

R1 Puerto EmailSender agnóstico al proveedor (specs/email-notifications/spec.md,
D8). Pure unit tests: ``ConsoleEmailSender`` never touches the network by
construction, and ``SmtpEmailSender`` is exercised with ``aiosmtplib.send``
mocked — this suite never reaches a real socket.
"""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.email.sender import ConsoleEmailSender, SmtpEmailSender, get_email_sender


@pytest.mark.asyncio(loop_scope="session")
async def test_console_sender_captures_message_in_memory_without_network() -> None:
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
async def test_smtp_sender_builds_multipart_message_and_calls_aiosmtplib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "user@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(settings, "FROM_EMAIL", "no-reply@solercia.com")
    monkeypatch.setattr(settings, "FROM_NAME", "Solercia")

    mock_send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr("app.email.sender.aiosmtplib.send", mock_send)

    sender = SmtpEmailSender()
    await sender.send(
        to="ana@example.com",
        subject="Licencia vencida",
        text_body="La licencia venció.",
        html_body="<p>La licencia venció.</p>",
    )

    assert mock_send.await_count == 1
    _args, kwargs = mock_send.await_args
    message = kwargs["message"] if "message" in kwargs else _args[0]

    assert message["To"] == "ana@example.com"
    assert message["Subject"] == "Licencia vencida"
    assert message.get_content_type() == "multipart/alternative"

    text_part, html_part = message.get_payload()
    assert "La licencia venció." in text_part.get_payload()
    assert "La licencia venció." in html_part.get_payload()

    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "user@example.com"
    assert kwargs["password"] == "secret"


@pytest.mark.asyncio(loop_scope="session")
async def test_smtp_sender_without_html_still_sends_text_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Triangulation: omitting html_body produces a plain (non-multipart) message —
    a different code path than the multipart/alternative one above."""

    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    mock_send = AsyncMock(return_value=({}, "OK"))
    monkeypatch.setattr("app.email.sender.aiosmtplib.send", mock_send)

    sender = SmtpEmailSender()
    await sender.send(to="ana@example.com", subject="Aviso", text_body="Solo texto.")

    assert mock_send.await_count == 1
    _args, kwargs = mock_send.await_args
    message = kwargs["message"] if "message" in kwargs else _args[0]
    assert message.get_content_type() == "text/plain"


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
