# flightassign-pier

A lightweight companion to [FlightAssign](https://aerovect.slack.com/archives/C0AQEA7NR28) that pulls live outbound flights from the AeroVect Fleet API and posts a Slack message **grouped by pier** (instead of by operator).

The post is intended to give pier-side teams a quick read on what bags are coming, which gate they're heading to, and when haulout should start — refreshed every 20 minutes.

---

## What it shows

For each pier (sorted numerically), the bot lists every upcoming in-scope outbound flight with:

- **Haulout time** — 55 minutes before scheduled departure
- **Departure time**
- **Flight number** (e.g., `DL2051`)
- **Destination** (3-letter airport code)
- **Gate** (departure gate the bags need to reach)

Example Slack post:

```
:airplane: ATL Pier View — Tue 5/13, 3:12 PM EDT

:bag: Pier 43
  • 3:40 PM haulout / 4:35 PM dept — DL376 → PNS | Gate A07
  • 4:55 PM haulout / 5:50 PM dept — DL956 → DEN | Gate A17

:bag: Pier 48
  • 3:46 PM haulout / 4:41 PM dept — DL2051 → HOU | Gate A01
  ...
```

In-scope gates match the existing FlightAssign tool: **T concourse + A01–A18**. Flights without a departure pier are omitted.

---

## How it runs

There are two supported run modes:

1. **GitHub Actions (recommended)** — a cron workflow runs `python -m flightassign_pier` every 20 minutes (`*/20 * * * *`). No server to manage.
2. **Local / one-shot** — `python -m flightassign_pier` posts a single message and exits. Use this for testing.
3. **Long-running loop** — `python -m flightassign_pier --loop` re-posts every 20 minutes in-process until interrupted. Useful if you'd rather host this on a small VM.

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/calebAV/flightassign-pier.git
cd flightassign-pier
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

To push this initial commit:

```bash
cd flightassign-pier
git init
git add .
git commit -m "Initial commit: pier-grouped FlightAssign"
git branch -M main
git remote add origin https://github.com/calebAV/flightassign-pier.git
git push -u origin main
```

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in:

| Var | What it is |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot token for the FlightAssign Bot Slack app (starts with `xoxb-`) |
| `SLACK_CHANNEL` | Channel to post to. Default: `#flight-assign-piers`. Make sure the bot is invited to the channel. |
| `FLEET_API_BASE` | Defaults to `https://beta.api.fleet.aerovect.com`. Override if/when prod-equivalent endpoint is preferred. |
| `AIRPORT` | Defaults to `ATL`. |
| `HOURS_FORWARD` | How far ahead to look. Defaults to `4` (matches Fleet API default). |
| `IN_SCOPE_GATES` | Comma-separated. Defaults to `T,A01,A02,A03,A04,A05,A06,A07,A08,A09,A10,A11,A12,A13,A14,A15,A16,A17,A18`. `T` is a prefix match (covers `T01`, `T01A`, `T02`, ...). |
| `HAULOUT_LEAD_MIN` | Defaults to `55`. |

For GitHub Actions, set these as **repository secrets** under Settings → Secrets and variables → Actions.

### 3. Run it once locally

```bash
python -m flightassign_pier --dry-run     # prints to stdout, doesn't post
python -m flightassign_pier               # posts a single message to Slack
```

### 4. Schedule via GitHub Actions

The included workflow at `.github/workflows/post.yml` runs every 20 minutes automatically and exposes a manual `workflow_dispatch` button. Just push the repo and add the secrets above.

---

## Design notes

- **Pier vs. gate**: piers are bag rooms; gates are where the aircraft is parked. One pier may feed many gates and one gate may pull bags from different piers throughout the day. Grouping by pier is the natural unit for pier-side operators.
- **55-minute haulout lead**: confirmed default. Tunable via `HAULOUT_LEAD_MIN` env var if Ops wants to A/B test.
- **No assignment logic**: this tool deliberately does *not* assign flights to people. It's a read-only schedule view. The operator-assignment side stays in the original FlightAssign repo.
- **Stateless**: each run is independent. No DB, no state file. The cron schedule is the only "memory."

---

## Repo layout

```
flightassign-pier/
├── src/flightassign_pier/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── api.py             # Fleet API client + filtering
│   ├── format.py          # Pier-grouped Slack message builder
│   ├── post.py            # Slack post + scheduling
│   └── config.py          # Env-driven config
├── tests/
│   └── test_format.py
├── .github/workflows/post.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```
