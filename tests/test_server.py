import json
import sys
from pathlib import Path

import httpx
import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import server
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


from conftest import rpc, read_rpc, INIT_PARAMS  # noqa: F401  re-exported for readability


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
    """Test that the tool returns a UI resource with the correct mimeType.
    
    We return a text instruction followed by the UI resource to ensure Mistral Vibe
    renders the HTML in a canvas.
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
    # Should have two content blocks: instruction text and UI resource
    assert len(content) == 2
    
    # First block should be the instruction
    instruction = content[0]
    assert instruction["type"] == "text"
    assert "canvas" in instruction["text"].lower()
    
    # Second block should be the UI resource
    ui = content[1]
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
    async def fake_fetch_from_list(url, *args, **kwargs):
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

    monkeypatch.setattr(server, "fetch_from_list", fake_fetch_from_list)

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
    # Should have two content blocks: instruction text and UI resource
    assert len(content) == 2
    
    # First block should be the instruction
    instruction = content[0]
    assert instruction["type"] == "text"
    assert "canvas" in instruction["text"].lower()
    
    # Second block should be the UI resource
    ui = content[1]
    assert ui["type"] == "resource"
    assert ui["resource"]["mimeType"] == "text/html"
    assert "Test Place" in ui["resource"]["text"]


async def test_server_advertises_logo_icon(client):
    res = await rpc(client, "initialize", INIT_PARAMS)
    body = read_rpc(res)
    assert "error" not in body
    server_info = body["result"]["serverInfo"]
    assert "icons" in server_info
    assert server_info["icons"][0]["src"] == "/logo.png"
    assert server_info["icons"][0]["mimeType"] == "image/png"


async def test_logo_endpoint_serves_image(client):
    res = await client.get("/logo.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert len(res.content) > 0
