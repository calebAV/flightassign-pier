# FlightAssign-Pier Handoff

Owner of record going forward: **Servet Bayimli** (<servet@aerovect.com>).
Built and handed off by Caleb Adams, week of 2026-05-26.

---

## What this tool does, in two lines

Pulls live outbound flights from the AeroVect Fleet API every 20 minutes and posts a Slack message to `#flight-assign-piers`, grouped by pier (numerically), showing only **actionable** flights at **T or A gates** with **piers 40–60**.

This is the pier-side companion to the original FlightAssign tool (which groups by operator and posts to `#flight-assign`). The two are independent — different repos, different post channels.

---

## Where the pieces live

| Component | Location | Owner | What it does |
| --- | --- | --- | --- |
| Source code | `github.com/<servet-username>/flightassign-pier` | Servet | The Python app. |
| Schedule | cron-job.org account | Servet's cron-job.org login | Triggers the workflow every 20 min. |
| Workflow runner | GitHub Actions | GitHub (free) | Runs the script on each trigger. |
| Slack app | https://api.slack.com/apps → "FlightAssign Bot" | Servet (owner) | Posts to Slack. Same app as original FlightAssign. |
| Slack channel | `#flight-assign-piers` (`C0B3G4F2YP7`) | Servet (channel manager) | Where the post lands. |
| Data source | `https://beta.api.fleet.aerovect.com/flights?airport=ATL` | AeroVect eng (JT, Abdul, Carter) | Flight data. |

Nothing else. No DB, no other infra.

---

## Credentials inventory

You need access to four things to fully manage this system:

1. **GitHub** (`<servet-username>`) — repo owner.
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
| Look further ahead | `HOURS_FORWARD` | e.g., `6` |
| Change the channel | `SLACK_CHANNEL` (secret, not variable) | new channel ID |

Changes take effect on the next 20-minute trigger — no redeploy needed.

---

## How to make code changes

Only needed for behavior changes the env vars can't handle (e.g., new message format, new filter logic).

```bash
git clone https://github.com/<servet-username>/flightassign-pier.git
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

The original FlightAssign tool (operator-grouped, posts to `#flight-assign`) is separate — Caleb ran that on his machine through Cowork. When his access ended, that tool stopped. If Ops wants it revived, it'll need similar productionization (port to GitHub Actions, same pattern as this repo).

---

## Closing the loop on Caleb's access

After Caleb's last day, audit these to make sure nothing's still tied to him:

- [ ] GitHub repo owner is `<servet-username>`, not `calebAV`
- [ ] cron-job.org job is in Servet's account; Caleb's job is deleted/disabled
- [ ] Slack app's owner list does NOT include Caleb (`api.slack.com/apps` → FlightAssign Bot → Collaborators)
- [ ] Slack channel `#flight-assign-piers` has Servet as manager
- [ ] `SLACK_BOT_TOKEN` was rotated AFTER Caleb's last day (best practice — the previous token leaks via him)
- [ ] If repo was ever cloned to Caleb's laptop, his local copy doesn't matter (the source of truth is GitHub), but worth confirming no shared secrets in any `.env` file he might have

---

*Last updated: 2026-05-26 by Caleb Adams. Ping him on Slack with questions while he's still around.*
