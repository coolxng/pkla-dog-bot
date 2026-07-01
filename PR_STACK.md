# PR stack for pkla-dog-bot improvements

Five independent branches are ready in `/Users/rishi/Documents/grok/pkla-dog-bot`.
Merge in this order to reduce conflicts.

## 1. `pr/owner-id-ci-cleanup`

**Title:** Fix OWNER_ID for !deletedms and add lint to CI

**Summary:**
- `!deletedms` now respects `OWNER_ID` instead of the hardcoded default
- Adds `requirements-dev.txt` with Ruff + mypy
- CI runs lint and type checks
- Removes stale `ENABLE_TRANSCRIPTION` / Piper TTS from `.env.example`
- Fixes pre-existing Ruff issues and mypy annotations

```bash
git push -u origin pr/owner-id-ci-cleanup
gh pr create --base main --head pr/owner-id-ci-cleanup \
  --title "Fix OWNER_ID for !deletedms and add lint to CI" \
  --body "See CHANGELOG Unreleased. Quick wins: owner bugfix, CI lint, env cleanup."
```

## 2. `pr/extract-say-template`

**Title:** Extract /say dashboard into templates/say.html

**Summary:**
- Moves ~1000 lines of inline HTML out of `bot.py`
- No behavior change; uses `render_template("say.html")`

```bash
git push -u origin pr/extract-say-template
gh pr create --base main --head pr/extract-say-template \
  --title "Extract /say dashboard into templates/say.html" \
  --body "Reduces bot.py by ~1000 lines. Easier to edit the /say UI."
```

## 3. `pr/health-gunicorn-logging`

**Title:** Add /health endpoint, structured logging, and gevent WSGI

**Summary:**
- `GET /health` returns Discord readiness, uptime, relay state
- `LOG_LEVEL` configures structured logging
- Replaces Flask dev server with gevent WSGI + WebSocket support by default
- Adds gevent, gevent-websocket, gunicorn deps

```bash
git push -u origin pr/health-gunicorn-logging
gh pr create --base main --head pr/health-gunicorn-logging \
  --title "Add /health endpoint, structured logging, and gevent WSGI" \
  --body "Production web server + observability. Set USE_PRODUCTION_WEB_SERVER=false for local dev."
```

## 4. `pr/sqlite-persistence`

**Title:** Add optional SQLite persistence for bot state

**Summary:**
- New `storage.py` persists universal memory + conversation history
- Opt in with `PERSIST_STATE=true` and `STATE_DB_PATH`
- Loads on startup; writes on updates and LRU eviction

```bash
git push -u origin pr/sqlite-persistence
gh pr create --base main --head pr/sqlite-persistence \
  --title "Add optional SQLite persistence for bot state" \
  --body "Survives restarts when enabled. Off by default for backward compatibility."
```

## 5. `pr/configurable-ping-members`

**Title:** Make ping member targets configurable via env

**Summary:**
- `PING_MEMBERS_JSON` maps trigger names to Discord user IDs
- Falls back to built-in defaults when unset/invalid

```bash
git push -u origin pr/configurable-ping-members
gh pr create --base main --head pr/configurable-ping-members \
  --title "Make ping member targets configurable via env" \
  --body "Fork-friendly ping config without editing bot.py."
```

## Push all branches

```bash
cd /Users/rishi/Documents/grok/pkla-dog-bot
git push -u origin pr/owner-id-ci-cleanup pr/extract-say-template pr/health-gunicorn-logging pr/sqlite-persistence pr/configurable-ping-members
```

## Notes

- Branches are based on `main` (6c9a7de) and are independent; later PRs may need a quick rebase after earlier merges.
- CI expects Python 3.11 (see `runtime.txt`). Local Python 3.9 cannot import `datetime.UTC` after Ruff's pyupgrade pass in PR1.
- After merging PR1, run `ruff check --fix .` locally if you touch imports on older branches.