from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo


def build_google_calendar_url(
    restaurant_name: str,
    address: str,
    reservation_at: datetime,
    party_size: int,
    duration_minutes: int = 120,
) -> str:
    if reservation_at.tzinfo is None:
        raise ValueError("reservation_at must include a timezone")

    ends_at = reservation_at + timedelta(minutes=duration_minutes)

    def format_datetime(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action": "TEMPLATE",
        "text": f"Reservation at {restaurant_name}",
        "dates": (
            f"{format_datetime(reservation_at)}/"
            f"{format_datetime(ends_at)}"
        ),
        "location": address,
        "details": f"Restaurant reservation for {party_size} people.",
    }

    return (
        "https://calendar.google.com/calendar/render?"
        + urlencode(params)
    )