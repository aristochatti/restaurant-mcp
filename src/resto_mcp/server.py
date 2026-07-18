import os
from typing import Annotated, Any

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ContentBlock, EmbeddedResource, TextContent, TextResourceContents
from pydantic import AnyUrl, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from .carousel import build_carousel_html
from .places import search_restaurants
from .booking import investigate_restaurant_booking

import sys
from pathlib import Path
_scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.append(str(_scripts_dir))
from extract_list import resolve_list_id, fetch_list_data, parse_places

def _transport_security() -> TransportSecuritySettings:
    """FastMCP defaults allowed_hosts to localhost only, with DNS-rebinding
    protection on. Behind Alpic the Host header is the public domain, so that
    default would 421 every request. Rebinding protection exists to stop a
    malicious page from reaching a server bound to the user's loopback  not a
    threat model a public MCP endpoint sits in  so it's off unless you pin
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


# Stateless Streamable HTTP  each request stands alone (simple + Alpic-friendly).
mcp = FastMCP(
    "resto-mcp",
    stateless_http=True,
    streamable_http_path="/mcp",
    transport_security=_transport_security(),
)


def _create_ui_resource(uri: str, html: str) -> EmbeddedResource:
    """Create a UI resource that Mistral Vibe will render as HTML in a canvas.
    
    For Mistral Vibe specifically, we use text/html mimeType and ensure
    the HTML is self-contained. The key is to return ONLY this resource block
    with NO text fallback, so Vibe has no choice but to render it.
    
    IMPORTANT: Mistral Vibe expects the HTML to be in the 'text' field of the
    resource, and it will render it in a canvas when the mimeType is text/html.
    
    We also add metadata to explicitly signal that this should be rendered in a canvas.
    """
    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri=AnyUrl(uri),
            mimeType="text/html",
            text=html,
            meta={
                "ui": {
                    "renderAs": "canvas"
                }
            }
        ),
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

    ui = _create_ui_resource(
        f"ui://restaurants/{location}",
        build_carousel_html(location, restaurants)
    )

    # IMPORTANT: Return ONLY the UI resource, no text fallback.
    # Mistral Vibe will render the HTML resource in a canvas when:
    # 1. It's the only content block returned
    # 2. It has mimeType "text/html"
    # 3. The HTML is self-contained (no external dependencies)
    return [ui]


def _summarise(index: int, r: dict[str, Any]) -> str:
    price = " \u00b7 " + "\u20ac" * r["priceLevel"] if r.get("priceLevel") else ""
    rating = f" \u00b7 \u2605{r['rating']}" if r.get("rating") else ""
    return f"{index + 1}. {r['name']}{rating}{price} \u2014 {r['address']}"


@mcp.tool(
    name="investigate_restaurant_booking",
    title="Investigate restaurant booking",
    description=(
        "Investigate booking methodologies and reservation options for a specific restaurant. "
        "Input the restaurant name/location, target date, preferred time range, and guest count. "
        "Returns available booking channels including phone, email, and pre-filled Zenchef or other platform links."
    ),
)
def investigate_restaurant_booking_tool(
    restaurant: Annotated[
        str,
        Field(description="Name and optional location of the restaurant (e.g. 'Septime Paris' or 'La D\u00e9mocratie, Paris')"),
    ],
    date: Annotated[
        str | None,
        Field(description="Reservation date (YYYY-MM-DD format, or 'today'/'tomorrow'). Defaults to 'today'"),
    ] = "today",
    time_start: Annotated[
        str | None,
        Field(description="Preferred meal start time (HH:MM format). Defaults to '19:00'"),
    ] = "19:00",
    time_end: Annotated[
        str | None,
        Field(description="Preferred meal end time (HH:MM format). Defaults to '21:00'"),
    ] = "21:00",
    pax: Annotated[
        int | None,
        Field(description="Number of guests/party size. Defaults to 2", ge=1),
    ] = 2,
) -> str:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return "Error: Google Places API key is not configured on the server."
        
    try:
        result = investigate_restaurant_booking(
            restaurant_query=restaurant,
            date_str=date or "today",
            time_start=time_start or "19:00",
            time_end=time_end or "21:00",
            pax=pax or 2,
            api_key=api_key
        )
        import json
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error investigating booking options: {str(e)}"


@mcp.tool(
    name="get_maps_list",
    title="Get Google Maps List",
    description=(
        "Extracts place names, addresses, coordinates, custom user notes, price levels, "
        "and photos from a public Google Maps shared list link (maps.app.goo.gl or playlist URL)."
    ),
)
def get_maps_list_tool(
    url: Annotated[
        str,
        Field(description="Public/shared Google Maps list link (e.g. https://maps.app.goo.gl/PyTE2vs6cQ7mvVLx5)"),
    ],
    enrich: Annotated[
        bool | None,
        Field(description="If true, enriches details using Google Places API (requires API key)"),
    ] = False,
    limit: Annotated[
        int | None,
        Field(description="Maximum number of places to retrieve from the raw list data. Default is 500", ge=1, le=500),
    ] = 500,
    user_location: Annotated[
        str | None,
        Field(description="User location coordinates (e.g., '48.8566,2.3522') or address (e.g., 'Paris, France') to sort results by distance"),
    ] = None,
    top_n: Annotated[
        int | None,
        Field(description="If specified, filters and returns only the top N closest places (only these will be enriched)"),
    ] = None,
) -> str:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if enrich and not api_key:
        return "Error: Enrichment requested but no Google Places API key found."
        
    try:
        list_id = resolve_list_id(url)
        if not list_id:
            return "Error: Could not resolve a Google Maps list ID from the provided URL."
            
        raw_data = fetch_list_data(list_id, limit=limit or 500)
        if not raw_data:
            return "Error: Failed to fetch list content from Google Maps."
            
        api_key_to_use = api_key if enrich else None
        parsed_data = parse_places(
            raw_data,
            api_key=api_key_to_use,
            user_location=user_location,
            top_n=top_n
        )
        if not parsed_data:
            return "Error: Failed to parse place details."
            
        import json
        return json.dumps(parsed_data, indent=2)
    except Exception as e:
        return f"Error extracting maps list: {str(e)}"


@mcp.custom_route("/", methods=["GET"])
async def root(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("resto-mcp is running. POST /mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


@mcp.custom_route("/proxy-image", methods=["GET"])
async def proxy_image(request: Request) -> Response:
    """Proxy for Google Places photos to avoid CORS issues in Mistral Vibe."""
    url = request.query_params.get("url")
    if not url or not url.startswith("https://places.googleapis.com"):
        return Response(status_code=400, content="Invalid URL")
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.is_error:
                return Response(status_code=resp.status_code, content="Failed to fetch image")
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24h
            )
    except Exception:
        return Response(status_code=500, content="Error fetching image")


class RejectMcpGet:
    """Answer GET /mcp with 405 instead of opening an SSE stream.

    Streamable HTTP allows GET for server->client push, but we run stateless, so
    such a stream can never carry anything  it would just pin a connection open
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


# Built last: snapshot both SSE and streamable-HTTP apps.
streamable_app = mcp.streamable_http_app()
streamable_app.add_middleware(RejectMcpGet)

sse_app = mcp.sse_app()

from starlette.middleware.cors import CORSMiddleware
for sub_app in (streamable_app, sse_app):
    sub_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )


class CombinedASGIApp:
    def __init__(self, sse, streamable):
        self.sse = sse
        self.streamable = streamable

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            # Delegate lifespan startup/shutdown to both apps
            # We want streamable_app to run first so session manager starts
            await self.streamable(scope, receive, send)
            return
        
        path = scope.get("path", "")
        if path.startswith("/sse") or path.startswith("/messages"):
            await self.sse(scope, receive, send)
        else:
            await self.streamable(scope, receive, send)


app = CombinedASGIApp(sse_app, streamable_app)


def main() -> None:
    # Alpic injects MCP_HTTP_PORT; fall back to PORT / 3000 for local runs.
    port = int(os.environ.get("MCP_HTTP_PORT") or os.environ.get("PORT") or 3000)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
