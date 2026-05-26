# flightassign-pier

A lightweight companion to [FlightAssign](https://aerovect.slack.com/archives/C0AQEA7NR28) that pulls live outbound flights from the AeroVect Fleet API and posts a Slack message **grouped by pier** (instead of by operator).

The post is intended to give pier-side teams a quick read on what bags are coming, which gate they're heading to, and when haulout should start — refreshed every 20 minutes by cron-job.org.

---

## What it shows

For each pier (sorted numerically), the bot lists every upcoming actionable outbound flight with:

- **Haulout time** — 55 minutes before scheduled departure
- **Departure time**
- **Flight number** (e.g., `DL2051`)
- **Destination** (3-letter airport code)
- **Gate** (departure gate the bags need to reach)

Example Slack post:

```
:airplane: ATL Pier View — Tue 5/13, 3:12 PM EDT

*Pier 43*
  • 3:25 PM haulout / 4:20 PM dept — DL376 → PNS | Gate A07
  • 4:55 PM haulout / 5:50 PM dept — DL956 → DEN | Gate A17 ⚠

*Pier 48*
  • 3:05 PM haulout / 4:00 PM dept — DL2051 → HOU | Gate A01

*Pier 49*
  • 3:35 PM haulout / 4:30 PM dept — DL1522 → CMH | Gate A25
...
```

A `⚠` next to a flight means the departure time is estimated (not yet confirmed).

---

## Scope

Three filters control what makes it into a post:

| Filter | Default | Notes |
| --- | --- | --- |
| Concourses | `T` + all `A` gates | Picks up the entire A concourse (A-south + A-north) plus the T concourse. Excludes B/C/D/E/F. |
| Pier range | `40`–`60` (inclusive) | Numeric pier numbers only. Flights with `"N/A"` or no pier are excluded. |
| Actionable only | yes | Drops any flight whose haulout time (dept − 55 min) has already passed. |

All three are tunable via env vars — see [Configuration](#configuration) below.

---

## How it runs

GitHub Actions handles the workflow; cron-job.org handles the schedule. The flow:

1. **cron-job.org** fires a POST every 20 minutes to GitHub's `workflow_dispatch` API.
2. **GitHub Actions** spins up an Ubuntu runner, installs deps, runs `python -m flightassign_pier`.
3. The script fetches flights, filters, formats, and posts to Slack.

cron-job.org is used instead of GitHub's built-in `schedule:` cron because GitHub's scheduler can drift 0–15 minutes per run. cron-job.org fires on the dot.

For local development you can also run it directly:

```bash
python -m flightassign_pier --dry-run    # print to stdout, don't post
python -m flightassign_pier              # post once to Slack
python -m flightassign_pier --loop       # post every 20 min in-process
```

---

## Setup

### 1. Clone & install locally (optional, for testing)

```bash
git clone https://github.com/calebAV/flightassign-pier.git
cd flightassign-pier
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Copy `.env.example` to `.env` and fill in `SLACK_BOT_TOKEN` to test locally.

### 2. Slack — create a channel and invite the bot

1. In Slack, create the channel (`flight-assign-piers` or whatever name you prefer).
2. Run `/invite @FlightAssign Bot` in the channel.
3. Grab the channel ID from the channel URL: `https://aerovect.slack.com/archives/<CHANNEL_ID>`.

### 3. GitHub — set secrets

In Settings → Secrets and variables → Actions, add two secrets:

| Name | Value |
| --- | --- |
| `SLACK_BOT_TOKEN` | `xoxb-...` token from the FlightAssign Bot app |
| `SLACK_CHANNEL` | The channel ID (e.g., `C0B3G4F2YP7`). IDs are preferred over `#names`. |

The other env vars have working defaults — only override if you need to.

### 4. cron-job.org — schedule the trigger

1. Create a fine-grained GitHub PAT scoped to this repo, with **Actions: Read and write** permission.
2. In cron-job.org, create a job with:
   - **URL:** `https://api.github.com/repos/calebAV/flightassign-pier/actions/workflows/post.yml/dispatches`
   - **Method:** `POST`
   - **Headers:**
     - `Authorization: Bearer <your-PAT>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
   - **Body:** `{"ref": "main"}`
   - **Schedule:** every 20 minutes
3. Run it once manually to confirm — cron-job.org should show `204 No Content` and a new run should appear in GitHub Actions.

---

## Configuration

All settings are env-var driven. For GitHub Actions, set these as **repository variables** (Settings → Secrets and variables → Actions → Variables). For local dev, set them in `.env`.

| Var | Default | What it does |
| --- | --- | --- |
| `SLACK_BOT_TOKEN` | — | Required. `xoxb-...` token. |
| `SLACK_CHANNEL` | `#flight-assign-piers` | Channel ID or `#name`. |
| `FLEET_API_BASE` | `https://beta.api.fleet.aerovect.com` | Fleet API base URL. |
| `AIRPORT` | `ATL` | Airport code. |
| `HOURS_FORWARD` | `4` | How far ahead the API pulls. |
| `IN_SCOPE_GATES` | `T,A` | Comma-separated. Single-letter tokens are prefix matches (T → T01, T01A...; A → A01...A30). Multi-character tokens are exact matches (e.g., `A01`). |
| `PIER_MIN` | `40` | Lower bound (inclusive). |
| `PIER_MAX` | `60` | Upper bound (inclusive). |
| `HAULOUT_LEAD_MIN` | `55` | Minutes before departure that haulout starts. |
| `DISPLAY_TZ` | `America/New_York` | IANA timezone for displayed times. |

Empty-string env vars are treated as unset — defaults always kick in. (This matters because GitHub Actions passes `${{ vars.X }}` as `""` when X isn't defined.)

### Adjusting scope without code changes

Common Ops adjustments are repo-variable overrides, no commit needed:

- **Narrow piers (e.g., during a single pier-zone test):** set `PIER_MIN`/`PIER_MAX` to a tighter range.
- **Exclude A-international (A26–A30):** set `IN_SCOPE_GATES` to an explicit list like `T,A01,A02,A03,A04,A05,A06,A07,A08,A09,A10,A11,A12,A13,A14,A15,A16,A17,A18,A19,A20,A21,A22,A23,A24,A25`.
- **Different haulout lead time:** override `HAULOUT_LEAD_MIN`.

---

## Design notes

- **Pier vs. gate:** piers are bag rooms; gates are where the aircraft is parked. One pier may feed many gates and one gate may pull bags from different piers throughout the day. Grouping by pier is the natural unit for pier-side operators.
- **Pier range as primary scope:** the gate filter is intentionally loose (any T or A gate). The pier range (40–60) is what actually defines "which flights are ours." This is why A-north gates are included automatically — they hit our piers.
- **Actionable-only:** every post drops flights whose haulout has already passed. Over the 20-min cycle, old flights naturally fall off — no manual cleanup or "next-shift" logic needed.
- **No assignment logic:** this tool deliberately does *not* assign flights to people. It's a read-only schedule view. The operator-assignment side stays in the original FlightAssign repo.
- **Stateless:** each run is independent. No DB, no state file.

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
│   └── test_format.py     # 11 unit tests
├── .github/workflows/post.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Running the tests

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

Tests cover the gate/pier/actionable filters, message formatting, and boundary cases.
