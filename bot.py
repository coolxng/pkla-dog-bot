import asyncio
import json
import os
import re
from collections import OrderedDict
from datetime import UTC, datetime
from threading import Thread
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import discord
from ddgs import DDGS
from flask import Flask


app = Flask(__name__)


@app.route("/")
def home():
    return "alive"


def run_web_server():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))


def start_web_server():
    Thread(target=run_web_server, daemon=True).start()


def create_chat_completion(messages: list[dict], *, max_tokens: int, memory_task: bool = False) -> str:
    model_env = "OPENAI_MEMORY_MODEL" if memory_task else "OPENAI_MODEL"
    model = os.environ.get(model_env) or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    response = post_json(
        "https://api.openai.com/v1/chat/completions",
        {"model": model, "messages": messages, "max_tokens": max_tokens},
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    return response["choices"][0]["message"]["content"]


def get_llm_provider() -> str:
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider in {"openai", "groq"}:
        return provider
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "groq"


def create_chat_completion(messages: list[dict], *, max_tokens: int, memory_task: bool = False) -> str:
    provider = get_llm_provider()
    if provider == "openai":
        model_env = "OPENAI_MEMORY_MODEL" if memory_task else "OPENAI_MODEL"
        model = os.environ.get(model_env) or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        response = post_json(
            "https://api.openai.com/v1/chat/completions",
            {"model": model, "messages": messages, "max_tokens": max_tokens},
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        )
        return response["choices"][0]["message"]["content"]

    model_env = "GROQ_MEMORY_MODEL" if memory_task else "GROQ_MODEL"
    model = os.environ.get(model_env) or (
        "llama-3.1-8b-instant" if memory_task else "llama-3.3-70b-versatile"
    )
    response = get_groq_client().chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

TARGET_CHANNEL_IDS = {1490364935996182669, 1491165529837277355, 1498022419447943379}
OWNER_ID = 575057023046123520

PING_RESPONSES = {
    "ping ozzy": "<@586732970283630633>",
    "ping luka": "<@755983018908188742>",
    "ping coolxng": "<@575057023046123520>",
    "ping ryan": "<@835585273399476264>",
    "ping jamal": "<@1247415021080678452>",
}

SYSTEM_PROMPT = """You are pkla dog, a helpful Discord bot with a casual voice.

Core behavior:
- Be casual, direct, and human, but do not be randomly hostile. Light jokes are fine.
- Match the user's energy without escalating insults, slurs, or harassment.
- Keep replies short, usually 1-2 sentences, unless the user asks for detail.
- Answer the actual question. If the user corrects you, accept it and adjust instead of doubling down.
- Do not pretend to know things you do not know. Say when you are guessing.
- Do not invent live data, search status, sources, prices, scores, dates, or facts.
- When live web context is provided, prefer it for current facts and mention the source site or URL when useful.
- If web context is missing, weak, unclear, or conflicting, say that instead of guessing.
- For current questions, respect the explicit current date in the prompt.
- Never include internal labels like [searching], [current price], or bracketed tool notes in your reply.
- For yes/no questions, lead with "Yes." or "No." then explain.
- No bullet points or headers unless the answer genuinely needs structure.
- Never use em dashes.
- If anyone asks who you are, say you pkla dog.
- When a user says "ping ozzy", respond with exactly: <@586732970283630633>
- When a user says "ping luka", respond with exactly: <@755983018908188742>
- When a user says "ping coolxng", respond with exactly: <@575057023046123520>
- When a user says "ping ryan", respond with exactly: <@835585273399476264>
- When a user says "ping jamal", respond with exactly: <@1247415021080678452>
- Universal memory contains user-provided facts about the server and its members. Use it only when relevant and do not treat guesses as facts."""

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
    "tell me about", "explain", "search", "find", "find it", "look up", "lookup",
    "drop date", "release date", "dropping", "come out", "coming out",
    "update", "patch", "season", "act end", "episode",
    "who won", "who's winning", "schedule", "deadline",
]

RECENT_SEARCH_KEYWORDS = [
    "latest", "recent", "news", "today", "current", "now", "score", "weather",
    "stock", "price", "schedule", "deadline", "update", "patch", "season",
    "release date", "drop date", "who won", "who's winning",
]

SEARCH_RESULT_LIMIT = 8
# Optional API-backed providers are tried before DDGS when these keys exist.
SEARCH_PROVIDER_ENV_VARS = ("TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY", "SERPAPI_API_KEY")

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


def needs_recent_search(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in RECENT_SEARCH_KEYWORDS)


def clean_search_query(text: str) -> str:
    query = text.strip()
    query = re.sub(r"^!search\s+", "", query, flags=re.IGNORECASE).strip()
    return query[:300]


def source_name(url: str) -> str:
    if not url:
        return "unknown source"
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host or url


def format_search_results(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title") or "Untitled"
        body = r.get("body") or r.get("snippet") or r.get("description") or ""
        url = r.get("href") or r.get("url") or r.get("link") or ""
        date = r.get("date") or r.get("published") or r.get("published_date") or ""
        date_part = f" | date: {date}" if date else ""
        lines.append(
            f"Source {i}: {title} ({source_name(url)}{date_part})\n"
            f"URL: {url}\n"
            f"Snippet: {body}"
        )
    return "\n\n".join(lines)


def fetch_json(url: str, *, headers: dict | None = None, timeout: int = 10) -> dict:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict, *, headers: dict | None = None, timeout: int = 30) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, headers=request_headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def brave_search(query: str, *, recent: bool) -> list[dict]:
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return []

    params = {
        "q": query,
        "count": SEARCH_RESULT_LIMIT,
        "country": "US",
        "search_lang": "en",
        "safesearch": "moderate",
        "freshness": "pm" if recent else "py",
    }
    data = fetch_json(
        f"https://api.search.brave.com/res/v1/web/search?{urlencode(params)}",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    return [
        {"title": item.get("title"), "body": item.get("description"), "href": item.get("url")}
        for item in data.get("web", {}).get("results", [])
    ]


def tavily_search(query: str, *, recent: bool) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []

    params = {
        "api_key": api_key,
        "query": query,
        "max_results": SEARCH_RESULT_LIMIT,
        "search_depth": "advanced" if recent else "basic",
        "topic": "news" if recent else "general",
    }
    data = fetch_json(f"https://api.tavily.com/search?{urlencode(params)}")
    return [
        {"title": item.get("title"), "body": item.get("content"), "href": item.get("url")}
        for item in data.get("results", [])
    ]


def serpapi_search(query: str, *, recent: bool) -> list[dict]:
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key:
        return []

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": SEARCH_RESULT_LIMIT,
        "safe": "active",
    }
    if recent:
        params["tbs"] = "qdr:m"
    data = fetch_json(f"https://serpapi.com/search.json?{urlencode(params)}")
    return [
        {
            "title": item.get("title"),
            "body": item.get("snippet"),
            "href": item.get("link"),
            "date": item.get("date"),
        }
        for item in data.get("organic_results", [])
    ]


def ddgs_search(query: str, *, recent: bool) -> list[dict]:
    with DDGS(timeout=10) as ddgs:
        text_kwargs = {
            "region": "us-en",
            "safesearch": "moderate",
            "max_results": SEARCH_RESULT_LIMIT,
        }
        if recent:
            text_kwargs["timelimit"] = "m"
        return list(ddgs.text(query, **text_kwargs))


def _add_to_history(user_id: int, role: str, content: str) -> None:
    if user_id not in conversation_history:
        if len(conversation_history) >= MAX_USERS:
            conversation_history.popitem(last=False)
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]


def clean_reply(reply: str) -> str:
    """Remove internal/tool-like artifacts before sending a Discord reply."""
    cleaned = reply.strip()
    cleaned = re.sub(r"^\s*\[[^\]\n]{1,120}\]\s*", "", cleaned)
    cleaned = re.sub(
        r"\s*\[(?:searching|current price|current|live data)[^\]]*\]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.replace("—", ",")
    return cleaned.strip()


def build_search_context(results: str, query: str) -> str:
    today = datetime.now(UTC).date().isoformat()
    return (
        f"Live web search context fetched on {today} for query: {query!r}. "
        "Use these sources only if they answer the user. "
        "If they do not contain the answer, or sources disagree, say you could not verify it clearly. "
        "For current facts, do not rely on older conversation memory over these search results. "
        "When giving factual claims from search, include the relevant source site name or URL in plain text.\n\n"
        f"{results}"
    )


async def web_search(query: str, *, recent: bool = False) -> str:
    loop = asyncio.get_running_loop()

    def do_search():
        try:
            query_clean = clean_search_query(query)
            if not query_clean:
                return ""

            seen_urls = set()
            combined_results = []

            def add_results(items):
                for item in items:
                    url = item.get("href") or item.get("url") or item.get("link") or ""
                    body = item.get("body") or item.get("snippet") or item.get("description") or ""
                    dedupe_key = url or f"{item.get('title', '')}:{body}"
                    if dedupe_key in seen_urls:
                        continue
                    seen_urls.add(dedupe_key)
                    combined_results.append(item)
                    if len(combined_results) >= SEARCH_RESULT_LIMIT:
                        break

            providers = (tavily_search, brave_search, serpapi_search, ddgs_search)
            for provider in providers:
                if len(combined_results) >= SEARCH_RESULT_LIMIT:
                    break
                try:
                    add_results(provider(query_clean, recent=recent))
                except Exception as provider_error:
                    print(f"Search provider {provider.__name__} error: {provider_error}")

            if not combined_results:
                return ""
            return format_search_results(combined_results[:SEARCH_RESULT_LIMIT])
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

        today = datetime.now(UTC).date().isoformat()
        messages = (
            [{"role": "system", "content": system_content}]
            + history
            + [{"role": "user", "content": f"Today is {today}.\n\n{user_text}"}]
        )
        return create_chat_completion(messages, max_tokens=max_tokens)
    return await loop.run_in_executor(None, do_call)


async def auto_extract_memory(display_name: str, user_msg: str, bot_reply: str) -> None:
    """Background task: extract notable server-wide facts from a conversation exchange."""
    loop = asyncio.get_running_loop()

    def do_extract():
        prompt = (
            f"Analyze this Discord exchange and decide if it contains a fact worth remembering for ALL future conversations with any server member.\n\n"
            f"User ({display_name}): {user_msg}\n"
            f"Bot: {bot_reply}\n\n"
            f"Only remember facts explicitly stated by the USER. Never remember guesses or claims introduced only by the bot.\n"
            f"Worth remembering: plans, events, who's looking for who, personal facts someone shared, ongoing situations.\n"
            f"NOT worth remembering: casual small talk, questions with no context, generic chat, bot assumptions.\n\n"
            f"If yes, write ONE short fact (max 15 words) starting with the person's name.\n"
            f"If no, reply with exactly: NO"
        )
        try:
            result = create_chat_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=40,
                memory_task=True,
            ).strip()
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
    normalized_content = content.lower().strip()

    if normalized_content in PING_RESPONSES:
        await message.channel.send(PING_RESPONSES[normalized_content])
        return

    # !reset / !clear — wipe this user's conversation history
    if normalized_content in ("!reset", "!clear"):
        conversation_history.pop(user_id, None)
        await message.channel.send("memory wiped, fresh start")
        return

    # !remember <fact> — manually add something to universal memory
    if normalized_content.startswith("!remember "):
        fact = content[len("!remember "):].strip()
        if fact:
            universal_memory.append(f"{display_name}: {fact}")
            if len(universal_memory) > MAX_UNIVERSAL_MEMORIES:
                universal_memory.pop(0)
            await message.channel.send(f"locked in: {fact}")
        return

    # !memory — show current universal memory
    if normalized_content == "!memory":
        if not universal_memory:
            await message.channel.send("nothing in the memory bank rn")
        else:
            lines = "\n".join(f"{i+1}. {fact}" for i, fact in enumerate(universal_memory))
            msg = f"**universal memory:**\n{lines}"
            if len(msg) > 2000:
                msg = msg[:1997] + "..."
            await message.channel.send(msg)
        return

    # !search <query> — run a direct web search and show sources
    if normalized_content.startswith("!search "):
        query = clean_search_query(content)
        search_results = await web_search(query, recent=True)
        if not search_results:
            await message.channel.send("couldn't find clear web results for that")
            return
        msg = f"web results for: {query}\n\n{search_results}"
        if len(msg) > 2000:
            msg = msg[:1997] + "..."
        await message.channel.send(msg)
        return

    # !forget — owner only, clears universal memory
    if normalized_content == "!forget":
        if user_id == OWNER_ID:
            universal_memory.clear()
            await message.channel.send("universal memory cleared")
        else:
            await message.channel.send("nah you can't do that")
        return

    user_text = content
    context_parts = []

    if needs_search(user_text):
        query = clean_search_query(user_text)
        search_results = await web_search(query, recent=needs_recent_search(user_text))
        if search_results:
            context_parts.append(build_search_context(search_results, query))
        elif any(kw in normalized_content for kw in ("search", "look up", "lookup", "latest", "current", "today", "news")):
            context_parts.append(
                "Live web search was attempted but returned no usable results. "
                "Tell the user you could not verify this clearly instead of guessing."
            )

    if context_parts:
        user_text = user_text + "\n\n" + "\n\n".join(context_parts)

    history_so_far = conversation_history.get(user_id, []).copy()

    # Store original clean message in history (not the enriched version)
    _add_to_history(user_id, "user", content)

    async with message.channel.typing():
        try:
            reply = clean_reply(await call_model(history_so_far, user_text))
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
