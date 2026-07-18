"""Thin wrapper over the Google Places API (Text Search v1).

Requires GOOGLE_MAPS_API_KEY in env with "Places API (New)" enabled.
"""

import base64
import json
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
    ]
)

_PRICE_MAP = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

# Use a smaller image size to keep base64-encoded HTML under MCP response limits
_IMAGE_MAX_WIDTH = 150


async def _fetch_image_as_base64(photo_name: str, key: str) -> str | None:
    """Fetch an image from Google Places and return it as a base64 data URL.
    
    The Google Places API v1 returns photo metadata (JSON) that contains the actual
    image URL in the 'photoUri' field. We need to:
    1. Fetch the photo metadata from the Places API
    2. Extract the photoUri from the JSON response
    3. Fetch the actual image from photoUri
    4. Convert to base64 data URL
    """
    try:
        # First, get the photo metadata from Google Places API
        photo_metadata_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={_IMAGE_MAX_WIDTH}&key={key}"
        
        async with httpx.AsyncClient(timeout=10) as client:
            # Fetch photo metadata
            resp = await client.get(photo_metadata_url)
            if resp.is_error:
                return None
            
            # Parse the JSON response to get the actual image URL
            photo_data = resp.json()
            photo_uri = photo_data.get("photoUri")
            if not photo_uri:
                return None
            
            # Now fetch the actual image from the photoUri
            img_resp = await client.get(photo_uri)
            if img_resp.is_error:
                return None
            
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            # Extract just the MIME type
            mime_type = content_type.split(";")[0] if content_type else "image/jpeg"
            
            # Encode to base64
            b64 = base64.b64encode(img_resp.content).decode("utf-8")
            return f"data:{mime_type};base64,{b64}"
    except Exception:
        return None


async def search_restaurants(query: str, limit: int = 8, fetch_images: bool = True) -> list[dict[str, Any]]:
    """Search for restaurants using Google Places API.
    
    Args:
        query: Location to search for restaurants
        limit: Maximum number of results (capped at 20)
        fetch_images: If True, fetch images and embed them as base64 data URLs
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
    
    # Fetch images in parallel if requested
    if fetch_images:
        import asyncio
        
        # Get photo names for each restaurant
        image_tasks = []
        for r in restaurant_list:
            photo_name = r.get("photoName")
            if photo_name:
                image_tasks.append(_fetch_image_as_base64(photo_name, key))
            else:
                image_tasks.append(None)
        
        # Wait for all image fetches to complete
        image_results = await asyncio.gather(*image_tasks)
        
        # Update photo URLs with base64 data (only if fetch succeeded)
        for i, result in enumerate(image_results):
            if result:
                restaurant_list[i]["photoUrl"] = result
    
    return restaurant_list


def _to_restaurant(p: dict[str, Any], key: str) -> dict[str, Any]:
    photos = p.get("photos") or []
    photo_name = photos[0].get("name") if photos else None
    
    # Generate direct Google Places photo metadata URL
    direct_photo_url = (
        f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={_IMAGE_MAX_WIDTH}&key={key}"
        if photo_name
        else None
    )

    return {
        "placeId": p.get("id"),
        "name": (p.get("displayName") or {}).get("text") or "Unnamed",
        "address": p.get("formattedAddress") or "",
        "rating": p.get("rating") or None,
        "userRatingsTotal": p.get("userRatingCount") or None,
        "priceLevel": _PRICE_MAP.get(p.get("priceLevel")),
        "openNow": (p.get("currentOpeningHours") or {}).get("openNow"),
        "photoUrl": direct_photo_url,
        "photoName": photo_name,  # Store the photo name for image fetching
    }
