"""Diagnostic script: verify what URL the MCP SDK actually POSTs to.

Run with pulse server running:
    cd war-room
    .venv/bin/python scripts/diagnose_mcp_url.py

Watch pulse server logs: should show POST /mcp/mcp 200 OK.
If it shows POST /mcp → the URL is reaching the SDK correctly but something
truncates it upstream. Report both labels to narrow the culprit.
"""
from __future__ import annotations

import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

HARDCODED_URL = "http://localhost:8001/mcp/mcp"
ENV_URL = os.environ.get("PULSE_MCP_URL", "NOT_SET")


async def probe(label: str, url: str) -> None:
    print(f"[{label}] connecting to {url!r} ...")
    try:
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                print(f"[{label}] OK — tools: {names}")
    except Exception as exc:
        print(f"[{label}] ERROR: {type(exc).__name__}: {exc}")


async def main() -> None:
    print(f"PULSE_MCP_URL from env : {ENV_URL!r}")
    print(f"hardcoded URL          : {HARDCODED_URL!r}")
    print()

    await probe("hardcoded", HARDCODED_URL)

    if ENV_URL != "NOT_SET":
        await probe("from_env", ENV_URL)
    else:
        print("[from_env] PULSE_MCP_URL not set — skipping")


asyncio.run(main())
