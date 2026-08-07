# pkla dog Privacy Policy

**Last updated: August 7, 2026**

This policy explains how **pkla dog** handles data when you use the Discord application. pkla dog is an independent application and is not affiliated with Discord Inc.

## Data processed

pkla dog processes the minimum Discord data needed to provide the feature you explicitly invoke. This can include your Discord user ID, display name, server/channel identifiers, slash-command inputs, voice-state information required for voice commands, and content you submit to `/chat`, `/search`, `/tts`, `/ping`, or the authenticated `/say` operator page.

The bot does **not** request Discord Message Content Intent or Server Members Intent. It does not read ordinary server messages for AI chat. AI chat is invoked through `/chat`.

## Conversation context and storage

Chat context is kept **only in process memory** and is scoped to the invoking Discord user plus the current server (or DM context). It is bounded to recent messages and is lost on process restart or earlier cache eviction.

The public bot does **not** use the old SQLite persistence layer and does not provide shared/universal memory. There is no cross-server or cross-user memory feature.

Use `/reset` to clear the current chat context. Use `/delete-data` to remove all in-memory conversation context and consent state associated with your Discord user ID across the running bot process.

## AI and search providers

When you explicitly use an AI or search feature, the content needed to fulfill that request may be sent to configured service providers. Depending on deployment configuration these can include Groq, OpenAI, DuckDuckGo/DDGS, Tavily, Brave Search, or SerpApi. Those providers process requests under their own terms and privacy policies.

Discord API data is not sold and is not used by pkla dog to train a machine-learning model.

## Voice and audio

pkla dog can join voice channels, play sounds, and provide text-to-speech. Browser voice listen-in is **disabled by default**. An operator must intentionally enable `ENABLE_LISTEN_IN=true`, and the relay will still refuse to start until **every current human participant in that voice channel has explicitly run `/listen-consent`**. Consent and the notification channel are stored only in memory.

When listen-in begins, the bot posts a visible notice in the text channel used for consent. If consent changes while listening is active, the relay stops and posts another notice. Participants can revoke consent with `/listen-revoke`. Incoming voice audio is relayed live and is not intentionally stored by the bot.

Uploaded audio for playback can be written to temporary files and is removed after validation failure, playback failure, or normal playback completion.

## Authenticated `/say` controls

The operator web page requires `EXTERNAL_SAY_CONTROL_TOKEN` for control actions. The page can post messages, control voice playback, use TTS, and perform configured moderation actions when Discord permissions allow.

## Retention and deletion

The bot intentionally avoids persistent Discord conversation storage. In-memory chat and consent state disappear when the process restarts. `/delete-data` removes the running process's retained user-specific context immediately.

Operational logs may contain technical errors and identifiers needed to diagnose failures. The bot is not designed to log full conversations as an analytics dataset.

For a privacy request that cannot be handled by `/delete-data`, use the support/report page or the GitHub issue tracker:

- https://pkladog.up.railway.app/support
- https://github.com/coolxng/pkla-dog-bot/issues

Do not post passwords, API keys, tokens, private message contents, or other secrets in a public issue.

## Security

Secrets are expected to be stored in deployment environment variables. The `/say` control surface is authenticated, uploads are bounded and validated, and public voice receive is off by default. No online service can guarantee perfect security.

## Changes

This policy may be updated when the bot's functionality or data practices change. The current policy remains available at `/privacy` and in this repository.
