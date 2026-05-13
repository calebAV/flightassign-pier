"""Fleet API client.

Wraps the AeroVect ``GET /flights`` endpoint. We deliberately only consume the
fields we actually need for the pier view; everything else is passed through.

See the API spec shared by Abdul Rahman Dabbour:
https://aerovect.slack.com/archives/D0AMU5093GR/p1774968192116289
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import requests

from .config import CONFIG, Config


@dataclass(frozen=True)
class Flight:
    """Normalized in-scope outbound flight."""

    flight_number: str          # e.g. "DL2051"
    destination: str            # e.g. "HOU"
    gate: str                   # e.g. "A01"
    pier: str                   # e.g. "48"
    departure_utc: datetime     # tz-aware UTC
    time_type: str              # "A" actual / "E" estimated / "S" scheduled
    raw: dict                   # full upstream record, for debugging

    @property
    def departure_sort_key(self) -> float:
        return self.departure_utc.timestamp()


# --------------------------------------------------------------------------- #
# HTTP

def fetch_outbound(cfg: Config = CONFIG, *, timeout: float = 20.0) -> dict:
    """Hit ``GET /flights`` for outbound flights only.

    Returns the raw decoded JSON. Raises requests.HTTPError on non-2xx.
    """
    url = f"{cfg.fleet_api_base}/flights"
    params = {
        "airport": cfg.airport,
        "mission_type": "OUTBOUND",
        "hours_forward": cfg.hours_forward,
        "require_bag_pier": "true",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------- #
# Normalization

def _parse_flight(record: dict) -> Optional[Flight]:
    """Convert one Fleet API flight dict into a Flight, or None if unusable."""
    flt_num = record.get("flt_num")
    al_cde = record.get("al_cde")
    dest = record.get("leg_dest_ap_cde")
    gate = record.get("dptr_gate")
    pier = record.get("dptr_bag_pier_num")
    mission_time_ms = record.get("mission_time")

    if flt_num is None or not al_cde or not dest or not gate or not pier or mission_time_ms is None:
        return None

    try:
        dt = datetime.fromtimestamp(int(mission_time_ms) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None

    return Flight(
        flight_number=f"{al_cde}{flt_num}",
        destination=str(dest).strip().upper(),
        gate=str(gate).strip().upper(),
        pier=str(pier).strip(),
        departure_utc=dt,
        time_type=str(record.get("time_type", "S")),
        raw=record,
    )


def _in_scope(flight: Flight, cfg: Config) -> bool:
    return cfg.gate_is_in_scope(flight.gate)


def list_in_scope_outbound(
    cfg: Config = CONFIG,
    *,
    now_utc: Optional[datetime] = None,
    api_payload: Optional[dict] = None,
) -> List[Flight]:
    """Return in-scope outbound flights, sorted by departure time.

    - Drops flights without a departure pier or gate
    - Drops flights whose departure is already in the past (relative to ``now_utc``)
    - Filters gates to the configured in-scope set

    Parameters
    ----------
    api_payload
        If provided, use this payload instead of calling the API. Useful for
        tests and dry runs against fixture data.
    """
    payload = api_payload if api_payload is not None else fetch_outbound(cfg)
    flights: List[Flight] = []
    now_utc = now_utc or datetime.now(timezone.utc)

    for record in payload.get("outbound", []) or []:
        flight = _parse_flight(record)
        if flight is None:
            continue
        if flight.departure_utc < now_utc:
            continue
        if not _in_scope(flight, cfg):
            continue
        flights.append(flight)

    flights.sort(key=lambda f: f.departure_sort_key)
    return flights


# --------------------------------------------------------------------------- #
# Helpers for downstream consumers

def total_outbound(payload: dict) -> int:
    return len(payload.get("outbound", []) or [])


def group_by_pier(flights: Iterable[Flight]) -> dict[str, List[Flight]]:
    """Group flights by their pier string. Returns a dict keyed by pier."""
    out: dict[str, List[Flight]] = {}
    for f in flights:
        out.setdefault(f.pier, []).append(f)
    for pier in out:
        out[pier].sort(key=lambda f: f.departure_sort_key)
    return out
