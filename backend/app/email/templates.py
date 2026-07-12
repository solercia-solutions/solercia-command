"""Pure Spanish (Colombian, formal tuteo) email templates — no Jinja (D6).

Both functions are pure: given the same input they always return the same
``(subject, text_body, html_body)`` tuple, with zero I/O and zero framework
dependency — trivially unit-testable. They accept duck-typed ``Protocol``
inputs instead of importing the ORM ``Notification``/``User`` models, so this
module has no cross-package import at all (narrower than the D2 "only
``notifications.models``" frontier — it needs neither).

Redacción: español colombiano formal con tuteo ("tu licencia", "verifica",
"revisa", "ingresa"); NUNCA voseo rioplatense ("tenés", "verificá").
"""

from collections.abc import Sequence
from typing import Protocol


class NotificationLike(Protocol):
    """Minimal shape ``render_immediate``/``render_digest`` need from a notification."""

    title: str
    body: str


class UserLike(Protocol):
    """Minimal shape ``render_digest`` needs from the recipient user."""

    primer_nombre: str


def render_immediate(notification: NotificationLike) -> tuple[str, str, str]:
    """Compose an immediate urgent email (MVP: ``license_expired`` only, D5).

    Reuses the already-rendered ``title``/``body`` produced by the alert
    engine and appends a formal-tuteo call to action.
    """

    subject = f"[Solercia] {notification.title}"
    text_body = (
        "Hola,\n\n"
        f"{notification.body}\n\n"
        "Verifica tu licencia y revisa el detalle en Solercia lo antes posible.\n\n"
        "— Equipo Solercia"
    )
    html_body = (
        "<html><body>"
        "<p>Hola,</p>"
        f"<p>{notification.body}</p>"
        "<p>Verifica tu licencia y revisa el detalle en Solercia lo antes posible.</p>"
        "<p>— Equipo Solercia</p>"
        "</body></html>"
    )
    return subject, text_body, html_body


def render_digest(
    user: UserLike, notifications: Sequence[NotificationLike]
) -> tuple[str, str, str]:
    """Compose a single digest email summarizing every pending notification."""

    count = len(notifications)
    subject = f"[Solercia] Resumen de tus notificaciones ({count})"

    items_text = "\n".join(f"- {n.title}: {n.body}" for n in notifications)
    text_body = (
        f"Hola {user.primer_nombre},\n\n"
        "Este es el resumen de tus notificaciones pendientes:\n\n"
        f"{items_text}\n\n"
        "Ingresa a Solercia para revisar el detalle de cada una.\n\n"
        "— Equipo Solercia"
    )

    items_html = "".join(
        f"<li><strong>{n.title}:</strong> {n.body}</li>" for n in notifications
    )
    html_body = (
        "<html><body>"
        f"<p>Hola {user.primer_nombre},</p>"
        "<p>Este es el resumen de tus notificaciones pendientes:</p>"
        f"<ul>{items_html}</ul>"
        "<p>Ingresa a Solercia para revisar el detalle de cada una.</p>"
        "<p>— Equipo Solercia</p>"
        "</body></html>"
    )
    return subject, text_body, html_body
