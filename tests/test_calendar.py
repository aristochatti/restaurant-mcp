from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from resto_mcp.calendar import build_google_calendar_url


def test_build_google_calendar_url():
    url = build_google_calendar_url(
        restaurant_name="Restaurant A",
        address="Via Roma 10, Milan",
        reservation_at=datetime(
            2026, 7, 19, 21, 0,
            tzinfo=ZoneInfo("Europe/Rome"),
        ),
        party_size=2,
    )

    params = parse_qs(urlparse(url).query)

    assert params["action"] == ["TEMPLATE"]
    assert params["text"] == ["Reservation at Restaurant A"]
    assert params["location"] == ["Via Roma 10, Milan"]
    assert params["dates"] == ["20260719T190000Z/20260719T210000Z"]