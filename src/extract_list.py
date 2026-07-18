"""
Core logic for extracting places from Google Maps lists.
This module provides functions to resolve list IDs, fetch list data, and parse places.
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.parse


# ---------------------------------------------------------------------------
# Adaptive fetch configuration
# ---------------------------------------------------------------------------
# Batch sizes tried in order when adaptive fetching is active (radius_km +
# top_n + user_location all provided).  Each step fetches incrementally more
# items from Google; the loop stops as soon as top_n results are found within
# the radius.  The final element should match _FETCH_LIMIT in lists.py.
_ADAPTIVE_BATCHES = [100, 300, 500]


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


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes the great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def resolve_coordinates(location_str: str, api_key: str | None = None) -> tuple[float, float] | None:
    """Resolves latitude/longitude from raw coordinate string or address name query."""
    location_str = location_str.strip()
    match = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$', location_str)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            pass
            
    if not api_key:
        # Cannot geocode a named address without a key. Raw "lat,lon" strings are
        # already handled above, so if we reach here it means the caller passed a
        # place name but no API key is configured.
        print(
            f"Warning: Cannot geocode '{location_str}' \u2014 no Google API key available. "
            "Provide raw 'lat,lon' coordinates or set GOOGLE_MAPS_API_KEY / GOOGLE_PLACES_API_KEY.",
            file=sys.stderr,
        )
        return None

    if api_key and location_str:
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.location"
        }
        data = {
            "textQuery": location_str,
            "maxResultCount": 1
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
                location = res_data["places"][0].get("location", {})
                lat = location.get("latitude")
                lon = location.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
        except Exception as e:
            print(f"Warning: Failed to resolve coordinates for location '{location_str}': {e}", file=sys.stderr)
            
    return None


def parse_places(
    api_response,
    api_key=None,
    geo_api_key=None,
    user_location=None,
    top_n=None,
    radius_km=None,
    fetch_limit=500,
):
    """
    Parses the JSON response into a clean list of place objects, sorting by
    distance and limiting results if specified.

    Args:
        api_response:  Raw JSON list from fetch_list_data().
        api_key:       Google Places API key used for *enrichment* (price/photos).
                       May be None when enrichment is not requested.
        geo_api_key:   Google API key used *only* for geocoding a named
                       user_location string (e.g. "Paris, France").  Raw
                       "lat,lon" strings work without any key.  Falls back
                       gracefully to None — sorting is simply skipped.
        user_location: User location string ("lat,lon" or address) for sorting.
        top_n:         If set, keep only the closest N places after sorting.
        radius_km:     If set, discard any place further than this distance
                       from user_location before sorting / slicing.  Requires
                       user_location to have an effect.
        fetch_limit:   The limit that was passed to fetch_list_data().  Used
                       to detect whether the list was truncated (i.e. the list
                       may have more items than what was fetched).
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
        # True when the API returned exactly fetch_limit items, meaning the list
        # likely has more entries that were not fetched.
        "is_truncated": False,
        "places": []
    }
    
    if len(main_data) > 8 and main_data[8]:
        places_list = main_data[8]
        list_metadata["total_items"] = len(places_list)
        # Detect truncation: if we got exactly as many items as we asked for,
        # the list almost certainly has more entries beyond what was fetched.
        list_metadata["is_truncated"] = len(places_list) >= fetch_limit
        
        # 1. Parse all items first (without Place API enrichment)
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
            
            place_obj = {
                "name": name,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "note": note,
                "price_level": None,
                "photos": [],
                "google_place_ids": place_ids,
                "kg_id": kg_id
            }
            list_metadata["places"].append(place_obj)
            
        # 2. Sort by distance / apply radius filter if user_location is provided
        if user_location:
            # Use geo_api_key for coordinate resolution; fall back to api_key
            # (enrichment key) if geo_api_key is not separately provided.
            # Raw "lat,lon" strings require no key at all.
            key_for_geocoding = geo_api_key or api_key
            user_coords = resolve_coordinates(user_location, key_for_geocoding)
            if user_coords:
                user_lat, user_lon = user_coords
                for place in list_metadata["places"]:
                    if place["latitude"] is not None and place["longitude"] is not None:
                        dist = haversine_distance(user_lat, user_lon, place["latitude"], place["longitude"])
                        place["distance_km"] = round(dist, 2)
                    else:
                        place["distance_km"] = None

                # 2a. Radius pre-filter: drop places beyond the requested radius.
                #     Places with no coordinates are also dropped here because we
                #     cannot confirm they are within the radius.
                if radius_km is not None:
                    list_metadata["places"] = [
                        p for p in list_metadata["places"]
                        if p["distance_km"] is not None and p["distance_km"] <= radius_km
                    ]
                    print(
                        f"Radius filter ({radius_km} km): {len(list_metadata['places'])} places remain.",
                        file=sys.stderr,
                    )

                # Sort: places with distance sorted increasing, places with None at the end
                list_metadata["places"].sort(key=lambda p: (p["distance_km"] is None, p["distance_km"] or 0))

        # 3. Restrict to top N matches if specified
        if top_n is not None:
            list_metadata["places"] = list_metadata["places"][:top_n]
            
        # 4. Enrich only the final filtered places
        if api_key:
            for idx, place in enumerate(list_metadata["places"]):
                name = place["name"]
                address = place["address"]
                print(f"Enriching place [{idx+1}/{len(list_metadata['places'])}]: {name}...", file=sys.stderr)
                price_level, photos = enrich_place_details(name, address, api_key)
                place["price_level"] = price_level
                place["photos"] = photos
                
    return list_metadata


# ---------------------------------------------------------------------------
# Adaptive fetch + parse
# ---------------------------------------------------------------------------

def adaptive_fetch_and_parse(
    list_id: str,
    api_key=None,
    geo_api_key=None,
    user_location=None,
    top_n=None,
    radius_km=None,
    max_fetch_limit=500,
):
    """
    Fetch list items in increasing batches, stopping as soon as *top_n* results
    are found within *radius_km* of *user_location*.

    Strategy
    --------
    1. Resolve user coordinates **once** (avoids repeated geocoding API calls).
    2. Loop through _ADAPTIVE_BATCHES (e.g. 100 → 300 → 500 items):
       a. Fetch that many items from Google.
       b. Compute haversine distances and apply the radius filter locally.
       c. If we have >= top_n results, or the list is exhausted, stop.
    3. Apply top_n slice on the final set.
    4. Run enrichment (price/photos) **only** on the final top_n places.

    Falls back to a single full fetch (no adaptive loop) when any of
    radius_km / top_n / user_location is absent.

    Args:
        list_id:         Google Maps list ID (from resolve_list_id).
        api_key:         Google Places API key for *enrichment* only (price/photos).
        geo_api_key:     Google API key for geocoding named user_location strings.
        user_location:   "lat,lon" string or human-readable address.
        top_n:           Target number of results to return.
        radius_km:       Only places within this distance are counted / returned.
        max_fetch_limit: Hard cap on total items fetched (default 500).

    Returns:
        Same dict format as parse_places(), or None on failure.
    """
    use_adaptive = (
        radius_km is not None
        and top_n is not None
        and user_location is not None
    )

    if not use_adaptive:
        # No optimisation possible — single full fetch.
        raw = fetch_list_data(list_id, limit=max_fetch_limit)
        if not raw:
            return None
        return parse_places(
            raw,
            api_key=api_key,
            geo_api_key=geo_api_key,
            user_location=user_location,
            top_n=top_n,
            radius_km=radius_km,
            fetch_limit=max_fetch_limit,
        )

    # ------------------------------------------------------------------
    # Resolve coordinates ONCE so subsequent parse_places calls receive a
    # raw "lat,lon" string and skip the geocoding HTTP round-trip.
    # ------------------------------------------------------------------
    key_for_geo = geo_api_key or api_key
    t_geo = time.perf_counter()
    user_coords = resolve_coordinates(user_location, key_for_geo)
    geo_ms = (time.perf_counter() - t_geo) * 1000

    if not user_coords:
        # Geocoding failed — fall back to single fetch with the original string.
        print(
            f"[adaptive] geocoding failed for '{user_location}' — falling back to full fetch.",
            file=sys.stderr,
        )
        raw = fetch_list_data(list_id, limit=max_fetch_limit)
        if not raw:
            return None
        return parse_places(
            raw,
            api_key=api_key,
            geo_api_key=geo_api_key,
            user_location=user_location,
            top_n=top_n,
            radius_km=radius_km,
            fetch_limit=max_fetch_limit,
        )

    # Use the resolved coordinates as a raw string for all inner parse_places
    # calls — this skips re-geocoding on every iteration.
    resolved_loc = f"{user_coords[0]},{user_coords[1]}"
    print(
        f"[adaptive] geocoded '{user_location}' → {resolved_loc} in {geo_ms:.0f} ms",
        file=sys.stderr,
    )

    # Build the list of batch sizes to try, capped at max_fetch_limit.
    batches = sorted(set(
        b for b in _ADAPTIVE_BATCHES if b <= max_fetch_limit
    ))
    if not batches or batches[-1] < max_fetch_limit:
        batches.append(max_fetch_limit)

    parsed = None
    total_fetch_ms = 0.0

    for batch_size in batches:
        t_fetch = time.perf_counter()
        raw = fetch_list_data(list_id, limit=batch_size)
        fetch_ms = (time.perf_counter() - t_fetch) * 1000
        total_fetch_ms += fetch_ms

        if not raw:
            print(f"[adaptive] batch={batch_size}: fetch failed.", file=sys.stderr)
            break

        # Parse WITHOUT enrichment (api_key=None); enrichment happens once
        # on the final set after the loop to avoid redundant API calls.
        parsed = parse_places(
            raw,
            api_key=None,          # skip enrichment in loop
            geo_api_key=None,      # coords already resolved
            user_location=resolved_loc,
            top_n=None,            # don't slice yet
            radius_km=radius_km,
            fetch_limit=batch_size,
        )

        if not parsed:
            break

        n_in_radius = len(parsed["places"])
        is_truncated = parsed.get("is_truncated", False)

        print(
            f"[adaptive] batch={batch_size:>4}: fetch={fetch_ms:>5.0f} ms | "
            f"{n_in_radius:>3} places within {radius_km} km | "
            f"list_truncated={is_truncated}",
            file=sys.stderr,
        )

        if n_in_radius >= top_n or not is_truncated:
            # Either we have enough results, or the list is fully exhausted.
            break

        print(
            f"[adaptive] {n_in_radius}/{top_n} found — expanding to next batch...",
            file=sys.stderr,
        )

    if not parsed:
        return None

    # Apply top_n on the final set.
    if top_n is not None:
        parsed["places"] = parsed["places"][:top_n]

    print(
        f"[adaptive] done — total fetch time={total_fetch_ms:.0f} ms, "
        f"returning {len(parsed['places'])} places.",
        file=sys.stderr,
    )

    # Enrich only the final top_n places (avoids enriching discarded results).
    if api_key:
        for idx, place in enumerate(parsed["places"]):
            name = place["name"]
            address = place["address"]
            print(
                f"Enriching [{idx+1}/{len(parsed['places'])}]: {name}...",
                file=sys.stderr,
            )
            price_level, photos = enrich_place_details(name, address, api_key)
            place["price_level"] = price_level
            place["photos"] = photos

    return parsed
