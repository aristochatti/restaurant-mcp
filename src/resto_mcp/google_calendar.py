from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

PROJECT_DIR = Path(__file__).resolve().parents[2]
TOKEN_FILE = PROJECT_DIR / "token.json"


def create_calendar_event(
    restaurant_name: str,
    address: str,
    reservation_at: datetime,
    party_size: int,
    duration_minutes: int = 120,
) -> dict:
    if reservation_at.tzinfo is None:
        raise ValueError("reservation_at must include a timezone")

    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            "Google Calendar is not authorized. "
            "Run scripts/authorize_google_calendar.py first."
        )

    credentials = Credentials.from_authorized_user_file(
        str(TOKEN_FILE),
        SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )
        TOKEN_FILE.chmod(0o600)

    if not credentials.valid:
        raise RuntimeError("Google Calendar credentials are invalid")

    ends_at = reservation_at + timedelta(
        minutes=duration_minutes
    )

    event_body = {
        "summary": f"Reservation at {restaurant_name}",
        "location": address,
        "description": (
            f"Restaurant reservation for {party_size} people."
        ),
        "start": {
            "dateTime": reservation_at.isoformat(),
            "timeZone": str(reservation_at.tzinfo),
        },
        "end": {
            "dateTime": ends_at.isoformat(),
            "timeZone": str(ends_at.tzinfo),
        },
    }

    service = build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    return (
        service.events()
        .insert(
            calendarId="primary",
            body=event_body,
        )
        .execute()
    )