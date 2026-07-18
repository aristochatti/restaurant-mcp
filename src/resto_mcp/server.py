import os
from typing import Annotated, Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ContentBlock, TextContent
from mcp_ui_server import create_ui_resource
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .carousel import build_carousel_html
from .places import search_restaurants

def _transport_security() -> TransportSecuritySettings:
    """FastMCP defaults allowed_hosts to localhost only, with DNS-rebinding
    protection on. Behind Alpic the Host header is the public domain, so that
    default would 421 every request. Rebinding protection exists to stop a
    malicious page from reaching a server bound to the user's loopback — not a
    threat model a public MCP endpoint sits in — so it's off unless you pin
    hosts explicitly via MCP_ALLOWED_HOSTS (comma-separated, ':*' wildcards ok).
    """
    allowed = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not allowed:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed,
        allowed_origins=[f"https://{h}" for h in allowed],
    )


# Stateless Streamable HTTP — each request stands alone (simple + Alpic-friendly).
mcp = FastMCP(
    "resto-mcp",
    stateless_http=True,
    streamable_http_path="/mcp",
    transport_security=_transport_security(),
)


@mcp.tool(
    name="search_restaurants",
    title="Search restaurants",
    description=(
        "Search restaurants in a given location (city, neighborhood, or address) and "
        "display them as an interactive carousel. Use whenever the user asks where to "
        "eat or for restaurant recommendations."
    ),
)
async def search_restaurants_tool(
    location: Annotated[
        str,
        Field(description="City, neighborhood, or address, e.g. 'Paris 11e' or 'Shibuya, Tokyo'"),
    ],
    limit: Annotated[
        int | None,
        Field(description="How many restaurants to return (default 8)", ge=1, le=20),
    ] = None,
) -> list[ContentBlock]:
    restaurants = await search_restaurants(location, limit or 8)

    if not restaurants:
        return [TextContent(type="text", text=f'No restaurants found in "{location}".')]

    ui = create_ui_resource({
        "uri": f"ui://restaurants/{location}",
        "content": {"type": "rawHtml", "htmlString": build_carousel_html(location, restaurants)},
        "encoding": "text"
    })

    # Text fallback for hosts that don't render mcp-ui.
    fallback = "\n".join(_summarise(i, r) for i, r in enumerate(restaurants))
    text = f"Found {len(restaurants)} restaurants in {location}:\n{fallback}"

    return [ui, TextContent(type="text", text=text)]


def _summarise(index: int, r: dict[str, Any]) -> str:
    price = " · " + "€" * r["priceLevel"] if r.get("priceLevel") else ""
    rating = f" · ★{r['rating']}" if r.get("rating") else ""
    return f"{index + 1}. {r['name']}{rating}{price} — {r['address']}"


@mcp.custom_route("/", methods=["GET"])
async def root(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("resto-mcp is running. POST /mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


class RejectMcpGet:
    """Answer GET /mcp with 405 instead of opening an SSE stream.

    Streamable HTTP allows GET for server->client push, but we run stateless, so
    such a stream can never carry anything — it would just pin a connection open
    forever. Kept as pure ASGI rather than BaseHTTPMiddleware, which buffers
    responses and would break the SSE streaming that POST /mcp relies on.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"].rstrip("/") == "/mcp"
        ):
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": "server-error",
                    "error": {"code": -32600, "message": "Method Not Allowed: use POST /mcp."},
                },
                status_code=405,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


# Built last: streamable_http_app() snapshots the routes registered so far.
app = mcp.streamable_http_app()
app.add_middleware(RejectMcpGet)


def main() -> None:
    # Alpic injects MCP_HTTP_PORT; fall back to PORT / 3000 for local runs.
    port = int(os.environ.get("MCP_HTTP_PORT") or os.environ.get("PORT") or 3000)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
