#!/usr/bin/env python3
"""
Google Maps List Extractor
Extracts place names, addresses, coordinates, and custom user notes from a public Google Maps list link.
Supports sorting by distance to the user's location and restricting to the top N closest matches.
"""

import argparse
import json
import os
import sys

# Ensure src directory is in sys.path so we can import extract_list
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from extract_list import resolve_list_id, fetch_list_data, parse_places


def format_markdown(list_data):
    """
    Formats the list data into a readable Markdown table, dynamically adding a distance column if available.
    """
    output = []
    output.append(f"# {list_data['title']}")
    if list_data['description']:
        output.append(f"*{list_data['description']}*\n")
    output.append(f"**Owner:** {list_data['owner']}")
    output.append(f"**Total Places:** {list_data['total_items']}\n")
    
    # Check if any place has distance
    has_distance = any(place.get("distance_km") is not None for place in list_data["places"])
    
    if has_distance:
        output.append("| # | Name | Address | Distance | Price | Note | Images |")
        output.append("|---|------|---------|----------|-------|------|--------|")
    else:
        output.append("| # | Name | Address | Price | Note | Images |")
        output.append("|---|------|---------|-------|------|--------|")
    
    for i, place in enumerate(list_data["places"]):
        price = place['price_level'] or "N/A"
        note = place['note'].replace("\n", " ") if place['note'] else ""
        
        images_str = "N/A"
        if place['photos']:
            img_links = [f"[Image {idx+1}]({url})" for idx, url in enumerate(place['photos'])]
            images_str = ", ".join(img_links)
            
        if has_distance:
            dist = f"{place.get('distance_km')} km" if place.get("distance_km") is not None else "N/A"
            output.append(f"| {i+1} | **{place['name']}** | {place['address'] or 'N/A'} | {dist} | {price} | {note} | {images_str} |")
        else:
            output.append(f"| {i+1} | **{place['name']}** | {place['address'] or 'N/A'} | {price} | {note} | {images_str} |")
        
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Extract places from a public Google Maps shared list.")
    parser.add_argument("url", help="Public Google Maps list short link (maps.app.goo.gl) or direct link.")
    parser.add_argument("-f", "--format", choices=["json", "markdown"], default="json", help="Output format (default: json).")
    parser.add_argument("-o", "--output", help="Save output directly to a file (optional).")
    parser.add_argument("-l", "--limit", type=int, default=500, help="Maximum number of raw list items to retrieve (default: 500).")
    parser.add_argument("-k", "--api-key", help="Google Places API key for geocoding and enriching details. Can also be set via GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY.")
    parser.add_argument("-e", "--enrich", action="store_true", default=False, help="Pull additional details (price levels, ranges, photos) from Google Places API (default: False).")
    parser.add_argument("-u", "--user-location", help="User coordinates ('lat,lon') or location/address string to sort results by increasing distance.")
    parser.add_argument("-n", "--top-n", type=int, help="Filter and return only the top N closest results. If -enrich is set, only these N will be enriched.")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or os.environ.get("GOOGLE_MAPS_API_KEY")
    
    # Check if enrich is requested but key is missing
    if args.enrich and not api_key:
        print("Error: --enrich requested but no Google Places API key found.", file=sys.stderr)
        print("Please provide it via --api-key / -k flag or GOOGLE_PLACES_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)
        
    # Check if geocoding coordinates is needed for textual location but key is missing
    if args.user_location and not api_key:
        # Check if user_location is not raw coordinates
        import re
        if not re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$', args.user_location):
            print("Warning: Address geocoding requested for --user-location but no Google Places API key found.", file=sys.stderr)
            print("Location sorting will only work if coordinates are passed as 'lat,lon' or if an API key is provided.", file=sys.stderr)
        
    print(f"Resolving list ID from URL...", file=sys.stderr)
    list_id = resolve_list_id(args.url)
    if not list_id:
        print("Error: Could not resolve a Google Maps list ID from the provided URL.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Found List ID: {list_id}", file=sys.stderr)
    print(f"Fetching place data...", file=sys.stderr)
    raw_data = fetch_list_data(list_id, limit=args.limit)
    if not raw_data:
        print("Error: Failed to fetch list content.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Parsing places...", file=sys.stderr)
    # api_key_to_use: only passed for enrichment (price/photos)
    # geo_api_key: always passed so named --user-location strings can be geocoded
    api_key_to_use = api_key if args.enrich else None
    parsed_data = parse_places(
        raw_data,
        api_key=api_key_to_use,
        geo_api_key=api_key,
        user_location=args.user_location,
        top_n=args.top_n
    )
    if not parsed_data:
        print("Error: Failed to parse places from list.", file=sys.stderr)
        sys.exit(1)
        
    # Format output
    if args.format == "markdown":
        output_str = format_markdown(parsed_data)
    else:
        output_str = json.dumps(parsed_data, indent=2)
        
    # Output to stdout or write to file
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"Successfully saved output to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error: Failed to write to file {args.output}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
