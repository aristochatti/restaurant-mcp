#!/usr/bin/env python3
"""
Google Maps List MCP Server
Exposes a tool to extract place details, coordinates, user notes, prices, and photos from a public Google Maps list URL.
Supports stdio (standard input/output) and sse (Server-Sent Events) transports with CORS enabled.
"""

import os
import sys
import json

# Add the directory containing this script to sys.path to ensure extract_list can be imported
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

try:
    from extract_list import resolve_list_id, fetch_list_data, parse_places
except ImportError as e:
    print(f"Error: Failed to import extract_list module: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print(f"Error: Failed to import FastMCP from mcp.server.fastmcp: {e}", file=sys.stderr)
    sys.exit(1)

# Initialize the FastMCP server with defaults
mcp = FastMCP("google-maps-list")

# Disable DNS Rebinding protection to allow public tunnels (like Pinggy/ngrok) to connect
mcp.settings.transport_security.enable_dns_rebinding_protection = False

# Monkey-patch the sse_app method to dynamically inject CORS middleware.
# This enables browser-based clients (e.g. Mistral Vibe Web, MCP Inspector) to connect to localhost.
original_sse_app = mcp.sse_app

def sse_app_with_cors(mount_path: str | None = None):
    app = original_sse_app(mount_path)
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # Required when allow_origins is ["*"]
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )
    return app

mcp.sse_app = sse_app_with_cors

@mcp.tool()
def get_maps_list(url: str, enrich: bool = False, limit: int = 500) -> str:
    """
    Extracts places (names, addresses, coordinates, custom user notes, price levels, and images)
    from a public Google Maps shared list link (maps.app.goo.gl or google.com/maps/playlist).

    Args:
        url: The public/shared Google Maps list link (e.g. https://maps.app.goo.gl/PyTE2vs6cQ7mvVLx5).
        enrich: If True, pulls additional price ranges, price levels, and photos from Google Places API. Default is False.
        limit: Maximum number of places to retrieve. Default is 500.
    """
    # Verify environment key if enrichment is requested
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if enrich and not api_key:
        return "Error: Enrichment requested (--enrich=true) but GOOGLE_PLACES_API_KEY environment variable is not set."

    # Resolve URL to List ID
    try:
        list_id = resolve_list_id(url)
        if not list_id:
            return "Error: Could not resolve a Google Maps list ID from the provided URL."
    except Exception as e:
        return f"Error resolving list ID: {e}"

    # Fetch list data
    try:
        raw_data = fetch_list_data(list_id, limit=limit)
        if not raw_data:
            return "Error: Failed to fetch list content from Google Maps."
    except Exception as e:
        return f"Error fetching list data: {e}"

    # Parse places (optionally using the Places API key if enrich is True)
    try:
        api_key_to_use = api_key if enrich else None
        parsed_data = parse_places(raw_data, api_key=api_key_to_use)
        if not parsed_data:
            return "Error: Failed to parse place details."
            
        # Return pretty JSON string
        return json.dumps(parsed_data, indent=2)
    except Exception as e:
        return f"Error parsing place details: {e}"

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Start Google Maps List MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio", help="Transport mode (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address for network transports (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port for network transports (default: 8000)")
    
    args = parser.parse_known_args()[0]
    
    if args.transport in ["sse", "streamable-http"]:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        endpoint_path = "/sse" if args.transport == "sse" else "/mcp"
        print(f"Starting Google Maps List MCP Server using '{args.transport}' transport at:", file=sys.stderr)
        print(f"--> http://{args.host}:{args.port}{endpoint_path}", file=sys.stderr)
        print("Press Ctrl+C to terminate.", file=sys.stderr)
        mcp.run(transport=args.transport)
    else:
        # Run using default stdio transport
        mcp.run(transport="stdio")
