# Discord Verification Readiness

This branch completes the repository-side verification hardening for pkla dog.

## Implemented

- repeated-DM `/pingdeaf` implementation removed
- legacy Poke ingest/`POKE_INGEST_URL` removed
- public `/terms`, `/privacy`, and `/support` pages
- `/support` slash command and GitHub report path
- `/delete-data` removes all in-memory user chat/consent data
- SQLite conversation persistence removed from the application
- shared/universal memory and automatic memory extraction removed
- browser listen-in defaults off and requires explicit consent from every current human participant plus visible start/stop notifications
- legacy `!` command handling removed in favor of slash commands
- Message Content Intent disabled
- Server Members Intent disabled

## Developer Portal

Use these URLs after Railway deploys the merged `main` branch:

- Terms: https://pkladog.up.railway.app/terms
- Privacy: https://pkladog.up.railway.app/privacy

Then complete Team Owner Identity Verification in Discord's Developer Portal and confirm all verification qualifications are green.

No repository change can complete Discord's identity-verification step for the Team owner.
