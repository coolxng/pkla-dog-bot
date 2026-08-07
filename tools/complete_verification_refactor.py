from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def replace_span(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_i = text.find(start)
    end_i = text.find(end, start_i + len(start)) if start_i >= 0 else -1
    if start_i < 0 or end_i < 0 or end_i <= start_i:
        raise SystemExit(f"Could not locate {label}")
    return text[:start_i] + replacement + text[end_i:]


def remove_test_classes_containing(text: str, needles: tuple[str, ...]) -> str:
    matches = list(re.finditer(r"(?m)^class [A-Za-z_][A-Za-z0-9_]*\([^\n]*\):\n", text))
    if not matches:
        return text
    chunks: list[str] = [text[: matches[0].start()]]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start():end]
        if not any(needle in block for needle in needles):
            chunks.append(block)
    return "".join(chunks)


bot_path = ROOT / "bot.py"
bot = bot_path.read_text(encoding="utf-8")

bot = bot.replace("from storage import default_state_store\n", "")
bot = bot.replace('env_bool("ENABLE_LISTEN_IN", True)', 'env_bool("ENABLE_LISTEN_IN", False)')

bot = replace_once(
    bot,
    'EXTERNAL_SAY_AUTH_COOKIE = "external_say_auth"\n',
    'EXTERNAL_SAY_AUTH_COOKIE = "external_say_auth"\nPUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://pkladog.up.railway.app").rstrip("/")\n',
    "public base URL insertion",
)

for old, new in (
    ("!join", "/join"),
    ("!leave", "/leave"),
    ("!bark", "/bark"),
    ("!tts", "/tts"),
    ("!reset", "/reset"),
    ("!clear", "/reset"),
    ("!search", "/search"),
    ("!help", "/help"),
    ("!uptime", "/uptime"),
    ("!coinflip", "/coinflip"),
    ("!roll", "/roll"),
    ("!status", "/status"),
    ("!deletedms", "/delete-data"),
):
    bot = bot.replace(old, new)

bot = bot.replace(
    "- Server history may label messages as Name: message. Universal memory is unverified shared context; use it only when directly relevant.\n",
    "- Conversation context is scoped to the invoking user and server and exists only in process memory. Never treat another user's context as this user's context.\n",
)
bot = bot.replace(
    "- `/bark`, `/tts <message>`, `/leave`, `/search <query>`, and the memory/reset commands work as named.\n",
    "- `/chat`, `/bark`, `/tts`, `/leave`, `/search`, `/reset`, and the other slash commands work as named. Shared memory commands do not exist.\n",
)
bot = bot.replace(
    "- The external `/say` web page can message, control voice, play {SOUND_CLIP_LABELS}, use TTS, and listen to live call audio in the browser.\n",
    "- The external `/say` web page can message, control voice, play {SOUND_CLIP_LABELS}, and use TTS. Browser listen-in is disabled by default and requires every current human participant to consent with `/listen-consent` before it can start.\n",
)

history_start = "# DM conversation history is keyed by user ID and wiped on restart.\n"
history_end = "intents = discord.Intents.default()\n"
history_replacement = '''# Slash-command conversation history is kept only in process memory and is scoped\n# to the invoking Discord user plus the current guild (or DM context).\nconversation_history: OrderedDict[tuple[int | None, int], list[dict]] = OrderedDict()\nMAX_CONVERSATIONS = 500\nlast_message_at: dict[int, datetime] = {}\n# Explicit consent for optional browser voice listen-in is kept only in memory.\nvoice_listen_consents: dict[tuple[int, int], set[int]] = {}\nvoice_listen_notice_channels: dict[tuple[int, int], int] = {}\n\n'''
bot = replace_span(bot, history_start, history_end, history_replacement, "conversation state block")
bot = bot.replace("intents.message_content = True", "intents.message_content = False")

helpers_start = "def format_user_history_content(display_name: str, content: str) -> str:\n"
helpers_end = "def clean_reply(reply: str) -> str:\n"
helpers = '''def conversation_key(guild_id: int | None, user_id: int) -> tuple[int | None, int]:\n    return guild_id, user_id\n\n\ndef get_user_history(guild_id: int | None, user_id: int) -> list[dict]:\n    return conversation_history.get(conversation_key(guild_id, user_id), []).copy()\n\n\ndef add_user_history(guild_id: int | None, user_id: int, role: str, content: str) -> None:\n    key = conversation_key(guild_id, user_id)\n    if key not in conversation_history:\n        if len(conversation_history) >= MAX_CONVERSATIONS:\n            conversation_history.popitem(last=False)\n        conversation_history[key] = []\n    conversation_history[key].append({"role": role, "content": content})\n    if len(conversation_history[key]) > 20:\n        conversation_history[key] = conversation_history[key][-20:]\n    conversation_history.move_to_end(key)\n\n\ndef pop_user_history(guild_id: int | None, user_id: int) -> None:\n    history = conversation_history.get(conversation_key(guild_id, user_id))\n    if history:\n        history.pop()\n\n\ndef clear_user_context(guild_id: int | None, user_id: int) -> None:\n    conversation_history.pop(conversation_key(guild_id, user_id), None)\n\n\ndef delete_all_user_data(user_id: int) -> int:\n    keys = [key for key in conversation_history if key[1] == user_id]\n    for key in keys:\n        conversation_history.pop(key, None)\n    last_message_at.pop(user_id, None)\n    for consented_users in voice_listen_consents.values():\n        consented_users.discard(user_id)\n    return len(keys)\n\n\n'''
bot = replace_span(bot, helpers_start, helpers_end, helpers + helpers_end, "history helper block")

memory_start = "def normalize_memory_fact(fact: str) -> str:\n"
memory_end = "def split_reply_chunks(text: str, limit: int = 2000) -> list[str]:\n"
bot = replace_span(bot, memory_start, memory_end, memory_end, "shared memory helpers")

bot = bot.replace(
    '''        system_content = SYSTEM_PROMPT\n        if universal_memory:\n            facts = "\\n".join(f"- {fact}" for fact in universal_memory)\n            system_content += f"\\n\\n[UNIVERSAL MEMORY — shared context about this server and its members]:\\n{facts}"\n\n        now = current_datetime_text()\n''',
    '''        system_content = SYSTEM_PROMPT\n        now = current_datetime_text()\n''',
)
bot = bot.replace(
    "The current Discord speaker is {display_name}. Recent channel messages may include other speakers as 'Name: message'.",
    "The current Discord speaker is {display_name}. Conversation context belongs only to this user in this server context.",
)

auto_start = "async def auto_extract_memory(display_name: str, user_msg: str, bot_reply: str) -> None:\n"
auto_end = "last_command_bark_at: dict[int, float] = {}\n"
bot = replace_span(bot, auto_start, auto_end, auto_end, "automatic memory extraction")

voice_helpers = '''def voice_consent_key(voice_channel) -> tuple[int, int]:\n    return voice_channel.guild.id, voice_channel.id\n\n\ndef voice_channel_participant_ids(voice_channel) -> set[int]:\n    return {\n        member.id\n        for member in getattr(voice_channel, "members", [])\n        if not getattr(member, "bot", False)\n    }\n\n\ndef voice_channel_has_full_consent(voice_channel) -> bool:\n    participants = voice_channel_participant_ids(voice_channel)\n    if not participants:\n        return False\n    return participants.issubset(voice_listen_consents.get(voice_consent_key(voice_channel), set()))\n\n\nasync def notify_voice_listen(voice_channel, message: str) -> None:\n    channel_id = voice_listen_notice_channels.get(voice_consent_key(voice_channel))\n    if channel_id is None:\n        return\n    channel = client.get_channel(channel_id)\n    if channel is None or not hasattr(channel, "send"):\n        return\n    try:\n        await channel.send(message)\n    except discord.HTTPException as error:\n        logger.warning("Could not send voice listen-in notice: %s", error)\n\n\n'''
bot = replace_once(
    bot,
    "async def ensure_receive_session(voice_channel) -> None:\n",
    voice_helpers + "async def ensure_receive_session(voice_channel) -> None:\n",
    "voice consent helpers",
)
bot = replace_once(
    bot,
    "    channel_id = voice_channel.id\n    voice_client = voice_channel.guild.voice_client\n",
    "    channel_id = voice_channel.id\n    if not voice_channel_has_full_consent(voice_channel):\n        raise RuntimeError(\"Every current human participant must run /listen-consent before listen-in can start\")\n    voice_client = voice_channel.guild.voice_client\n",
    "voice consent gate",
)
bot = replace_once(
    bot,
    "    active_receive_channel_id = channel_id\n\n\nasync def start_browser_audio_session",
    "    active_receive_channel_id = channel_id\n    await notify_voice_listen(\n        voice_channel,\n        f\"🔊 Live browser listen-in started in {voice_channel.mention}. All current human participants explicitly consented. Audio is relayed live and is not stored.\",\n    )\n\n\nasync def start_browser_audio_session",
    "voice listen start notice",
)
bot = replace_once(
    bot,
    "    voice_client = getattr(getattr(voice_channel, \"guild\", None), \"voice_client\", None)\n    if voice_client and hasattr(voice_client, \"is_listening\") and voice_client.is_listening():\n",
    "    voice_client = getattr(getattr(voice_channel, \"guild\", None), \"voice_client\", None)\n    if voice_channel is not None:\n        await notify_voice_listen(voice_channel, \"🔇 Live browser listen-in stopped.\")\n    if voice_client and hasattr(voice_client, \"is_listening\") and voice_client.is_listening():\n",
    "voice listen stop notice",
)

voice_event_start = "@client.event\nasync def on_voice_state_update(member, before, after):\n"
voice_event_end = "\n\n@client.event\nasync def on_message(message):\n"
voice_event = '''@client.event\nasync def on_voice_state_update(member, before, after):\n    if client.user is not None and member.id == client.user.id:\n        if before.channel is not None and after.channel is None:\n            close_browser_talk_session("Discord voice connection closed")\n            await asyncio.to_thread(\n                close_receive_session, "Discord voice connection closed"\n            )\n        return\n\n    if before.channel is not None and before.channel != after.channel:\n        voice_listen_consents.get(voice_consent_key(before.channel), set()).discard(member.id)\n\n    checked_ids: set[int] = set()\n    for voice_channel in (before.channel, after.channel):\n        if voice_channel is None or voice_channel.id in checked_ids:\n            continue\n        checked_ids.add(voice_channel.id)\n        if active_receive_channel_id != voice_channel.id:\n            continue\n        if voice_channel_has_full_consent(voice_channel):\n            continue\n        close_receive_session("Participant consent changed")\n        await notify_voice_listen(\n            voice_channel,\n            "🔇 Live browser listen-in stopped because participant consent changed. Everyone currently in the voice channel must run `/listen-consent` before it can start again.",\n        )\n'''
bot = replace_span(bot, voice_event_start, voice_event_end, voice_event + "\n\n", "voice state handler")

slash_block = r'''async def send_interaction_chunks(interaction: discord.Interaction, text: str, *, ephemeral: bool = False) -> None:
    chunks = split_reply_chunks(text)
    if not chunks:
        chunks = ["done"]
    if not interaction.response.is_done():
        await interaction.response.send_message(chunks[0], ephemeral=ephemeral)
        chunks = chunks[1:]
    for chunk in chunks:
        await interaction.followup.send(chunk, ephemeral=ephemeral)


@command_tree.command(name="chat", description="Chat with pkla dog.")
@app_commands.describe(prompt="What you want to say")
async def chat(interaction: discord.Interaction, prompt: str) -> None:
    prompt = prompt.strip()
    if not prompt:
        await interaction.response.send_message("add a message", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    now = current_central_datetime()
    last_seen = last_message_at.get(user_id)
    if last_seen and (now - last_seen).total_seconds() < COOLDOWN_SECONDS:
        await interaction.followup.send("slow down a sec", ephemeral=True)
        return
    last_message_at[user_id] = now

    history_so_far = get_user_history(guild_id, user_id)
    user_text = prompt
    context_parts = []
    reply_style_guidance = short_casual_reply_guidance(prompt)
    if reply_style_guidance:
        context_parts.append(reply_style_guidance)
    if needs_time_context(prompt):
        context_parts.append(build_time_context())
    if needs_search(prompt):
        query = build_search_query(prompt, history_so_far)
        search_results = await web_search(query, recent=needs_recent_search(prompt))
        if search_results:
            context_parts.append(build_search_context(search_results, query))
        else:
            context_parts.append(
                "Live web search was attempted but returned no usable results. Tell the user you could not verify the current fact instead of guessing."
            )
    if context_parts:
        user_text += "\n\n" + "\n\n".join(context_parts)

    add_user_history(guild_id, user_id, "user", prompt)
    try:
        max_tokens = 60 if reply_style_guidance else DEFAULT_CHAT_MAX_COMPLETION_TOKENS
        reply = clean_reply(
            await call_model(
                history_so_far,
                user_text,
                max_tokens=max_tokens,
                display_name=getattr(interaction.user, "display_name", interaction.user.name),
            )
        )
        if reply_style_guidance:
            reply = keep_first_reply_line(reply)
        if not reply:
            raise ValueError("Empty response")
        add_user_history(guild_id, user_id, "assistant", reply)
        await send_interaction_chunks(interaction, reply)
    except Exception as error:
        pop_user_history(guild_id, user_id)
        logger.exception("Slash chat failed")
        await interaction.followup.send(error_reply(error), ephemeral=True)


@command_tree.command(name="search", description="Search the web and get a concise answer.")
@app_commands.describe(query="What to search for")
async def search_command(interaction: discord.Interaction, query: str) -> None:
    await interaction.response.defer(thinking=True)
    query = clean_search_query(query)
    search_results = await web_search(query, recent=True)
    if not search_results:
        await interaction.followup.send("couldn't find clear web results for that", ephemeral=True)
        return
    prompt = (
        "Answer this using the live web context. Do not list links or sources."
        f"\n\n{query}\n\n{build_search_context(search_results, query)}"
    )
    try:
        reply = clean_reply(await call_model([], prompt))
    except Exception as error:
        reply = error_reply(error, during_search=True)
    await send_interaction_chunks(interaction, reply)


@command_tree.command(name="reset", description="Clear your pkla dog chat context in this server.")
async def reset_command(interaction: discord.Interaction) -> None:
    clear_user_context(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message("chat context cleared", ephemeral=True)


@command_tree.command(name="delete-data", description="Delete all in-memory data pkla dog has for you.")
async def delete_data_command(interaction: discord.Interaction) -> None:
    removed_contexts = delete_all_user_data(interaction.user.id)
    await interaction.response.send_message(
        f"deleted your in-memory pkla dog data across {removed_contexts} context(s). The bot does not persist conversation history to a database.",
        ephemeral=True,
    )


@command_tree.command(name="join", description="Join your current voice channel and bark once.")
async def join_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("use /join in a server", ephemeral=True)
        return
    voice_state = getattr(interaction.user, "voice", None)
    voice_channel = getattr(voice_state, "channel", None)
    if voice_channel is None:
        await interaction.response.send_message("join a voice channel first", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(await join_voice_channel(voice_channel, interaction.guild))


@command_tree.command(name="leave", description="Disconnect pkla dog from voice.")
async def leave_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("use /leave in a server", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    await interaction.followup.send(await leave_guild_voice(interaction.guild))


@command_tree.command(name="bark", description="Play the bundled bark sound.")
async def bark_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(bark_on_command(interaction))


@command_tree.command(name="tts", description="Queue text-to-speech in the connected voice channel.")
@app_commands.describe(message="Text to speak")
async def tts_command(interaction: discord.Interaction, message: str) -> None:
    response = await speak_message(interaction, message.strip())
    await interaction.response.send_message(response or "queued")


@command_tree.command(name="ping", description="Mention a configured member without sending DMs.")
@app_commands.describe(target="Configured member name", message="Optional message after the mention")
async def ping_command(interaction: discord.Interaction, target: str, message: str | None = None) -> None:
    mention = PING_TARGETS.get(target.strip().lower())
    if mention is None:
        await interaction.response.send_message("unknown configured member", ephemeral=True)
        return
    suffix = f", {message.strip()}" if message and message.strip() else ""
    await interaction.response.send_message(f"{mention}{suffix}")


@command_tree.command(name="uptime", description="Show process uptime.")
async def uptime_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"uptime: {format_elapsed_time(time.monotonic() - BOT_STARTED_AT)}"
    )


@command_tree.command(name="coinflip", description="Flip a coin.")
async def coinflip_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(random.choice(("heads", "tails")))


@command_tree.command(name="roll", description="Roll dice such as d20 or 2d6.")
@app_commands.describe(expression="Dice expression, for example d20 or 2d6")
async def roll_command(interaction: discord.Interaction, expression: str = "1d6") -> None:
    await interaction.response.send_message(roll_dice_command(f"/roll {expression}"))


@command_tree.command(name="status", description="Show bot runtime feature status.")
async def status_slash_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(status_command_text(), ephemeral=True)


@command_tree.command(name="help", description="Show pkla dog commands.")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "Commands: `/chat`, `/search`, `/reset`, `/delete-data`, `/join`, `/leave`, `/bark`, `/tts`, `/ping`, `/uptime`, `/coinflip`, `/roll`, `/status`, `/listen-consent`, `/listen-revoke`, `/support`, `/birthdayryan`",
        ephemeral=True,
    )


@command_tree.command(name="support", description="Get support, privacy, and reporting links.")
async def support_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"Support/report: {PUBLIC_BASE_URL}/support\nPrivacy: {PUBLIC_BASE_URL}/privacy\nTerms: {PUBLIC_BASE_URL}/terms",
        ephemeral=True,
    )


@command_tree.command(name="listen-consent", description="Explicitly consent to optional live browser voice relay.")
async def listen_consent_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("use this in a server", ephemeral=True)
        return
    voice_state = getattr(interaction.user, "voice", None)
    voice_channel = getattr(voice_state, "channel", None)
    if voice_channel is None:
        await interaction.response.send_message("join the voice channel you want to consent in first", ephemeral=True)
        return
    key = voice_consent_key(voice_channel)
    voice_listen_consents.setdefault(key, set()).add(interaction.user.id)
    if interaction.channel_id is not None:
        voice_listen_notice_channels[key] = interaction.channel_id
    participants = voice_channel_participant_ids(voice_channel)
    consented = voice_listen_consents[key]
    remaining = len(participants - consented)
    if remaining:
        message = f"{interaction.user.mention} explicitly consented to live browser listen-in for {voice_channel.mention}. {remaining} current participant(s) still need to run `/listen-consent`."
    else:
        message = f"{interaction.user.mention} explicitly consented to live browser listen-in for {voice_channel.mention}. All current human participants have consented."
    await interaction.response.send_message(message)


@command_tree.command(name="listen-revoke", description="Revoke your live browser voice relay consent.")
async def listen_revoke_command(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("use this in a server", ephemeral=True)
        return
    voice_state = getattr(interaction.user, "voice", None)
    voice_channel = getattr(voice_state, "channel", None)
    if voice_channel is None:
        await interaction.response.send_message("join the voice channel first", ephemeral=True)
        return
    key = voice_consent_key(voice_channel)
    voice_listen_consents.get(key, set()).discard(interaction.user.id)
    if active_receive_channel_id == voice_channel.id:
        close_receive_session("Participant revoked consent")
        await notify_voice_listen(
            voice_channel,
            f"🔇 Live browser listen-in stopped because {interaction.user.mention} revoked consent.",
        )
    await interaction.response.send_message(
        f"{interaction.user.mention} revoked live browser listen-in consent for {voice_channel.mention}."
    )
'''

message_start = "@client.event\nasync def on_message(message):\n"
message_end = "\n\nasync def run_discord_client(token: str) -> None:\n"
bot = replace_span(bot, message_start, message_end, slash_block + "\n\nasync def run_discord_client(token: str) -> None:\n", "message handler")

bot_path.write_text(bot, encoding="utf-8")

# The verification entrypoint now only needs to force the opt-in voice feature off.
entry_path = ROOT / "verification_entry.py"
entry = entry_path.read_text(encoding="utf-8")
entry = entry.replace(
    "# These must be set before importing bot.py because the state store and client\n# configuration are created at import time.\nos.environ[\"PERSIST_STATE\"] = \"false\"\nos.environ[\"AUTO_MEMORY_ENABLED\"] = \"false\"\nos.environ[\"ENABLE_LISTEN_IN\"] = \"false\"\n",
    "# Browser voice receive is opt-in and stays off for the public deployment.\nos.environ[\"ENABLE_LISTEN_IN\"] = \"false\"\n",
)
entry = entry.replace(
    '        "Starting verification-safe deployment: persistence, auto-memory, "\n        "and browser listen-in are disabled"\n',
    '        "Starting verification-safe deployment: no persistent chat database, "\n        "no shared memory, no privileged message/member intents, and browser listen-in disabled by default"\n',
)
entry_path.write_text(entry, encoding="utf-8")

# Environment template: persistence/shared-memory toggles no longer exist.
env_path = ROOT / ".env.example"
env = env_path.read_text(encoding="utf-8")
env = re.sub(
    r"# Verification-safe privacy defaults\n# The default Procfile runs verification_entry.py, which forces these values off\n# for the public deployment even if a hosting environment contains older values\.\nENABLE_LISTEN_IN=false\nPERSIST_STATE=false\nAUTO_MEMORY_ENABLED=false\n",
    "# Optional browser voice receive. Keep false unless you intentionally enable the consent-gated feature.\nENABLE_LISTEN_IN=false\nPUBLIC_BASE_URL=https://pkladog.up.railway.app\n",
    env,
)
env = env.replace("TARGET_CHANNEL_IDS=\n", "")
env = env.replace("OWNER_ID=\n", "")
env_path.write_text(env, encoding="utf-8")

privacy = '''# pkla dog Privacy Policy\n\n**Last updated: August 7, 2026**\n\nThis policy explains how **pkla dog** handles data when you use the Discord application. pkla dog is an independent application and is not affiliated with Discord Inc.\n\n## Data processed\n\npkla dog processes the minimum Discord data needed to provide the feature you explicitly invoke. This can include your Discord user ID, display name, server/channel identifiers, slash-command inputs, voice-state information required for voice commands, and content you submit to `/chat`, `/search`, `/tts`, `/ping`, or the authenticated `/say` operator page.\n\nThe bot does **not** request Discord Message Content Intent or Server Members Intent. It does not read ordinary server messages for AI chat. AI chat is invoked through `/chat`.\n\n## Conversation context and storage\n\nChat context is kept **only in process memory** and is scoped to the invoking Discord user plus the current server (or DM context). It is bounded to recent messages and is lost on process restart or earlier cache eviction.\n\nThe public bot does **not** use the old SQLite persistence layer and does not provide shared/universal memory. There is no cross-server or cross-user memory feature.\n\nUse `/reset` to clear the current chat context. Use `/delete-data` to remove all in-memory conversation context and consent state associated with your Discord user ID across the running bot process.\n\n## AI and search providers\n\nWhen you explicitly use an AI or search feature, the content needed to fulfill that request may be sent to configured service providers. Depending on deployment configuration these can include Groq, OpenAI, DuckDuckGo/DDGS, Tavily, Brave Search, or SerpApi. Those providers process requests under their own terms and privacy policies.\n\nDiscord API data is not sold and is not used by pkla dog to train a machine-learning model.\n\n## Voice and audio\n\npkla dog can join voice channels, play sounds, and provide text-to-speech. Browser voice listen-in is **disabled by default**. An operator must intentionally enable `ENABLE_LISTEN_IN=true`, and the relay will still refuse to start until **every current human participant in that voice channel has explicitly run `/listen-consent`**. Consent and the notification channel are stored only in memory.\n\nWhen listen-in begins, the bot posts a visible notice in the text channel used for consent. If consent changes while listening is active, the relay stops and posts another notice. Participants can revoke consent with `/listen-revoke`. Incoming voice audio is relayed live and is not intentionally stored by the bot.\n\nUploaded audio for playback can be written to temporary files and is removed after validation failure, playback failure, or normal playback completion.\n\n## Authenticated `/say` controls\n\nThe operator web page requires `EXTERNAL_SAY_CONTROL_TOKEN` for control actions. The page can post messages, control voice playback, use TTS, and perform configured moderation actions when Discord permissions allow.\n\n## Retention and deletion\n\nThe bot intentionally avoids persistent Discord conversation storage. In-memory chat and consent state disappear when the process restarts. `/delete-data` removes the running process's retained user-specific context immediately.\n\nOperational logs may contain technical errors and identifiers needed to diagnose failures. The bot is not designed to log full conversations as an analytics dataset.\n\nFor a privacy request that cannot be handled by `/delete-data`, use the support/report page or the GitHub issue tracker:\n\n- https://pkladog.up.railway.app/support\n- https://github.com/coolxng/pkla-dog-bot/issues\n\nDo not post passwords, API keys, tokens, private message contents, or other secrets in a public issue.\n\n## Security\n\nSecrets are expected to be stored in deployment environment variables. The `/say` control surface is authenticated, uploads are bounded and validated, and public voice receive is off by default. No online service can guarantee perfect security.\n\n## Changes\n\nThis policy may be updated when the bot's functionality or data practices change. The current policy remains available at `/privacy` and in this repository.\n'''
(ROOT / "PRIVACY.md").write_text(privacy, encoding="utf-8")

terms = '''# pkla dog Terms of Service\n\n**Last updated: August 7, 2026**\n\nBy installing or using **pkla dog**, you agree to these terms and to Discord's applicable Terms, Community Guidelines, and Developer policies.\n\n## Acceptable use\n\nDo not use pkla dog to spam, harass, threaten, impersonate, evade moderation, violate privacy, distribute illegal content, or violate Discord rules or applicable law. Do not attempt to bypass the bot's authorization, consent, rate-limit, or safety controls.\n\n## Slash commands and AI output\n\nUser-facing Discord actions are provided through slash commands. AI and search output can be wrong or incomplete and should not be treated as professional, legal, financial, medical, or safety-critical advice. You are responsible for how you use generated output.\n\n## Voice features\n\nVoice playback must be used in servers where the bot has appropriate permissions. Browser voice listen-in is disabled by default and, when intentionally enabled by the operator, requires explicit consent from every current human participant before the relay can start. Do not attempt to bypass that consent requirement or use the feature in violation of law or Discord policy.\n\n## Operator controls\n\nThe `/say` control page is intended for authorized operators. Keep its control token secret. Server administrators are responsible for granting only the Discord permissions needed for the features they choose to enable.\n\n## Availability\n\npkla dog is provided as-is without a guarantee of uptime, uninterrupted service, or error-free output. Features may change or be removed when required for security, reliability, policy compliance, or maintenance.\n\n## Privacy\n\nUse of the bot is also governed by the [Privacy Policy](./PRIVACY.md), available on the deployed service at `/privacy`.\n\n## Support and reports\n\nSupport, abuse reports, and privacy requests are available at `/support` or through the project issue tracker: https://github.com/coolxng/pkla-dog-bot/issues\n'''
(ROOT / "TERMS.md").write_text(terms, encoding="utf-8")

support = '''# pkla dog Support and Reports\n\nUse this page for support, abuse reports, security reports, or privacy requests involving pkla dog.\n\n## Fastest options\n\n- Use `/delete-data` in Discord to immediately clear all user-specific data retained in the running bot process.\n- Use `/reset` to clear only your current server/DM chat context.\n- Open an issue at https://github.com/coolxng/pkla-dog-bot/issues for a support, privacy, or abuse request that needs maintainer action.\n\nFor security reports, describe the problem without publishing secrets, access tokens, private message contents, or exploit details that would put users at risk. Ask for private follow-up if sensitive evidence is required.\n\n## Voice consent\n\nUse `/listen-consent` only when you knowingly agree to the optional live browser voice relay for the voice channel you are currently in. Use `/listen-revoke` at any time to withdraw consent; an active relay stops when consent changes.\n\nPublic policy pages:\n\n- https://pkladog.up.railway.app/privacy\n- https://pkladog.up.railway.app/terms\n'''
(ROOT / "SUPPORT.md").write_text(support, encoding="utf-8")

verification = '''# Discord Verification Readiness\n\nThis branch completes the repository-side verification hardening for pkla dog.\n\n## Implemented\n\n- repeated-DM `/pingdeaf` implementation removed\n- legacy Poke ingest/`POKE_INGEST_URL` removed\n- public `/terms`, `/privacy`, and `/support` pages\n- `/support` slash command and GitHub report path\n- `/delete-data` removes all in-memory user chat/consent data\n- SQLite conversation persistence removed from the application\n- shared/universal memory and automatic memory extraction removed\n- browser listen-in defaults off and requires explicit consent from every current human participant plus visible start/stop notifications\n- legacy `!` command handling removed in favor of slash commands\n- Message Content Intent disabled\n- Server Members Intent disabled\n\n## Developer Portal\n\nUse these URLs after Railway deploys the merged `main` branch:\n\n- Terms: https://pkladog.up.railway.app/terms\n- Privacy: https://pkladog.up.railway.app/privacy\n\nThen complete Team Owner Identity Verification in Discord's Developer Portal and confirm all verification qualifications are green.\n\nNo repository change can complete Discord's identity-verification step for the Team owner.\n'''
(ROOT / "VERIFICATION.md").write_text(verification, encoding="utf-8")

readme = '''# pkla dog Discord Bot\n\nA Python Discord bot with slash-command AI chat, web search, voice playback/TTS, authenticated browser controls, and verification-focused privacy defaults.\n\n- [Terms of Service](./TERMS.md)\n- [Privacy Policy](./PRIVACY.md)\n- [Support and reports](./SUPPORT.md)\n- [Verification checklist](./VERIFICATION.md)\n\n## Discord verification posture\n\nThe public deployment uses `python verification_entry.py` and does not request **Message Content Intent** or **Server Members Intent**. Ordinary server messages are not used for AI chat; use `/chat`.\n\nThere is no persistent conversation database and no shared/universal memory. Chat context is in-memory only and scoped to the invoking user plus the current guild/DM context.\n\n## Commands\n\n| Command | Description |\n| --- | --- |\n| `/chat <prompt>` | Chat with pkla dog. |\n| `/search <query>` | Search the web and get a concise answer. |\n| `/reset` | Clear your current chat context. |\n| `/delete-data` | Delete all in-memory data associated with your Discord user ID. |\n| `/join` | Join your current voice channel and bark once. |\n| `/leave` | Leave the current voice channel. |\n| `/bark` | Play the bundled bark sound. |\n| `/tts <message>` | Queue text-to-speech in voice. |\n| `/ping <target> [message]` | Mention a configured member without sending a DM. |\n| `/uptime` | Show process uptime. |\n| `/coinflip` | Flip a coin. |\n| `/roll [expression]` | Roll dice such as `d20` or `2d6`. |\n| `/status` | Show runtime feature status. |\n| `/listen-consent` | Explicitly consent to optional live browser voice relay in your current voice channel. |\n| `/listen-revoke` | Revoke voice relay consent; an active relay stops. |\n| `/support` | Show support, privacy, Terms, and reporting links. |\n| `/birthdayryan` | Send the bundled birthday embed. |\n\nThe old `!` message-command handler, shared memory commands, `/pingdeaf`, and Poke ingest are removed.\n\n## Voice listen-in consent\n\n`ENABLE_LISTEN_IN` defaults to `false`. Even if an operator intentionally sets it to `true`, the browser receive path refuses to start unless **every current human participant** in the selected voice channel has run `/listen-consent`. A visible message is posted when listen-in starts and when it stops because consent changes. Incoming audio is relayed live and is not intentionally stored.\n\n## Data deletion\n\n`/delete-data` clears every in-memory chat context associated with the invoking Discord user ID and removes that user's voice consent state. The application no longer uses the old plaintext SQLite conversation persistence layer.\n\n## Required environment variables\n\n| Variable | Required | Description |\n| --- | --- | --- |\n| `DISCORD_TOKEN` | Yes | Discord bot token. |\n| `GROQ_API_KEY` | Yes for AI chat | Groq key for normal `/chat` responses. |\n| `OPENAI_API_KEY` | For OpenAI features | Optional chat fallback, search, and TTS. |\n| `PING_MEMBERS_JSON` | Optional | JSON mapping `/ping` target names to Discord user IDs. |\n| `EXTERNAL_SAY_CONTROL_TOKEN` | Required for `/say` controls | Secret protecting the operator web UI. |\n| `EXTERNAL_CHANNEL_ID` | Optional | Default text channel for `/say`. |\n| `EXTERNAL_VOICE_CHANNEL_ID` | Optional | Default voice channel for `/say`. |\n| `PUBLIC_BASE_URL` | Optional | Public policy/support base URL. Defaults to `https://pkladog.up.railway.app`. |\n\n## Optional settings\n\n`ENABLE_LISTEN_IN=false` is the safe default. Set it to `true` only if you intentionally want the consent-gated browser voice relay. Other optional provider/model settings remain documented in `.env.example`.\n\n## Railway\n\nThe `Procfile` starts `python verification_entry.py`. If Railway has a manual Start Command override, set it to the same command. After deployment verify:\n\n- https://pkladog.up.railway.app/terms\n- https://pkladog.up.railway.app/privacy\n- https://pkladog.up.railway.app/support\n\nUse the Terms and Privacy URLs in Discord's Developer Portal. The Team owner must complete Discord Identity Verification manually.\n\n## `/say` operator page\n\n`/say` remains an authenticated operator control surface for posting messages, voice join/leave, audio playback, TTS, uploads, and configured moderation controls. Keep `EXTERNAL_SAY_CONTROL_TOKEN` secret. Browser incoming-audio relay is separately protected by the consent gate described above.\n'''
(ROOT / "README.md").write_text(readme, encoding="utf-8")

# Remove tests tied to the deleted message-handler/persistence/shared-memory architecture.
test_path = ROOT / "tests" / "test_bot.py"
tests = test_path.read_text(encoding="utf-8")
tests = remove_test_classes_containing(
    tests,
    (
        "bot.on_message",
        "state_store",
        "universal_memory",
        "auto_extract_memory",
        "get_active_history",
        "add_to_active_history",
        "clear_active_history",
        "record_command_exchange",
        "format_user_history_content",
        "channel_conversation_history",
    ),
)
tests = tests.replace("self.assertTrue(bot.intents.message_content)", "self.assertFalse(bot.intents.message_content)")
for old, new in (
    ("!join", "/join"),
    ("!leave", "/leave"),
    ("!bark", "/bark"),
    ("!tts", "/tts"),
    ("!reset", "/reset"),
    ("!search", "/search"),
    ("!help", "/help"),
    ("!uptime", "/uptime"),
    ("!coinflip", "/coinflip"),
    ("!roll", "/roll"),
    ("!status", "/status"),
):
    tests = tests.replace(old, new)

tests += '''\n\nclass VerificationReadyArchitectureTests(unittest.TestCase):\n    def test_no_privileged_message_or_member_intents(self):\n        self.assertFalse(bot.intents.message_content)\n        self.assertFalse(bot.intents.members)\n\n    def test_message_event_handler_is_removed(self):\n        self.assertFalse(hasattr(bot, "on_message"))\n\n    def test_required_slash_commands_are_registered(self):\n        names = {command.name for command in bot.command_tree.get_commands()}\n        expected = {\n            "chat", "search", "reset", "delete-data", "join", "leave", "bark",\n            "tts", "ping", "uptime", "coinflip", "roll", "status", "help",\n            "support", "listen-consent", "listen-revoke", "birthdayryan",\n        }\n        self.assertTrue(expected.issubset(names))\n\n    def test_user_data_is_scoped_and_deletable(self):\n        bot.conversation_history.clear()\n        bot.voice_listen_consents.clear()\n        bot.add_user_history(10, 123, "user", "hello")\n        bot.add_user_history(20, 123, "assistant", "yo")\n        bot.add_user_history(10, 456, "user", "other")\n        bot.voice_listen_consents[(10, 99)] = {123, 456}\n        removed = bot.delete_all_user_data(123)\n        self.assertEqual(removed, 2)\n        self.assertEqual(bot.get_user_history(10, 123), [])\n        self.assertEqual(bot.get_user_history(20, 123), [])\n        self.assertEqual(bot.get_user_history(10, 456), [{"role": "user", "content": "other"}])\n        self.assertEqual(bot.voice_listen_consents[(10, 99)], {456})\n\n    def test_listen_in_default_is_off(self):\n        with patch.dict(bot.os.environ, {}, clear=False):\n            bot.os.environ.pop("ENABLE_LISTEN_IN", None)\n            self.assertFalse(bot.env_bool("ENABLE_LISTEN_IN", False))\n'''
test_path.write_text(tests, encoding="utf-8")
