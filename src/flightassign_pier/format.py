"""Pier-grouped Slack message formatter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from .api import Flight, group_by_pier
from .config import CONFIG, Config, ShiftWindow


def _fmt_clock(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%-I:%M %p")


def _fmt_header_date(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%a %-m/%-d")


def _fmt_header_time(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%-I:%M %p %Z")


def _pier_sort_key(pier: str) -> tuple[int, str]:
    try:
        return (0, f"{int(pier):05d}")
    except ValueError:
        return (1, pier.upper())


def _format_flight_line(flight: Flight, cfg: Config, tz: ZoneInfo) -> str:
    haulout = flight.departure_utc - timedelta(minutes=cfg.haulout_lead_min)
    flagged = " :warning:" if flight.time_type == "E" else ""
    return (
        f"  • {_fmt_clock(haulout, tz)} haulout / {_fmt_clock(flight.departure_utc, tz)} dept — "
        f"_{flight.flight_number}_ → {flight.destination} | Gate {flight.gate}{flagged}"
    )


def build_message(
    flights: Iterable[Flight],
    *,
    cfg: Config = CONFIG,
    now_utc: Optional[datetime] = None,
    total_outbound_count: Optional[int] = None,
    shift: Optional[ShiftWindow] = None,
) -> str:
    """Return a Slack-formatted message grouped by pier.

    If ``shift`` is provided, the header includes the shift name and label, and
    the summary line mentions the end-of-shift haulout cutoff.
    """
    cfg = cfg or CONFIG
    tz = ZoneInfo(cfg.display_tz)
    now_utc = now_utc or datetime.now(timezone.utc)

    flight_list: List[Flight] = sorted(flights, key=lambda f: f.departure_sort_key)
    grouped = group_by_pier(flight_list)

    lines: List[str] = []
    if shift is not None:
        lines.append(
            f":airplane: *{cfg.airport} Pier View — {shift.name} ({shift.label})* — "
            f"{_fmt_header_date(now_utc, tz)}, {_fmt_header_time(now_utc, tz)}"
        )
        shift_end_clock = _fmt_clock(shift.haulout_end_utc, tz)
        lines.append(f"_Showing flights with haulouts through {shift_end_clock} (end of shift)_")
    else:
        lines.append(
            f":airplane: *{cfg.airport} Pier View* — "
            f"{_fmt_header_date(now_utc, tz)}, {_fmt_header_time(now_utc, tz)}"
        )
    lines.append("")

    if not flight_list:
        lines.append("_No upcoming in-scope outbound flights with a pier assignment._")
    else:
        for pier in sorted(grouped.keys(), key=_pier_sort_key):
            lines.append(f"*Pier {pier}*")
            for flight in grouped[pier]:
                lines.append(_format_flight_line(flight, cfg, tz))
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    lines.append("")
    summary = f"_{len(flight_list)} flights across {len(grouped)} piers"
    if total_outbound_count is not None:
        summary += f" | Fleet API: {total_outbound_count} outbound flights total"
    summary += " | refresh every 20 min_"
    lines.append(summary)
    return "\n".join(lines)
