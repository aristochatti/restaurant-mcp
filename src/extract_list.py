"""
Core logic for extracting places from Google Maps lists.
This module provides functions to resolve list IDs, fetch list data, and parse places.
"""

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
