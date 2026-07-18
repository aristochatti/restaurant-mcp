import json
import sys
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server import app
import server

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
    data = res.json()
    assert data["ok"] is True
    assert "extraction_available" in data


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


async def test_tool_call_returns_ui_resource(client, monkeypatch):
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

    # Need to patch places.search_restaurants since server imports from places
    import places
    monkeypatch.setattr(places, "search_restaurants", fake_search)

    res = await rpc(
        client,
        "tools/call",
        {"name": "search_restaurants", "arguments": {"location": "Rome", "limit": 1}},
        id=3,
    )
    body = read_rpc(res)
    assert "error" not in body, body

    content = body["result"]["content"]
    assert len(content) == 1, "Should return only UI resource, no text fallback"
    
    ui = content[0]
    assert ui["type"] == "resource"
    assert ui["resource"]["uri"].startswith("ui://restaurants/")
    # The mimeType should be text/html
    assert ui["resource"]["mimeType"] == "text/html"
    assert "Where to eat in Rome" in ui["resource"]["text"]
    assert "Trattoria Da Enzo" in ui["resource"]["text"]


async def test_public_host_is_accepted_not_421(client):
    """Regression guard: FastMCP's default allowed_hosts is localhost-only, which
    would 421 every request once deployed behind Alpic's public domain."""
    res = await rpc(client, "initialize", INIT_PARAMS)
    assert res.status_code != 421, "public Host header must not be rejected"


async def test_tools_list_exposes_get_maps_list_with_its_input_schema(client):
    await rpc(client, "initialize", INIT_PARAMS)
    res = await rpc(client, "tools/list", {}, id=2)

    body = read_rpc(res)
    assert "error" not in body

    tools = body["result"]["tools"]
    tool = next((t for t in tools if t["name"] == "get_maps_list"), None)
    assert tool, f"get_maps_list missing from: {[t['name'] for t in tools]}"
    assert "google maps list" in tool["description"].lower()
    assert "url" in tool["inputSchema"]["required"]
    assert tool["inputSchema"]["properties"]["url"]["type"] == "string"


async def test_get_maps_list_tool_call(client, monkeypatch):
    def fake_fetch_from_list(url, enrich=False):
        return [
            {
                "placeId": "p1",
                "name": "Test Place",
                "address": "Test Address",
                "rating": 4.5,
                "userRatingsTotal": 100,
                "priceLevel": 2,
                "openNow": True,
                "photoUrl": None,
            }
        ]

    # Need to patch lists.fetch_from_list since server imports from lists
    import lists
    monkeypatch.setattr(lists, "fetch_from_list", fake_fetch_from_list)

    res = await rpc(
        client,
        "tools/call",
        {
            "name": "get_maps_list",
            "arguments": {
                "url": "https://maps.app.goo.gl/some-list"
            }
        },
        id=4
    )
    body = read_rpc(res)
    assert "error" not in body

    content = body["result"]["content"]
    assert len(content) == 1
    ui = content[0]
    assert ui["type"] == "resource"
    assert ui["resource"]["mimeType"] == "text/html"
    assert "Test Place" in ui["resource"]["text"]


