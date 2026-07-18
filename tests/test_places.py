import functools
import json

import httpx
import pytest

from resto_mcp import places
from resto_mcp.places import search_restaurants


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")


@pytest.fixture
def stub_places(monkeypatch):
    """Route the module's AsyncClient through a MockTransport, recording requests."""

    calls: list[httpx.Request] = []

    def install(status_code: int, body, *, text: str | None = None):
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if text is not None:
                return httpx.Response(status_code, text=text)
            return httpx.Response(status_code, json=body)

        monkeypatch.setattr(
            places.httpx,
            "AsyncClient",
            functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
        )
        return calls

    return install


async def test_maps_a_places_response_into_the_carousels_restaurant_shape(stub_places):
    stub_places(
        200,
        {
            "places": [
                {
                    "id": "place-1",
                    "displayName": {"text": "Osteria Fernanda"},
                    "formattedAddress": "Via Crescenzo del Monte 18, Roma",
                    "rating": 4.6,
                    "userRatingCount": 900,
                    "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                    "currentOpeningHours": {"openNow": True},
                    "photos": [{"name": "places/place-1/photos/xyz"}],
                }
            ]
        },
    )

    (r,) = await search_restaurants("Rome", 5, fetch_images=False)

    assert r["placeId"] == "place-1"
    assert r["name"] == "Osteria Fernanda"
    assert r["address"] == "Via Crescenzo del Monte 18, Roma"
    assert r["rating"] == 4.6
    assert r["userRatingsTotal"] == 900
    assert r["priceLevel"] == 3
    assert r["openNow"] is True
    assert "places.googleapis.com/v1/places/place-1/photos/xyz/media" in r["photoUrl"]
    assert "maxWidthPx=500" in r["photoUrl"]
    assert "key=test-key" in r["photoUrl"]
    assert r["photoName"] == "places/place-1/photos/xyz"


async def test_fills_in_defaults_for_sparse_places(stub_places):
    stub_places(200, {"places": [{"id": "place-2"}]})

    (r,) = await search_restaurants("Rome", fetch_images=False)

    assert r["name"] == "Unnamed"
    assert r["address"] == ""
    assert r["rating"] is None
    assert r["priceLevel"] is None
    assert r["photoUrl"] is None
    assert r["photoName"] is None


async def test_returns_an_empty_list_when_places_returns_no_results(stub_places):
    stub_places(200, {})
    assert await search_restaurants("Atlantis", fetch_images=False) == []


async def test_caps_max_result_count_at_20_and_scopes_the_query_to_restaurants(stub_places):
    calls = stub_places(200, {"places": []})

    await search_restaurants("Tokyo", 50, fetch_images=False)

    body = json.loads(calls[0].content)
    assert body["maxResultCount"] == 20
    assert body["includedType"] == "restaurant"
    assert body["textQuery"] == "restaurants in Tokyo"
    assert calls[0].headers["X-Goog-Api-Key"] == "test-key"


async def test_raises_with_the_api_status_when_places_rejects_the_request(stub_places):
    stub_places(403, None, text="PERMISSION_DENIED: Places API is not enabled")

    with pytest.raises(RuntimeError, match=r"Places API 403.*PERMISSION_DENIED"):
        await search_restaurants("Rome", fetch_images=False)


async def test_raises_when_the_api_key_is_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_MAPS_API_KEY is not set"):
        await search_restaurants("Rome", fetch_images=False)
