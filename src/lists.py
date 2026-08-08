"""Module 2: Fetching from Google Maps Lists

Extracts places from public Google Maps shared lists.
Returns data in the same format as places.py for consistency.
"""

import os
from typing import Any

try:
    # Import from extract_list module in same directory
    from extract_list import resolve_list_id, fetch_list_data, parse_places, adaptive_fetch_and_parse
    EXTRACTION_AVAILABLE = True
except ImportError:
    EXTRACTION_AVAILABLE = False
    resolve_list_id = None
    fetch_list_data = None
    parse_places = None
    adaptive_fetch_and_parse = None


# How many raw items we request from Google's entitylist API in one call.
# Increasing this has no server-side cost but means more data to parse locally.
_FETCH_LIMIT = 500


async def fetch_from_list(
    url: str,
    enrich: bool = False,
    user_location: str | None = None,
    top_n: int | None = None,
    radius_km: float | None = None,
) -> dict[str, Any]:
    """
    Fetch places from a Google Maps shared list.

    Args:
        url:           Public Google Maps list URL (e.g., https://maps.app.goo.gl/abc123)
        enrich:        If True, enrich with price levels and photos via Google Places API.
        user_location: Optional user coordinates or address to sort results by distance.
        top_n:         Optional number of closest places to return (applied after sorting).
        radius_km:     Optional radius filter.  Only places within this distance from
                       user_location are returned.  Applied before top_n slicing.

    Returns:
        {
            "places":       list of place dicts (carousel-compatible),
            "is_truncated": True when the raw list likely has more items than fetched,
            "total_fetched": number of items fetched from Google before filtering,
        }
    """
    _empty = {"places": [], "is_truncated": False, "total_fetched": 0}

    if not EXTRACTION_AVAILABLE:
        return _empty

    # Geocoding key: needed to resolve named locations (e.g. "Paris, France") even
    # when enrichment is disabled. Falls back gracefully if the key is absent —
    # raw "lat,lon" strings still work without any key.
    geo_api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")

    # Enrichment key: only used when the caller explicitly requests price/photos.
    enrich_api_key = geo_api_key if enrich else None

    # Step 1: Resolve list ID from URL
    list_id = resolve_list_id(url)
    if not list_id:
        return _empty

    # Step 2 / Step 3: Fetch and parse.
    # When radius_km + top_n + user_location are all set, use the adaptive
    # batcher (resolves coords once, fetches in increasing batches 100→300→500,
    # stops as soon as top_n places are found within radius_km).
    # Otherwise fall back to a single full fetch of _FETCH_LIMIT items.
    use_adaptive = radius_km is not None and top_n is not None and user_location is not None

    if use_adaptive:
        parsed = adaptive_fetch_and_parse(
            list_id,
            api_key=enrich_api_key,
            geo_api_key=geo_api_key,
            user_location=user_location,
            top_n=top_n,
            radius_km=radius_km,
            max_fetch_limit=_FETCH_LIMIT,
        )
    else:
        # Single full fetch — needed when no radius is given, because we must
        # sort the entire list by distance before slicing to top_n.
        raw_data = fetch_list_data(list_id, limit=_FETCH_LIMIT)
        if not raw_data:
            return _empty

        # Parse places with geo_api_key so named locations can be geocoded
        # even when enrichment is off.
        parsed = parse_places(
            raw_data,
            api_key=enrich_api_key,
            geo_api_key=geo_api_key,
            user_location=user_location,
            top_n=top_n,
            radius_km=radius_km,
            fetch_limit=_FETCH_LIMIT,
        )
    if not parsed or not parsed.get("places"):
        return {
            "places": [],
            "is_truncated": parsed.get("is_truncated", False) if parsed else False,
            "total_fetched": parsed.get("total_items", 0) if parsed else 0,
        }

    # Step 4: Normalize to places.py format for carousel compatibility
    restaurants = []
    for place in parsed["places"]:
        distance_km = place.get("distance_km")  # None when no user_location given
        restaurants.append({
            "placeId": place.get("google_place_ids", [None])[0] if place.get("google_place_ids") else None,
            "name": place.get("name", "Unknown"),
            "address": place.get("address") or "",
            "rating": None,  # Not in list data
            "userRatingsTotal": None,
            "priceLevel": _normalize_price_level(place.get("price_level")),
            "openNow": None,  # Not in list data
            "photoUrl": place.get("photos", [None])[0] if place.get("photos") else None,
            "websiteUrl": None,
            "distanceKm": distance_km,  # populated when user_location is provided
        })

    return {
        "places": restaurants,
        "is_truncated": parsed.get("is_truncated", False),
        "total_fetched": parsed.get("total_items", len(restaurants)),
    }


def _normalize_price_level(price_level: str | None) -> int | None:
    """Convert various price level formats to numeric (1-4) for carousel."""
    if not price_level:
        return None
    
    price_map = {
        # From Google Maps lists (symbols)
        "$": 1, "$$": 2, "$$$": 3, "$$$$": 4,
        # From Places API (strings)
        "PRICE_LEVEL_INEXPENSIVE": 1,
        "PRICE_LEVEL_MODERATE": 2,
        "PRICE_LEVEL_EXPENSIVE": 3,
        "PRICE_LEVEL_VERY_EXPENSIVE": 4,
        "PRICE_LEVEL_FREE": 0,
        # Lowercase variants
        "inexpensive": 1, "moderate": 2, "expensive": 3, "very_expensive": 4,
    }
    return price_map.get(price_level.upper().strip("$ "), None)
