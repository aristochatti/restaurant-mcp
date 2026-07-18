import re
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from carousel import build_carousel_html, _esc_url

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


def test_view_and_book_button_removed():
    html = build_carousel_html("Rome", SAMPLE)
    # View & Book button should not be present
    assert "View &amp; book" not in html
    assert 'class="book"' not in html


def test_uses_the_emoji_placeholder_when_there_is_no_photo():
    html = build_carousel_html("Rome", SAMPLE)
    assert 'class="photo ph"' in html


def test_handles_an_empty_restaurant_list_without_throwing():
    html = build_carousel_html("Nowhere", [])
    assert "0 places" in html
    assert 'class="card"' not in html


def test_handles_base64_data_urls_without_escaping_data():
    """Test that base64 data URLs are not HTML-escaped by _esc_url."""
    base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    url = f"data:image/png;base64,{base64_data}"
    escaped = _esc_url(url)
    assert escaped == url
    assert base64_data in escaped


def test_handles_regular_urls_properly():
    """Test that regular URLs are still properly escaped by _esc_url."""
    url = "https://example.com/photo.jpg?param=value&other=test"
    escaped = _esc_url(url)
    assert "https://example.com/photo.jpg" in escaped
