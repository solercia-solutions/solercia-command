"""``ExternalResourceReaderPort`` implementation for MCP (change
19-mcp-connector, design.md "reader.py": `list_resources`/`read_resource`/
`list_tools`/`call_tool` orquestando sesión+mapeo+topes+enforcement").

``read_resource``'s byte tope (MC-R4, "sin cargar el contenido completo"):
the MCP SDK's `ClientSession.read_resource` is a SYNCHRONOUS JSON-RPC
call — the Streamable HTTP transport delivers a resource's content as ONE
response payload, with no server-side truncation or streaming primitive
for a SINGLE `resources/read`. This reader honors the tope at the DOMAIN
boundary instead: an oversized response is measured and REJECTED before it
is ever mapped into an `ExternalResourceContent` — the raw bytes never
reach the DTO, the caller, or any log, even though the SDK necessarily
buffered them once in-process to deliver the JSON-RPC response.

``call_tool`` enforcement (MC-R5, default-deny): `name ∈ tools_allowlist`
(authoritative, admin-controlled, per-connector) **∩** `readOnlyHint ==
true` (secondary, provider-controlled — the server is UNTRUSTED data, so
its hint is NEVER trusted alone). A name absent from the allowlist is
rejected WITHOUT ever opening a session toward the server
(mcp-connector/spec.md, "se rechaza sin contactar al servidor").
"""

from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp import ClientSession
from pydantic import AnyUrl

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.mcp import errors
from app.integrations.adapters.mcp.mapping import (
    map_call_tool_result,
    map_resource,
    map_resource_content,
    map_tool,
    resource_content_byte_length,
)
from app.integrations.adapters.mcp.session import (
    McpAccessContext,
    TransportFactory,
    decode_access_context,
    open_session,
    streamable_http_default,
)
from app.integrations.dtos import ExternalResource, ExternalResourceContent, ExternalTool
from app.integrations.ports import AccessContext


class McpResourceReader:
    """``ExternalResourceReaderPort`` implementation over the MCP SDK.

    ``transport_factory`` is injected (defaults to the real
    ``streamable_http_default``) — tests inject the in-memory fake server's
    factory instead, exercising this EXACT class against the real wire
    protocol without any real socket (MC-R11).
    """

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport_factory: TransportFactory = streamable_http_default,
    ) -> None:
        self._settings = settings
        self._transport_factory = transport_factory

    async def list_resources(self, ctx: AccessContext) -> list[ExternalResource]:
        mcp_ctx = decode_access_context(ctx)
        async with self._open(mcp_ctx) as session:
            result = await session.list_resources()
        resources = [map_resource(resource) for resource in result.resources]
        return resources[: self._settings.MCP_MAX_LIST_ITEMS]

    async def read_resource(self, ctx: AccessContext, uri: str) -> ExternalResourceContent:
        mcp_ctx = decode_access_context(ctx)
        async with self._open(mcp_ctx) as session:
            result = await session.read_resource(AnyUrl(uri))

        if not result.contents:
            return ExternalResourceContent(
                uri=uri, mime_type=None, text=None, blob_b64=None, truncated=False
            )

        content = result.contents[0]
        if resource_content_byte_length(content) > self._settings.MCP_MAX_RESOURCE_BYTES:
            # The oversized content is discarded HERE — never mapped into a
            # DTO, never returned to the caller (see module docstring).
            raise errors.McpResourceTooLargeError()
        return map_resource_content(content)

    async def list_tools(self, ctx: AccessContext) -> list[ExternalTool]:
        mcp_ctx = decode_access_context(ctx)
        async with self._open(mcp_ctx) as session:
            result = await session.list_tools()
        tools = [map_tool(tool) for tool in result.tools]
        return tools[: self._settings.MCP_MAX_LIST_ITEMS]

    async def call_tool(
        self, ctx: AccessContext, name: str, arguments: dict[str, Any]
    ) -> ExternalResourceContent:
        mcp_ctx = decode_access_context(ctx)
        if name not in mcp_ctx.tools_allowlist:
            # Default-deny — REJECTED without ever opening a session.
            raise errors.McpToolNotAllowedError()

        # NOTE: the enforcement DECISION is captured here but the domain
        # error is raised AFTER the `async with` block below exits cleanly
        # — the SDK's `ClientSession`/transport context managers run their
        # OWN `anyio` task groups internally, and throwing an exception
        # into a generator suspended INSIDE an active task group wraps it
        # in a `BaseExceptionGroup` (an anyio/asyncio gotcha, not a
        # `McpToolNotAllowedError` the caller could still catch cleanly).
        # Same reasoning `read_resource`'s byte-tope check already follows.
        result = None
        async with self._open(mcp_ctx) as session:
            tools_result = await session.list_tools()
            tool = next((entry for entry in tools_result.tools if entry.name == name), None)
            annotations = tool.annotations if tool is not None else None
            is_read_only = annotations is not None and bool(annotations.readOnlyHint)
            if is_read_only:
                result = await session.call_tool(name, arguments)

        if result is None:
            # Allowlisted alone is never enough — the hint must be
            # explicitly `True` (mcp-connector/spec.md MC-R5).
            raise errors.McpToolNotAllowedError()
        return map_call_tool_result(result)

    def _open(self, mcp_ctx: McpAccessContext) -> AbstractAsyncContextManager[ClientSession]:
        return open_session(
            mcp_ctx, transport_factory=self._transport_factory, settings=self._settings
        )
