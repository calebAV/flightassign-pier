"""Environment-driven configuration.

Empty-string env vars are treated as unset. This matters because GitHub Actions
passes ``${{ vars.X }}`` as an empty string when X isn't defined, which would
otherwise override our Python-side defaults with ``""``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Tuple

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


@dataclass(frozen=True)
class Config:
    slack_bot_token: str = field(default_factory=lambda: _env("SLACK_BOT_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: _env("SLACK_CHANNEL", "#flight-assign-piers"))

    fleet_api_base: str = field(
        default_factory=lambda: _env("FLEET_API_BASE", "https://beta.api.fleet.aerovect.com").rstrip("/")
    )
    airport: str = field(default_factory=lambda: _env("AIRPORT", "ATL").upper())
    hours_forward: int = field(default_factory=lambda: _env_int("HOURS_FORWARD", 4))

    in_scope_gates: Tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "IN_SCOPE_GATES",
            "T,A01,A02,A03,A04,A05,A06,A07,A08,A09,A10,A11,A12,A13,A14,A15,A16,A17,A18",
        )
    )

    # Pier scope: only show flights whose departure bag pier number falls in
    # [pier_min, pier_max] inclusive. Flights with a non-numeric pier or a pier
    # outside this range are excluded.
    pier_min: int = field(default_factory=lambda: _env_int("PIER_MIN", 40))
    pier_max: int = field(default_factory=lambda: _env_int("PIER_MAX", 60))

    haulout_lead_min: int = field(default_factory=lambda: _env_int("HAULOUT_LEAD_MIN", 55))
    display_tz: str = field(default_factory=lambda: _env("DISPLAY_TZ", "America/New_York"))

    def gate_is_in_scope(self, gate: str | None) -> bool:
        """Return True if `gate` matches any token in `in_scope_gates`.

        A bare letter token (e.g. ``"T"``) is treated as a prefix match — useful for the
        T concourse which has gates like T01, T01A, T02, etc. Multi-character tokens
        (e.g. ``"A01"``) are exact matches.
        """
        if not gate:
            return False
        g = gate.strip().upper()
        for token in self.in_scope_gates:
            t = token.strip().upper()
            if not t:
                continue
            if len(t) == 1 and t.isalpha():
                # Prefix match for single-letter concourse tokens
                if g.startswith(t):
                    return True
            else:
                if g == t:
                    return True
        return False

    def pier_is_in_scope(self, pier: str | None) -> bool:
        """Return True if `pier` is a numeric string within [pier_min, pier_max]."""
        if not pier:
            return False
        try:
            n = int(str(pier).strip())
        except ValueError:
            return False
        return self.pier_min <= n <= self.pier_max


CONFIG = Config()
