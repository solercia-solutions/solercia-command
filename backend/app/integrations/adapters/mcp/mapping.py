"""MCP SDK types -> core DTOs (change 19-mcp-connector, design.md "adaptador
MCP + reader del puerto + ... + mapeo→DTOs"). Pure functions — no I/O, no
adapter state; every function here is trivially unit-testable in isolation.

Content mapped here is treated as INERT DATA (mcp-connector/spec.md MC-R8):
these functions only copy fields into a frozen dataclass, they NEVER
evaluate, execute or interpolate anything from the provider's response.
"""

import base64

from mcp import types as mcp_types

from app.integrations.dtos import ExternalResource, ExternalResourceContent, ExternalTool


def map_resource(resource: mcp_types.Resource) -> ExternalResource:
    """`mcp.types.Resource` (a `resources/list` entry) -> `ExternalResource`."""

    return ExternalResource(
        uri=str(resource.uri),
        name=resource.name,
        mime_type=resource.mimeType,
        description=resource.description,
    )


def map_tool(tool: mcp_types.Tool) -> ExternalTool:
    """`mcp.types.Tool` (a `tools/list` entry) -> `ExternalTool`.

    ``read_only`` mirrors the provider's own ``readOnlyHint`` VERBATIM — an
    ABSENT annotation or an explicit ``readOnlyHint: false`` both map to
    ``False``; only an explicit ``readOnlyHint: true`` maps to ``True``
    (mcp-connector/spec.md, "el hint por sí solo nunca es suficiente" —
    THIS DTO carries the raw hint, the allowlist ∩ hint enforcement itself
    lives in ``reader.py``, never here).
    """

    read_only = bool(tool.annotations.readOnlyHint) if tool.annotations is not None else False
    return ExternalTool(
        name=tool.name,
        description=tool.description,
        read_only=read_only,
        input_schema=tool.inputSchema,
    )


def resource_content_byte_length(
    content: mcp_types.TextResourceContents | mcp_types.BlobResourceContents,
) -> int:
    """The actual byte size of ``content`` — text is UTF-8 encoded, a blob's
    ``blob`` field is already base64 (MCP spec) and is decoded back to raw
    bytes so the tope compares against the REAL size, not the inflated
    base64 length."""

    if isinstance(content, mcp_types.TextResourceContents):
        return len(content.text.encode("utf-8"))
    return len(base64.b64decode(content.blob))


def map_resource_content(
    content: mcp_types.TextResourceContents | mcp_types.BlobResourceContents,
) -> ExternalResourceContent:
    """`mcp.types.{Text,Blob}ResourceContents` -> `ExternalResourceContent`.

    Exactly one of ``text``/``blob_b64`` is populated, mirroring the SDK's
    own union. ``truncated`` is always ``False`` here — the byte tope
    rejection (MC-R4) is enforced by the CALLER (``reader.py``) BEFORE this
    function is ever invoked for an oversized resource, so an
    ``ExternalResourceContent`` this function returns is always the
    complete content.
    """

    if isinstance(content, mcp_types.TextResourceContents):
        return ExternalResourceContent(
            uri=str(content.uri),
            mime_type=content.mimeType,
            text=content.text,
            blob_b64=None,
            truncated=False,
        )
    return ExternalResourceContent(
        uri=str(content.uri),
        mime_type=content.mimeType,
        text=None,
        blob_b64=content.blob,
        truncated=False,
    )


def map_call_tool_result(result: mcp_types.CallToolResult) -> ExternalResourceContent:
    """`mcp.types.CallToolResult` -> `ExternalResourceContent`.

    A tool call is not URI-addressed (``uri=None``). Only the TEXT parts of
    the result's content blocks are concatenated — image/audio/embedded
    parts are out of scope for this wave's read-only text-oriented ports
    (mirrors ``ExternalResourceContent`` never carrying non-text payloads
    beyond ``blob_b64``, which `read_resource` alone populates).
    """

    text_parts = [
        block.text for block in result.content if isinstance(block, mcp_types.TextContent)
    ]
    text = "\n".join(text_parts) if text_parts else None
    return ExternalResourceContent(
        uri=None,
        mime_type=None,
        text=text,
        blob_b64=None,
        truncated=False,
    )
