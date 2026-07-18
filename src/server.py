"""Resto-MCP Server

MCP server with THREE clear components:
1. places.py - Google fetching (general Places API search)
2. lists.py  - Fetching from your Google Maps lists
3. carousel.py - Visualizer (carousel HTML rendering)

Exposes FOUR MCP tools:
- search_restaurants: Search via Google Places API
- get_maps_list: Extract from Google Maps lists
- visualize_restaurants: Render restaurant data as interactive carousel
- book_restaurant: Generate booking links (external)
"""

import os
from typing import Annotated, Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ContentBlock, EmbeddedResource, TextContent, TextResourceContents
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

# =============================================================================
# THREE COMPONENTS
# =============================================================================

# 1. VISUALIZER: Carousel HTML rendering
from carousel import build_carousel_html

# 2. GOOGLE FETCHING: General Places API search
from places import search_restaurants

# 3. GOOGLE MAPS LISTS: Your saved lists extraction
from lists import fetch_from_list, EXTRACTION_AVAILABLE


# =============================================================================
# MCP SERVER SETUP
# =============================================================================

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


# =============================================================================
# TOOL 1: General Google Places Search
# =============================================================================

@mcp.tool(
    name="search_restaurants",
    title="Search Restaurants",
    description=(
        "IMMEDIATELY display an interactive carousel of restaurants when user asks "
        "'where to eat', 'find restaurants', 'show me places to eat', or similar. "
        "ALWAYS return only the carousel visualization, NEVER add text commentary. "
        "Fetch from Google Places API and render as clickable carousel UI."
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
    """Search via Google Places API and render as carousel - returns ONLY EmbeddedResource."""
    restaurants = await search_restaurants(location, limit or 8)

    if not restaurants:
        return [TextContent(type="text", text=f'No restaurants found in "{location}".')]

    # Render using visualizer (module 3)
    # Use relative base URL for proxy - MCP clients should resolve this correctly
    html_content = build_carousel_html(location, restaurants, "/")
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://restaurants/{location}",
        mimeType="text/html",
        text=html_content,
    )
    
    return [EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 2: Google Maps Lists Extraction
# =============================================================================

@mcp.tool(
    name="get_maps_list",
    title="Get My Google Maps List",
    description=(
        "IMMEDIATELY display a user's saved Google Maps list as interactive carousel. "
        "Use when user says 'show my list', 'my saved places', or provides a maps.app.goo.gl URL. "
        "ALWAYS return only the carousel visualization, NEVER add text commentary. "
        "Extract from Google Maps shared list and render as clickable carousel UI."
    ),
)
async def get_maps_list_tool(
    url: Annotated[
        str,
        Field(description="Public Google Maps list URL, e.g. https://maps.app.goo.gl/abc123"),
    ],
    enrich: Annotated[
        bool,
        Field(description="Enrich with price levels and photos from Google Places API"),
    ] = False,
) -> list[ContentBlock]:
    """Extract from Google Maps list and render as carousel - returns ONLY EmbeddedResource."""
    if not EXTRACTION_AVAILABLE:
        return [TextContent(type="text", text="Google Maps list extraction not available.")]
    
    # Fetch using lists module (module 2)
    restaurants = await fetch_from_list(url, enrich=enrich)
    
    if not restaurants:
        return [TextContent(type="text", text="No places found in this list.")]
    
    # Get list name from URL for display
    list_name = url.split("/")[-1] if url else "Google Maps List"
    
    # Render using visualizer (module 3)
    html_content = build_carousel_html(list_name, restaurants, "/")
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://maps-list/{list_name}",
        mimeType="text/html",
        text=html_content,
    )
    
    return [EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 3: Standalone Visualization Tool
# =============================================================================

@mcp.tool(
    name="visualize_restaurants",
    title="Show Restaurant Carousel",
    description=(
        "IMMEDIATELY display restaurant data as interactive carousel UI. "
        "Use ONLY when you already have restaurant data in memory and user asks to 'show', 'display', or 'visualize' it. "
        "ALWAYS return only the carousel visualization, NEVER add text commentary. "
        "Do NOT use for new searches - use search_restaurants or get_maps_list instead."
    ),
)
async def visualize_restaurants_tool(
    title: Annotated[
        str,
        Field(description="Title/location to display in the carousel header"),
    ],
    restaurants: Annotated[
        list[dict[str, Any]],
        Field(description="List of restaurant objects with: name, address, rating, userRatingsTotal, priceLevel, openNow, photoUrl, placeId, websiteUrl"),
    ],
) -> list[ContentBlock]:
    """Render restaurant data as carousel - returns ONLY EmbeddedResource, no text."""
    if not restaurants:
        return [TextContent(type="text", text="No restaurants provided to visualize.")]
    
    # Render using visualizer (module 3)
    html_content = build_carousel_html(title, restaurants, "/")
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://visualize/{title}",
        mimeType="text/html",
        text=html_content,
    )
    
    return [EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 4: Booking Tool
# =============================================================================

@mcp.tool(
    name="book_restaurant",
    title="Open Booking Link",
    description=(
        "When user wants to book a specific restaurant, provide a direct booking URL. "
        "Use when user says 'book', 'reserve', 'make reservation' for a restaurant. "
        "ALWAYS return only the booking link as text, no extra commentary."
    ),
)
async def book_restaurant_tool(
    place_id: Annotated[
        str | None,
        Field(description="Google Places ID for the restaurant (optional, opens Google Maps)"),
    ] = None,
    website_url: Annotated[
        str | None,
        Field(description="Direct website URL for booking (optional)"),
    ] = None,
    restaurant_name: Annotated[
        str | None,
        Field(description="Restaurant name for fallback search"),
    ] = None,
    address: Annotated[
        str | None,
        Field(description="Restaurant address for fallback search"),
    ] = None,
) -> list[ContentBlock]:
    """Generate a booking link - returns ONLY the URL as TextContent."""
    # Priority: website_url > place_id > name+address search
    if website_url:
        booking_url = website_url
    elif place_id:
        from urllib.parse import quote
        booking_url = f"https://www.google.com/maps/place/?q=place_id:{quote(str(place_id), safe='')}"
    else:
        from urllib.parse import urlencode
        query_parts = []
        if restaurant_name:
            query_parts.append(restaurant_name)
        if address:
            query_parts.append(address)
        query = " ".join(query_parts) if query_parts else "restaurant"
        booking_url = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})
    
    return [TextContent(type="text", text=booking_url)]


# =============================================================================
# HEALTH & ROUTES
# =============================================================================

@mcp.custom_route("/", methods=["GET"])
async def root(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("resto-mcp is running. POST /mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "extraction_available": EXTRACTION_AVAILABLE})


@mcp.custom_route("/proxy-image", methods=["GET"])
async def proxy_image(request: Request) -> Response:
    """Proxy for Google Places/Google Maps photos to avoid CORS issues in Mistral Vibe."""
    url = request.query_params.get("url")
    if not url:
        return Response(status_code=400, content="Invalid URL: missing url parameter")
    
    # Allow Google Places API and Google Maps/Google User Content domains
    allowed_domains = ["places.googleapis.com", "googleusercontent.com", "maps.googleapis.com"]
    if not any(domain in url for domain in allowed_domains):
        return Response(status_code=400, content=f"Invalid URL: domain not allowed. URL must be from Google services. Got: {url}")
    
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
    except Exception as e:
        return Response(status_code=500, content=f"Error fetching image: {str(e)}")


class RejectMcpGet:
    """Answer GET /mcp with 405 instead of opening an SSE stream."""

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
    port = int(os.environ.get("MCP_HTTP_PORT") or os.environ.get("PORT") or 3000)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
