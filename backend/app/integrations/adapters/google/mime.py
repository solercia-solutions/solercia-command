"""Gmail MIME `payload` → plain text (change 16-adapter-google, design.md
"Parseo de cuerpo": `email`/`base64` de stdlib sobre `payload` MIME
(`format=full`)). Gmail's message resource nests a multipart tree of
`text/plain`/`text/html` parts, each base64url-encoded — `body_text` is the
ONE function `mail.py` uses to turn that tree into the plain string
`MailMessage.body_text` needs.

Never raises on an unusual/attachment-only payload shape — a message this
adapter cannot find readable text in maps to `""`, not a crash (mirrors the
15's degrade-gracefully convention for provider payload edge cases).
"""

import base64
import re
from typing import Any

# A conservative plain-text approximation for an HTML-only body: strip
# every tag, collapse the surrounding whitespace. Not a full HTML→text
# renderer (no entity decoding beyond what Python's `html` module already
# handles at read time) — good enough for a snippet/summary, never crashes.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")


def _decode_base64url(data: str) -> str:
    """Decode a Gmail `body.data` base64url string (no `=` padding
    guaranteed) to UTF-8 text."""

    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
        "utf-8", errors="replace"
    )


def _find_part(payload: dict[str, Any], mime_type: str) -> dict[str, Any] | None:
    """Depth-first search of ``payload``'s ``parts`` tree for the first
    node whose ``mimeType`` is ``mime_type`` (also matches ``payload``
    itself for a single-part message)."""

    if payload.get("mimeType") == mime_type:
        return payload
    for part in payload.get("parts") or []:
        found = _find_part(part, mime_type)
        if found is not None:
            return found
    return None


def _part_data(part: dict[str, Any]) -> str | None:
    return (part.get("body") or {}).get("data")


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def body_text(payload: dict[str, Any]) -> str:
    """Decode a Gmail message ``payload``'s MIME body to plain text.

    Prefers the ``text/plain`` part; when only ``text/html`` is present,
    strips tags to a plain-text approximation. Returns ``""`` when no
    readable body part is found (e.g. an attachment-only message) — NEVER
    raises."""

    plain_part = _find_part(payload, "text/plain")
    if plain_part is not None:
        data = _part_data(plain_part)
        if data:
            return _decode_base64url(data).strip()

    html_part = _find_part(payload, "text/html")
    if html_part is not None:
        data = _part_data(html_part)
        if data:
            return _strip_html(_decode_base64url(data))

    return ""
