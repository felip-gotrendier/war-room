"""Empirical test: what path does the MCP SDK actually POST to?

Uses httpx directly (no asyncio server needed) to intercept the outgoing
request before it hits the network.  No pulse server required.

Run:
    .venv/bin/python scripts/test_mcp_url.py
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# Intercept httpx.AsyncClient.stream to capture the URL
# ---------------------------------------------------------------------------

_captured: list[str] = []


class _FakeStreamCM:
    """Minimal async context manager returned by the patched client.stream()."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def __aenter__(self) -> httpx.Response:
        _captured.append(self._url)
        # Return a minimal 200 response with valid MCP JSON so the SDK can
        # proceed past the HTTP layer.  Content mimics an initialize response.
        resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mock", "version": "1.0"},
                },
            }).encode(),
            request=httpx.Request("POST", self._url),
        )
        return resp

    async def __aexit__(self, *_) -> None:
        pass


def _fake_stream(method: str, url, **kwargs) -> _FakeStreamCM:
    return _FakeStreamCM(str(url))


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


async def probe(label: str, url: str) -> None:
    _captured.clear()
    print(f"\n--- {label}: url={url!r} ---")

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    # Patch the AsyncClient that the SDK uses so requests never hit the network.
    with patch("httpx.AsyncClient.stream", side_effect=_fake_stream):
        try:
            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=5)
        except Exception as exc:
            pass  # Expected: mock returns wrong response format

    print(f"    URLs captured by httpx: {_captured}")
    if _captured:
        actual = _captured[0]
        if actual == url:
            print(f"    MATCH — SDK posts to the full URL (SDK is correct)")
        else:
            print(f"    MISMATCH — expected {url!r}, got {actual!r}  ← SDK truncates!")


async def main() -> None:
    await probe("double_path", "http://localhost:9001/mcp/mcp")
    await probe("single_path", "http://localhost:9001/mcp")

    print("\n=== VERDICT ===")
    print("If double_path shows MATCH → SDK is correct, bug is elsewhere in war-room.")
    print("If double_path shows MISMATCH → SDK truncates the path.")


asyncio.run(main())
