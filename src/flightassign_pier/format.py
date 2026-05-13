"""Pier-grouped Slack message formatter.

The output is plain mrkdwn text suitable for ``chat.postMessage``'s ``text`` field.
We don't use Block Kit here — for an at-a-glance pier roster the compact bullet
style reads better on mobile and matches the existing FlightAssign aesthetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from .api import Flight, group_by_pier
from .config import CONFIG, Config


def _fmt_clock(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    # Strip leading zero from hour, lowercase am/pm to "AM"/"PM"
    return local.strftime("%-I:%M %p")


def _fmt_header_date(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    # e.g. "Tue 5/13"
    return local.strftime("%a %-m/%-d")


def _fmt_header_time(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%-I:%M %p %Z")


def _pier_sort_key(pier: str) -> tuple[int, str]:
    """Numeric piers first (ascending), then anything non-numeric alphabetically."""
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
) -> str:
    """Return a Slack-formatted message grouped by pier."""
    cfg = cfg or CONFIG
    tz = ZoneInfo(cfg.display_tz)
    now_utc = now_utc or datetime.now(timezone.utc)

    flight_list: List[Flight] = sorted(flights, key=lambda f: f.departure_sort_key)
    grouped = group_by_pier(flight_list)

    lines: List[str] = []
    lines.append(
        f":airplane: *{cfg.airport} Pier View* — {_fmt_header_date(now_utc, tz)}, "
        f"{_fmt_header_time(now_utc, tz)}"
    )
    lines.append("")

    if not flight_list:
        lines.append("_No upcoming in-scope outbound flights with a pier assignment._")
    else:
        for pier in sorted(grouped.keys(), key=_pier_sort_key):
            lines.append(f":bag: *Pier {pier}*")
            for flight in grouped[pier]:
                lines.append(_format_flight_line(flight, cfg, tz))
            lines.append("")
        # Drop trailing empty line
        if lines[-1] == "":
            lines.pop()

    lines.append("")
    summary = (
        f"_{len(flight_list)} flights across {len(grouped)} piers"
        f" | refresh every 20 min_"
    )
    if total_outbound_count is not None:
        summary = (
            f"_{len(flight_list)} flights across {len(grouped)} piers"
            f" | Fleet API: {total_outbound_count} outbound flights total"
            f" | refresh every 20 min_"
        )
    lines.append(summary)
    return "\n".join(lines)
