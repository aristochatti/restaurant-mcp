import json

import httpx
import pytest

from resto_mcp import server

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "0.0.0"},
}


from conftest import rpc, read_rpc, INIT_PARAMS  # noqa: F401 – re-exported for readability


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
    
    We return ONLY the UI resource (no text fallback) to ensure Mistral Vibe
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
    # Should only have one content block - the UI resource
    assert len(content) == 1
    
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


async def test_tools_list_exposes_investigate_restaurant_booking_with_its_input_schema(client):
    await rpc(client, "initialize", INIT_PARAMS)
    res = await rpc(client, "tools/list", {}, id=2)

    body = read_rpc(res)
    assert "error" not in body

    tools = body["result"]["tools"]
    tool = next((t for t in tools if t["name"] == "investigate_restaurant_booking"), None)
    assert tool, f"investigate_restaurant_booking missing from: {[t['name'] for t in tools]}"
    assert "booking" in tool["description"].lower()
    assert "restaurant" in tool["inputSchema"]["required"]
    assert tool["inputSchema"]["properties"]["restaurant"]["type"] == "string"


async def test_investigate_restaurant_booking_tool_call(client, monkeypatch):
    def fake_investigate(restaurant_query, date_str, time_start, time_end, pax, api_key):
        return {
            "restaurant_details": {"name": "Test Bistro"},
            "booking_options": [{"type": "phone", "phone_number": "123"}]
        }

    monkeypatch.setattr(server, "investigate_restaurant_booking", fake_investigate)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")

    res = await rpc(
        client,
        "tools/call",
        {
            "name": "investigate_restaurant_booking",
            "arguments": {
                "restaurant": "Test Bistro",
                "date": "today"
            }
        },
        id=3
    )
    body = read_rpc(res)
    assert "error" not in body

    content = body["result"]["content"]
    text = next(c for c in content if c["type"] == "text")
    data = json.loads(text["text"])
    assert data["restaurant_details"]["name"] == "Test Bistro"
    assert data["booking_options"][0]["type"] == "phone"


async def test_tools_list_exposes_get_maps_list_with_its_input_schema(client):
    await rpc(client, "initialize", INIT_PARAMS)
    res = await rpc(client, "tools/list", {}, id=2)

    body = read_rpc(res)
    assert "error" not in body

    tools = body["result"]["tools"]
    tool = next((t for t in tools if t["name"] == "get_maps_list"), None)
    assert tool, f"get_maps_list missing from: {[t['name'] for t in tools]}"
    assert "shared list" in tool["description"].lower()
    assert "url" in tool["inputSchema"]["required"]
    assert tool["inputSchema"]["properties"]["url"]["type"] == "string"


async def test_get_maps_list_tool_call(client, monkeypatch):
    def fake_resolve(url):
        return "list-123"

    def fake_fetch(list_id, limit):
        return {"some": "raw-data"}

    def fake_parse(raw_data, *args, **kwargs):
        return {"title": "Test List", "places": [{"name": "Test Place"}]}

    monkeypatch.setattr(server, "resolve_list_id", fake_resolve)
    monkeypatch.setattr(server, "fetch_list_data", fake_fetch)
    monkeypatch.setattr(server, "parse_places", fake_parse)

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
    text = next(c for c in content if c["type"] == "text")
    data = json.loads(text["text"])
    assert data["title"] == "Test List"
    assert data["places"][0]["name"] == "Test Place"


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


