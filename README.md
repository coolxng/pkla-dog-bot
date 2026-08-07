# pkla dog Discord Bot

A Python Discord bot with Groq-backed chat responses, optional OpenAI web search and text to speech, voice playback, authenticated browser controls, lightweight conversation context, and utility commands.

The default production deployment now uses **verification-safe mode** through `verification_entry.py`.

- [Terms of Service](./TERMS.md)
- [Privacy Policy](./PRIVACY.md)
- [Support and privacy requests](./SUPPORT.md)
- [Discord verification checklist](./VERIFICATION.md)

## Verification-safe public deployment

The repository `Procfile` starts:

```text
python verification_entry.py
```

That entrypoint intentionally disables features that should not be exposed by the public/verified bot without another policy review:

- repeated-DM `/pingdeaf` command;
- legacy `POKE_INGEST_URL` Discord-message forwarding;
- browser voice listen-in / inbound voice relay;
- persistent SQLite conversation storage;
- automatic memory extraction.

It also serves the legal and support documents at:

```text
/terms
/privacy
/support
```

After deployment, use the public HTTPS `/terms` and `/privacy` URLs in the Discord Developer Portal.

## Required environment variables

Set secrets in your hosting provider's environment-variable UI. Do not commit real secrets.

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token used by `discord.py`. |
| `GROQ_API_KEY` | Yes | Groq API key used for normal AI chat responses. |
| `OPENAI_API_KEY` | For OpenAI features | Used for explicitly enabled OpenAI web search, optional chat fallback, and text to speech. |
| `TARGET_CHANNEL_IDS` | Recommended | Comma-separated channel IDs where the bot should respond. |
| `OWNER_ID` | Recommended | Discord user ID allowed to DM the bot and run owner-only commands. |
| `PING_MEMBERS_JSON` | Recommended | JSON object mapping configured ping trigger names to Discord user IDs. |
| `EXTERNAL_CHANNEL_ID` | For `/say` text posting | Discord channel ID prefilled for the authenticated external control page. |

## Optional environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `GROQ_CHAT_MODEL` | `llama-3.1-8b-instant` | Model used for normal AI chat. |
| `OPENAI_CHAT_FALLBACK` | `false` | Allows normal chat to fall back to OpenAI when explicitly enabled. |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | OpenAI model used by optional chat fallback. |
| `ENABLE_OPENAI_WEB_SEARCH` | `false` | Enables the OpenAI web-search provider. |
| `OPENAI_SEARCH_MODEL` | `chat-latest` | OpenAI model used for web search. |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | OpenAI model used for text to speech. |
| `OPENAI_TTS_VOICE` | `alloy` | Default `/say` page TTS voice. |
| `TAVILY_API_KEY` | unset | Optional search-provider key. |
| `BRAVE_SEARCH_API_KEY` | unset | Optional search-provider key. |
| `SERPAPI_API_KEY` | unset | Optional search-provider key. |
| `EXTERNAL_VOICE_CHANNEL_ID` | configured ID | Voice channel prefilled on `/say`. |
| `EXTERNAL_SAY_CONTROL_TOKEN` | unset | Secret protecting `/say` controls. Set a strong value before exposing controls. |
| `PORT` | `3000` | Flask web server port. |
| `LOG_LEVEL` | `INFO` | Runtime log level. |
| `USE_PRODUCTION_WEB_SERVER` | `false` | Leave false unless the gevent/asyncio interaction has been explicitly validated. |

The following values are shown in `.env.example` for clarity, but `verification_entry.py` forces them off in the public deployment:

```text
ENABLE_LISTEN_IN=false
PERSIST_STATE=false
AUTO_MEMORY_ENABLED=false
```

## Railway deploy steps

1. Create or connect a Railway service to this repository.
2. Add `DISCORD_TOKEN`, `GROQ_API_KEY`, `TARGET_CHANNEL_IDS`, and `OWNER_ID` under **Variables**. Add `OPENAI_API_KEY` only if you use OpenAI-backed features.
3. Confirm the start command is `python verification_entry.py`. The repository `Procfile` already sets this. If Railway has a manual start-command override, update or remove the override.
4. Deploy the service.
5. In the [Discord Developer Portal](https://discord.com/developers/applications), enable the privileged intents currently requested by the code: **Server Members Intent** and **Message Content Intent**. Privileged-intent review at scale is separate from basic App Verification.
6. Invite the bot with only the Discord permissions needed for the features you actually use. Voice playback normally needs **View Channel**, **Connect**, and **Speak**. Moderation actions need their corresponding moderation permissions and role hierarchy.
7. Keep FFmpeg and the dependencies in `requirements.txt` available to the deployment.
8. Set a strong `EXTERNAL_SAY_CONTROL_TOKEN` before using `/say` controls over a public domain.
9. Open `/health` to confirm the Discord client is connected.
10. Confirm `/terms`, `/privacy`, and `/support` load over HTTPS, then complete the steps in [VERIFICATION.md](./VERIFICATION.md).

## Bot commands

| Command | Description |
| --- | --- |
| `ping <configured name>` | Mentions the configured Discord member. |
| `!reset` or `!clear` | Clears active conversation history for the current context. |
| `!remember <fact>` | Adds a shared in-memory memory fact manually. |
| `!memory` | Shows current shared in-memory memory facts. |
| `!forget` | Owner-only command that clears shared memory. |
| `!search <query>` | Runs a live web search and returns a concise answer. |
| `!help` | Shows a concise command list. |
| `!uptime` | Shows process uptime. |
| `!coinflip` | Flips a coin. |
| `!roll [NdM]` | Rolls dice, such as `d20` or `2d6`. |
| `!status` | Shows TTS, API-call, and listen-in status. |
| `!deletedms` | Owner-only DM cleanup command for messages sent by this bot. |
| `!join` | Joins the invoking user's voice channel and barks once. |
| `!bark` | Plays the bundled bark sound while connected. |
| `!tts <message>` | Queues up to 500 characters for OpenAI text-to-speech playback. |
| `!leave` | Disconnects the bot from its current voice channel. |
| `/birthdayryan` | Posts the bundled birthday message and image. |

### `/pingdeaf`

The legacy source contains a `/pingdeaf` implementation that repeatedly DMed another member. **The verification-safe production entrypoint removes this command from the global command tree before Discord synchronization, so it is not available in the public deployment.**

Do not re-enable the repeated-DM implementation for a verified/public bot without redesigning it around explicit recipient consent and re-checking Discord's current Developer Policy.

## Authenticated `/say` controls

The web service includes an operator control page at `/say`.

Set a strong `EXTERNAL_SAY_CONTROL_TOKEN` before exposing it. If the token is unset, the page can load as a setup page but control requests are rejected.

Authorized operators can use supported controls for:

- posting a message to an available Discord text channel;
- joining and leaving a Discord voice channel;
- playing bundled sounds;
- stopping current audio;
- text-to-speech playback;
- uploading small MP3/MP4 audio for playback;
- server mute/deafen controls when Discord permissions allow;
- browser microphone talk into the connected Discord voice channel.

Uploads are limited to 8 MiB and are validated before playback. Temporary files are removed after failure or playback completion when normal cleanup runs.

### Browser listen-in

The repository contains inbound voice receive code and a DAVE-compatible `discord-ext-voice-recv` dependency. The **verification-safe public deployment forces `ENABLE_LISTEN_IN=false`**, so incoming Discord call audio is not relayed to browser listeners.

Do not enable inbound voice relay for a public deployment without reviewing participant consent, Discord policy, applicable law, and the Privacy Policy first.

## Conversation data

The public verification deployment keeps normal conversation context in process memory and forces persistent SQLite storage off.

- Context is bounded by the bot's in-memory caps.
- There is no separate time-based expiry for ordinary conversation history.
- Context is removed on process restart and may be removed earlier by cache eviction or `!reset` / `!clear`.
- Automatic memory extraction is forced off.
- The legacy external Poke message-ingest path is disabled.

See [PRIVACY.md](./PRIVACY.md) for the complete public-facing data description and deletion-request process.

## API providers

Groq handles normal AI chat. OpenAI can provide explicitly enabled chat fallback, web search, and text to speech. Search fallback support also exists for Tavily, Brave Search, SerpApi, and DDGS depending on configuration.

Deterministic Discord actions such as configured mentions remain handled by bot code.

## Voice dependency

`discord.py==2.7.1` provides outbound voice playback and DAVE session handling. The project also pins a DAVE-compatible `discord-ext-voice-recv` revision for the legacy inbound receive pipeline. Discord voice changes can break that receive path independently of normal outbound playback.

The inbound receive path is disabled by `verification_entry.py` for the public deployment.

## Discord verification

See [VERIFICATION.md](./VERIFICATION.md) for the post-merge checklist, including:

- public Terms of Service URL;
- public Privacy Policy URL;
- Team Owner Identity Verification;
- verification-qualification checks;
- privileged-intent notes.

## Known limitations

- Server-channel AI history is shared by channel, while DM history is per user.
- In-memory history is not shared across multiple bot replicas.
- Live search quality depends on provider availability.
- Global text-command behavior still requires Message Content Intent. Migrating user actions to slash commands would reduce privileged message access and is recommended before large-scale distribution.
- The public deployment intentionally disables persistence, auto-memory extraction, inbound voice listen-in, legacy message forwarding, and `/pingdeaf`.
