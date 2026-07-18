import json

import httpx
import pytest
from asgi_lifespan import LifespanManager

from resto_mcp import server
from resto_mcp.server import app

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
    """Drive the real ASGI app, lifespan included, the way Alpic's proxy does.

    Session-scoped because the MCP session manager refuses to start twice, and
    driven by LifespanManager so startup/shutdown happen in one task — entering
    the lifespan context directly trips anyio's cancel-scope task check.
    """
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


async def test_health_endpoint_responds(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


async def test_root_endpoint_advertises_the_mcp_path(client):
    res = await client.get("/")
    assert res.status_code == 200
    assert "POST /mcp" in res.text


async def test_initialize_handshake_returns_the_server_identity(client):
    res = await rpc(client, "initialize", INIT_PARAMS)
    assert res.status_code == 200

    body = read_rpc(res)
    assert "error" not in body
    assert body["result"]["serverInfo"]["name"] == "resto-mcp"
    assert body["result"]["capabilities"]["tools"], "server must advertise tools capability"


async def test_tools_list_exposes_search_restaurants_with_its_input_schema(client):
    # Stateless transport: each request stands alone, but the SDK still wants
    # an initialize on the same request chain, so re-init then list.
    await rpc(client, "initialize", INIT_PARAMS)
    res = await rpc(client, "tools/list", {}, id=2)

    body = read_rpc(res)
    assert "error" not in body

    tools = body["result"]["tools"]
    tool = next((t for t in tools if t["name"] == "search_restaurants"), None)
    assert tool, f"search_restaurants missing from: {[t['name'] for t in tools]}"
    assert "restaurant" in tool["description"].lower()
    assert tool["inputSchema"]["required"] == ["location"]
    assert tool["inputSchema"]["properties"]["location"]["type"] == "string"


async def test_get_and_delete_mcp_are_rejected_with_405(client):
    for method in ("GET", "DELETE"):
        res = await client.request(method, "/mcp", headers=MCP_HEADERS)
        assert res.status_code == 405, f"{method} /mcp should be 405"

        body = res.json()
        assert body["jsonrpc"] == "2.0"
        assert body["error"]["code"] == -32600


async def test_malformed_json_body_does_not_crash_the_server(client):
    res = await client.post("/mcp", headers=MCP_HEADERS, content="{not json")
    assert res.status_code >= 400

    # Server still alive afterwards.
    health = await client.get("/health")
    assert health.status_code == 200


async def test_tool_call_returns_a_ui_resource(client, monkeypatch):
    """Test that the tool returns a UI resource with the correct mimeType.
    
    We now return ONLY the UI resource (no text fallback) to ensure clients
    render the HTML instead of using a text fallback.
    """
    async def fake_search(location, limit):
        return [
            {
                "placeId": "p1",
                "name": "Trattoria Da Enzo",
                "address": "Via dei Vascellari 29, Roma",
                "rating": 4.5,
                "userRatingsTotal": 1820,
                "priceLevel": 2,
                "openNow": True,
                "photoUrl": None,
            }
        ]

    monkeypatch.setattr(server, "search_restaurants", fake_search)

    res = await rpc(
        client,
        "tools/call",
        {"name": "search_restaurants", "arguments": {"location": "Rome", "limit": 1}},
        id=3,
    )
    body = read_rpc(res)
    assert "error" not in body, body

    content = body["result"]["content"]
    # Should only have one content block - the UI resource
    assert len(content) == 1
    
    ui = content[0]
    assert ui["type"] == "resource"
    assert ui["resource"]["uri"].startswith("ui://restaurants/")
    # The mimeType should be text/html;profile=mcp-app to signal MCP-UI support
    assert ui["resource"]["mimeType"] == "text/html;profile=mcp-app"
    assert "Where to eat in Rome" in ui["resource"]["text"]
    assert "Trattoria Da Enzo" in ui["resource"]["text"]


async def test_public_host_is_accepted_not_421(client):
    """Regression guard: FastMCP's default allowed_hosts is localhost-only, which
    would 421 every request once deployed behind Alpic's public domain."""
    res = await rpc(client, "initialize", INIT_PARAMS)
    assert res.status_code != 421, "public Host header must not be rejected"
