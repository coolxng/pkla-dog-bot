# Discord Bot

A Python Discord bot with OpenAI-backed chat responses, optional web search, lightweight in-memory conversation history, and optional universal memory commands.

## Required environment variables

Set these in your hosting provider's secret/environment variable UI. Do not commit real secrets.

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token used by `discord.py`. |
| `OPENAI_API_KEY` | Yes | OpenAI API key for chat completions and OpenAI web search. |
| `TARGET_CHANNEL_IDS` | Recommended | Comma-separated channel IDs where the bot should respond. Defaults to the existing hardcoded channel list if unset. |
| `OWNER_ID` | Recommended | Discord user ID allowed to DM the bot and run owner-only commands. Defaults to the existing owner ID if unset. |

## Optional environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_MODEL` | `chat-latest` | Model used for normal bot replies. `chat-latest` is the API model alias intended for chat-style behavior close to ChatGPT. Override this if you need a specific model or lower cost. |
| `OPENAI_SEARCH_MODEL` | `OPENAI_MODEL` or `chat-latest` | Model used for OpenAI web search requests. |
| `OPENAI_WEB_SEARCH_TOOL` | `web_search` | OpenAI Responses API web-search tool name. |
| `OPENAI_REASONING_EFFORT` | `none` for GPT-5 models, otherwise `minimal` | Reasoning effort for chat completions when supported. |
| `OPENAI_SEARCH_REASONING_EFFORT` | `low` for reasoning-capable models | Reasoning effort for OpenAI web search when supported. |
| `AUTO_MEMORY_ENABLED` | `false` | Enables automatic extraction of shared memory facts from conversations. Off by default. |
| `TAVILY_API_KEY` | unset | Optional fallback search provider. |
| `BRAVE_SEARCH_API_KEY` | unset | Optional fallback search provider. |
| `SERPAPI_API_KEY` | unset | Optional fallback search provider. |
| `PORT` | `3000` | Flask keepalive web server port. |

## Railway deploy steps

1. Create a new Railway project from this repository.
2. Add the required variables in **Variables**: `DISCORD_TOKEN`, `OPENAI_API_KEY`, `TARGET_CHANNEL_IDS`, and `OWNER_ID`.
3. Confirm the start command uses the `Procfile`: `worker: python bot.py`.
4. Deploy the service.
5. In Discord, invite the bot with message-content permissions enabled and add the target channel IDs to `TARGET_CHANNEL_IDS`.
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
| `!reset` or `!clear` | Clears your per-user conversation history. |
| `!remember <fact>` | Adds a shared memory fact manually. |
| `!memory` | Shows current shared memory facts. |
| `!search <query>` | Runs a live web search and returns a concise answer. |
| `!forget` | Owner-only command that clears shared memory. |

## Channel setup

The bot only responds in channels listed in `TARGET_CHANNEL_IDS`, or in DMs from `OWNER_ID`. Set `TARGET_CHANNEL_IDS` as a comma-separated list, for example:

```text
TARGET_CHANNEL_IDS=123456789012345678,234567890123456789
```

If `TARGET_CHANNEL_IDS` is unset or invalid, the bot falls back to the existing default channel IDs in `bot.py`.

## API provider setup

OpenAI is the primary provider for chat and web search. Set `OPENAI_API_KEY` and optionally override `OPENAI_MODEL`. The default `chat-latest` model is chosen for ChatGPT-like chat behavior, while deterministic Discord actions such as ping commands are still handled by bot code so mentions stay exact. OpenAI web search runs first when available. Tavily, Brave Search, SerpAPI, and DDGS remain fallback search providers if configured or available.

## Known limitations

- Conversation history is RAM-only and is wiped on restart.
- Universal memory is RAM-only and is wiped on restart.
- Auto-memory extraction is disabled by default because it can store personal facts across users.
- The bot should run as a single replica because in-memory history and memory are not shared across processes.
- There is no time-based expiry for conversation history; users are evicted silently when the in-memory user cap is reached.
- Live search quality depends on the configured providers and API availability.
