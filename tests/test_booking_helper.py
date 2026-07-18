import re
from datetime import datetime, timedelta
import httpx
import pytest

from resto_mcp.booking import (
    parse_date,
    extract_emails,
    extract_zenchef_id,
    scrape_website,
    search_restaurant
)


def test_parse_date():
    now = datetime.now()
    assert parse_date("today") == now.strftime("%Y-%m-%d")
    assert parse_date("tomorrow") == (now + timedelta(days=1)).strftime("%Y-%m-%d")
    assert parse_date("2026-07-20") == "2026-07-20"
    assert parse_date("invalid-date") == "invalid-date"  # fallback behavior


def test_extract_emails():
    html = """
    <html>
        <body>
            <p>For bookings contact us at booking@restaurant.com or reserve@restaurant.com.</p>
            <p>General inquiries: info@restaurant.com or billing@restaurant.com.</p>
        </body>
    </html>
    """
    emails = extract_emails(html)
    # Should prioritize reservation/info related emails
    assert "booking@restaurant.com" in emails
    assert "reserve@restaurant.com" in emails
    assert "info@restaurant.com" in emails
    # Should be sorted/filtered
    assert "billing@restaurant.com" not in emails or len(emails) <= 3


def test_extract_zenchef_id_from_data_attribute():
    html = '<div class="zc-widget-config" data-restaurant="123456"></div>'
    links = []
    assert extract_zenchef_id(html, links) == "123456"


def test_extract_zenchef_id_from_js_config():
    html = "<script>window.zenchefWidgetConfig = { restaurantId: '987654' };</script>"
    links = []
    assert extract_zenchef_id(html, links) == "987654"


def test_extract_zenchef_id_from_links():
    html = "<html></html>"
    links = [
        "https://booking.zenchef.com/consumers/init/index/restaurant/456789",
        "https://link.zenchef.com/r/alias123"
    ]
    assert extract_zenchef_id(html, [links[0]]) == "456789"
    assert extract_zenchef_id(html, [links[1]]) == "alias123"


def test_scrape_website(monkeypatch):
    website_url = "https://test-restaurant.com"
    html_content = """
    <html>
        <body>
            <a href="https://booking.zenchef.com/consumers/init/index/restaurant/55555">Book Table</a>
            <a href="mailto:reservations@test-restaurant.com">Email Us</a>
            <a href="https://www.thefork.fr/restaurant/some-fork-id">TheFork</a>
            <a href="/reserve-table">Local booking page</a>
        </body>
    </html>
    """

    def mock_get(*args, **kwargs):
        class MockResponse:
            status_code = 200
            text = html_content
        return MockResponse()

    monkeypatch.setattr(httpx, "get", mock_get)

    results = scrape_website(website_url)
    assert results["zenchef_id"] == "55555"
    assert "reservations@test-restaurant.com" in results["emails"]
    assert results["booking_links"]["thefork"] == "https://www.thefork.fr/restaurant/some-fork-id"
    assert "https://test-restaurant.com/reserve-table" in results["generic_booking_paths"]


def test_search_restaurant(monkeypatch):
    def mock_post(url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "places": [
                        {
                            "id": "place-xyz",
                            "displayName": {"text": "Test Bistro"},
                            "formattedAddress": "123 Main St",
                            "websiteUri": "https://testbistro.com",
                            "reservable": True
                        }
                    ]
                }
        return MockResponse()

    monkeypatch.setattr(httpx, "post", mock_post)

    place = search_restaurant("Test Bistro", "fake-key")
    assert place is not None
    assert place["id"] == "place-xyz"
    assert place["displayName"]["text"] == "Test Bistro"
    assert place["reservable"] is True
