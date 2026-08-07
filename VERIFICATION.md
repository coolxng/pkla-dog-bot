# Discord Verification Checklist for pkla dog

This document tracks the repository-side work needed to prepare pkla dog for Discord App Verification.

## What this branch fixes

- Adds a public Terms of Service document.
- Adds a public Privacy Policy.
- Adds a support/privacy-request path.
- Serves the legal documents from the deployed bot at `/terms`, `/privacy`, and `/support`.
- Changes the default production start command to `python verification_entry.py`.
- Disables the legacy external Discord-message ingest path in the public deployment.
- Disables browser voice listen-in in the public deployment.
- Disables persistent SQLite conversation storage in the public deployment.
- Disables automatic memory extraction in the public deployment.
- Keeps existing secrets outside source control through environment variables.

## Manual steps after this PR is merged

### 1. Redeploy the bot

The repository `Procfile` now starts:

```text
python verification_entry.py
```

If Railway has a manually configured start-command override, change that override to the same command or remove the override so the `Procfile` is used.

After deployment, confirm these pages load publicly over HTTPS:

```text
https://<your-domain>/terms
https://<your-domain>/privacy
https://<your-domain>/support
```

The root `/health` route can be used to confirm the Discord client is connected.

### 2. Add the policy URLs in the Discord Developer Portal

In the Discord Developer Portal for the pkla dog application, set:

**Terms of Service URL**

```text
https://<your-domain>/terms
```

**Privacy Policy URL**

```text
https://<your-domain>/privacy
```

If the deployment domain is temporarily unavailable, the repository documents are also public after merge:

```text
https://github.com/coolxng/pkla-dog-bot/blob/main/TERMS.md
https://github.com/coolxng/pkla-dog-bot/blob/main/PRIVACY.md
```

The deployed HTTPS pages are preferable because they are clean, stable application URLs.

### 3. Complete Team Owner Identity Verification

The remaining Developer Portal qualification shown as **Team owner must complete Identity Verification** cannot be completed through repository code. The owner of the Discord Developer Team must complete Discord's identity-verification flow in the Developer Portal.

### 4. Confirm the verification qualifications are green

After the policy URLs are saved and identity verification is complete, re-open the Verification page and confirm all listed qualifications are green.



Do not re-enable the old repeated-DM implementation for the public bot. Discord's Developer Policy requires explicit permission before an application contacts users, and repeated unsolicited DMs create a clear policy risk.

## Privileged intents

The existing bot currently uses **Message Content Intent** and **Server Members Intent**. These are separate from the basic App Verification qualification checklist.

Discord changed privileged-intent review requirements in June 2026. Apps reaching Discord's current review threshold for privileged data access must separately justify and maintain approval for those intents.

Before requesting privileged-intent approval at scale, consider migrating text commands to slash commands and reducing member/message access to only what is necessary for the Bot's stated functionality.

## Do not enable these features in the verified deployment without another review

The verification entrypoint intentionally disables:

- `PERSIST_STATE`
- `AUTO_MEMORY_ENABLED`
- `ENABLE_LISTEN_IN`

If any of these are reintroduced for a public deployment, review Discord's current Developer Terms and Developer Policy again and update the Privacy Policy to match the actual data flow before enabling them.

## Official Discord references

- Developer Policy: https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy
- Developer Terms of Service: https://support-dev.discord.com/hc/en-us/articles/8562894815383-Discord-Developer-Terms-of-Service
- June 2026 privileged-data changes: https://discord.com/blog/updated-requirements-to-how-apps-access-data-in-servers
