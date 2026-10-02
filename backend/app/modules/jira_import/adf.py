"""Atlassian Document Format (ADF) -> Markdown, best effort and dependency free.

Covers the nodes Jira descriptions actually use (paragraphs, headings, lists,
code blocks, quotes, tables, rules, mentions, links, emoji, media); any
unknown node degrades to the text of its children, never to an error.
"""

from typing import Any

_MARKS = {"strong": "**", "em": "_", "strike": "~~", "code": "`"}


def _text(node: dict[str, Any]) -> str:
    value = str(node.get("text", ""))
    href = None
    for mark in node.get("marks") or []:
        kind = mark.get("type")
        if kind in _MARKS and value.strip():
            value = f"{_MARKS[kind]}{value}{_MARKS[kind]}"
        elif kind == "link":
            href = (mark.get("attrs") or {}).get("href")
    return f"[{value}]({href})" if href else value


def _inline(nodes: list[dict[str, Any]] | None) -> str:
    out: list[str] = []
    for node in nodes or []:
        kind = node.get("type")
        attrs = node.get("attrs") or {}
        if kind == "text":
            out.append(_text(node))
        elif kind == "hardBreak":
            out.append("\n")
        elif kind == "mention":
            out.append(str(attrs.get("text") or "@usuario"))
        elif kind == "emoji":
            out.append(str(attrs.get("text") or attrs.get("shortName") or ""))
        elif kind in ("inlineCard", "blockCard", "embedCard"):
            out.append(str(attrs.get("url") or ""))
        elif kind == "status":
            out.append(f"[{attrs.get('text', '')}]")
        elif kind == "date":
            out.append(str(attrs.get("timestamp", "")))
        else:
            out.append(_inline(node.get("content")))
    return "".join(out)


def _block(node: dict[str, Any], depth: int = 0) -> str:
    kind = node.get("type")
    content = node.get("content") or []
    attrs = node.get("attrs") or {}
    if kind == "paragraph":
        return _inline(content)
    if kind == "heading":
        return f"{'#' * int(attrs.get('level', 1) or 1)} {_inline(content)}"
    if kind in ("bulletList", "orderedList"):
        lines = []
        for index, item in enumerate(content, start=1):
            bullet = f"{index}." if kind == "orderedList" else "-"
            body = "\n".join(_block(child, depth + 1) for child in item.get("content") or [])
            first, *rest = body.split("\n") or [""]
            lines.append(f"{'  ' * depth}{bullet} {first}")
            lines.extend(rest)
        return "\n".join(lines)
    if kind == "codeBlock":
        return f"```{attrs.get('language') or ''}\n{_inline(content)}\n```"
    if kind == "blockquote":
        inner = "\n\n".join(_block(child, depth) for child in content)
        return "\n".join(f"> {line}" for line in inner.split("\n"))
    if kind == "rule":
        return "---"
    if kind == "table":
        rows = []
        for row in content:
            cells = [
                " ".join(_block(c, depth) for c in cell.get("content") or []).replace("\n", " ")
                for cell in row.get("content") or []
            ]
            rows.append("| " + " | ".join(cells) + " |")
        if rows:
            width = rows[0].count("|") - 1
            rows.insert(1, "|" + " --- |" * max(width, 1))
        return "\n".join(rows)
    if kind in ("mediaSingle", "mediaGroup", "media"):
        return "_(adjunto en Jira)_"
    if kind in ("panel", "expand", "nestedExpand", "layoutSection", "layoutColumn", "doc"):
        return "\n\n".join(part for child in content if (part := _block(child, depth)))
    return _inline(content) if content else _inline([node])


def adf_to_markdown(value: Any) -> str | None:
    """Convert an ADF document (or a plain string) to Markdown; ``None`` if empty."""

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    text = _block(value).strip()
    return text or None
