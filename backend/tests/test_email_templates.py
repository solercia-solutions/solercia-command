"""Tests for the Spanish (Colombian, formal, tuteo) email templates (change 08, Fase A).

R9 Plantillas en español colombiano formal (specs/email-notifications/spec.md,
D6 — funciones puras sin Jinja). Pure unit tests: no database, no network —
notifications/users are lightweight duck-typed stand-ins (``SimpleNamespace``)
since ``render_immediate``/``render_digest`` only read plain attributes.
"""

from types import SimpleNamespace

from app.email.templates import render_digest, render_immediate

# Voseo rioplatense forms that MUST NEVER appear — the hard rule is formal
# Colombian tuteo (e.g. "verifica"/"revisa"), never "verificá"/"tenés".
_VOSEO_FORMS = ("tenés", "verificá", "ingresá", "revisá", "sos ")


def _license_notification() -> SimpleNamespace:
    return SimpleNamespace(
        title="Licencia vencida",
        body='La licencia de "Antivirus Corporativo" venció el 2026-07-01.',
        rule_type="license_expired",
    )


def test_render_immediate_returns_subject_text_and_html() -> None:
    subject, text_body, html_body = render_immediate(_license_notification())

    assert subject
    assert "Licencia vencida" in subject
    assert text_body
    assert html_body is not None
    assert html_body  # non-empty — required for multipart/alternative


def test_render_immediate_uses_formal_tuteo_not_voseo() -> None:
    _subject, text_body, html_body = render_immediate(_license_notification())

    combined = f"{text_body} {html_body}".lower()
    assert "tu licencia" in combined
    assert ("verifica" in combined) or ("revisa" in combined)
    for voseo in _VOSEO_FORMS:
        assert voseo not in combined


def test_render_immediate_includes_original_body() -> None:
    """The alert engine's already-composed body (asset name + date) is preserved."""

    notif = _license_notification()
    _subject, text_body, _html = render_immediate(notif)

    assert notif.body in text_body


def _digest_user() -> SimpleNamespace:
    return SimpleNamespace(primer_nombre="Ana", email="ana@example.com")


def _digest_notifications(n: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            title=f"Notificación {i}",
            body=f"Cuerpo de la notificación número {i}.",
            rule_type="task_overdue",
        )
        for i in range(n)
    ]


def test_render_digest_returns_subject_text_and_html() -> None:
    user = _digest_user()
    notifications = _digest_notifications(3)

    subject, text_body, html_body = render_digest(user, notifications)

    assert subject
    assert text_body
    assert html_body is not None
    assert html_body


def test_render_digest_lists_every_notification() -> None:
    """A digest with N items lists all N in both the text and the HTML body."""

    user = _digest_user()
    notifications = _digest_notifications(3)

    _subject, text_body, html_body = render_digest(user, notifications)

    for notif in notifications:
        assert notif.title in text_body
        assert notif.body in text_body
        assert notif.title in html_body
        assert notif.body in html_body


def test_render_digest_single_item_differs_from_three_items() -> None:
    """Triangulation: a 1-item digest body differs from a 3-item digest body —
    proves the list is actually built from the input, not hardcoded."""

    user = _digest_user()
    _subject_one, text_one, _html_one = render_digest(user, _digest_notifications(1))
    _subject_three, text_three, _html_three = render_digest(user, _digest_notifications(3))

    assert text_one != text_three
    assert "Notificación 2" not in text_one
    assert "Notificación 2" in text_three


def test_render_digest_uses_formal_tuteo_not_voseo() -> None:
    user = _digest_user()
    _subject, text_body, html_body = render_digest(user, _digest_notifications(2))

    combined = f"{text_body} {html_body}".lower()
    for voseo in _VOSEO_FORMS:
        assert voseo not in combined
