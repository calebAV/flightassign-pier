# Making code changes to flightassign-pier

A practical guide for Servet (or anyone managing this repo who isn't a full-time developer). Covers setting up your Mac the first time, making changes, testing them, and pushing safely. Plan for ~30 minutes the first time you set up; subsequent edits take 5–15 minutes each.

If you ever feel stuck, the troubleshooting section at the bottom covers the most common failure modes. Worst case, you can always undo a change — git history is preserved forever.

---

## When to make a code change vs. just changing a repo variable

**Most adjustments don't require a code change at all.** Before opening Terminal, check whether the change you want is just an env-var tweak:

- Pier range, gate list, haulout lead time, shift hours, channel ID → change a **repo variable** (`https://github.com/servetAV/flightassign-pier/settings/variables/actions`). No code, no clone, no push.
- See HANDOFF.md "How to make common Ops changes" for the full list.

**Code changes are needed for:**
- Changing the wording or structure of the Slack message
- Adding a new field to flight lines (e.g., showing the aircraft type)
- Changing how flights are sorted or filtered
- Adding a brand-new feature
- Fixing a bug
- Editing the README or other docs

If your change is in the second list, keep reading.

---

## One-time setup on your Mac

You'll need four tools installed. If you already have Homebrew, this is fast.

### 1. Install Homebrew (if you don't have it)

Open Terminal (Applications → Utilities → Terminal, or `⌘ + Space` and type "Terminal"). Paste:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes, follow the "Next steps" instructions it prints — usually two `eval` lines you paste to add Homebrew to your shell.

Verify with:

```bash
brew --version
```

### 2. Install Git, Python, and the GitHub CLI

```bash
brew install git python@3.11 gh
```

Verify each:

```bash
git --version          # should be 2.40+
python3 --version      # should be 3.10 or higher
gh --version           # the GitHub CLI
```

### 3. Sign in to GitHub from Terminal

This step is what lets you push code without typing a password every time.

```bash
gh auth login
```

Answer the prompts:
- **What account?** → GitHub.com
- **Preferred protocol?** → HTTPS
- **Authenticate Git?** → Yes
- **How to authenticate?** → Login with a web browser

It'll show you an 8-character code. Press Enter, your browser opens to https://github.com/login/device, paste the code, and approve. Terminal will say "Authentication complete."

You'll only have to do this once on this Mac.

### 4. Install a code editor (recommended: VS Code)

Don't use TextEdit — it doesn't understand code formatting. Two solid free options:

- **Visual Studio Code:** https://code.visualstudio.com/ — most popular, lots of extensions
- **Cursor:** https://cursor.sh/ — fork of VS Code with AI built in, also free

Either one works fine. Download, install, drag the app to Applications.

### 5. Clone the repo

In Terminal:

```bash
cd ~/Documents
git clone https://github.com/servetAV/flightassign-pier.git
cd flightassign-pier
```

You should now see all the files. `ls` will list them.

### 6. Set up a Python virtual environment

This isolates this project's dependencies from any other Python you might have. Run these once in the repo folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

The `(.venv)` prefix will appear in your prompt. To deactivate later, type `deactivate`. Next time you come back, just run `source .venv/bin/activate` again.

You're now set up.

---

## Making a change — the standard workflow

Every time you want to make an edit, follow these six steps. Most of them are one-line commands.

### Step 1 — Pull the latest code

Always start by pulling the latest from GitHub. This catches any changes made by anyone else (or by you on another machine).

```bash
cd ~/Documents/flightassign-pier
git pull
```

If it says "Already up to date," you're current.

### Step 2 — Open the project in your editor

```bash
code .        # if you installed VS Code
# OR
cursor .      # if you installed Cursor
```

(The `.` means "this folder.")

### Step 3 — Make your edit

Common files you might edit:

| What you want to change | File to edit |
| --- | --- |
| Slack message wording or layout | `src/flightassign_pier/format.py` |
| What flights are included (gate/pier logic) | `src/flightassign_pier/api.py` |
| Shift definitions or new config options | `src/flightassign_pier/config.py` |
| The README or HANDOFF docs | `README.md` or `HANDOFF.md` |
| Workflow / cron behavior | `.github/workflows/post.yml` |

Save the file when done (`⌘+S`).

### Step 4 — Test locally before pushing

This is the most important step. Always test before pushing — if you push something broken, the next cron tick will fail in production.

**Quick smoke test (dry run, no Slack post):**

```bash
source .venv/bin/activate    # if you're not already in the venv
python -m flightassign_pier --dry-run
```

This fetches live Fleet API data and prints the formatted message to your Terminal — same data the production cron would post, but nothing actually sent to Slack. Verify the output looks right.

Note: this will print "(no post — outside shift message window)" if you're testing outside 4am-12:40pm or 1pm-8:40pm Eastern. That's correct behavior.

**Run the test suite:**

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

You should see "15 passed" (or however many tests we have at the time). If any test fails, fix it before pushing.

### Step 5 — Commit and push

Once your change looks right:

```bash
git add .                                       # stage all your changes
git status                                      # double-check what's about to be committed
git commit -m "Brief description of the change"
git push
```

The commit message should be short but clear. Examples:
- "Add aircraft type to flight lines"
- "Change pier sort to alphabetical"
- "Fix typo in README"

### Step 6 — Verify in production

GitHub Actions will pick up your push automatically on the next cron tick (within 20 minutes), but you can verify immediately:

1. Go to https://github.com/servetAV/flightassign-pier/actions
2. Click "Post pier view to Slack"
3. Click "Run workflow" → leave dry_run on `false` → Run
4. Wait 30 seconds, refresh, click into the run, expand the steps
5. Check `#flight-assign-piers` in Slack — the post should look as expected

If the action shows green and Slack looks right, you're done.

---

## Common changes — examples

### Change the wording of the post header

Open `src/flightassign_pier/format.py`. Find the line starting with `f":airplane: *{cfg.airport} Pier View — ..."`. Edit the words around the airport name and shift label.

### Show aircraft tail number on each flight line

Edit `src/flightassign_pier/api.py` — the `Flight` dataclass already accepts the raw API record. The Fleet API returns `ac_reg_num` (aircraft registration number). You'd:
1. Add `ac_reg_num: str` to the `Flight` dataclass
2. Extract it in `_parse_flight`
3. Reference it in `format.py`'s `_format_flight_line`

### Change a default that's also a repo variable

If you change a default in `config.py` (e.g., `pier_min: int = field(default_factory=lambda: _env_int("PIER_MIN", 40))` → change `40` to `45`), remember: any existing repo variable still overrides it. Either remove the repo variable or update both.

### Fix a typo in the README

Just edit `README.md` and push. No tests needed for doc-only changes.

---

## Troubleshooting

### "Permission denied" when pushing

```
fatal: unable to access 'https://github.com/servetAV/flightassign-pier.git/': The requested URL returned error: 403
```

Your GitHub auth has expired or was revoked. Run `gh auth login` again.

### "Your branch is behind" on push

Someone (probably you on another machine) pushed changes you don't have locally. Run:

```bash
git pull --rebase
git push
```

If the rebase has conflicts, open the conflicted files in your editor — you'll see `<<<<<<<` markers. Edit to resolve, then:

```bash
git add .
git rebase --continue
git push
```

### Tests fail after your change

Read the failure output — pytest tells you which test broke and why. The test might be telling you you accidentally broke an existing behavior. Either fix your code OR update the test to reflect the new intended behavior (if the change is intentional).

### Action fails in GitHub after a push

Go to the Actions tab, click the failed run, expand the failed step. Common causes:
- Python syntax error in your change → run `python -m flightassign_pier --dry-run` locally to catch
- A missing import → check the failure message
- Test failed in CI but passed locally → make sure you didn't push uncommitted local changes (`git status` should be empty)

### How to undo a bad push

Two options:

**Option A — Revert the bad commit (preserves history, recommended):**

```bash
git revert HEAD       # creates a new commit that undoes the last one
git push
```

**Option B — Hard reset and force-push (rewrites history, only do this within minutes of the bad push):**

```bash
git reset --hard HEAD~1
git push --force
```

If anyone else might have pulled the bad commit, use Option A. If you just pushed and nobody's pulled it yet, Option B is cleaner.

---

## Things to never do

- **Don't commit `.env`.** It contains the Slack bot token. If you ever create a `.env` for local testing, make sure it stays uncommitted. The `.gitignore` should already protect this, but double-check `git status` before committing.
- **Don't hardcode secrets in code.** Tokens, passwords, API keys — always go through env vars / repo secrets.
- **Don't `git push --force` to main without thinking.** It rewrites history that others may have pulled. Only do this for fresh mistakes within the last few minutes.
- **Don't delete files from `.github/workflows/` without understanding what they do.** That's where the post-to-Slack workflow lives.

---

## Getting help

If you're stuck:

1. Read the failure message carefully — most errors tell you exactly what's wrong.
2. Check HANDOFF.md's troubleshooting section.
3. Search the error message on Google or ChatGPT — for general git/Python issues this is faster than asking a human.

---

*This guide is intentionally tactical — it doesn't try to teach Python or git from scratch, just gives you the muscle memory for making changes to this specific repo. If you find yourself needing to do something not covered here, open an issue or just experiment in a side branch.*
