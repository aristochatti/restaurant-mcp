from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from reservation_calendar import build_google_calendar_url
from google_calendar import PROJECT_DIR, TOKEN_FILE


def test_google_calendar_token_is_read_from_project_root():
    assert PROJECT_DIR == Path(__file__).resolve().parent.parent
    assert TOKEN_FILE == PROJECT_DIR / "token.json"


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
