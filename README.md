# Discord Bot

A Python Discord bot with OpenAI-backed chat responses, optional web search, lightweight in-memory DM/channel conversation history, and optional universal memory commands.

## Required environment variables

Set these in your hosting provider's secret/environment variable UI. Do not commit real secrets.

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token used by `discord.py`. |
| `OPENAI_API_KEY` | Yes | OpenAI API key for chat completions and OpenAI web search. |
| `TARGET_CHANNEL_IDS` | Recommended | Comma-separated channel IDs where the bot should respond. Defaults to the existing hardcoded channel list if unset. |
| `OWNER_ID` | Recommended | Discord user ID allowed to DM the bot and run owner-only commands. Defaults to the existing owner ID if unset. |
| `EXTERNAL_CHANNEL_ID` | Required for `/say` | Discord channel ID where messages from the external send page are posted. It must also appear in `TARGET_CHANNEL_IDS`. |

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
| `EXTERNAL_VOICE_CHANNEL_ID` | `1447148315312521256` | Voice channel prefilled on the `/say` page for its Join, Leave, sound, and TTS controls. |

## Railway deploy steps

1. Create a new Railway project from this repository.
2. Add the required variables in **Variables**: `DISCORD_TOKEN`, `OPENAI_API_KEY`, `TARGET_CHANNEL_IDS`, and `OWNER_ID`.
3. Confirm the start command uses the `Procfile`: `worker: python bot.py`.
4. Deploy the service.
5. In Discord, invite the bot with message-content permissions enabled, grant it **Connect** and **Speak** permissions in voice channels, and add the target channel IDs to `TARGET_CHANNEL_IDS`.
6. Keep a single Railway replica running. The bot stores conversation and universal memory in RAM, so multiple replicas will not share state.

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
| `!join` | Joins your current voice channel, barks once immediately, and continues barking every five minutes. The bot does not record or process incoming audio. |
| `!bark` | Plays a bark immediately while the bot is connected. Has a five-second server-wide cooldown. |
| `!leave` | Stops scheduled barking and disconnects the bot from its current voice channel. |

## Send a message from outside Discord

You can make the bot post a message from a web browser:

1. Set `EXTERNAL_CHANNEL_ID` to the channel where the bot should speak. That ID must also be included in `TARGET_CHANNEL_IDS`.
2. Restart or redeploy the bot.
3. In Railway, open the bot service, select **Settings** → **Networking**, and choose **Generate Domain**.
4. When Railway asks for the target port, enter the port used by the bot's web server: `3000` by default, or the value of `PORT` if you set that variable yourself. Do not enter `8080` unless `PORT=8080` is configured.
5. After Railway creates an address such as `https://your-service.up.railway.app`, open that address with `/say` added to the end: `https://your-service.up.railway.app/say`.
6. Enter a message, then select **Send to Discord**. The same page also has **Join call** and **Leave call** controls, plus buttons for the wolf bark, Minecraft bark, bark-fart, and Jamal crazy idek sounds. Voice channel `1447148315312521256` is selected by default; you can edit the channel ID before using the controls.
7. To use text to speech, select **Join call** for the chosen voice channel first. Enter up to 500 characters under **Text to speech**, choose one of the allowed voices, and select **Speak in call**. The bot must remain connected to that selected channel, and each server can start TTS at most once every 30 seconds.

If Railway already shows a public domain under **Settings** → **Networking**, use that existing domain instead of generating another one. Opening the domain without `/say` should display `alive`, which confirms that Railway is routing to the correct port.

The `/say` page has no login or control token. Anyone who knows or discovers its public URL can make the bot post to the configured channel, control its voice connection, and request billable OpenAI TTS generation. Keep the URL private or add authentication before exposing it broadly. The page returns an error instead of sending if Discord is not connected, the configured channel is not allowed, a message exceeds Discord's 2,000-character limit, speech exceeds 500 characters, the selected voice is not allowed, another sound is playing, or the 30-second server-wide TTS cooldown is active.

OpenAI text-to-speech requests use the billable Speech API associated with `OPENAI_API_KEY`. The cooldown and text limit reduce accidental usage, but they are not a substitute for authentication or provider-side budget limits.

## Channel setup

The bot only responds in channels listed in `TARGET_CHANNEL_IDS`, or in DMs from `OWNER_ID`. In server channels, recent conversation history is shared by channel and labels each user's messages by display name so different people can continue the same ChatGPT-style group conversation. DMs keep separate per-user history. Set `TARGET_CHANNEL_IDS` as a comma-separated list, for example:

```text
TARGET_CHANNEL_IDS=123456789012345678,234567890123456789
```

If `TARGET_CHANNEL_IDS` is unset or invalid, the bot falls back to the existing default channel IDs in `bot.py`.

## API provider setup

OpenAI is the primary provider for chat, web search, and optional text to speech. Set `OPENAI_API_KEY` and optionally override `OPENAI_MODEL`, `OPENAI_TTS_MODEL`, or `OPENAI_TTS_VOICE`. The default `chat-latest` model is chosen for ChatGPT-like chat behavior, while deterministic Discord actions such as ping commands are still handled by bot code so mentions stay exact. OpenAI web search runs first when available. Tavily, Brave Search, SerpAPI, and DDGS remain fallback search providers if configured or available.

## Known limitations

- Conversation history is RAM-only and is wiped on restart. Server-channel history is shared by channel, while DM history remains per user.
- Universal memory is RAM-only and is wiped on restart.
- Auto-memory extraction is disabled by default because it can store personal facts across users.
- The bot should run as a single replica because in-memory history and memory are not shared across processes.
- There is no time-based expiry for conversation history; users and channels are evicted silently when the in-memory caps are reached.
- Live search quality depends on the configured providers and API availability.
