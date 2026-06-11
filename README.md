# Discord Bot

A Python Discord bot with OpenAI-backed chat responses, optional web search, voice playback, explicitly controlled call transcription, lightweight in-memory DM/channel conversation history, and optional universal memory commands.

## Required environment variables

Set these in your hosting provider's secret/environment variable UI. Do not commit real secrets.

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token used by `discord.py`. |
| `OPENAI_API_KEY` | Yes | OpenAI API key for chat completions and OpenAI web search. |
| `TARGET_CHANNEL_IDS` | Recommended | Comma-separated channel IDs where the bot should respond. Defaults to the existing hardcoded channel list if unset. |
| `OWNER_ID` | Recommended | Discord user ID allowed to DM the bot and run owner-only commands. Defaults to the existing owner ID if unset. |
| `EXTERNAL_CHANNEL_ID` | Required for `/say` | Discord channel ID where messages from the external send page are posted. It must also appear in `TARGET_CHANNEL_IDS`. |
| `EXTERNAL_SAY_CONTROL_TOKEN` | Required for transcription | Long random password used for HTTP Basic authentication on transcription controls and transcript retrieval. Store it as a secret. |

## Optional environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_MODEL` | `chat-latest` | Model used for normal bot replies. `chat-latest` is the API model alias intended for chat-style behavior close to ChatGPT. Override this if you need a specific model or lower cost. |
| `OPENAI_SEARCH_MODEL` | `OPENAI_MODEL` or `chat-latest` | Model used for OpenAI web search requests. |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | Model used by the OpenAI Speech API for **Speak in call**. |
| `OPENAI_TTS_VOICE` | `alloy` | Default voice selected on `/say`. Unsupported values fall back to `alloy`; the page only accepts voices from the server-side allowlist. |
| `OPENAI_WEB_SEARCH_TOOL` | `web_search` | OpenAI Responses API web-search tool name. |
| `OPENAI_REASONING_EFFORT` | `none` for GPT-5 models, otherwise `minimal` | Reasoning effort for chat completions when supported. |
| `OPENAI_SEARCH_REASONING_EFFORT` | `low` for reasoning-capable models | Reasoning effort for OpenAI web search when supported. |
| `AUTO_MEMORY_ENABLED` | `false` | Enables automatic extraction of shared memory facts from conversations. Off by default. |
| `TAVILY_API_KEY` | unset | Optional fallback search provider. |
| `BRAVE_SEARCH_API_KEY` | unset | Optional fallback search provider. |
| `SERPAPI_API_KEY` | unset | Optional fallback search provider. |
| `PORT` | `3000` | Flask keepalive web server port. |
| `EXTERNAL_VOICE_CHANNEL_ID` | `1447148315312521256` | Voice channel prefilled on the `/say` page for its Join, Leave, sound, TTS, and audio upload controls. |
| `EXTERNAL_SAY_CONTROL_TOKEN` | unset | Password that protects all `/say` access with HTTP Basic authentication. It is **required** before incoming call audio or transcripts can start. Store it as a secret; do not commit it. |

## Railway deploy steps

1. Create a new Railway project from this repository.
2. Add the required variables in **Variables**: `DISCORD_TOKEN`, `OPENAI_API_KEY`, `TARGET_CHANNEL_IDS`, and `OWNER_ID`.
3. Confirm the start command uses the `Procfile`: `worker: python bot.py`.
4. Deploy the service.
5. In the [Discord Developer Portal](https://discord.com/developers/applications), open the application, select **Bot**, and enable both **Server Members Intent** and **Message Content Intent** under **Privileged Gateway Intents**. The members intent lets `/pingdeaf` reliably resolve server members beyond Discord's initial short suggestion list.
6. Invite the bot and grant **View Channel**, **Connect**, **Speak**, and **Send Messages** in voice channels that may be transcribed. **Send Messages** is required so the bot can post visible start/stop capture notices in the voice channel's text chat. Add text target IDs to `TARGET_CHANNEL_IDS`.
7. Ensure the deployment installs `requirements.txt`, including `discord.py[voice]` (PyNaCl) and the pinned `discord-ext-voice-recv` pre-release. The extension supplies inbound voice support that `discord.py` itself does not expose. Keep FFmpeg available for the existing playback features.
8. To enable transcription, set `TRANSCRIPTION_ENABLED=true`, set `OPENAI_API_KEY`, choose `OPENAI_TRANSCRIPTION_MODEL` if desired, and set a strong `EXTERNAL_SAY_CONTROL_TOKEN`. Restart after changing environment settings.
9. Keep a single Railway replica running. Conversation history, universal memory, transcription sessions, and transcripts are RAM-only and are not shared between replicas.

## Bot commands

| Command | Description |
| --- | --- |
| `ping ozzy` | Mentions Ozzy. |
| `ping luka` | Mentions Luka. |
| `ping coolxng` | Mentions coolxng. |
| `ping ryan` | Mentions Ryan. |
| `ping jamal` | Mentions Jamal. |
| `ping jaedon` / `ping j` | Mentions Jaedon. |
| `ping reqo` | Mentions Reqo. |
| `ping hayden` | Mentions Hayden. |
| `ping 6uke` | Mentions 6uke. |
| `ping tom pearls` | Mentions Tom Pearls. |
| `!reset` or `!clear` | Clears the active conversation history: your DM history in DMs, or the current channel's shared history in server channels. |
| `!remember <fact>` | Adds a shared memory fact manually. |
| `!memory` | Shows current shared memory facts. |
| `!search <query>` | Runs a live web search and returns a concise answer. |
| `!forget` | Owner-only command that clears shared memory. |
| `!deletedms` | Available only in DMs to Discord user `575057023046123520`; deletes past messages sent by this bot across every DM conversation available to the connected bot and reacts to the command with the result. |
| `!join` | Joins your current voice channel, barks once immediately, and continues barking every five minutes. Incoming audio is processed only while an authenticated browser listener or transcription consumer is active. |
| `!bark` | Plays a bark immediately while the bot is connected. Has a five-second server-wide cooldown. |
| `!tts <message>` | Queues up to 500 characters to be read with the Onyx voice in the connected voice channel. Multiple `!tts` messages play in order without overlapping. |
| `!leave` | Stops scheduled barking and disconnects the bot from its current voice channel. |
| `/pingdeaf user:@member` | DMs a deafened voice member every two seconds until they undeafen. The sender sees a live count of reminder DMs sent, both people get a stop button, the sender is notified if the receiver stops the reminders, and the bot deletes its reminder DMs two minutes after the reminders stop. |

The bot synchronizes `/pingdeaf` globally at startup and removes obsolete server-specific commands registered to the same Discord application. Discord controls the member picker's initial suggestions, so it may show only a few members before you type; enter part of a member's display name or username to search the rest of the server. **Server Members Intent** must be enabled in the Developer Portal and in the bot configuration above.

## Send a message from outside Discord

You can make the bot post a message from a web browser:

1. Set `EXTERNAL_CHANNEL_ID` to the channel where the bot should speak. That ID must also be included in `TARGET_CHANNEL_IDS`.
2. Restart or redeploy the bot.
3. In Railway, open the bot service, select **Settings** → **Networking**, and choose **Generate Domain**.
4. When Railway asks for the target port, enter the port used by the bot's web server: `3000` by default, or the value of `PORT` if you set that variable yourself. Do not enter `8080` unless `PORT=8080` is configured.
5. After Railway creates an address such as `https://your-service.up.railway.app`, open that address with `/say` added to the end: `https://your-service.up.railway.app/say`.
6. Enter a message, then select **Send to Discord**. The same page also has **Join call**, **Stop audio**, and **Leave call** controls, plus buttons for the wolf bark, Minecraft bark, bark-fart, Jamal crazy idek, and Evan crash sounds. Voice channel `1447148315312521256` is selected by default; you can edit the channel ID before using the controls.
7. To use text to speech, select **Join call** for the chosen voice channel first. Enter up to 500 characters under **Text to speech**, choose one of the allowed voices, and select **Speak in call**. The bot must remain connected to that selected channel, and each server can start TTS at most once every 30 seconds.
8. To play your own clip, use the right-side **Upload audio** panel. Select the same voice channel the bot already joined, choose an `.mp3` or `.mp4` file, and select **Upload and play**. Uploads are limited to 8 MiB. The server checks both the filename extension and the corresponding MP3 or MP4 header signature instead of trusting the browser MIME type. Video streams in MP4 files are ignored; only their audio is played.

9. To hear the call in the browser, set `EXTERNAL_SAY_CONTROL_TOKEN`, join the selected voice channel, and select **Start listening**. **Mute** affects only that browser, while **Stop listening** closes its stream. Live listening and transcription share one Discord receive session, so either feature can be started first.

The Discord bot role needs **View Channel**, **Connect**, **Speak**, and **Send Messages** permissions in the selected voice channel for all controls. Uploading and transcription do not connect or move the bot: it must already be connected to that exact channel. Only one clip can play at a time. Select **Stop audio** to end the current sound, uploaded audio, or text-to-speech playback without disconnecting the bot.

Uploaded files receive server-generated temporary paths with server-selected `.mp3` or `.mp4` extensions; submitted filenames are never used as filesystem paths. Temporary files are removed when validation, Discord scheduling, or playback startup fails, and successful uploads are removed by the playback completion callback (including playback errors). Files can remain briefly only if the process is forcibly terminated before cleanup runs.

If Railway already shows a public domain under **Settings** → **Networking**, use that existing domain instead of generating another one. Opening the domain without `/say` should display `alive`, which confirms that Railway is routing to the correct port.

Set `EXTERNAL_SAY_CONTROL_TOKEN` to a long random secret before exposing `/say`. When configured, `/say` shows an external-control-token login popup and stores a validated HttpOnly browser cookie. API clients can continue sending HTTP Basic credentials with any non-empty username and the configured token as the password. Railway and similar hosts should store the token in their secret-variable UI.

If `EXTERNAL_SAY_CONTROL_TOKEN` is intentionally left unset, the non-capture `/say` controls remain unauthenticated for backward compatibility. **Incoming call audio and transcript capabilities refuse to start without the token.** Anyone who knows or discovers an unauthenticated public URL can still post to Discord, join or leave voice calls, play sounds, upload audio, and request billable OpenAI TTS. Keeping the URL private is not equivalent to authentication.

The page returns an error instead of sending if Discord is not connected, the configured channel is not allowed, a message exceeds Discord's 2,000-character limit, speech exceeds 500 characters, an upload is missing, empty, malformed, not an MP3 or MP4, or over 8 MiB, the selected TTS voice is not allowed, another sound is playing, or the 30-second server-wide TTS cooldown is active. Flask also rejects oversized request bodies with a readable HTTP 413 response.

OpenAI text-to-speech and transcription requests use billable APIs associated with `OPENAI_API_KEY`. Transcription sends per-user WAV chunks outside the Discord event-loop thread. Chunks end after configured silence or at the bounded duration, and at most four provider chunks are queued per guild; overload and provider errors appear as transcript entries. These controls and limits reduce accidental usage, but they are not substitutes for participant consent, authentication, or provider-side budget limits.

## Voice receive dependency

`discord.py==2.7.1` provides outbound voice playback but no supported inbound receive pipeline. This project therefore pins `discord-ext-voice-recv==0.5.2a179`, whose `VoiceRecvClient` and `AudioSink` expose decoded per-user PCM. The package is maintained but still labeled alpha/pre-release and warns that Discord protocol changes may break it. Test voice receive after dependency or Discord voice changes before deploying. If the extension cannot be imported, the connected client was created without receive support, credentials are missing, or required Discord permissions are absent, `/say` returns a clear error and does not begin capture.

Received audio is never persisted by this bot. Only bounded WAV request bodies exist transiently for provider calls, and only the newest `TRANSCRIPT_RETENTION_LIMIT` text entries are retained in memory. Entries include timestamp, Discord user ID, display name, text, and partial/final status. Stopping retains the bounded transcript for review; clearing it, disconnecting voice, losing the Discord connection, or restarting removes state.

## Channel setup

The bot only responds in channels listed in `TARGET_CHANNEL_IDS`, or in DMs from `OWNER_ID`. In server channels, recent conversation history is shared by channel and labels each user's messages by display name so different people can continue the same ChatGPT-style group conversation. DMs keep separate per-user history. Set `TARGET_CHANNEL_IDS` as a comma-separated list, for example:

```text
TARGET_CHANNEL_IDS=123456789012345678,234567890123456789
```

If `TARGET_CHANNEL_IDS` is unset or invalid, the bot falls back to the existing default channel IDs in `bot.py`.

## API provider setup

OpenAI is the primary provider for chat, web search, optional text to speech, and optional call transcription. Set `OPENAI_API_KEY` and optionally override `OPENAI_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`, or `OPENAI_TRANSCRIPTION_MODEL`. The default `chat-latest` model is chosen for ChatGPT-like chat behavior, while deterministic Discord actions such as ping commands are still handled by bot code so mentions stay exact. OpenAI web search runs first when available. Tavily, Brave Search, SerpAPI, and DDGS remain fallback search providers if configured or available.

## Known limitations

- Conversation history is RAM-only and is wiped on restart. Server-channel history is shared by channel, while DM history remains per user.
- Universal memory is RAM-only and is wiped on restart.
- Voice transcripts are bounded and RAM-only. They are removed on clear, voice disconnect, Discord disconnect, or restart; no cross-replica transcript synchronization exists.
- Voice receive depends on an alpha extension built on Discord's undocumented/reverse-engineered receive behavior, so Discord changes can disrupt transcription independently of outbound playback.
- Auto-memory extraction is disabled by default because it can store personal facts across users.
- The bot should run as a single replica because in-memory history and memory are not shared across processes.
- There is no time-based expiry for conversation history; users and channels are evicted silently when the in-memory caps are reached.
- Live search quality depends on the configured providers and API availability.
