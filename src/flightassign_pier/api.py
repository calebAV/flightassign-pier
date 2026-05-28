"""Fleet API client.

Wraps the AeroVect ``GET /flights`` endpoint. We deliberately only consume the
fields we actually need for the pier view; everything else is passed through.

See the API spec shared by Abdul Rahman Dabbour:
https://aerovect.slack.com/archives/D0AMU5093GR/p1774968192116289
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

import requests

from .config import CONFIG, Config


@dataclass(frozen=True)
class Flight:
    flight_number: str
    destination: str
    gate: str
    pier: str
    departure_utc: datetime
    time_type: str
    raw: dict

    @property
    def departure_sort_key(self) -> float:
        return self.departure_utc.timestamp()

    def haulout_utc(self, lead_min: int) -> datetime:
        return self.departure_utc - timedelta(minutes=lead_min)


def fetch_outbound(cfg: Config = CONFIG, *, timeout: float = 20.0) -> dict:
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


def _parse_flight(record: dict) -> Optional[Flight]:
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


def list_in_scope_outbound(
    cfg: Config = CONFIG,
    *,
    now_utc: Optional[datetime] = None,
    haulout_end_utc: Optional[datetime] = None,
    api_payload: Optional[dict] = None,
) -> List[Flight]:
    """Return in-scope, actionable outbound flights sorted by departure time.

    Filters applied (in order):
      - Drops flights missing required fields (pier, gate, dept time, etc.)
      - Drops flights whose gate is not in the configured in-scope set
      - Drops flights whose pier is not in [pier_min, pier_max]
      - Drops non-actionable flights (haulout already passed)
      - If ``haulout_end_utc`` is set, drops flights whose haulout is after that
        cutoff. Caller provides this to bound the list to end-of-shift.
    """
    payload = api_payload if api_payload is not None else fetch_outbound(cfg)
    flights: List[Flight] = []
    now_utc = now_utc or datetime.now(timezone.utc)

    for record in payload.get("outbound", []) or []:
        flight = _parse_flight(record)
        if flight is None:
            continue
        if not cfg.gate_is_in_scope(flight.gate):
            continue
        if not cfg.pier_is_in_scope(flight.pier):
            continue
        haulout = flight.haulout_utc(cfg.haulout_lead_min)
        if haulout < now_utc:
            continue
        if haulout_end_utc is not None and haulout > haulout_end_utc:
            continue
        flights.append(flight)

    flights.sort(key=lambda f: f.departure_sort_key)
    return flights


def total_outbound(payload: dict) -> int:
    return len(payload.get("outbound", []) or [])


def group_by_pier(flights: Iterable[Flight]) -> dict[str, List[Flight]]:
    out: dict[str, List[Flight]] = {}
    for f in flights:
        out.setdefault(f.pier, []).append(f)
    for pier in out:
        out[pier].sort(key=lambda f: f.departure_sort_key)
    return out
