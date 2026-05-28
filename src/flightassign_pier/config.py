"""Environment-driven configuration.

Empty-string env vars are treated as unset. This matters because GitHub Actions
passes ``${{ vars.X }}`` as an empty string when X isn't defined, which would
otherwise override our Python-side defaults with ``""``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _csv(name: str, default: str) -> Tuple[str, ...]:
    raw = _env(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_pier_ranges(
    raw_ranges: str,
    fallback_min: int,
    fallback_max: int,
) -> Tuple[Tuple[int, int], ...]:
    """Parse a ``PIER_RANGES`` string like ``"40-60,75-85"`` into tuples.

    If ``raw_ranges`` is empty, fall back to a single range built from
    ``fallback_min`` and ``fallback_max`` (legacy PIER_MIN/PIER_MAX behavior).
    Malformed entries are skipped silently — never crash the post over config.
    """
    ranges: list[tuple[int, int]] = []
    if raw_ranges and raw_ranges.strip():
        for part in raw_ranges.split(","):
            part = part.strip()
            if not part or "-" not in part:
                continue
            try:
                lo_s, hi_s = part.split("-", 1)
                lo, hi = int(lo_s.strip()), int(hi_s.strip())
                if lo <= hi:
                    ranges.append((lo, hi))
            except ValueError:
                continue
    if not ranges:
        ranges = [(fallback_min, fallback_max)]
    return tuple(ranges)


def _hour_label(hour: int) -> str:
    period = "AM" if hour < 12 else "PM"
    h12 = 12 if hour % 12 == 0 else hour % 12
    return f"{h12}:00 {period}"


@dataclass(frozen=True)
class ShiftWindow:
    name: str
    start_hour: int
    end_hour: int
    haulout_end_utc: datetime

    @property
    def label(self) -> str:
        return f"{_hour_label(self.start_hour)} – {_hour_label(self.end_hour)}"


@dataclass(frozen=True)
class Config:
    slack_bot_token: str = field(default_factory=lambda: _env("SLACK_BOT_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: _env("SLACK_CHANNEL", "#flight-assign-piers"))

    fleet_api_base: str = field(
        default_factory=lambda: _env("FLEET_API_BASE", "https://beta.api.fleet.aerovect.com").rstrip("/")
    )
    airport: str = field(default_factory=lambda: _env("AIRPORT", "ATL").upper())
    hours_forward: int = field(default_factory=lambda: _env_int("HOURS_FORWARD", 12))

    in_scope_gates: Tuple[str, ...] = field(
        default_factory=lambda: _csv("IN_SCOPE_GATES", "T,A")
    )

    # Pier scope. Prefer PIER_RANGES (multi-range) when set; otherwise fall back to
    # PIER_MIN/PIER_MAX (single contiguous range). Both are tunable as repo variables.
    pier_ranges: Tuple[Tuple[int, int], ...] = field(
        default_factory=lambda: _parse_pier_ranges(
            _env("PIER_RANGES", ""),
            _env_int("PIER_MIN", 40),
            _env_int("PIER_MAX", 60),
        )
    )

    haulout_lead_min: int = field(default_factory=lambda: _env_int("HAULOUT_LEAD_MIN", 55))
    display_tz: str = field(default_factory=lambda: _env("DISPLAY_TZ", "America/New_York"))

    shift1_worked_start_hour: int = field(default_factory=lambda: _env_int("SHIFT1_WORKED_START_HOUR", 5))
    shift1_worked_end_hour: int = field(default_factory=lambda: _env_int("SHIFT1_WORKED_END_HOUR", 14))
    shift1_msg_start_hour: int = field(default_factory=lambda: _env_int("SHIFT1_MSG_START_HOUR", 4))

    shift2_worked_start_hour: int = field(default_factory=lambda: _env_int("SHIFT2_WORKED_START_HOUR", 14))
    shift2_worked_end_hour: int = field(default_factory=lambda: _env_int("SHIFT2_WORKED_END_HOUR", 22))
    shift2_msg_start_hour: int = field(default_factory=lambda: _env_int("SHIFT2_MSG_START_HOUR", 13))
    shift2_msg_end_hour: int = field(default_factory=lambda: _env_int("SHIFT2_MSG_END_HOUR", 21))

    def gate_is_in_scope(self, gate: str | None) -> bool:
        if not gate:
            return False
        g = gate.strip().upper()
        for token in self.in_scope_gates:
            t = token.strip().upper()
            if not t:
                continue
            if len(t) == 1 and t.isalpha():
                if g.startswith(t):
                    return True
            else:
                if g == t:
                    return True
        return False

    def pier_is_in_scope(self, pier: str | None) -> bool:
        """Return True if `pier` is a numeric string within any configured range."""
        if not pier:
            return False
        try:
            n = int(str(pier).strip())
        except ValueError:
            return False
        return any(lo <= n <= hi for lo, hi in self.pier_ranges)

    @property
    def pier_min(self) -> int:
        """Backwards-compat: the lowest pier in any configured range."""
        return min(lo for lo, _ in self.pier_ranges)

    @property
    def pier_max(self) -> int:
        """Backwards-compat: the highest pier in any configured range."""
        return max(hi for _, hi in self.pier_ranges)

    def current_shift(self, now_utc: datetime) -> Optional[ShiftWindow]:
        tz = ZoneInfo(self.display_tz)
        local = now_utc.astimezone(tz)
        hour_decimal = local.hour + local.minute / 60.0

        def cutoff_at(hour: int) -> datetime:
            return local.replace(hour=hour, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        if self.shift1_msg_start_hour <= hour_decimal < self.shift2_msg_start_hour:
            return ShiftWindow(
                name="Shift 1",
                start_hour=self.shift1_worked_start_hour,
                end_hour=self.shift1_worked_end_hour,
                haulout_end_utc=cutoff_at(self.shift1_worked_end_hour),
            )
        if self.shift2_msg_start_hour <= hour_decimal < self.shift2_msg_end_hour:
            return ShiftWindow(
                name="Shift 2",
                start_hour=self.shift2_worked_start_hour,
                end_hour=self.shift2_worked_end_hour,
                haulout_end_utc=cutoff_at(self.shift2_worked_end_hour),
            )
        return None


CONFIG = Config()
