"""Smoke + unit tests for the pier-grouped formatter."""
from __future__ import annotations

from datetime import datetime, timezone

from flightassign_pier.api import list_in_scope_outbound
from flightassign_pier.config import Config
from flightassign_pier.format import build_message


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


# Fixed "now" for deterministic assertions. 2026-05-13 15:00 EDT = 19:00 UTC.
NOW = datetime(2026, 5, 13, 19, 0, 0, tzinfo=timezone.utc)


def _flight(
    flt_num: int,
    al_cde: str = "DL",
    dest: str = "MCO",
    gate: str = "A10",
    pier: str = "47",
    dept_offset_min: int = 60,
    time_type: str = "S",
) -> dict:
    dt = NOW.replace(minute=0) + (NOW - NOW)  # NOW
    # build departure time
    from datetime import timedelta
    dt = NOW + timedelta(minutes=dept_offset_min)
    return {
        "al_cde": al_cde,
        "flt_num": flt_num,
        "leg_dest_ap_cde": dest,
        "dptr_gate": gate,
        "dptr_bag_pier_num": pier,
        "mission_time": _ms(dt),
        "time_type": time_type,
    }


SAMPLE_PAYLOAD = {
    "outbound": [
        # In-scope flights, varied piers + gates
        _flight(2051, dest="HOU", gate="A01", pier="48", dept_offset_min=60),
        _flight(376, dest="PNS", gate="A07", pier="43", dept_offset_min=80),
        _flight(956, dest="DEN", gate="A17", pier="43", dept_offset_min=170, time_type="E"),
        _flight(1335, dest="AUS", gate="T01A", pier="71", dept_offset_min=50),
        _flight(2213, dest="LEX", gate="T06", pier="59", dept_offset_min=95),
        # Out-of-scope: gate B04 should be filtered out
        _flight(787, dest="GEG", gate="B04", pier="44", dept_offset_min=60),
        # Out-of-scope: gate A30 (above A18) should be filtered out
        _flight(2650, dest="RIC", gate="A30", pier="53", dept_offset_min=60),
        # Past flight: should be filtered out
        _flight(9999, dest="JFK", gate="A12", pier="74", dept_offset_min=-30),
        # Missing pier: should be filtered out by `_parse_flight`
        {"al_cde": "DL", "flt_num": 111, "leg_dest_ap_cde": "BOS",
         "dptr_gate": "A05", "dptr_bag_pier_num": None,
         "mission_time": _ms(NOW), "time_type": "S"},
    ]
}


def _cfg() -> Config:
    # Don't depend on a .env file in tests
    return Config(
        slack_bot_token="",
        slack_channel="#test",
        fleet_api_base="https://example.invalid",
        airport="ATL",
        hours_forward=4,
        in_scope_gates=("T", "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08",
                        "A09", "A10", "A11", "A12", "A13", "A14", "A15", "A16",
                        "A17", "A18"),
        haulout_lead_min=55,
        display_tz="America/New_York",
    )


def test_filters_to_in_scope_and_future() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    flight_numbers = {f.flight_number for f in flights}
    assert flight_numbers == {"DL2051", "DL376", "DL956", "DL1335", "DL2213"}


def test_t_concourse_prefix_matches() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    t_flights = [f for f in flights if f.gate.startswith("T")]
    assert {f.gate for f in t_flights} == {"T01A", "T06"}


def test_message_groups_by_pier_and_includes_required_fields() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    msg = build_message(flights, cfg=cfg, now_utc=NOW, total_outbound_count=len(SAMPLE_PAYLOAD["outbound"]))

    # Header
    assert ":airplane:" in msg
    assert "ATL Pier View" in msg

    # Pier groupings present
    assert ":bag: *Pier 43*" in msg
    assert ":bag: *Pier 48*" in msg
    assert ":bag: *Pier 59*" in msg
    assert ":bag: *Pier 71*" in msg

    # Pier 43 (lowest numeric) should appear before Pier 48
    assert msg.index("Pier 43") < msg.index("Pier 48") < msg.index("Pier 59") < msg.index("Pier 71")

    # Each flight line contains haulout/dept/flight#/destination/gate
    assert "DL2051" in msg and "HOU" in msg and "Gate A01" in msg
    assert "DL1335" in msg and "AUS" in msg and "Gate T01A" in msg
    assert "haulout" in msg and "dept" in msg

    # Estimated-time flag for DL956
    assert ":warning:" in msg


def test_empty_payload_renders_friendly_message() -> None:
    cfg = _cfg()
    msg = build_message([], cfg=cfg, now_utc=NOW, total_outbound_count=0)
    assert "No upcoming in-scope outbound flights" in msg


def test_haulout_is_55_minutes_before_departure() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    # DL2051 departs at NOW + 60 min = 20:00 UTC = 4:00 PM EDT
    # Haulout should be 55 min earlier = 19:05 UTC = 3:05 PM EDT
    msg = build_message(flights, cfg=cfg, now_utc=NOW)
    assert "3:05 PM haulout / 4:00 PM dept" in msg
