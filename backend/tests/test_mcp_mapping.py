"""RED tests for `mapping.py` (change 19-mcp-connector, Fix 4 WARNING:
`resource_content_byte_length`'s `base64.b64decode` had no guard).
"""

import base64

import pytest
from mcp import types as mcp_types

from app.integrations.adapters.mcp import errors
from app.integrations.adapters.mcp.mapping import resource_content_byte_length


def test_resource_content_byte_length_rejects_non_base64_blob_with_domain_error() -> None:
    """Un `blob` que NO es base64 válido levanta `McpProtocolError` — nunca
    un `binascii.Error` sin controlar."""

    content = mcp_types.BlobResourceContents(uri="fake://notes/blob", blob="no-es-base64!!!")

    with pytest.raises(errors.McpProtocolError) as exc_info:
        resource_content_byte_length(content)

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "mcp_protocol_error"


def test_resource_content_byte_length_accepts_valid_base64_blob() -> None:
    """Regresión: un `blob` base64 válido se sigue midiendo correctamente."""

    raw = b"contenido binario de prueba"
    content = mcp_types.BlobResourceContents(
        uri="fake://notes/blob", blob=base64.b64encode(raw).decode("ascii")
    )

    assert resource_content_byte_length(content) == len(raw)
