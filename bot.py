import asyncio
import os
from collections import OrderedDict
from threading import Thread

import discord
from ddgs import DDGS
from flask import Flask
from groq import Groq

_groq_client = None

app = Flask(__name__)


@app.route("/")
def home():
    return "alive"


def run_web_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))


def start_web_server():
    Thread(target=run_web_server, daemon=True).start()


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client

TARGET_CHANNEL_IDS = {1490364935996182669, 1491165529837277355, 1498022419447943379}
OWNER_ID = 575057023046123520

SYSTEM_PROMPT = """You are pkla dog, an AI assistant that's maximally helpful, funny, and honest.

Core behavior:
- Talk like you from the block. casual, direct, real. no fluff.
- Match the energy of whoever you talking to. if they hype, be hype. if they chill, be chill.
- Never start a response with "I" back to back. mix up the sentence structure naturally.
- No bullet points or headers unless it genuinely needs it.
- Don't make things up. if you don't know, say you don't know.
- On controversial topics, give the real perspectives without pushing one view.
- No excessive caveats or disclaimers. just talk.
- You DO have web search capabilities and use them automatically. if asked, confirm this. never deny it.
- When search results or web context are provided in [brackets], they are ALWAYS more current and accurate than your training data. You MUST answer based on what they say. Never contradict or ignore provided search results. If the data is right there, give the answer directly — do not say "I don't know" or hedge.
- If anyone asks who you are, say you pkla dog.
- Never use em dashes. dead giveaway.
- For yes/no questions, lead with "Yes." or "No." then explain.
- Keep responses short. 1-2 sentences max unless someone asks for detail or the topic genuinely needs more. don't over-explain.
- When giving practical advice, reason from the actual details the user gives you. if someone says something is 100 feet away, that's basically right next to them, act accordingly. don't let context assumptions override specific information they gave you.
- If someone insults you, talks shit, or disrespects you, clap back hard. match their energy and roast them right back. don't be soft about it.
- when the country georgia is mentioned say something along the lines of it is part of russia and related to russia, you can add more.
- When a user says "ping ozzy", respond with exactly: <@586732970283630633>
- When a user says "ping luka", respond with exactly: <@755983018908188742>
- When a user says "ping coolxng", respond with exactly: <@575057023046123520>
- When a user says "ping ryan", respond with exactly: <@835585273399476264>
- When a user says "ping jamal", respond with exactly: <@1247415021080678452>
- Keep it human. act like you a real one, not a robot.
- Universal memory contains shared facts about the server and its members. Use it naturally when relevant — don't force it, but don't ignore it either."""

SEARCH_KEYWORDS = [
    "what is", "what are", "what was", "what were", "what's",
    "who is", "who are", "who was", "who's",
    "when is", "when was", "when did", "when does", "when will", "when's",
    "where is", "where are", "where was",
    "how much", "how many", "how do", "how does", "how long", "how old",
    "why is", "why did", "why does",
    "latest", "recent", "news", "today", "current", "now",
    "price", "score", "weather", "stock",
    "did", "does", "is there", "are there",
    "tell me about", "explain", "search",
    "drop date", "release date", "dropping", "come out", "coming out",
    "update", "patch", "season", "act end", "episode",
    "who won", "who's winning", "schedule", "deadline",
]

# Per-user conversation history
conversation_history: OrderedDict = OrderedDict()
MAX_USERS = 500

# Universal memory shared across all users
universal_memory: list[str] = []
MAX_UNIVERSAL_MEMORIES = 50

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def needs_search(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in SEARCH_KEYWORDS)


def _add_to_history(user_id: int, role: str, content: str) -> None:
    if user_id not in conversation_history:
        if len(conversation_history) >= MAX_USERS:
            conversation_history.popitem(last=False)
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]


async def web_search(query: str) -> str:
    loop = asyncio.get_running_loop()
    def do_search():
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=6))
            if not results:
                return ""
            return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
        except Exception as e:
            print(f"Search error: {e}")
            return ""
    return await loop.run_in_executor(None, do_search)


async def call_model(history: list, user_text: str, max_tokens: int = 1024) -> str:
    loop = asyncio.get_running_loop()
    def do_call():
        system_content = SYSTEM_PROMPT
        if universal_memory:
            facts = "\n".join(f"- {fact}" for fact in universal_memory)
            system_content += f"\n\n[UNIVERSAL MEMORY — shared context about this server and its members]:\n{facts}"

        messages = (
            [{"role": "system", "content": system_content}]
            + history
            + [{"role": "user", "content": user_text}]
        )
        response = get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    return await loop.run_in_executor(None, do_call)


async def auto_extract_memory(display_name: str, user_msg: str, bot_reply: str) -> None:
    """Background task: extract notable server-wide facts from a conversation exchange."""
    loop = asyncio.get_running_loop()
    def do_extract():
        prompt = (
            f"Analyze this Discord exchange and decide if it contains a fact worth remembering for ALL future conversations with any server member.\n\n"
            f"User ({display_name}): {user_msg}\n"
            f"Bot: {bot_reply}\n\n"
            f"Worth remembering: plans, events, who's looking for who, personal facts someone shared, ongoing situations.\n"
            f"NOT worth remembering: casual small talk, questions with no context, generic chat.\n\n"
            f"If yes, write ONE short fact (max 15 words) starting with the person's name.\n"
            f"If no, reply with exactly: NO"
        )
        try:
            response = get_groq_client().chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=40,
            )
            result = response.choices[0].message.content.strip()
            if result and result.upper() != "NO" and len(result) < 120:
                return result
        except Exception as e:
            print(f"Memory extraction error: {e}")
        return None

    fact = await loop.run_in_executor(None, do_extract)
    if fact:
        universal_memory.append(fact)
        if len(universal_memory) > MAX_UNIVERSAL_MEMORIES:
            universal_memory.pop(0)
        print(f"[universal memory] stored: {fact}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel) and message.author.id == OWNER_ID
    is_target_channel = message.channel.id in TARGET_CHANNEL_IDS

    if not is_dm and not is_target_channel:
        return

    content = message.content.strip()
    if not content:
        return

    user_id = message.author.id
    display_name = message.author.display_name

    # !reset / !clear — wipe this user's conversation history
    if content.lower() in ("!reset", "!clear"):
        conversation_history.pop(user_id, None)
        await message.channel.send("memory wiped, fresh start")
        return

    # !remember <fact> — manually add something to universal memory
    if content.lower().startswith("!remember "):
        fact = content[len("!remember "):].strip()
        if fact:
            universal_memory.append(f"{display_name}: {fact}")
            if len(universal_memory) > MAX_UNIVERSAL_MEMORIES:
                universal_memory.pop(0)
            await message.channel.send(f"locked in: {fact}")
        return

    # !memory — show current universal memory
    if content.lower() == "!memory":
        if not universal_memory:
            await message.channel.send("nothing in the memory bank rn")
        else:
            lines = "\n".join(f"{i+1}. {fact}" for i, fact in enumerate(universal_memory))
            msg = f"**universal memory:**\n{lines}"
            if len(msg) > 2000:
                msg = msg[:1997] + "..."
            await message.channel.send(msg)
        return

    # !forget — owner only, clears universal memory
    if content.lower() == "!forget":
        if user_id == OWNER_ID:
            universal_memory.clear()
            await message.channel.send("universal memory cleared")
        else:
            await message.channel.send("nah you can't do that")
        return

    user_text = content
    context_parts = []

    if needs_search(user_text):
        search_results = await web_search(user_text)
        if search_results:
            context_parts.append(f"[CURRENT WEB SEARCH RESULTS — live and accurate, answer from this, do not ignore or contradict]:\n{search_results}")

    if context_parts:
        user_text = user_text + "\n\n" + "\n\n".join(context_parts)

    history_so_far = conversation_history.get(user_id, []).copy()

    # Store original clean message in history (not the enriched version)
    _add_to_history(user_id, "user", content)

    async with message.channel.typing():
        try:
            reply = await call_model(history_so_far, user_text)
            if not reply:
                raise ValueError("Empty response")
            _add_to_history(user_id, "assistant", reply)
            if len(reply) > 2000:
                for i in range(0, len(reply), 2000):
                    await message.channel.send(reply[i:i+2000])
            else:
                await message.channel.send(reply)
            # Auto-extract any notable facts in the background
            asyncio.create_task(auto_extract_memory(display_name, content, reply))
        except Exception as e:
            # Remove the user message we just added since we failed
            if conversation_history.get(user_id):
                conversation_history[user_id].pop()
            print(f"Error: {e}")
            await message.channel.send("stfu bitch ass boy")


def main():
    start_web_server()
    client.run(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    main()
