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
except ImportError:  # pragma: no cover - optional in deployed envs
    pass


def _env(name: str, default: str) -> str:
    """Return os.environ[name], or default if missing OR empty string."""
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


def _hour_label(hour: int) -> str:
    """Convert 24-hour int to '5:00 AM' / '2:00 PM' style label."""
    period = "AM" if hour < 12 else "PM"
    h12 = 12 if hour % 12 == 0 else hour % 12
    return f"{h12}:00 {period}"


@dataclass(frozen=True)
class ShiftWindow:
    """Active shift context: which shift, what haulout window to show."""
    name: str                       # "Shift 1"
    start_hour: int                 # 5 = 5am (the worked-shift start, for label only)
    end_hour: int                   # 14 = 2pm (the worked-shift end)
    haulout_end_utc: datetime       # absolute cutoff for haulout time in this post

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
    # Look 12 hours ahead so a 4am Shift 1 post can see haulouts through 2pm.
    hours_forward: int = field(default_factory=lambda: _env_int("HOURS_FORWARD", 12))

    in_scope_gates: Tuple[str, ...] = field(
        default_factory=lambda: _csv("IN_SCOPE_GATES", "T,A")
    )

    pier_min: int = field(default_factory=lambda: _env_int("PIER_MIN", 40))
    pier_max: int = field(default_factory=lambda: _env_int("PIER_MAX", 60))

    haulout_lead_min: int = field(default_factory=lambda: _env_int("HAULOUT_LEAD_MIN", 55))
    display_tz: str = field(default_factory=lambda: _env("DISPLAY_TZ", "America/New_York"))

    # Shift configuration (hours in 24-hour local time, per DISPLAY_TZ).
    # Defaults match the ATL Ops GM's spec:
    #   Shift 1: worked 5am-2pm; messages fire 4am-12:40pm; haulouts shown through 2pm.
    #   Shift 2: worked 2pm-10pm; messages fire 1pm-8:40pm; haulouts shown through 10pm.
    # Outside these message windows the script exits without posting.
    shift1_worked_start_hour: int = field(default_factory=lambda: _env_int("SHIFT1_WORKED_START_HOUR", 5))
    shift1_worked_end_hour: int = field(default_factory=lambda: _env_int("SHIFT1_WORKED_END_HOUR", 14))
    shift1_msg_start_hour: int = field(default_factory=lambda: _env_int("SHIFT1_MSG_START_HOUR", 4))
    # Shift 1 messages end when Shift 2 messages start (no overlap, no gap)

    shift2_worked_start_hour: int = field(default_factory=lambda: _env_int("SHIFT2_WORKED_START_HOUR", 14))
    shift2_worked_end_hour: int = field(default_factory=lambda: _env_int("SHIFT2_WORKED_END_HOUR", 22))
    shift2_msg_start_hour: int = field(default_factory=lambda: _env_int("SHIFT2_MSG_START_HOUR", 13))
    # Last shift-2 message fires 1 hour before shift 2 ends by default (= 9pm). To
    # keep posting right up to 10pm, set this to shift2_worked_end_hour.
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
        if not pier:
            return False
        try:
            n = int(str(pier).strip())
        except ValueError:
            return False
        return self.pier_min <= n <= self.pier_max

    def current_shift(self, now_utc: datetime) -> Optional[ShiftWindow]:
        """Return ShiftWindow for the message-firing window we're currently in.

        Returns None if outside both message windows (e.g., 9pm-4am).
        """
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
