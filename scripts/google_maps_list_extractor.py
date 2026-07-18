#!/usr/bin/env python3
"""
Google Maps List Extractor
Extracts place names, addresses, coordinates, and custom user notes from a public Google Maps list link.
Optionally enriches place details (price levels, ranges, photos) using the new Google Places API.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse


def resolve_list_id(short_url):
    """
    Resolves the maps.app.goo.gl shortlink and extracts the list ID.
    """
    req = urllib.request.Request(
        short_url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            final_url = response.geturl()
    except Exception as e:
        print(f"Error: Failed to resolve the URL redirect: {e}", file=sys.stderr)
        return None

    # Try extracting list ID from the final URL
    match = re.search(r'placelists/list/([a-zA-Z0-9_-]+)', final_url)
    if match:
        return match.group(1)

    match = re.search(r'[!&]2s([a-zA-Z0-9_-]{20,})', final_url)
    if match:
        return match.group(1)

    match = re.search(r'2s([a-zA-Z0-9_-]{20,})', short_url)
    if match:
        return match.group(1)

    return None


def fetch_list_data(list_id, limit=500):
    """
    Fetches the raw list data from Google's internal entitylist API.
    """
    pb_param = f"!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i{limit}"
    
    params = urllib.parse.urlencode({
        "authuser": "0",
        "hl": "en",
        "pb": pb_param
    })
    
    url = f"https://www.google.com/maps/preview/entitylist/getlist?{params}"
    
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error: Failed to fetch data from API: {e}", file=sys.stderr)
        return None

    if raw_response.startswith(")]}'"):
        json_str = raw_response[4:].strip()
    else:
        json_str = raw_response.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON API response: {e}", file=sys.stderr)
        return None


def enrich_place_details(name, address, api_key):
    """
    Uses the Google Places API (New) to search for the place and extract price level, price range, and photos.
    """
    if not api_key:
        return None, []

    # Clean query containing place name and address
    query = f"{name}, {address}" if address else name
    
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.priceLevel,places.priceRange,places.photos"
    }
    
    data = {
        "textQuery": query
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        if "places" in res_data and res_data["places"]:
            place = res_data["places"][0]
            
            # 1. Map price level string to symbols
            price_level_str = place.get("priceLevel")
            price_map = {
                "PRICE_LEVEL_INEXPENSIVE": "$",
                "PRICE_LEVEL_MODERATE": "$$",
                "PRICE_LEVEL_EXPENSIVE": "$$$",
                "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
                "PRICE_LEVEL_FREE": "Free"
            }
            price_level = price_map.get(price_level_str)
            if not price_level and price_level_str:
                price_level = price_level_str.replace("PRICE_LEVEL_", "").title()
            
            # 2. Extract price range if available
            price_range = place.get("priceRange")
            range_str = None
            if price_range:
                start = price_range.get("startPrice", {})
                end = price_range.get("endPrice", {})
                start_units = start.get("units")
                end_units = end.get("units")
                currency = start.get("currencyCode") or end.get("currencyCode") or ""
                
                if start_units and end_units:
                    range_str = f"{start_units}-{end_units} {currency}".strip()
                elif start_units:
                    range_str = f"> {start_units} {currency}".strip()
                elif end_units:
                    range_str = f"< {end_units} {currency}".strip()
            
            # Combine price level and range
            final_price = None
            if price_level and range_str:
                final_price = f"{price_level} ({range_str})"
            elif price_level:
                final_price = price_level
            elif range_str:
                final_price = range_str
            
            # 3. Extract up to 2 photo URLs (using new Places API media endpoint format)
            photo_urls = []
            if "photos" in place:
                for photo in place["photos"][:2]:
                    photo_name = photo.get("name")
                    if photo_name:
                        photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=800&maxWidthPx=800&key={api_key}"
                        photo_urls.append(photo_url)
                        
            return final_price, photo_urls
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'read'):
            try:
                err_details = json.loads(e.read().decode('utf-8'))
                err_msg = err_details.get("error", {}).get("message", err_msg)
            except Exception:
                pass
        print(f"Warning: Failed to enrich place '{name}' via Places API: {err_msg}", file=sys.stderr)
        
    return None, []


def parse_places(api_response, api_key=None):
    """
    Parses the JSON response into a clean list of place objects.
    """
    if not api_response or not isinstance(api_response, list) or len(api_response) == 0:
        return None
        
    main_data = api_response[0]
    
    list_metadata = {
        "list_id": main_data[0][0] if len(main_data) > 0 and len(main_data[0]) > 0 else None,
        "title": main_data[4] if len(main_data) > 4 else "Unnamed List",
        "description": main_data[5] if len(main_data) > 5 else "",
        "owner": main_data[3][0] if len(main_data) > 3 and main_data[3] else "Unknown Owner",
        "total_items": 0,
        "places": []
    }
    
    if len(main_data) > 8 and main_data[8]:
        places_list = main_data[8]
        list_metadata["total_items"] = len(places_list)
        
        for idx, item in enumerate(places_list):
            name = item[2] if len(item) > 2 else "Unknown Name"
            note = item[3] if len(item) > 3 and item[3] else ""
            
            address = None
            latitude = None
            longitude = None
            kg_id = None
            place_ids = []
            
            if len(item) > 1 and item[1]:
                details = item[1]
                address = details[4] if len(details) > 4 else None
                kg_id = details[7] if len(details) > 7 else None
                
                if len(details) > 5 and details[5]:
                    coords = details[5]
                    latitude = coords[2] if len(coords) > 2 else None
                    longitude = coords[3] if len(coords) > 3 else None
                
                if len(details) > 6 and details[6]:
                    place_ids = details[6]
            
            # Enrich details if API key is provided
            price_level = None
            photos = []
            if api_key:
                print(f"Enriching place [{idx+1}/{len(places_list)}]: {name}...", file=sys.stderr)
                price_level, photos = enrich_place_details(name, address, api_key)
                
            place_obj = {
                "name": name,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "note": note,
                "price_level": price_level,
                "photos": photos,
                "google_place_ids": place_ids,
                "kg_id": kg_id
            }
            list_metadata["places"].append(place_obj)
            
    return list_metadata


def format_markdown(list_data):
    """
    Formats the list data into a readable Markdown table.
    """
    output = []
    output.append(f"# {list_data['title']}")
    if list_data['description']:
        output.append(f"*{list_data['description']}*\n")
    output.append(f"**Owner:** {list_data['owner']}")
    output.append(f"**Total Places:** {list_data['total_items']}\n")
    
    output.append("| # | Name | Address | Price | Note | Images |")
    output.append("|---|------|---------|-------|------|--------|")
    
    for i, place in enumerate(list_data["places"]):
        price = place['price_level'] or "N/A"
        note = place['note'].replace("\n", " ") if place['note'] else ""
        
        images_str = "N/A"
        if place['photos']:
            img_links = [f"[Image {idx+1}]({url})" for idx, url in enumerate(place['photos'])]
            images_str = ", ".join(img_links)
            
        output.append(f"| {i+1} | **{place['name']}** | {place['address'] or 'N/A'} | {price} | {note} | {images_str} |")
        
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Extract places from a public Google Maps shared list.")
    parser.add_argument("url", help="Public Google Maps list short link (maps.app.goo.gl) or direct link.")
    parser.add_argument("-f", "--format", choices=["json", "markdown"], default="json", help="Output format (default: json).")
    parser.add_argument("-o", "--output", help="Save output directly to a file (optional).")
    parser.add_argument("-l", "--limit", type=int, default=500, help="Maximum number of places to retrieve (default: 500).")
    parser.add_argument("-k", "--api-key", help="Google Places API key for enriching details. Can also be set via GOOGLE_PLACES_API_KEY env variable.")
    parser.add_argument("-e", "--enrich", action="store_true", default=False, help="Pull additional details (price levels, ranges, photos) from Google Places API (default: False).")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get("GOOGLE_PLACES_API_KEY")
    
    # Check if enrich is requested but key is missing
    if args.enrich and not api_key:
        print("Error: --enrich requested but no Google Places API key found.", file=sys.stderr)
        print("Please provide it via --api-key / -k flag or GOOGLE_PLACES_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)
        
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
    # Only supply api_key to parse_places if enrichment flag is True
    api_key_to_use = api_key if args.enrich else None
    parsed_data = parse_places(raw_data, api_key=api_key_to_use)
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
