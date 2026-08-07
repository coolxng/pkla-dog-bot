# pkla dog Discord Bot

A Python Discord bot with slash-command AI chat, web search, voice playback/TTS, authenticated browser controls, and verification-focused privacy defaults.

- [Terms of Service](./TERMS.md)
- [Privacy Policy](./PRIVACY.md)
- [Support and reports](./SUPPORT.md)
- [Verification checklist](./VERIFICATION.md)

## Discord verification posture

The public deployment uses `python verification_entry.py` and does not request **Message Content Intent** or **Server Members Intent**. Ordinary server messages are not used for AI chat; use `/chat`.

There is no persistent conversation database and no shared/universal memory. Chat context is in-memory only and scoped to the invoking user plus the current guild/DM context.

## Commands

| Command | Description |
| --- | --- |
| `/chat <prompt>` | Chat with pkla dog. |
| `/search <query>` | Search the web and get a concise answer. |
| `/reset` | Clear your current chat context. |
| `/delete-data` | Delete all in-memory data associated with your Discord user ID. |
| `/join` | Join your current voice channel and bark once. |
| `/leave` | Leave the current voice channel. |
| `/bark` | Play the bundled bark sound. |
| `/tts <message>` | Queue text-to-speech in voice. |
| `/ping <target> [message]` | Mention a configured member without sending a DM. |
| `/uptime` | Show process uptime. |
| `/coinflip` | Flip a coin. |
| `/roll [expression]` | Roll dice such as `d20` or `2d6`. |
| `/status` | Show runtime feature status. |
| `/listen-consent` | Explicitly consent to optional live browser voice relay in your current voice channel. |
| `/listen-revoke` | Revoke voice relay consent; an active relay stops. |
| `/support` | Show support, privacy, Terms, and reporting links. |
| `/birthdayryan` | Send the bundled birthday embed. |

The old `!` message-command handler, shared memory commands, `/pingdeaf`, and Poke ingest are removed.

## Voice listen-in consent

`ENABLE_LISTEN_IN` defaults to `false`. Even if an operator intentionally sets it to `true`, the browser receive path refuses to start unless **every current human participant** in the selected voice channel has run `/listen-consent`. A visible message is posted when listen-in starts and when it stops because consent changes. Incoming audio is relayed live and is not intentionally stored.

## Data deletion

`/delete-data` clears every in-memory chat context associated with the invoking Discord user ID and removes that user's voice consent state. The application no longer uses the old plaintext SQLite conversation persistence layer.

## Required environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token. |
| `GROQ_API_KEY` | Yes for AI chat | Groq key for normal `/chat` responses. |
| `OPENAI_API_KEY` | For OpenAI features | Optional chat fallback, search, and TTS. |
| `PING_MEMBERS_JSON` | Optional | JSON mapping `/ping` target names to Discord user IDs. |
| `EXTERNAL_SAY_CONTROL_TOKEN` | Required for `/say` controls | Secret protecting the operator web UI. |
| `EXTERNAL_CHANNEL_ID` | Optional | Default text channel for `/say`. |
| `EXTERNAL_VOICE_CHANNEL_ID` | Optional | Default voice channel for `/say`. |
| `PUBLIC_BASE_URL` | Optional | Public policy/support base URL. Defaults to `https://pkladog.up.railway.app`. |

## Optional settings

`ENABLE_LISTEN_IN=false` is the safe default. Set it to `true` only if you intentionally want the consent-gated browser voice relay. Other optional provider/model settings remain documented in `.env.example`.

## Railway

The `Procfile` starts `python verification_entry.py`. If Railway has a manual Start Command override, set it to the same command. After deployment verify:

- https://pkladog.up.railway.app/terms
- https://pkladog.up.railway.app/privacy
- https://pkladog.up.railway.app/support

Use the Terms and Privacy URLs in Discord's Developer Portal. The Team owner must complete Discord Identity Verification manually.

## `/say` operator page

`/say` remains an authenticated operator control surface for posting messages, voice join/leave, audio playback, TTS, uploads, and configured moderation controls. Keep `EXTERNAL_SAY_CONTROL_TOKEN` secret. Browser incoming-audio relay is separately protected by the consent gate described above.
