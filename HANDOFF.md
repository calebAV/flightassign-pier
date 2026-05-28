# FlightAssign-Pier Handoff

Owner of record going forward: **Servet Bayimli** (<servet@aerovect.com>).
Built and handed off by Caleb Adams, week of 2026-05-26.

---

## What this tool does, in two lines

Pulls live outbound flights from the AeroVect Fleet API every 20 minutes and posts a Slack message to `#flight-assign-piers`, grouped by pier (numerically), showing every actionable flight at **T or A gates** with **piers 40–60** between **now and the end of the current shift**.

This is the pier-side companion to the original FlightAssign tool (which groups by operator and posts to `#flight-assign`). The two are independent — different repos, different post channels.

## Shift windows

Posts only fire during these local-time (America/New_York) windows. Outside them, the workflow runs but no Slack message is sent.

| Shift | Worked hours | Posts fire | Haulouts shown through |
| --- | --- | --- | --- |
| Shift 1 | 5:00 AM – 2:00 PM | 4:00 AM – 12:40 PM | 2:00 PM |
| Shift 2 | 2:00 PM – 10:00 PM | 1:00 PM – 8:40 PM | 10:00 PM |
| Off-hours | — | No posts | — |

To adjust shift timing (Ops change, new shift schedule, daylight savings handling, etc.), update the `SHIFT*_*_HOUR` repo variables — no code change needed.

---

## Where the pieces live

| Component | Location | Owner | What it does |
| --- | --- | --- | --- |
| Source code | `github.com/servetAV/flightassign-pier` | Servet | The Python app. |
| Schedule | cron-job.org account | Servet's cron-job.org login | Triggers the workflow every 20 min. |
| Workflow runner | GitHub Actions | GitHub (free) | Runs the script on each trigger. |
| Slack app | https://api.slack.com/apps → "FlightAssign Bot" | Servet (owner) | Posts to Slack. Same app as original FlightAssign. |
| Slack channel | `#flight-assign-piers` (`C0B3G4F2YP7`) | Servet (channel manager) | Where the post lands. |
| Data source | `https://beta.api.fleet.aerovect.com/flights?airport=ATL` | AeroVect eng (JT, Abdul, Carter) | Flight data. |

Nothing else. No DB, no other infra.

---

## Credentials inventory

You need access to four things to fully manage this system:

1. **GitHub** (`servetAV`) — repo owner.
2. **cron-job.org** account — schedules the trigger.
3. **Slack app management** — for the FlightAssign Bot app, at https://api.slack.com/apps. You should be listed as an Owner (not just Collaborator).
4. **Slack channel** — `#flight-assign-piers`, you should be a channel manager.

GitHub stores two things tied to your account:

- **Repository secrets** (Settings → Secrets and variables → Actions → Secrets):
  - `SLACK_BOT_TOKEN` — `xoxb-...` from the FlightAssign Bot app's OAuth & Permissions page
  - `SLACK_CHANNEL` — `C0B3G4F2YP7` (the channel ID, not the #name)
- **Personal Access Token (PAT)** — created in your GitHub account, used by cron-job.org to trigger the workflow. Fine-grained, scoped to `flightassign-pier` only, with **Actions: Read and write**.

If the PAT ever needs to rotate, see "Rotating the PAT" below.

---

## How to make common Ops changes

Most adjustments are repo-variable overrides — no code change, no commit, no deploy. Go to repo Settings → Secrets and variables → Actions → **Variables** tab → New repository variable.

| What you want to do | Variable to set | Value |
| --- | --- | --- |
| Narrow piers (e.g., test single pier zone) | `PIER_MIN`, `PIER_MAX` | e.g., `43`, `50` |
| Expand piers (e.g., add more bag rooms) | `PIER_MAX` | e.g., `80` |
| Restrict gates (e.g., exclude A-international) | `IN_SCOPE_GATES` | `T,A01,A02,...,A25` (explicit list) |
| Change haulout lead time | `HAULOUT_LEAD_MIN` | e.g., `45` |
| Look further ahead | `HOURS_FORWARD` | e.g., `16` |
| Change the channel | `SLACK_CHANNEL` (secret, not variable) | new channel ID |
| Move Shift 1 start/end (changes the haulout cutoff too) | `SHIFT1_WORKED_START_HOUR`, `SHIFT1_WORKED_END_HOUR` | 24h local time, e.g., `6`, `15` |
| Move Shift 2 start/end | `SHIFT2_WORKED_START_HOUR`, `SHIFT2_WORKED_END_HOUR` | e.g., `15`, `23` |
| Start Shift 1 messages earlier/later than 4am | `SHIFT1_MSG_START_HOUR` | e.g., `3` |
| Keep Shift 2 messages firing through 10pm (not stopping at 9pm) | `SHIFT2_MSG_END_HOUR` | `22` |

Changes take effect on the next 20-minute trigger — no redeploy needed.

---

## How to make code changes

Only needed for behavior changes the env vars can't handle (e.g., new message format, new filter logic).

```bash
git clone https://github.com/servetAV/flightassign-pier.git
cd flightassign-pier
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

# Optional: test locally with .env (copy from .env.example, fill in the Slack token).
python -m flightassign_pier --dry-run    # prints to stdout, doesn't post
```

Make changes, run tests:

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

Commit, push to `main`. Next cron-job.org trigger picks it up automatically.

---

## Troubleshooting — "Posts stopped, what do I check?"

In order of likelihood:

1. **cron-job.org didn't fire.** Log into cron-job.org → check the job's execution log. If it's red/disabled, re-enable. If 401, the PAT expired (rotate it).
2. **GitHub Action failed.** Repo → Actions tab → find the most recent failed run → expand the failed step. Common failures:
   - `Slack post failed: not_in_channel` → bot got kicked from `#flight-assign-piers`. Re-invite: `/invite @FlightAssign Bot`.
   - `Slack post failed: invalid_auth` → bot token rotated or revoked. Get a new `xoxb-...` from the Slack app and update the `SLACK_BOT_TOKEN` secret.
   - Fleet API 5xx → AeroVect side. Ping JT in `#ask-engineering`. Tool will self-recover on the next cycle.
3. **Posting but data looks wrong.** The Fleet API beta stack has known accuracy gaps. The original heads-up is in [Abdul's DM thread](https://aerovect.slack.com/archives/D0AMU5093GR/p1774968192116289). For persistent issues, ping JT or Abdul.

For ad-hoc testing without waiting for the cron:

- Repo → Actions tab → "Post pier view to Slack" → "Run workflow" → optionally flip `dry_run` to `true` (renders to logs only, doesn't post).

---

## Rotating the PAT

The PAT cron-job.org uses to trigger workflows expires (1 year default, or sooner if you set a shorter window). Steps to rotate:

1. Go to https://github.com/settings/personal-access-tokens
2. Either click your existing token → Regenerate, or create a new fine-grained token with: Repository = `flightassign-pier`, Permissions → Actions: Read and write.
3. Copy the new token (`github_pat_...`).
4. In cron-job.org, edit the job → Advanced → Headers → update the `Authorization: Bearer <token>` header.
5. Click "Run now" to test. cron-job.org should return `204 No Content` and a new run should appear in GitHub Actions.

Worth setting up cron-job.org email alerts so you know if the trigger starts failing silently.

---

## Who to ping for what

| Issue | Person | Channel |
| --- | --- | --- |
| Fleet API down or wrong data | JT, Abdul | `#ask-engineering` or DM |
| Slack channel/app permissions | Whoever's the Slack workspace admin | `#it-support` |
| Cron-job.org account | You (Servet) own it | self-serve |
| GitHub repo / Actions | You (Servet) own it | self-serve |

The original FlightAssign tool (operator-grouped, posts to `#flight-assign`) is separate. Caleb ran that on his machine through Cowork, and it stopped posting when his AeroVect access ended on 2026-05-29. The channel is dark. If Ops wants it revived, it needs the same productionization as this repo (port to GitHub Actions + cron-job.org). Use this repo as the template.

---

## Closing the loop on Caleb's access

Note: this repo lives on a GitHub account that was renamed from `calebAV` to `servetAV`. The account is now Servet's — Caleb handed over the login credentials and no longer has access. Audit these on or after Caleb's last day:

- [ ] Account password has been changed by Servet (so Caleb can no longer log in)
- [ ] 2FA has been enabled on the GitHub account by Servet (account did not have 2FA pre-handoff — make sure it's on now)
- [ ] GitHub recovery codes have been regenerated by Servet
- [ ] The primary email on the account is Servet's (Settings → Emails → primary)
- [ ] `caleb@aerovect.com` is removed from the account's email list entirely
- [ ] Slack app's owner list does NOT include Caleb (`api.slack.com/apps` → FlightAssign Bot → Collaborators)
- [ ] Slack channel `#flight-assign-piers` has Servet as manager and Caleb is removed
- [ ] `SLACK_BOT_TOKEN` was rotated AFTER Caleb's last day (the previous token leaks via him)
- [ ] cron-job.org account password has been changed by Servet
- [ ] The PAT used by cron-job.org was rotated AFTER Caleb's last day
- [ ] If repo was cloned to Caleb's laptop, no shared secrets remain in any local `.env` file

---

---

## Adding a new concourse (B, C, D, E, F, etc.)

When AeroVect Ops onboards a new concourse, you'll need to expand the gate and pier scopes. **No code change required** — it's all repo variable overrides. Steps:

### 1. Confirm the new gate + pier ranges with Ops

Before touching anything, get two pieces of info from the Ops GM (or by checking the Fleet API directly):

- **Gate identifier(s):** typically a single letter (`B`, `C`, etc.) but sometimes specific gates (`B01`, `B02`).
- **Pier number range that feeds the new concourse:** check by looking at Fleet API responses for outbound flights at the new gates — the `dptr_bag_pier_num` field tells you which piers.

### 2. Decide whether to use a single range or multiple

Two cases:

**Case A — Adjacent piers.** If B concourse uses piers 61–70 (right next to A's 40–60), you can just widen the existing range. Set `PIER_MAX=70` and add `B` to `IN_SCOPE_GATES`. Done.

**Case B — Non-adjacent piers.** If, say, C concourse uses piers 75–85 with no flights at piers 61–74, you do NOT want to widen `PIER_MAX` to 85 (you'd start showing irrelevant flights from piers 61–74). Use the multi-range variable instead.

### 3. Set the repo variables

Go to `https://github.com/servetAV/flightassign-pier/settings/variables/actions` and update:

| Variable | Case A (adjacent) | Case B (non-adjacent) |
| --- | --- | --- |
| `IN_SCOPE_GATES` | `T,A,B` | `T,A,C` |
| `PIER_MAX` | `70` | leave at 60 |
| `PIER_RANGES` | leave unset | `40-60,75-85` |

Reminder: `PIER_RANGES` overrides `PIER_MIN`/`PIER_MAX` if set. Format is comma-separated `start-end` pairs.

### 4. Smoke-test

Repo → Actions → "Post pier view to Slack" → "Run workflow" → set `dry_run` to `true` → Run.

Open the log. Confirm:
- The new gate prefix (B/C/etc.) appears in the rendered output
- New piers show up grouped correctly
- No "garbage" piers from outside the desired range have snuck in

If the dry-run looks right, run again with `dry_run=false` to post live. From there, cron-job.org takes over.

### 5. Reverse the change (if needed)

If Ops decides to pause the expansion (e.g., during a soft launch), just remove the new gate letter from `IN_SCOPE_GATES` and either reset `PIER_MAX` or clear `PIER_RANGES`. Changes take effect on the next 20-minute cron tick.

### Things this *doesn't* require

- **No code change, no commit, no PR, no deploy.** Everything is env-driven.
- **No restart.** GitHub Actions reads repo variables fresh on each workflow run.
- **No coordination with engineering.** Fleet API already returns all gates and piers; you're just choosing which subset to display.

If a new concourse ever requires *behavior* changes (different haulout lead times per concourse, separate Slack channels per concourse, etc.), that would be a code change. Ping a developer or use this repo as a starting point.

---

*Last updated: 2026-05-28 by Caleb Adams (final handoff pass).*
