"""Unit tests for shift-window filtering and pier-grouped formatting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flightassign_pier.api import list_in_scope_outbound
from flightassign_pier.config import Config
from flightassign_pier.format import build_message


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


# Anchor times in UTC, chosen to fall inside specific local-time shift windows.
# America/New_York EDT = UTC-4 (May 2026 is daylight time).
SHIFT1_NOW = datetime(2026, 5, 27, 14, 0, 0, tzinfo=timezone.utc)   # 10:00 AM EDT, mid-Shift 1
SHIFT2_NOW = datetime(2026, 5, 27, 21, 0, 0, tzinfo=timezone.utc)   # 5:00 PM EDT, mid-Shift 2
OFF_NOW    = datetime(2026, 5, 28,  3, 0, 0, tzinfo=timezone.utc)   # 11:00 PM EDT, off-hours


def _flight(
    flt_num: int,
    al_cde: str = "DL",
    dest: str = "MCO",
    gate: str = "A10",
    pier: str = "47",
    dept_offset_min: int = 60,
    time_type: str = "S",
    anchor: datetime = SHIFT1_NOW,
) -> dict:
    dt = anchor + timedelta(minutes=dept_offset_min)
    return {
        "al_cde": al_cde,
        "flt_num": flt_num,
        "leg_dest_ap_cde": dest,
        "dptr_gate": gate,
        "dptr_bag_pier_num": pier,
        "mission_time": _ms(dt),
        "time_type": time_type,
    }


def _cfg() -> Config:
    return Config(
        slack_bot_token="",
        slack_channel="#test",
        fleet_api_base="https://example.invalid",
        airport="ATL",
        hours_forward=12,
        in_scope_gates=("T", "A"),
        pier_ranges=((40, 60),),
        haulout_lead_min=55,
        display_tz="America/New_York",
        shift1_worked_start_hour=5,
        shift1_worked_end_hour=14,
        shift1_msg_start_hour=4,
        shift2_worked_start_hour=14,
        shift2_worked_end_hour=22,
        shift2_msg_start_hour=13,
        shift2_msg_end_hour=21,
    )


# --------------------------------------------------------------------------- #
# Shift window detection

def test_shift1_window_detected_mid_morning() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT1_NOW)
    assert shift is not None
    assert shift.name == "Shift 1"
    assert shift.label == "5:00 AM – 2:00 PM"
    # Shift 1 haulout cutoff = 2pm EDT = 18:00 UTC same day
    assert shift.haulout_end_utc == datetime(2026, 5, 27, 18, 0, 0, tzinfo=timezone.utc)


def test_shift2_window_detected_afternoon() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT2_NOW)
    assert shift is not None
    assert shift.name == "Shift 2"
    assert shift.label == "2:00 PM – 10:00 PM"
    # Shift 2 haulout cutoff = 10pm EDT = 02:00 UTC next day
    assert shift.haulout_end_utc == datetime(2026, 5, 28, 2, 0, 0, tzinfo=timezone.utc)


def test_off_hours_returns_none() -> None:
    cfg = _cfg()
    assert cfg.current_shift(OFF_NOW) is None


def test_shift1_boundary_first_message_at_4am() -> None:
    cfg = _cfg()
    # 4:00 AM EDT = 08:00 UTC — first allowed Shift 1 message
    t = datetime(2026, 5, 27, 8, 0, 0, tzinfo=timezone.utc)
    assert cfg.current_shift(t).name == "Shift 1"


def test_shift_handoff_at_1pm() -> None:
    cfg = _cfg()
    # 12:59 PM EDT = 16:59 UTC — still Shift 1
    just_before = datetime(2026, 5, 27, 16, 59, 0, tzinfo=timezone.utc)
    assert cfg.current_shift(just_before).name == "Shift 1"
    # 1:00 PM EDT = 17:00 UTC — Shift 2 begins
    at_handoff = datetime(2026, 5, 27, 17, 0, 0, tzinfo=timezone.utc)
    assert cfg.current_shift(at_handoff).name == "Shift 2"


def test_shift2_msg_window_ends_at_9pm() -> None:
    cfg = _cfg()
    # 8:59 PM EDT = 00:59 UTC next day — last Shift 2 message
    just_before = datetime(2026, 5, 28, 0, 59, 0, tzinfo=timezone.utc)
    assert cfg.current_shift(just_before).name == "Shift 2"
    # 9:00 PM EDT = 01:00 UTC next day — windows closed
    at_close = datetime(2026, 5, 28, 1, 0, 0, tzinfo=timezone.utc)
    assert cfg.current_shift(at_close) is None


# --------------------------------------------------------------------------- #
# Haulout-end cap (end-of-shift filter)

def _payload_with_mixed_haulouts(anchor: datetime) -> dict:
    """Flights spread across the rest of a 10-hour Shift 1 day."""
    return {"outbound": [
        # Haulout +5 min (in shift) → actionable
        _flight(2051, gate="A01", pier="48", dept_offset_min=60, anchor=anchor),
        # Haulout +1h (in shift)
        _flight(376, gate="A07", pier="43", dept_offset_min=115, anchor=anchor),
        # Haulout in 4h (still in shift if it's 10am)
        _flight(956, gate="A17", pier="43", dept_offset_min=240, anchor=anchor),
        # Haulout at 1:55pm → in shift (just before 2pm cutoff)
        _flight(1111, gate="A05", pier="50", dept_offset_min=290, anchor=anchor),
        # Departure 4pm → haulout 3:05pm → OUTSIDE shift (after 2pm cutoff)
        _flight(2222, gate="A10", pier="51", dept_offset_min=360, anchor=anchor),
        # Departure 9pm → haulout 8:05pm → OUTSIDE shift 1
        _flight(3333, gate="A12", pier="52", dept_offset_min=660, anchor=anchor),
    ]}


def test_shift1_drops_flights_past_haulout_cutoff() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT1_NOW)
    payload = _payload_with_mixed_haulouts(SHIFT1_NOW)
    flights = list_in_scope_outbound(
        cfg,
        now_utc=SHIFT1_NOW,
        haulout_end_utc=shift.haulout_end_utc,
        api_payload=payload,
    )
    nums = {f.flight_number for f in flights}
    assert "DL2051" in nums
    assert "DL376" in nums
    assert "DL956" in nums
    assert "DL2222" not in nums   # haulout after 2pm
    assert "DL3333" not in nums   # haulout 8pm


def test_no_haulout_cap_keeps_everything_actionable() -> None:
    cfg = _cfg()
    payload = _payload_with_mixed_haulouts(SHIFT1_NOW)
    flights = list_in_scope_outbound(cfg, now_utc=SHIFT1_NOW, api_payload=payload)
    nums = {f.flight_number for f in flights}
    # Without a cap, every actionable in-scope flight is kept
    assert "DL2222" in nums and "DL3333" in nums


# --------------------------------------------------------------------------- #
# Formatter — header reflects shift

def test_header_includes_shift_name_and_label() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT1_NOW)
    msg = build_message([], cfg=cfg, now_utc=SHIFT1_NOW, shift=shift)
    assert "Shift 1 (5:00 AM – 2:00 PM)" in msg
    assert "haulouts through 2:00 PM" in msg


def test_header_for_shift2() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT2_NOW)
    msg = build_message([], cfg=cfg, now_utc=SHIFT2_NOW, shift=shift)
    assert "Shift 2 (2:00 PM – 10:00 PM)" in msg
    assert "haulouts through 10:00 PM" in msg


def test_header_without_shift_omits_shift_label() -> None:
    cfg = _cfg()
    msg = build_message([], cfg=cfg, now_utc=SHIFT1_NOW)
    assert "Shift 1" not in msg
    assert "Shift 2" not in msg


# --------------------------------------------------------------------------- #
# Pier filtering + grouping (carried over)

def test_pier_grouping_and_sort() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT1_NOW)
    payload = _payload_with_mixed_haulouts(SHIFT1_NOW)
    flights = list_in_scope_outbound(
        cfg, now_utc=SHIFT1_NOW, haulout_end_utc=shift.haulout_end_utc, api_payload=payload
    )
    msg = build_message(flights, cfg=cfg, now_utc=SHIFT1_NOW, shift=shift)
    assert "*Pier 43*" in msg
    assert "*Pier 48*" in msg
    assert "*Pier 50*" in msg
    # Numeric sort
    assert msg.index("Pier 43") < msg.index("Pier 48") < msg.index("Pier 50")


def test_empty_flight_list_in_shift_renders_friendly_message() -> None:
    cfg = _cfg()
    shift = cfg.current_shift(SHIFT1_NOW)
    msg = build_message([], cfg=cfg, now_utc=SHIFT1_NOW, shift=shift)
    assert "No upcoming in-scope outbound flights" in msg


# --------------------------------------------------------------------------- #
# PIER_RANGES (multi-range support)

def test_multi_range_pier_filter_includes_both_ranges() -> None:
    """A two-range config (40-60 + 75-85) should include flights in either range."""
    from flightassign_pier.config import Config
    cfg = Config(
        slack_bot_token="",
        slack_channel="#test",
        fleet_api_base="https://example.invalid",
        airport="ATL",
        hours_forward=12,
        in_scope_gates=("T", "A", "C"),  # imagined C concourse online
        pier_ranges=((40, 60), (75, 85)),
        haulout_lead_min=55,
        display_tz="America/New_York",
        shift1_worked_start_hour=5,
        shift1_worked_end_hour=14,
        shift1_msg_start_hour=4,
        shift2_worked_start_hour=14,
        shift2_worked_end_hour=22,
        shift2_msg_start_hour=13,
        shift2_msg_end_hour=21,
    )
    assert cfg.pier_is_in_scope("48") is True   # in first range
    assert cfg.pier_is_in_scope("80") is True   # in second range
    assert cfg.pier_is_in_scope("65") is False  # gap between ranges
    assert cfg.pier_is_in_scope("90") is False  # past second range


def test_pier_min_max_properties_reflect_outer_bounds() -> None:
    """pier_min/pier_max should be the outer envelope of all configured ranges."""
    from flightassign_pier.config import Config
    cfg = Config(
        slack_bot_token="",
        slack_channel="#test",
        fleet_api_base="https://example.invalid",
        airport="ATL",
        hours_forward=12,
        in_scope_gates=("T", "A"),
        pier_ranges=((40, 60), (75, 85)),
        haulout_lead_min=55,
        display_tz="America/New_York",
        shift1_worked_start_hour=5,
        shift1_worked_end_hour=14,
        shift1_msg_start_hour=4,
        shift2_worked_start_hour=14,
        shift2_worked_end_hour=22,
        shift2_msg_start_hour=13,
        shift2_msg_end_hour=21,
    )
    assert cfg.pier_min == 40
    assert cfg.pier_max == 85
