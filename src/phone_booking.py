"""ElevenLabs outbound phone-call integration for restaurant bookings.

Initiates an ElevenLabs Conversational AI outbound call to a restaurant's phone
number using the native Twilio integration.  The agent is primed with all the
booking context (restaurant name, date, time, party size, guest name) via
``conversation_initiation_client_data`` dynamic variables so the AI can conduct
the full reservation conversation autonomously.

Required environment variables
-------------------------------
ELEVENLABS_API_KEY            Your ElevenLabs API key.
ELEVENLABS_AGENT_ID           ID of the Conversational AI agent to use.
ELEVENLABS_PHONE_NUMBER_ID    ID of the Twilio phone number linked to that agent
                               in the ElevenLabs dashboard.

All three must be present for the tool to make a real call; if any is missing
the function returns an informative error message so the agent can report it.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_OUTBOUND_CALL_URL = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"

# System prompt template injected into the agent for every restaurant call.
# Dynamic variable placeholders ({{…}}) are resolved by ElevenLabs at call time.
_BOOKING_SYSTEM_PROMPT = """You are a friendly and professional restaurant reservation assistant.

Your task is to call the restaurant and make a table reservation on behalf of the guest.

Booking details:
- Restaurant name: {{restaurant_name}}
- Guest name: {{guest_name}}
- Date: {{date}}
- Preferred time: {{time_start}} (flexible until {{time_end}})
- Number of guests (pax): {{pax}}
- Special requests: {{special_requests}}

Instructions:
1. Greet the restaurant staff politely in the language they use (auto-detect from their greeting).
2. State that you are calling to make a reservation for {{guest_name}}.
3. Request a table for {{pax}} people on {{date}} around {{time_start}}.
4. If the exact time is not available, try to negotiate the closest available slot within the {{time_start}}–{{time_end}} window.
5. Confirm the restaurant's name, date, time, and number of guests before concluding.
6. If a reservation is confirmed, thank the staff and end the call politely.
7. If the restaurant cannot accommodate the booking, politely thank them and end the call.

Important: Speak naturally and conversationally. Do not reveal that you are an AI unless directly asked.
"""


def initiate_booking_call(
    *,
    restaurant_name: str,
    phone_number: str,
    guest_name: str,
    date: str,
    time_start: str,
    time_end: str,
    pax: int,
    special_requests: str = "",
    elevenlabs_api_key: str | None = None,
    agent_id: str | None = None,
    phone_number_id: str | None = None,
) -> dict[str, Any]:
    """Initiate an ElevenLabs outbound call to book a table at a restaurant.

    Parameters
    ----------
    restaurant_name:
        Display name of the restaurant.
    phone_number:
        Destination phone number in E.164 format (e.g. ``+33123456789``).
    guest_name:
        Name of the guest for the reservation.
    date:
        Reservation date in a human-readable format (e.g. ``2026-07-20``).
    time_start:
        Preferred start time (e.g. ``19:30``).
    time_end:
        Latest acceptable time (e.g. ``21:00``).
    pax:
        Number of guests.
    special_requests:
        Any dietary requirements or special requests (optional).
    elevenlabs_api_key / agent_id / phone_number_id:
        Override the environment-variable defaults for testing.

    Returns
    -------
    dict with keys:
        ``success`` (bool), ``call_id`` (str | None), ``message`` (str),
        ``details`` (dict with the full booking context that was sent).
    """
    api_key = elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY")
    _agent_id = agent_id or os.environ.get("ELEVENLABS_AGENT_ID")
    _phone_number_id = phone_number_id or os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")

    # --- Validate required config ---
    missing = [
        name
        for name, val in [
            ("ELEVENLABS_API_KEY", api_key),
            ("ELEVENLABS_AGENT_ID", _agent_id),
            ("ELEVENLABS_PHONE_NUMBER_ID", _phone_number_id),
        ]
        if not val
    ]
    if missing:
        return {
            "success": False,
            "call_id": None,
            "message": (
                f"Cannot place call — the following environment variables are not set: "
                f"{', '.join(missing)}. "
                "Please configure them in your .env or deployment settings."
            ),
            "details": {},
        }

    # --- Normalise phone number to E.164 if needed ---
    to_number = _normalise_phone(phone_number)
    if not to_number:
        return {
            "success": False,
            "call_id": None,
            "message": (
                f"Invalid phone number '{phone_number}'. "
                "Please provide a number in E.164 format (e.g. +33123456789)."
            ),
            "details": {},
        }

    booking_context = {
        "restaurant_name": restaurant_name,
        "guest_name": guest_name,
        "date": date,
        "time_start": time_start,
        "time_end": time_end,
        "pax": str(pax),
        "special_requests": special_requests or "none",
    }

    payload = {
        "agent_id": _agent_id,
        "agent_phone_number_id": _phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": {
            "dynamic_variables": booking_context,
            "conversation_config_override": {
                "agent": {
                    "prompt": {
                        "prompt": _BOOKING_SYSTEM_PROMPT,
                    },
                    "first_message": (
                        f"Hello, I'm calling to make a reservation for {guest_name}."
                    ),
                }
            },
        },
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                _OUTBOUND_CALL_URL,
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code in (200, 201):
            data = response.json()
            call_id = data.get("callSid") or data.get("call_id") or data.get("id")
            return {
                "success": True,
                "call_id": call_id,
                "message": (
                    f"✅ Call initiated successfully to {to_number} "
                    f"({restaurant_name}). "
                    f"The AI agent will now conduct the booking conversation. "
                    f"Call ID: {call_id}"
                ),
                "details": booking_context,
            }
        else:
            error_body = _safe_json(response)
            return {
                "success": False,
                "call_id": None,
                "message": (
                    f"ElevenLabs API returned HTTP {response.status_code}: "
                    f"{error_body.get('detail', response.text)}"
                ),
                "details": booking_context,
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "call_id": None,
            "message": "Request to ElevenLabs API timed out. Please try again.",
            "details": booking_context,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "call_id": None,
            "message": f"Unexpected error while initiating call: {exc}",
            "details": booking_context,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_phone(raw: str) -> str | None:
    """Best-effort normalisation to E.164.  Returns None if clearly invalid."""
    import re
    # Strip spaces, dashes, dots, parentheses
    cleaned = re.sub(r"[\s\-\.\(\)]", "", raw.strip())
    # Already E.164
    if re.match(r"^\+\d{7,15}$", cleaned):
        return cleaned
    # Bare digits — prepend + (caller must supply country code in digits)
    if re.match(r"^\d{7,15}$", cleaned):
        return f"+{cleaned}"
    return None


def _safe_json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Post-call: conversation summary & transcript
# ---------------------------------------------------------------------------

_CONVERSATIONS_URL = "https://api.elevenlabs.io/v1/convai/conversations"


def get_conversation_summary(
    conversation_id: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Fetch transcript and analysis for a completed ElevenLabs conversation.

    Returns a dict with keys: ``conversation_id``, ``status``,
    ``transcript`` (list of turn dicts), ``summary`` (str | None),
    ``analysis`` (dict | None), ``reservation_confirmed`` (bool | None).
    """
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return {"error": "ELEVENLABS_API_KEY not set"}

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{_CONVERSATIONS_URL}/{conversation_id}",
                headers={"xi-api-key": api_key},
            )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

        data = resp.json()
        transcript = data.get("transcript", [])
        analysis = data.get("analysis", {})
        summary = analysis.get("transcript_summary") or analysis.get("summary")

        # Try to determine reservation outcome from analysis / evaluation
        confirmed = None
        eval_data = analysis.get("evaluation_criteria_results", {})
        for key, val in eval_data.items():
            if "success" in key.lower() or "reserv" in key.lower() or "book" in key.lower() or "confirm" in key.lower():
                confirmed = val.get("result") == "success"
                break
        # Fallback: check data collection fields
        data_collected = analysis.get("data_collection_results", {})
        for key, val in data_collected.items():
            if "confirm" in key.lower() or "reserv" in key.lower() or "book" in key.lower():
                raw = str(val.get("value", "")).lower()
                if raw in ("yes", "true", "confirmed", "success"):
                    confirmed = True
                elif raw in ("no", "false", "failed", "unsuccessful"):
                    confirmed = False

        return {
            "conversation_id": conversation_id,
            "status": data.get("status"),
            "duration_seconds": data.get("metadata", {}).get("call_duration_secs"),
            "transcript": [
                {"role": t.get("role"), "message": t.get("message")}
                for t in transcript
            ],
            "summary": summary,
            "analysis": analysis,
            "reservation_confirmed": confirmed,
        }
    except Exception as exc:
        return {"error": f"Failed to fetch conversation: {exc}"}


def wait_for_conversation_summary(
    agent_id: str,
    called_at_epoch: float,
    api_key: str | None = None,
    poll_interval: int = 5,
    max_wait: int = 300,
) -> dict[str, Any]:
    """Poll the conversations list until the most recent call finishes, then return its summary.

    Parameters
    ----------
    agent_id:
        ElevenLabs agent ID (used to filter conversations).
    called_at_epoch:
        Unix timestamp of when ``initiate_booking_call`` was invoked.
        Used to identify the right conversation (the one started after this time).
    poll_interval:
        Seconds between polls (default 5).
    max_wait:
        Maximum seconds to wait for the call to finish (default 300 = 5 min).
    """
    import time

    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return {"error": "ELEVENLABS_API_KEY not set"}

    deadline = time.time() + max_wait
    conversation_id = None

    while time.time() < deadline:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    _CONVERSATIONS_URL,
                    headers={"xi-api-key": api_key},
                    params={"agent_id": agent_id, "page_size": 10},
                )
            if resp.status_code != 200:
                time.sleep(poll_interval)
                continue

            conversations = resp.json().get("conversations", [])

            # Find the conversation that started after our call was placed
            for conv in conversations:
                start_time = conv.get("start_time_unix_secs", 0)
                if start_time >= called_at_epoch - 10:  # 10s tolerance
                    conversation_id = conv.get("conversation_id")
                    status = conv.get("status", "")
                    if status in ("done", "failed"):
                        return get_conversation_summary(conversation_id, api_key=api_key)
                    # Still in progress — keep polling
                    break

        except Exception:
            pass

        time.sleep(poll_interval)

    if conversation_id:
        # Timed out but we have an ID — fetch whatever we have
        return get_conversation_summary(conversation_id, api_key=api_key)

    return {"error": f"Timed out after {max_wait}s waiting for conversation to complete"}

