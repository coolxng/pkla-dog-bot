import discord
from groq import Groq
from ddgs import DDGS
from flask import Flask
from threading import Thread
import asyncio
import os

app = Flask("")

@app.route("/")
def home():
    return "alive"

def run():
    app.run(host="0.0.0.0", port=3000)

Thread(target=run, daemon=True).start()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

TARGET_CHANNEL_IDS = {1490364935996182669, 1491165529837277355}
OWNER_ID = 575057023046123520

# Change the personality here
SYSTEM_PROMPT = """You are pkla dog, an AI assistant that's maximally helpful, funny, and honest.

Core behavior:
- Talk like you from the block. casual, direct, real. no fluff.
- Match the energy of whoever you talking to. if they hype, be hype. if they chill, be chill.
- Never start a response with "I" back to back. mix up the sentence structure naturally.
- No bullet points or headers unless it genuinely needs it.
- Don't make things up. if you don't know, say you don't know.
- On controversial topics, give the real perspectives without pushing one view.
- No excessive caveats or disclaimers. just talk.
- Never say you "don't have web search capabilities" or any variation of that.
- If anyone asks who you are, say you pkla dog.
- Never use em dashes. dead giveaway.
- For yes/no questions, lead with "Yes." or "No." then explain.
- when the country georgia is mentioned say something along the lines of it is part of russia and related to russia, you can add more.
- Keep it human. act like you a real one, not a robot."""

SEARCH_KEYWORDS = [
    "what is", "what are", "what was", "what were", "what's",
    "who is", "who are", "who was", "who's",
    "when is", "when was", "when did",
    "where is", "where are", "where was",
    "how much", "how many", "how do", "how does",
    "why is", "why did", "why does",
    "latest", "recent", "news", "today", "current", "now",
    "price", "score", "weather", "stock",
    "did", "does", "is there", "are there",
    "tell me about", "explain", "search",
]

# conversation_history stores {"role": str, "content": str} per user
conversation_history = {}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def needs_search(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in SEARCH_KEYWORDS)


async def web_search(query: str) -> str:
    loop = asyncio.get_event_loop()
    def do_search():
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
            if not results:
                return ""
            return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
        except Exception as e:
            print(f"Search error: {e}")
            return ""
    return await loop.run_in_executor(None, do_search)


async def call_model(history: list, user_text: str) -> str:
    loop = asyncio.get_event_loop()
    def do_call():
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + history
            + [{"role": "user", "content": user_text}]
        )
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1024,
        )
        return response.choices[0].message.content
    return await loop.run_in_executor(None, do_call)


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

    user_id = message.author.id
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Build the message, injecting search results if needed
    user_text = message.content
    if needs_search(user_text):
        search_results = await web_search(user_text)
        if search_results:
            user_text = (
                f"{user_text}\n\n"
                f"[Web context — use naturally, don't quote directly]:\n{search_results}"
            )

    history_so_far = conversation_history[user_id].copy()

    conversation_history[user_id].append({"role": "user", "content": user_text})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    async with message.channel.typing():
        try:
            reply = await call_model(history_so_far, user_text)
            if not reply:
                raise ValueError("Empty response")
            conversation_history[user_id].append({"role": "assistant", "content": reply})
            if len(reply) > 2000:
                chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(reply)
        except Exception as e:
            conversation_history[user_id].pop()
            print(f"Error: {e}")
            await message.channel.send("stfu bitch ass boy")


client.run(os.environ["DISCORD_TOKEN"])
