"""Smoke + unit tests for the pier-grouped formatter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


# With haulout_lead_min = 55:
#   dept_offset >= 55  → haulout is at/after NOW → ACTIONABLE
#   dept_offset < 55   → haulout already passed → NOT actionable
SAMPLE_PAYLOAD = {
    "outbound": [
        # Actionable: pier in [40,60], in-scope gate, haulout in future
        _flight(2051, dest="HOU", gate="A01", pier="48", dept_offset_min=60),    # haulout +5 min
        _flight(376, dest="PNS", gate="A07", pier="43", dept_offset_min=80),     # haulout +25 min
        _flight(956, dest="DEN", gate="A17", pier="43", dept_offset_min=170, time_type="E"),
        _flight(2213, dest="LEX", gate="T06", pier="59", dept_offset_min=95),

        # Non-actionable: haulout already passed (dept in 50 min, haulout was 5 min ago)
        _flight(5555, dest="MCO", gate="A10", pier="47", dept_offset_min=50),

        # Non-actionable: haulout was 30 min ago (dept in 25 min)
        _flight(6666, dest="ORD", gate="A04", pier="55", dept_offset_min=25),

        # Out-of-range piers
        _flight(1335, dest="AUS", gate="T01A", pier="71", dept_offset_min=120),  # > 60
        _flight(537, dest="DCA", gate="A05", pier="39", dept_offset_min=120),    # < 40

        # Out-of-scope gates
        _flight(787, dest="GEG", gate="B04", pier="44", dept_offset_min=120),
        _flight(2650, dest="RIC", gate="A30", pier="53", dept_offset_min=120),

        # Already-departed (in the past)
        _flight(9999, dest="JFK", gate="A12", pier="48", dept_offset_min=-30),

        # Non-numeric pier "N/A"
        _flight(7777, dest="BOS", gate="A05", pier="N/A", dept_offset_min=120),

        # Missing pier
        {"al_cde": "DL", "flt_num": 111, "leg_dest_ap_cde": "BOS",
         "dptr_gate": "A05", "dptr_bag_pier_num": None,
         "mission_time": _ms(NOW), "time_type": "S"},
    ]
}


def _cfg(pier_min: int = 40, pier_max: int = 60, haulout_lead_min: int = 55) -> Config:
    return Config(
        slack_bot_token="",
        slack_channel="#test",
        fleet_api_base="https://example.invalid",
        airport="ATL",
        hours_forward=4,
        in_scope_gates=("T", "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08",
                        "A09", "A10", "A11", "A12", "A13", "A14", "A15", "A16",
                        "A17", "A18"),
        pier_min=pier_min,
        pier_max=pier_max,
        haulout_lead_min=haulout_lead_min,
        display_tz="America/New_York",
    )


def test_only_actionable_in_scope_flights_returned() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    flight_numbers = {f.flight_number for f in flights}
    assert flight_numbers == {"DL2051", "DL376", "DL956", "DL2213"}


def test_non_actionable_haulout_in_past_is_excluded() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    # DL5555 (dept +50min) → haulout was 5 min ago
    # DL6666 (dept +25min) → haulout was 30 min ago
    assert not any(f.flight_number in {"DL5555", "DL6666"} for f in flights)


def test_actionable_boundary_haulout_exactly_now_is_included() -> None:
    """A flight whose haulout == now should be included (cutoff is strict <)."""
    cfg = _cfg()
    payload = {"outbound": [
        # dept = NOW + 55 min → haulout exactly NOW
        _flight(8888, gate="A10", pier="47", dept_offset_min=55),
    ]}
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=payload)
    assert any(f.flight_number == "DL8888" for f in flights)


def test_pier_range_filter_excludes_high_and_low_piers() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    piers = {f.pier for f in flights}
    assert piers == {"43", "48", "59"}


def test_pier_range_filter_excludes_non_numeric_piers() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    assert not any(f.flight_number == "DL7777" for f in flights)


def test_pier_range_is_configurable() -> None:
    cfg = _cfg(pier_min=40, pier_max=80)
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    piers = {f.pier for f in flights}
    assert "71" in piers  # DL1335 (dept +120min) is now actionable AND in pier range


def test_message_groups_by_pier_with_required_fields() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    msg = build_message(flights, cfg=cfg, now_utc=NOW, total_outbound_count=len(SAMPLE_PAYLOAD["outbound"]))

    assert ":airplane:" in msg
    assert "ATL Pier View" in msg
    assert "*Pier 43*" in msg
    assert "*Pier 48*" in msg
    assert "*Pier 59*" in msg
    # Out-of-range piers must not appear
    assert "Pier 71" not in msg
    assert "Pier 39" not in msg
    # Non-actionable flights must not appear
    assert "DL5555" not in msg
    assert "DL6666" not in msg
    # Sort order
    assert msg.index("Pier 43") < msg.index("Pier 48") < msg.index("Pier 59")
    assert "DL2051" in msg and "HOU" in msg and "Gate A01" in msg
    assert ":warning:" in msg


def test_empty_payload_renders_friendly_message() -> None:
    cfg = _cfg()
    msg = build_message([], cfg=cfg, now_utc=NOW, total_outbound_count=0)
    assert "No upcoming in-scope outbound flights" in msg


def test_haulout_is_55_minutes_before_departure() -> None:
    cfg = _cfg()
    flights = list_in_scope_outbound(cfg, now_utc=NOW, api_payload=SAMPLE_PAYLOAD)
    msg = build_message(flights, cfg=cfg, now_utc=NOW)
    assert "3:05 PM haulout / 4:00 PM dept" in msg
