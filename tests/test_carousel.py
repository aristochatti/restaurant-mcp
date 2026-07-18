import re

from resto_mcp.carousel import build_carousel_html

SAMPLE = [
    {
        "placeId": "abc123",
        "name": "Trattoria Da Enzo",
        "address": "Via dei Vascellari 29, Roma",
        "rating": 4.5,
        "userRatingsTotal": 1820,
        "priceLevel": 2,
        "openNow": True,
        "photoUrl": "https://example.com/photo.jpg",
    },
    {
        "placeId": None,
        "name": "Chez <script>alert(1)</script>",
        "address": 'A "quoted" street',
        "rating": None,
        "userRatingsTotal": None,
        "priceLevel": None,
        "openNow": False,
        "photoUrl": None,
    },
]


def test_renders_one_card_per_restaurant_with_location_in_heading():
    html = build_carousel_html("Rome", SAMPLE)

    assert html.startswith("<!doctype html>")
    assert html.count('class="card"') == 2
    assert "Where to eat in Rome" in html
    assert "2 places" in html


def test_escapes_restaurant_names_and_addresses():
    html = build_carousel_html("Rome", SAMPLE)

    assert "<script>alert(1)</script>" not in html, "script tag must not survive raw"
    assert "Chez &lt;script&gt;" in html
    assert "A &quot;quoted&quot; street" in html


def test_escapes_the_location_which_lands_in_the_heading_unfiltered_otherwise():
    html = build_carousel_html('"><img src=x onerror=alert(1)>', [])

    assert "<img src=x" not in html, "location must be escaped"
    assert "&lt;img src=x" in html


def test_renders_price_level_as_repeated_euro_signs():
    html = build_carousel_html("Rome", SAMPLE)
    assert '<span class="price">€€</span>' in html


def test_shows_open_closed_tags_only_when_open_now_is_known():
    html = build_carousel_html("Rome", SAMPLE)
    assert "Open now" in html
    assert "Closed" in html

    unknown = build_carousel_html("Rome", [{**SAMPLE[0], "openNow": None}])
    assert "Open now" not in unknown
    assert ">Closed<" not in unknown


def test_links_to_place_id_when_available_falls_back_to_a_text_search():
    html = build_carousel_html("Rome", SAMPLE)
    assert "place/?q=place_id:abc123" in html
    assert re.search(r"maps/search/\?api=1&amp;query=", html)


def test_uses_the_emoji_placeholder_when_there_is_no_photo():
    html = build_carousel_html("Rome", SAMPLE)
    assert 'class="photo ph"' in html
    assert "background-image:url('https://example.com/photo.jpg')" in html


def test_handles_an_empty_restaurant_list_without_throwing():
    html = build_carousel_html("Nowhere", [])
    assert "0 places" in html
    assert 'class="card"' not in html
