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
    ]
)

_PRICE_MAP = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


async def search_restaurants(query: str, limit: int = 8) -> list[dict[str, Any]]:
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
    return [_to_restaurant(p, key) for p in places]


def _to_restaurant(p: dict[str, Any], key: str) -> dict[str, Any]:
    photos = p.get("photos") or []
    photo_name = photos[0].get("name") if photos else None
    photo_url = (
        f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx=500&key={key}"
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
        "photoUrl": photo_url,
    }