"""Module 2: Fetching from Google Maps Lists

Extracts places from public Google Maps shared lists.
Returns data in the same format as places.py for consistency.
"""

import os
from typing import Any

try:
    # Import from extract_list module in same directory
    from extract_list import resolve_list_id, fetch_list_data, parse_places
    EXTRACTION_AVAILABLE = True
except ImportError:
    EXTRACTION_AVAILABLE = False
    resolve_list_id = None
    fetch_list_data = None
    parse_places = None


async def fetch_from_list(
    url: str,
    enrich: bool = False,
    user_location: str | None = None,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch places from a Google Maps shared list.
    
    This uses the extraction logic from scripts/ to parse public list URLs.
    
    Args:
        url: Public Google Maps list URL (e.g., https://maps.app.goo.gl/abc123)
        enrich: If True, use GOOGLE_MAPS_API_KEY to enrich with photos/prices
        user_location: Optional user coordinates or address to sort results by distance
        top_n: Optional number of closest places to return
        
    Returns:
        List of places matching the format from places.search_restaurants()
        so they can use the same carousel visualizer.
    """
    if not EXTRACTION_AVAILABLE:
        return []
    
    # Get API key for enrichment
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") if enrich else None
    
    # Step 1: Resolve list ID from URL
    list_id = resolve_list_id(url)
    if not list_id:
        return []
    
    # Step 2: Fetch raw list data
    raw_data = fetch_list_data(list_id)
    if not raw_data:
        return []
    
    # Step 3: Parse places (optionally sorted and enriched)
    parsed = parse_places(
        raw_data,
        api_key=api_key if enrich else None,
        user_location=user_location,
        top_n=top_n
    )
    if not parsed or not parsed.get("places"):
        return []
    
    # Step 4: Normalize to places.py format for carousel compatibility
    restaurants = []
    for place in parsed["places"]:
        # Extract website URL if available (from enriched data)
        website_url = None
        # Check if enrichment added website data
        # Note: extract_list.parse_places doesn't currently return websiteUri,
        # but if we enrich via Places API, we could add it. For now, leave as None.
        # The places.py module handles websiteUri from direct Places API calls.
        
        restaurants.append({
            "placeId": place.get("google_place_ids", [None])[0] if place.get("google_place_ids") else None,
            "name": place.get("name", "Unknown"),
            "address": place.get("address") or "",
            "rating": None,  # Not in list data
            "userRatingsTotal": None,
            "priceLevel": _normalize_price_level(place.get("price_level")),
            "openNow": None,  # Not in list data
            "photoUrl": place.get("photos", [None])[0] if place.get("photos") else None,
            "websiteUrl": website_url,  # Will be None for now, populated by places.py
        })
    
    return restaurants


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
