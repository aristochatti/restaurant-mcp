"""Thin wrapper over the Google Places API (Text Search v1).

Requires GOOGLE_MAPS_API_KEY in env with "Places API (New)" enabled.
"""

import os
from typing import Any

import httpx

_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.currentOpeningHours.openNow",
        "places.photos",
        "places.websiteUri",  # For direct booking links
    ]
)

_PRICE_MAP = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


async def _get_photo_uri(photo_name: str, key: str) -> str | None:
    """Get the direct photo URI from Google Places API.
    
    The Google Places API v1 returns photo metadata (JSON) that contains the actual
    image URL in the 'photoUri' field. This is a direct lh3.googleusercontent.com URL
    that should work with CORS.
    """
    try:
        photo_metadata_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx=400&key={key}"
        
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(photo_metadata_url)
            if resp.is_error:
                return None
            
            photo_data = resp.json()
            return photo_data.get("photoUri")
    except Exception:
        return None


async def search_restaurants(query: str, limit: int = 8, fetch_images: bool = True) -> list[dict[str, Any]]:
    """Search for restaurants using Google Places API.
    
    Args:
        query: Location to search for restaurants
        limit: Maximum number of results (capped at 20)
        fetch_images: If True, fetch direct photo URIs from Google Places
    """
    # Read at call time (not import time) so tests and reloads pick up env changes.
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set")

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            _ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": _FIELD_MASK,
            },
            json={
                "textQuery": f"restaurants in {query}",
                "includedType": "restaurant",
                "maxResultCount": min(limit, 20),
            },
        )

    if res.is_error:
        raise RuntimeError(f"Places API {res.status_code}: {res.text[:300]}")

    places = res.json().get("places") or []
    
    # Convert places to restaurant dicts
    restaurant_list = [_to_restaurant(p, key) for p in places]
    
    # Fetch direct photo URIs in parallel if requested
    if fetch_images:
        import asyncio
        
        image_tasks = []
        for r in restaurant_list:
            photo_name = r.get("photoName")
            if photo_name:
                image_tasks.append(_get_photo_uri(photo_name, key))
            else:
                image_tasks.append(None)
        
        # Wait for all image URI fetches to complete
        image_results = await asyncio.gather(*image_tasks)
        
        # Update photo URLs with direct URIs
        for i, result in enumerate(image_results):
            if result:
                restaurant_list[i]["photoUrl"] = result
    
    return restaurant_list


def _to_restaurant(p: dict[str, Any], key: str) -> dict[str, Any]:
    photos = p.get("photos") or []
    photo_name = photos[0].get("name") if photos else None

    # Extract website URI for direct booking links
    website_uri = (p.get("websiteUri") or "").strip()
    website_url = website_uri if website_uri and website_uri.startswith("http") else None
    
    return {
        "placeId": p.get("id"),
        "name": (p.get("displayName") or {}).get("text") or "Unnamed",
        "address": p.get("formattedAddress") or "",
        "rating": p.get("rating") or None,
        "userRatingsTotal": p.get("userRatingCount") or None,
        "priceLevel": _PRICE_MAP.get(p.get("priceLevel")),
        "openNow": (p.get("currentOpeningHours") or {}).get("openNow"),
        "photoUrl": None,
        "photoName": photo_name,
        "websiteUrl": website_url,
    }
