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

import asyncio
import os
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ContentBlock, EmbeddedResource, TextContent, TextResourceContents, Icon
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, FileResponse
from phone_booking import initiate_booking_call
from pathlib import Path

# =============================================================================
# THREE COMPONENTS
# =============================================================================

# 1. VISUALIZER: Carousel HTML rendering
from carousel import build_carousel_html

# 2. GOOGLE FETCHING: General Places API search
from places import search_restaurants

# 3. GOOGLE MAPS LISTS: Your saved lists extraction
from lists import fetch_from_list, EXTRACTION_AVAILABLE
from google_calendar import create_calendar_event


# =============================================================================
# MCP SERVER SETUP
# =============================================================================

def _transport_security() -> TransportSecuritySettings:
    """FastMCP defaults allowed_hosts to localhost only, with DNS-rebinding
    protection on. Behind Alpic the Host header is the public domain, so that
    default would 421 every request once deployed behind Alpic's public domain.
    Rebinding protection exists to stop a malicious page from reaching a server
    bound to the user's loopback  not a threat model a public MCP endpoint sits in  so it's off unless you pin
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
    icons=[
        Icon(
            src="/logo.png",
            mimeType="image/png"
        )
    ]
)


# =============================================================================
# TOOL 1: General Google Places Search
# =============================================================================

@mcp.tool(
    name="search_restaurants",
    title="Search Restaurants",
    description=(
        "MANDATORY: When user asks for restaurants, places to eat, food recommendations, "
        "or anything about finding restaurants - YOU MUST call this tool first. "
        "DO NOT generate any text response. DO NOT say 'Here are restaurants...'. "
        "Call this tool with the location and return ONLY the tool result (interactive carousel). "
        "Trigger phrases: 'restaurant', 'where to eat', 'find me food', 'best places to eat', 'show restaurants'"
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

    # Use relative base URL for proxy - MCP clients should resolve this correctly
    html_content = build_carousel_html(location, restaurants)
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://restaurants/{location}",
        mimeType="text/html",
        text=html_content,
    )
    
    # Return a text instruction followed by the UI resource.
    # This ensures Mistral Vibe understands it should render the HTML in a canvas.
    instruction = TextContent(
        type="text",
        text="Please render the following HTML in a canvas:"
    )
    return [instruction, EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 2: Google Maps Lists Extraction
# =============================================================================

@mcp.tool(
    name="get_maps_list",
    title="Get My Google Maps List",
    description=(
        "MANDATORY: When user provides a Google Maps list URL (maps.app.goo.gl or google.com/maps) "
        "or asks about 'my list', 'saved places', 'my maps' - YOU MUST call this tool. "
        "Supports 'user_location' (coordinates 'lat,lon' or address) to sort results by distance and 'top_n' (integer) to limit results count. "
        "DO NOT generate any text response. DO NOT say 'Here is your list...'. "
        "Call this tool with the URL and return ONLY the tool result (interactive carousel). "
        "Trigger: any Google Maps URL or phrase containing 'my list', 'saved places', 'google maps list'"
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
    user_location: Annotated[
        str | None,
        Field(description="User location coordinates (e.g. '48.8566,2.3522') or address (e.g. 'Paris, France') to sort results by distance"),
    ] = None,
    top_n: Annotated[
        int | None,
        Field(description="If specified, filters and returns only the top N closest places"),
    ] = None,
) -> list[ContentBlock]:
    """Extract from Google Maps list and render as carousel - returns ONLY EmbeddedResource."""
    if not EXTRACTION_AVAILABLE:
        return [TextContent(type="text", text="Google Maps list extraction not available.")]
    
    # Fetch using lists module (module 2)
    restaurants = await fetch_from_list(
        url,
        enrich=enrich,
        user_location=user_location,
        top_n=top_n
    )
    
    if not restaurants:
        return [TextContent(type="text", text="No places found in this list.")]
    
    # Get list name from URL for display
    list_name = url.split("/")[-1] if url else "Google Maps List"
    
    # Render using visualizer (module 3)
    html_content = build_carousel_html(list_name, restaurants)
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://maps-list/{list_name}",
        mimeType="text/html",
        text=html_content,
    )
    
    # Return a text instruction followed by the UI resource.
    # This ensures Mistral Vibe understands it should render the HTML in a canvas.
    instruction = TextContent(
        type="text",
        text="Please render the following HTML in a canvas:"
    )
    return [instruction, EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 3: Standalone Visualization Tool
# =============================================================================

@mcp.tool(
    name="visualize_restaurants",
    title="Show Restaurant Carousel",
    description=(
        "MANDATORY: When user says 'visualize', 'show', 'display' with restaurant data context - "
        "YOU MUST call this tool. Use ONLY when you already have restaurant data. "
        "DO NOT generate any text response. DO NOT say 'Here are the restaurants...' or 'visualized for you'. "
        "Call this tool with the data and return ONLY the tool result (interactive carousel). "
        "Trigger: 'visualize', 'show me', 'display' when restaurants are being discussed. "
        "NEVER use for new searches - use search_restaurants or get_maps_list for those."
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
    html_content = build_carousel_html(title, restaurants)
    
    # Create proper EmbeddedResource with TextResourceContents
    resource_content = TextResourceContents(
        uri=f"ui://visualize/{title}",
        mimeType="text/html",
        text=html_content,
    )
    
    # Return a text instruction followed by the UI resource.
    # This ensures Mistral Vibe understands it should render the HTML in a canvas.
    instruction = TextContent(
        type="text",
        text="Please render the following HTML in a canvas:"
    )
    return [instruction, EmbeddedResource(type="resource", resource=resource_content)]


# =============================================================================
# TOOL 4: Booking Tool
# =============================================================================

@mcp.tool(
    name="book_restaurant",
    title="Open Booking Link",
    description=(
        "MANDATORY: When user says 'book', 'reserve', 'make a reservation', 'I want to book' "
        "for a specific restaurant - YOU MUST call this tool. "
        "DO NOT generate any text response except the URL itself. "
        "DO NOT say 'Here is the booking link...' or add any commentary. "
        "Call this tool and return ONLY the URL as plain text."
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


@mcp.tool(
    name="add_reservation_to_calendar",
    title="Add restaurant reservation to Google Calendar",
    description=(
        "Add a confirmed restaurant reservation directly to Google Calendar. "
        "Use after the user has confirmed the restaurant, date, time, party size, and timezone."
    ),
)
async def add_reservation_to_calendar_tool(
    restaurant_name: Annotated[str, Field(description="Name of the restaurant")],
    address: Annotated[str, Field(description="Full restaurant address")],
    reservation_date: Annotated[str, Field(description="Reservation date in YYYY-MM-DD format")],
    reservation_time: Annotated[str, Field(description="Reservation time in HH:MM 24-hour format")],
    party_size: Annotated[int, Field(description="Number of people", ge=1)],
    timezone_name: Annotated[
        str,
        Field(description="IANA timezone, such as Europe/Rome or America/New_York"),
    ] = "Europe/Rome",
) -> list[ContentBlock]:
    try:
        local_datetime = datetime.strptime(
            f"{reservation_date} {reservation_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo(timezone_name))
    except (ValueError, KeyError):
        return [TextContent(type="text", text="Invalid reservation date, time, or timezone.")]

    try:
        event = await asyncio.to_thread(
            create_calendar_event,
            restaurant_name=restaurant_name,
            address=address,
            reservation_at=local_datetime,
            party_size=party_size,
        )
    except Exception as error:
        return [
            TextContent(
                type="text",
                text=f"Could not add the reservation to Google Calendar: {error}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=(
                f"Added your reservation at {restaurant_name} to Google Calendar.\n"
                f"{event.get('htmlLink', '')}"
            ),
        )
    ]


# =============================================================================
# TOOL 5: AI Phone Call Booking Tool
# =============================================================================

@mcp.tool(
    name="call_restaurant_for_booking",
    title="Call Restaurant for Booking",
    description=(
        "Places an AI-powered outbound phone call to a restaurant using ElevenLabs "
        "Conversational AI to make a reservation on behalf of the user. "
        "The AI agent speaks to the restaurant staff and books a table autonomously. "
        "Requires ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, and ELEVENLABS_PHONE_NUMBER_ID "
        "environment variables to be configured."
    ),
)
def call_restaurant_for_booking(
    restaurant_name: Annotated[
        str,
        Field(description="Name of the restaurant to call"),
    ],
    phone_number: Annotated[
        str,
        Field(description="Restaurant phone number in E.164 format (e.g. +33123456789) or local format"),
    ],
    guest_name: Annotated[
        str,
        Field(description="Full name of the guest for the reservation"),
    ],
    date: Annotated[
        str,
        Field(description="Reservation date (e.g. '2026-07-20', 'today', 'tomorrow')"),
    ],
    time_start: Annotated[
        str,
        Field(description="Preferred reservation time (e.g. '19:30')"),
    ],
    pax: Annotated[
        int,
        Field(description="Number of guests (party size)", ge=1, le=50),
    ],
    time_end: Annotated[
        str | None,
        Field(description="Latest acceptable time if preferred slot is unavailable (e.g. '21:00'). Defaults to 1.5h after time_start."),
    ] = None,
    special_requests: Annotated[
        str | None,
        Field(description="Any dietary requirements or special requests (e.g. 'window table', 'gluten-free menu')"),
    ] = None,
) -> str:
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
    if agent_id:
        from phone_booking import check_active_call, wait_for_conversation_summary
        active_conv_id = check_active_call(agent_id)
        if active_conv_id:
            import json
            import time
            return json.dumps({
                "success": True,
                "status": "in_progress",
                "conversation_id": active_conv_id,
                "called_at": time.time() - 30,
                "message": "⚠️ A booking call is already active and in progress. Call check_booking_status using this conversation_id to check the outcome."
            }, indent=2)

    # Default time_end to 1.5 hours after time_start if not provided
    if not time_end:
        try:
            from datetime import datetime, timedelta
            t = datetime.strptime(time_start, "%H:%M")
            time_end = (t + timedelta(hours=1, minutes=30)).strftime("%H:%M")
        except ValueError:
            time_end = time_start

    import time
    called_at = time.time()

    result = initiate_booking_call(
        restaurant_name=restaurant_name,
        phone_number=phone_number,
        guest_name=guest_name,
        date=date,
        time_start=time_start,
        time_end=time_end,
        pax=pax,
        special_requests=special_requests or "",
    )

    if result.get("success"):
        agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
        if agent_id:
            # Sleep 3 seconds to let ElevenLabs register the conversation
            time.sleep(3)
            conversation_id = None
            try:
                from phone_booking import _CONVERSATIONS_URL
                import httpx
                with httpx.Client(timeout=5) as client:
                    resp = client.get(
                        _CONVERSATIONS_URL,
                        headers={"xi-api-key": os.environ.get("ELEVENLABS_API_KEY")},
                        params={"agent_id": agent_id, "page_size": 5},
                    )
                if resp.status_code == 200:
                    conversations = resp.json().get("conversations", [])
                    for conv in conversations:
                        start_time = conv.get("start_time_unix_secs", 0)
                        if start_time >= called_at - 15:
                            conversation_id = conv.get("conversation_id")
                            break
            except Exception:
                pass

            import json
            return json.dumps({
                "success": True,
                "status": "initiated",
                "conversation_id": conversation_id,
                "called_at": called_at,
                "message": "📞 Phone call successfully initiated on the ElevenLabs network! You MUST now actively call the check_booking_status tool using this conversation_id and called_at timestamp every 10-15 seconds until it completes."
            }, indent=2)

    import json
    return json.dumps(result, indent=2)


@mcp.tool(
    name="check_booking_status",
    title="Check Booking Call Status",
    description=(
        "MANDATORY: Call this tool every 10-15 seconds after initiating a booking call "
        "to check its progress and get the final transcript/summary. "
        "Pass the conversation_id and called_at timestamp returned by call_restaurant_for_booking."
    ),
)
async def check_booking_status_tool(
    conversation_id: Annotated[
        str | None,
        Field(description="The conversation ID returned by call_restaurant_for_booking (optional)"),
    ] = None,
    called_at: Annotated[
        float | None,
        Field(description="The epoch timestamp when the call was initiated (optional)"),
    ] = None,
) -> str:
    """Check status of an active booking call."""
    import json
    import time
    from phone_booking import get_conversation_summary, _CONVERSATIONS_URL
    import httpx
    import os

    agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
    api_key = os.environ.get("ELEVENLABS_API_KEY")

    if not agent_id or not api_key:
        return json.dumps({"status": "error", "message": "Missing ElevenLabs credentials"}, indent=2)

    # 1. If we don't have conversation_id, try to find it using called_at
    if not conversation_id and called_at:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    _CONVERSATIONS_URL,
                    headers={"xi-api-key": api_key},
                    params={"agent_id": agent_id, "page_size": 10},
                )
            if resp.status_code == 200:
                conversations = resp.json().get("conversations", [])
                for conv in conversations:
                    start_time = conv.get("start_time_unix_secs", 0)
                    if start_time >= called_at - 15:  # 15s tolerance
                        conversation_id = conv.get("conversation_id")
                        break
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error looking up conversation: {str(e)}"}, indent=2)

    if not conversation_id:
        return json.dumps({
            "status": "initializing",
            "message": "Call is still initializing on the network. Please wait 10 seconds and try again."
        }, indent=2)

    # 2. Fetch the conversation status
    try:
        summary_result = get_conversation_summary(conversation_id, api_key=api_key)
        status = summary_result.get("status", "")
        if status not in ("done", "failed"):
            return json.dumps({
                "status": "in_progress",
                "conversation_id": conversation_id,
                "message": f"Call is currently {status}. The AI is talking to the restaurant. Please wait 10-15 seconds and check status again."
            }, indent=2)

        # Call is done! Return the final summary
        return json.dumps({
            "status": "completed",
            "conversation_id": conversation_id,
            "post_call_analysis": summary_result
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Error fetching conversation summary: {str(e)}"}, indent=2)


# =============================================================================
# HEALTH & ROUTES
# =============================================================================

@mcp.custom_route("/logo.png", methods=["GET"])
async def get_logo(_request: Request) -> FileResponse:
    logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    return FileResponse(logo_path, media_type="image/png")


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
    port = int(os.environ.get("MCP_HTTP_PORT") or os.environ.get("PORT") or 3000)
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
