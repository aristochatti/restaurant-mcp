"""Tests for the ElevenLabs phone booking module and MCP tool."""

import json
import pytest
import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from phone_booking import (
    initiate_booking_call,
    _normalise_phone,
    get_conversation_summary,
    wait_for_conversation_summary,
)


# ---------------------------------------------------------------------------
# Unit tests for the phone normaliser helper
# ---------------------------------------------------------------------------

def test_normalise_phone_already_e164():
    assert _normalise_phone("+33123456789") == "+33123456789"


def test_normalise_phone_bare_digits():
    assert _normalise_phone("33123456789") == "+33123456789"


def test_normalise_phone_strips_formatting():
    assert _normalise_phone("+33 1 23 45 67 89") == "+33123456789"
    assert _normalise_phone("+33-1-23-45-67-89") == "+33123456789"
    assert _normalise_phone("(33) 123456789") == "+33123456789"


def test_normalise_phone_invalid_returns_none():
    assert _normalise_phone("not-a-phone") is None
    assert _normalise_phone("123") is None  # Too short


# ---------------------------------------------------------------------------
# Unit tests for initiate_booking_call
# ---------------------------------------------------------------------------

_BOOKING_KWARGS = dict(
    restaurant_name="Benoit Paris",
    phone_number="+33142726925",
    guest_name="Lorenzo Santolini",
    date="2026-07-25",
    time_start="20:00",
    time_end="21:30",
    pax=2,
    special_requests="",
)


def test_missing_credentials_returns_error(monkeypatch):
    """Without env vars the function should return a descriptive error."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_PHONE_NUMBER_ID", raising=False)
    result = initiate_booking_call(
        **_BOOKING_KWARGS,
        elevenlabs_api_key=None,
        agent_id=None,
        phone_number_id=None,
    )
    assert result["success"] is False
    assert "ELEVENLABS_API_KEY" in result["message"]
    assert result["call_id"] is None


def test_invalid_phone_returns_error():
    result = initiate_booking_call(
        **{**_BOOKING_KWARGS, "phone_number": "not-a-number"},
        elevenlabs_api_key="fake-key",
        agent_id="fake-agent",
        phone_number_id="fake-phone-id",
    )
    assert result["success"] is False
    assert "Invalid phone number" in result["message"]


def test_successful_call(monkeypatch):
    """Mocks the HTTP call and verifies the success path."""

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"callSid": "CA123abc", "status": "queued"}

    class FakeClient:
        def __init__(self, **kwargs): pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            assert "xi-api-key" in kwargs["headers"]
            body = kwargs["json"]
            assert body["to_number"] == "+33142726925"
            assert body["agent_id"] == "test-agent-id"
            dvars = body["conversation_initiation_client_data"]["dynamic_variables"]
            assert dvars["restaurant_name"] == "Benoit Paris"
            assert dvars["pax"] == "2"
            return FakeResponse()

    monkeypatch.setattr("phone_booking.httpx.Client", FakeClient)

    result = initiate_booking_call(
        **_BOOKING_KWARGS,
        elevenlabs_api_key="test-xi-key",
        agent_id="test-agent-id",
        phone_number_id="test-phone-number-id",
    )

    assert result["success"] is True
    assert result["call_id"] == "CA123abc"
    assert "Benoit Paris" in result["message"]
    assert result["details"]["guest_name"] == "Lorenzo Santolini"


def test_api_error_response(monkeypatch):
    """A 4xx from ElevenLabs should return success=False."""

    class FakeResponse:
        status_code = 400
        text = "Bad Request"

        def json(self):
            return {"detail": "agent_phone_number_id not found"}

    class FakeClient:
        def __init__(self, **kwargs): pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("phone_booking.httpx.Client", FakeClient)

    result = initiate_booking_call(
        **_BOOKING_KWARGS,
        elevenlabs_api_key="test-xi-key",
        agent_id="test-agent-id",
        phone_number_id="wrong-id",
    )

    assert result["success"] is False
    assert "400" in result["message"]
    assert "agent_phone_number_id not found" in result["message"]


def test_timeout_returns_error(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs): pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("phone_booking.httpx.Client", FakeClient)

    result = initiate_booking_call(
        **_BOOKING_KWARGS,
        elevenlabs_api_key="test-xi-key",
        agent_id="test-agent-id",
        phone_number_id="test-phone-number-id",
    )

    assert result["success"] is False
    assert "timed out" in result["message"].lower()


# ---------------------------------------------------------------------------
# MCP tool schema test (via test_server fixture)
# ---------------------------------------------------------------------------

import server
from conftest import rpc, read_rpc, INIT_PARAMS


async def test_tools_list_exposes_call_restaurant_for_booking(client):
    await rpc(client, "initialize", INIT_PARAMS)
    res = await rpc(client, "tools/list", {}, id=2)
    body = read_rpc(res)
    assert "error" not in body

    tools = body["result"]["tools"]
    tool = next((t for t in tools if t["name"] == "call_restaurant_for_booking"), None)
    assert tool is not None, f"Tool not found. Available: {[t['name'] for t in tools]}"
    assert "elevenlabs" in tool["description"].lower()

    required = tool["inputSchema"]["required"]
    for field in ("restaurant_name", "phone_number", "guest_name", "date", "time_start", "pax"):
        assert field in required, f"'{field}' missing from required fields"

    # time_end and special_requests are optional
    props = tool["inputSchema"]["properties"]
    assert "time_end" in props
    assert "special_requests" in props


async def test_call_restaurant_for_booking_tool_call_missing_env(client, monkeypatch):
    """With no ElevenLabs env vars, tool should return a non-error MCP response
    whose text describes the missing credentials."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_PHONE_NUMBER_ID", raising=False)

    res = await rpc(
        client,
        "tools/call",
        {
            "name": "call_restaurant_for_booking",
            "arguments": {
                "restaurant_name": "Benoit Paris",
                "phone_number": "+33142726925",
                "guest_name": "Lorenzo Santolini",
                "date": "2026-07-25",
                "time_start": "20:00",
                "pax": 2,
            },
        },
        id=5,
    )
    body = read_rpc(res)
    assert "error" not in body

    content = body["result"]["content"]
    text = next(c for c in content if c["type"] == "text")
    data = json.loads(text["text"])
    assert data["success"] is False
    assert "ELEVENLABS_API_KEY" in data["message"]


def test_get_conversation_summary_success(monkeypatch):
    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "status": "done",
                "transcript": [
                    {"role": "user", "message": "Hi"},
                    {"role": "agent", "message": "Hello"}
                ],
                "analysis": {
                    "transcript_summary": "Booking confirmed for Lorenzo",
                    "evaluation_criteria_results": {
                        "Is booking successful?": {"result": "success"}
                    }
                },
                "metadata": {
                    "call_duration_secs": 45
                }
            }

    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert "conversations/conv-123" in url
            return FakeResponse()

    monkeypatch.setattr("phone_booking.httpx.Client", FakeClient)
    res = get_conversation_summary("conv-123", api_key="test-key")
    assert res["status"] == "done"
    assert res["duration_seconds"] == 45
    assert len(res["transcript"]) == 2
    assert res["summary"] == "Booking confirmed for Lorenzo"
    assert res["reservation_confirmed"] is True


def test_wait_for_conversation_summary_polls_and_finds_match(monkeypatch):
    import time
    now_epoch = time.time()

    list_called = 0
    detail_called = 0

    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            nonlocal list_called, detail_called
            if "conversations/conv-456" in url:
                detail_called += 1
                class DetailResponse:
                    status_code = 200
                    def json(self):
                        return {
                            "status": "done",
                            "transcript": [],
                            "analysis": {
                                "transcript_summary": "Summary",
                                "data_collection_results": {
                                    "Is reservation confirmed": {"value": "Yes"}
                                }
                            }
                        }
                return DetailResponse()
            else:
                list_called += 1
                class ListResponse:
                    status_code = 200
                    def json(self):
                        return {
                            "conversations": [
                                {
                                    "conversation_id": "conv-456",
                                    "start_time_unix_secs": now_epoch,
                                    "status": "done"
                                }
                            ]
                        }
                return ListResponse()

    monkeypatch.setattr("phone_booking.httpx.Client", FakeClient)
    # Patch time.sleep so the test runs instantly
    monkeypatch.setattr("time.sleep", lambda s: None)

    res = wait_for_conversation_summary(
        agent_id="agent-123",
        called_at_epoch=now_epoch,
        api_key="test-key",
        poll_interval=1,
        max_wait=10
    )

    assert list_called == 1
    assert detail_called == 1
    assert res["summary"] == "Summary"
    assert res["reservation_confirmed"] is True

