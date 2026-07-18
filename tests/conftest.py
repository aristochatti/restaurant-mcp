"""Shared fixtures for all server-level tests.

The MCP StreamableHTTPSessionManager can only be started once per process,
so the ``client`` fixture is session-scoped and lives here in conftest so
every test module (test_server, test_phone_booking, …) shares the same
single lifespan instead of each trying to start its own.
"""

import json

import httpx
import pytest
from asgi_lifespan import LifespanManager

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from server import app

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "0.0.0"},
}


@pytest.fixture(scope="session")
async def client():
    """Drive the real ASGI app with its lifespan, session-scoped so the MCP
    session manager is only started once across all test modules."""
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://resto-mcp.example.com", timeout=10
        ) as c:
            yield c


def read_rpc(res: httpx.Response) -> dict:
    """The transport may answer as JSON or as an SSE stream; accept either."""
    if "text/event-stream" in res.headers.get("content-type", ""):
        line = next((ln for ln in res.text.splitlines() if ln.startswith("data:")), None)
        assert line, f"no SSE data frame in: {res.text[:200]}"
        return json.loads(line[5:].strip())
    return res.json()


async def rpc(client: httpx.AsyncClient, method: str, params: dict, id: int = 1):
    return await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        content=json.dumps({"jsonrpc": "2.0", "id": id, "method": method, "params": params}),
    )
