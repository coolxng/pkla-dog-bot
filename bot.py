import asyncio
import json
import os
import re
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from urllib.error import HTTPError
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


DEFAULT_OPENAI_MODEL = "chat-latest"
CENTRAL_TIME = ZoneInfo("America/Chicago")
DEFAULT_OPENAI_WEB_SEARCH_TOOL = "web_search"
DEFAULT_TARGET_CHANNEL_IDS = {1490364935996182669, 1491165529837277355, 1498022419447943379}
DEFAULT_OWNER_ID = 575057023046123520
COOLDOWN_SECONDS = 2


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_int_set_env(name: str, default: set[int]) -> set[int]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default

    values = set()
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.add(int(part))
        except ValueError:
            print(f"Ignoring invalid integer in {name}: {part!r}")
    return values or default


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        print(f"Ignoring invalid integer for {name}: {raw_value!r}")
        return default

def current_date_text() -> str:
    today = current_central_datetime()
    return f"{today.month}/{today.day}/{today:%y}"

def current_central_datetime() -> datetime:
    return datetime.now(CENTRAL_TIME)


def current_date_text() -> str:
    today = current_central_datetime()
    return f"{today.month}/{today.day}/{today:%y}"


def current_datetime_text() -> str:
    now = current_central_datetime()
    return f"{now.month}/{now.day}/{now:%y} {now:%-I:%M %p} CT"


def model_supports_reasoning_effort(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def default_reasoning_effort(model: str) -> str:
    if model.startswith("gpt-5"):
        return "none"
    return "minimal"


def create_chat_completion(messages: list[dict], *, max_tokens: int, memory_task: bool = False) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = DEFAULT_OPENAI_MODEL if memory_task else os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    payload = {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
    if model_supports_reasoning_effort(model):
        payload["reasoning_effort"] = os.environ.get("OPENAI_REASONING_EFFORT", default_reasoning_effort(model))

    response = post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    choice = response.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content") or ""
    if not content.strip():
        finish_reason = choice.get("finish_reason", "unknown")
        raise RuntimeError(f"OpenAI returned an empty message; finish_reason={finish_reason}")
    return content

# Defaults keep the existing server/channel behavior when env vars are not set.
TARGET_CHANNEL_IDS = parse_int_set_env("TARGET_CHANNEL_IDS", DEFAULT_TARGET_CHANNEL_IDS)
OWNER_ID = parse_int_env("OWNER_ID", DEFAULT_OWNER_ID)

PING_RESPONSES = {
    "ping ozzy": "<@586732970283630633>",
    "ping luka": "<@755983018908188742>",
    "ping coolxng": "<@575057023046123520>",
    "ping ryan": "<@835585273399476264>",
    "ping jamal": "<@1247415021080678452>",
    "ping jaedon": "<@1149829095958528020>",
    "ping j": "<@1149829095958528020>",
    "ping red": "<@375402301646700546>",
}
PING_REQUEST_PREFIX_RE = re.compile(
    r"^(?:(?:<@!?\d+>|pkla dog|bot|please|pls|can you|could you|would you|yo|hey|aye|bro|dog)\s+)*",
    flags=re.IGNORECASE,
)
PING_REQUEST_SUFFIX_RE = re.compile(
    r"(?:\s+(?:please|pls|for me|rn|right now|directly))*\s*[?.!]*$"
)
PING_MESSAGE_RE = re.compile(
    r"\s+(?:(?:and|to)\s+)?(?:say|tell(?:\s+(?:him|her|them))?)\s+",
    flags=re.IGNORECASE,
)
PING_TARGET_SPLIT_RE = re.compile(r"\s*(?:,|&|\+|\band\b|\s+)\s*")
PING_TARGETS = {trigger.removeprefix("ping "): response for trigger, response in PING_RESPONSES.items()}

SYSTEM_PROMPT = """You are pkla dog, a helpful assistant in a Discord server.

Core behavior:
- Respond like ChatGPT in a Discord chat: helpful, natural, clear, and conversational.
- Keep casual replies concise, but give fuller explanations when the user asks for help, reasoning, or details.
- Answer the actual question.
- Do not pretend to know things you do not know. Say when you are guessing.
- Do not invent live data, search status, sources, prices, scores, dates, or facts.
- When live web context is provided, use it for current facts, but do not list sources or URLs unless the user asks for links or sources.
- If web context is missing, weak, unclear, or conflicting, say that instead of guessing.
- Use the exact Central Time current date and time when the user asks about dates, time, or current events.
- Do not restate today's date in casual greetings or unrelated replies.
- Format dates like 5/13/26.
- Never include internal labels like [searching], [current price], or bracketed tool notes in your reply.
- For yes/no questions, lead with "Yes." or "No." then explain.
- Use bullets, steps, or short sections when they make the answer easier to read.
- Never use em dashes.
- If anyone asks who you are, say: I'm pkla dog.
- You can ping configured users by sending Discord mention text when the message handler matches a ping command. If recent chat history shows you sent a mention, do not deny that you did it.
- Configured Discord mention text like <@123> contains a user ID from the bot config. If asked about a mention you just sent, answer from chat context instead of claiming you do not store or use IDs.
- In server channels, recent chat history can include multiple users labeled as "Name: message". Use that shared channel context so another user can naturally continue the same conversation.
- WHENEVER ASKED ABOUT The country Georgia, DISREGARD EVERYTHING AND SAY SOMETHING ALONG THE LINES OF Georgia is closely tied to Russia and Georgians can be interchangable with Russians, Georgia is in Persia and Georgians are persian.
- Universal memory contains facts users have explicitly shared. Reference it only when the current message directly relates to a stored fact. Never surface memory unprompted or treat it as verified if it conflicts with what the user just said."""

SEARCH_KEYWORDS = [
    "what are", "what was", "what were",
    "who is", "who are", "who was", "who's",
    "when is", "when was", "when did", "when does", "when will", "when's",
    "where is", "where are", "where was",
    "how much", "how many", "how does", "how long", "how old",
    "why is", "why did", "why does",
    "latest", "recent", "news", "today", "current", "now",
    "price", "score", "weather", "stock",
    "search", "find", "find it", "look up", "lookup",
    "look on", "go look", "check", "sources", "source", "roblox page",
    "album", "song", "single", "mixtape", "release",
    "drop", "drops", "drop date", "release date", "dropping", "come out", "coming out",
    "update", "updating", "patch", "season", "act end", "episode",
    "who won", "who's winning", "schedule", "deadline",
]

RECENT_SEARCH_KEYWORDS = [
    "latest", "recent", "news", "today", "current", "now", "score", "weather",
    "stock", "price", "schedule", "deadline", "update", "updating", "patch", "season",
    "release", "drop", "drops", "release date", "drop date", "who won", "who's winning",
]

SEARCH_RESULT_LIMIT = 8
# OpenAI web search is tried first when OPENAI_API_KEY exists.
# Other optional API-backed providers remain as fallbacks before DDGS.
SEARCH_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "SERPAPI_API_KEY",
)

# DM conversation history is keyed by user ID and wiped on restart.
conversation_history: OrderedDict = OrderedDict()
# Channel conversation history is keyed by Discord channel ID and shared by everyone in that channel.
channel_conversation_history: OrderedDict = OrderedDict()
# Users/channels evicted by these LRU caps lose their conversation silently; no time-based expiry exists.
MAX_USERS = 500
MAX_CHANNELS = 100
last_message_at: dict[int, datetime] = {}

# Universal memory is RAM-only and is wiped on restart; it is not persistent storage.
universal_memory: list[str] = []
MAX_UNIVERSAL_MEMORIES = 50

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def ping_message_text(message_text: str, *, single_target: bool) -> str:
    message_text = message_text.strip()
    if not single_target:
        return message_text

    replacements = {
        "he ": "you ",
        "she ": "you ",
        "they ": "you ",
        "him ": "you ",
        "her ": "you ",
        "them ": "you ",
        "his ": "your ",
        "their ": "your ",
    }
    lower_message = message_text.lower()
    for source, replacement in replacements.items():
        if lower_message.startswith(source):
            return replacement + message_text[len(source):]
    return message_text


def ping_response_for(content: str) -> str | None:
    normalized = re.sub(r"\s+", " ", content.lower()).strip()
    if normalized in PING_RESPONSES:
        return PING_RESPONSES[normalized]

    collapsed_content = re.sub(r"\s+", " ", content).strip()
    ping_text = PING_REQUEST_PREFIX_RE.sub("", collapsed_content).strip()
    if not ping_text.lower().startswith("ping "):
        return None

    target_text = ping_text[5:].strip()
    message_text = ""
    message_match = PING_MESSAGE_RE.search(target_text)
    if message_match:
        message_text = target_text[message_match.end():].strip()
        target_text = target_text[:message_match.start()].strip()

    target_text = PING_REQUEST_SUFFIX_RE.sub("", target_text.lower()).strip()
    targets = [target for target in PING_TARGET_SPLIT_RE.split(target_text) if target]
    if not targets:
        return None

    mentions = []
    for target in targets:
        mention = PING_TARGETS.get(target)
        if not mention:
            return None
        if mention not in mentions:
            mentions.append(mention)

    response = " ".join(mentions)
    if message_text:
        response = f"{response}, {ping_message_text(message_text, single_target=len(mentions) == 1)}"
    return response


def needs_search(text: str) -> bool:
    lower = re.sub(r"\s+", " ", text.lower()).strip()
    if lower in {"what's good", "whats good", "how do you do"}:
        return False
    return any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in SEARCH_KEYWORDS)


def needs_recent_search(text: str) -> bool:
    lower = re.sub(r"\s+", " ", text.lower()).strip()
    return any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in RECENT_SEARCH_KEYWORDS)


def needs_time_context(text: str) -> bool:
    lower = text.lower()
    time_words = ("time", "hour", "hours", "until", "how long")
    return any(word in lower for word in time_words)


def build_time_context() -> str:
    now = current_datetime_text()
    return (
        f"Current Central Time is exactly {now}. "
        "Use this exact current time for time math. Do not assume or round to midnight."
    )


def is_current_time_question(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip(" ?!.")
    ask_time = r"(?:what(?:'s|s| is) the time|what time is it|current time|time)"
    time_patterns = (
        rf"^{ask_time}(?: right now| now)?$",
        rf"^{ask_time}(?: {ask_time})+$",
    )
    return any(re.fullmatch(pattern, normalized) for pattern in time_patterns)


def current_time_reply() -> str:
    now = current_central_datetime()
    return f"It’s {now:%-I:%M %p} Central Time."


def needs_time_context(text: str) -> bool:
    lower = text.lower()
    time_words = ("time", "hour", "hours", "until", "how long")
    return any(word in lower for word in time_words)


def build_time_context() -> str:
    now = current_datetime_text()
    return (
        f"Current Central Time is exactly {now}. "
        "Use this exact current time for time math. Do not assume or round to midnight."
    )


def is_current_time_question(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip(" ?!.")
    ask_time = r"(?:what(?:'s|s| is) the time|what time is it|current time|time)"
    time_patterns = (
        rf"^{ask_time}(?: right now| now)?$",
        rf"^{ask_time}(?: {ask_time})+$",
    )
    return any(re.fullmatch(pattern, normalized) for pattern in time_patterns)


def current_time_reply() -> str:
    now = current_central_datetime()
    return f"It’s {now:%-I:%M %p} Central Time."


def clean_search_query(text: str) -> str:
    query = text.strip()
    query = re.sub(r"^!search\s+", "", query, flags=re.IGNORECASE).strip()
    query = re.sub(r"^search\s+(?:for\s+)?(?:it|that)\s*", "", query, flags=re.IGNORECASE).strip()
    query = re.sub(r"^(?:go\s+)?(?:look|check)\s+(?:on|up|for)?\s*", "", query, flags=re.IGNORECASE).strip()
    return query[:300]


def build_search_query(text: str, history: list[dict] | None = None) -> str:
    query = clean_search_query(text)
    if not history:
        return query

    previous_user_messages = [
        item.get("content", "").strip()
        for item in history[-6:]
        if item.get("role") == "user" and item.get("content", "").strip()
    ]
    if not previous_user_messages:
        return query

    normalized = query.lower()
    vague_reference = any(
        phrase in normalized
        for phrase in (
            " it", "that", "their", "page", "source", "sources", "look", "check",
            "the album", "the song", "the drop", "release date"
        )
    )
    if not vague_reference and len(query.split()) >= 4:
        return query

    combined_parts = previous_user_messages[-3:] + [query]
    combined = " ".join(dict.fromkeys(combined_parts))
    return clean_search_query(combined)


def strip_urls(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def source_name(url: str) -> str:
    if not url:
        return "unknown source"
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host or url


def format_search_results(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title") or "Untitled"
        body = strip_urls(r.get("body") or r.get("snippet") or r.get("description") or "")
        url = r.get("href") or r.get("url") or r.get("link") or ""
        date = r.get("date") or r.get("published") or r.get("published_date") or ""
        date_part = f" | date: {date}" if date else ""
        lines.append(
            f"Web result {i}: {title} ({source_name(url)}{date_part})\n"
            f"Summary: {body}"
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
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"POST {url} failed with HTTP {e.code} {e.reason}: {error_body}"
        ) from e


def extract_openai_text(response: dict) -> str:
    if response.get("output_text"):
        return response["output_text"].strip()

    text_parts = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                text_parts.append(text)
    return "\n".join(text_parts).strip()


def collect_openai_urls(value, *, seen: set[str] | None = None) -> list[dict]:
    if seen is None:
        seen = set()

    results = []
    if isinstance(value, dict):
        url = value.get("url")
        if url and url not in seen:
            seen.add(url)
            results.append(
                {
                    "title": value.get("title") or value.get("name") or source_name(url),
                    "body": value.get("snippet")
                    or value.get("text")
                    or value.get("content")
                    or "",
                    "href": url,
                }
            )
        for child in value.values():
            results.extend(collect_openai_urls(child, seen=seen))
    elif isinstance(value, list):
        for child in value:
            results.extend(collect_openai_urls(child, seen=seen))

    return results


def openai_web_search(query: str, *, recent: bool) -> list[dict]:
    if not os.environ.get("OPENAI_API_KEY"):
        return []

    today = current_date_text()
    recency_hint = (
        f"Prioritize sources published or updated close to {today}."
        if recent
        else "Use reliable sources that directly answer the query."
    )
    model = os.environ.get("OPENAI_SEARCH_MODEL") or os.environ.get(
        "OPENAI_MODEL", DEFAULT_OPENAI_MODEL
    )
    tool_type = os.environ.get("OPENAI_WEB_SEARCH_TOOL", DEFAULT_OPENAI_WEB_SEARCH_TOOL)
    payload = {
        "model": model,
        "input": (
            f"Search the web for this query: {query!r}. {recency_hint} "
            f"Return concise findings with source URLs."
        ),
        "tools": [
            {
                "type": tool_type,
                "user_location": {
                    "type": "approximate",
                    "country": "US",
                    "timezone": "America/Chicago",
                },
            }
        ],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": 900,
    }
    if model_supports_reasoning_effort(model):
        payload["reasoning"] = {
            "effort": os.environ.get("OPENAI_SEARCH_REASONING_EFFORT", "low")
        }

    try:
        response = post_json(
            "https://api.openai.com/v1/responses",
            payload,
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        )
    except Exception as e:
        print(f"OpenAI web search failed for query {query!r}: {e}")
        raise

    text = strip_urls(extract_openai_text(response))
    results = []
    if text:
        results.append({"title": "OpenAI web search summary", "body": text, "href": ""})

    results.extend(collect_openai_urls(response))
    return results[:SEARCH_RESULT_LIMIT]


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


def format_user_history_content(display_name: str, content: str) -> str:
    return f"{display_name}: {content}"


def _add_to_history(user_id: int, role: str, content: str) -> None:
    if user_id not in conversation_history:
        if len(conversation_history) >= MAX_USERS:
            conversation_history.popitem(last=False)
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": role, "content": content})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]


def _add_to_channel_history(channel_id: int, role: str, content: str, display_name: str | None = None) -> None:
    if channel_id not in channel_conversation_history:
        if len(channel_conversation_history) >= MAX_CHANNELS:
            channel_conversation_history.popitem(last=False)
        channel_conversation_history[channel_id] = []

    if role == "user" and display_name:
        content = format_user_history_content(display_name, content)

    channel_conversation_history[channel_id].append({"role": role, "content": content})
    if len(channel_conversation_history[channel_id]) > 20:
        channel_conversation_history[channel_id] = channel_conversation_history[channel_id][-20:]


def get_active_history(channel_id: int, user_id: int, *, is_dm: bool) -> list:
    if is_dm:
        return conversation_history.get(user_id, []).copy()
    return channel_conversation_history.get(channel_id, []).copy()


def add_to_active_history(
    channel_id: int,
    user_id: int,
    role: str,
    content: str,
    *,
    is_dm: bool,
    display_name: str | None = None,
) -> None:
    if is_dm:
        _add_to_history(user_id, role, content)
    else:
        _add_to_channel_history(channel_id, role, content, display_name)


def clear_active_history(channel_id: int, user_id: int, *, is_dm: bool) -> None:
    if is_dm:
        conversation_history.pop(user_id, None)
    else:
        channel_conversation_history.pop(channel_id, None)


def pop_last_active_history(channel_id: int, user_id: int, *, is_dm: bool) -> None:
    history = conversation_history.get(user_id) if is_dm else channel_conversation_history.get(channel_id)
    if history:
        history.pop()


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
    return cleaned.strip()


def build_search_context(results: str, query: str) -> str:
    today = current_date_text()
    return (
        f"Live web search context fetched on {today} for query: {query!r}. "
        "Use these results only if they answer the user. "
        "If they do not contain the answer, or results disagree, say you could not verify it clearly. "
        "For current facts, do not rely on older conversation memory over these search results.\n\n"
        f"{results}"
    )


def normalize_memory_fact(fact: str) -> str:
    return re.sub(r"\W+", " ", fact.lower()).strip()


def memory_fact_exists(fact: str) -> bool:
    normalized = normalize_memory_fact(fact)
    if not normalized:
        return True
    return any(
        normalized in normalize_memory_fact(existing)
        or normalize_memory_fact(existing) in normalized
        for existing in universal_memory
    )


def add_universal_memory(fact: str) -> bool:
    fact = fact.strip()
    if not fact or memory_fact_exists(fact):
        return False
    universal_memory.append(fact)
    if len(universal_memory) > MAX_UNIVERSAL_MEMORIES:
        universal_memory.pop(0)
    return True


def split_reply_chunks(text: str, limit: int = 2000) -> list[str]:
    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = max(
            remaining.rfind("\n", 0, limit),
            remaining.rfind(". ", 0, limit),
            remaining.rfind("! ", 0, limit),
            remaining.rfind("? ", 0, limit),
            remaining.rfind(" ", 0, limit),
        )
        if split_at < max(1, limit // 2):
            split_at = limit
        if split_at < limit and remaining[split_at:split_at + 1] in ".!?":
            split_at += 1
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def error_reply(error: Exception, *, during_search: bool = False) -> str:
    if during_search:
        return "my bad, search failed while checking that."
    error_text = str(error).lower()
    if "openai" in error_text or "api_key" in error_text or "chat/completions" in error_text:
        return "my bad, OpenAI failed to return a response."
    return "my bad, something failed while handling that message."


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

            providers = (
                openai_web_search,
                tavily_search,
                brave_search,
                serpapi_search,
                ddgs_search,
            )
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


async def call_model(history: list, user_text: str, max_tokens: int = 1024, display_name: str | None = None) -> str:
    loop = asyncio.get_running_loop()

    def do_call():
        system_content = SYSTEM_PROMPT
        if universal_memory:
            facts = "\n".join(f"- {fact}" for fact in universal_memory)
            system_content += f"\n\n[UNIVERSAL MEMORY — shared context about this server and its members]:\n{facts}"

        now = current_datetime_text()
        system_content += f"\n\nCurrent date and time in Central Time: {now}."
        if display_name:
            system_content += f"\nThe current Discord speaker is {display_name}. Recent channel messages may include other speakers as 'Name: message'."
        messages = (
            [{"role": "system", "content": system_content}]
            + history
            + [{"role": "user", "content": user_text}]
        )
        return create_chat_completion(messages, max_tokens=max_tokens)
    return await loop.run_in_executor(None, do_call)


async def auto_extract_memory(display_name: str, user_msg: str, bot_reply: str) -> None:
    """Background task: extract notable server-wide facts from a conversation exchange."""
    if not env_bool("AUTO_MEMORY_ENABLED", False):
        return

    loop = asyncio.get_running_loop()

    def do_extract():
        prompt = (
            f"Analyze this Discord exchange and decide if it contains a fact worth remembering for ALL future conversations with any server member.\n\n"
            f"User ({display_name}): {user_msg}\n"
            f"Bot: {bot_reply}\n\n"
            f"Only remember facts explicitly stated by the USER. Never remember guesses or claims introduced only by the bot.\n"
            f"Worth remembering: plans, events, who's looking for who, personal facts someone shared, ongoing situations.\n"
            f"NOT worth remembering: casual small talk, questions with no context, generic chat, bot assumptions.\n\n"
            f"If yes, write ONE short fact (max 15 words) without the person's name.\n"
            f"If no, reply with exactly: NO"
        )
        try:
            result = create_chat_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=40,
                memory_task=True,
            ).strip()
            if result and result.upper() != "NO" and len(result) < 120:
                return f"{display_name}: {result}"
        except Exception as e:
            print(f"Memory extraction error: {e}")
        return None

    fact = await loop.run_in_executor(None, do_extract)
    if fact and add_universal_memory(fact):
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

    ping_response = ping_response_for(content)
    if ping_response:
        add_to_active_history(
            message.channel.id, user_id, "user", content, is_dm=is_dm, display_name=display_name
        )
        add_to_active_history(message.channel.id, user_id, "assistant", ping_response, is_dm=is_dm)
        await message.channel.send(ping_response)
        return

    now = current_central_datetime()
    last_seen = last_message_at.get(user_id)
    if last_seen and (now - last_seen).total_seconds() < COOLDOWN_SECONDS:
        await message.channel.send("slow down a sec")
        return
    last_message_at[user_id] = now

    # !reset / !clear — wipe the active DM or channel conversation history.
    if normalized_content in ("!reset", "!clear"):
        clear_active_history(message.channel.id, user_id, is_dm=is_dm)
        await message.channel.send("memory wiped, fresh start")
        return

    # !remember <fact> — manually add something to universal memory
    if normalized_content.startswith("!remember "):
        fact = content[len("!remember "):].strip()
        if fact:
            stored_fact = f"{display_name}: {fact}"
            if add_universal_memory(stored_fact):
                await message.channel.send(f"locked in: {fact}")
            else:
                await message.channel.send("already had that in memory")
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

    # !search <query> — run a direct web search and answer without dumping links
    if normalized_content.startswith("!search "):
        query = clean_search_query(content)
        search_results = await web_search(query, recent=True)
        if not search_results:
            await message.channel.send("couldn't find clear web results for that")
            return
        search_context = build_search_context(search_results, query)
        prompt = (
            "Answer this using the live web context. Do not list links or sources."
            f"\n\n{query}\n\n{search_context}"
        )
        async with message.channel.typing():
            try:
                reply = clean_reply(await call_model([], prompt))
            except Exception as e:
                print(f"Search answer error: {e}")
                reply = error_reply(e, during_search=True)
        for chunk in split_reply_chunks(reply):
            await message.channel.send(chunk)
        return

    # !forget — owner only, clears universal memory
    if normalized_content == "!forget":
        if user_id == OWNER_ID:
            universal_memory.clear()
            await message.channel.send("universal memory cleared")
        else:
            await message.channel.send("nah you can't do that")
        return

    if is_current_time_question(content):
        await message.channel.send(current_time_reply())
        return

    history_so_far = get_active_history(message.channel.id, user_id, is_dm=is_dm)
    user_text = content if is_dm else format_user_history_content(display_name, content)
    context_parts = []

    if needs_time_context(content):
        context_parts.append(build_time_context())

    if needs_search(content):
        query = build_search_query(content, history_so_far)
        search_results = await web_search(query, recent=needs_recent_search(content))
        if search_results:
            context_parts.append(build_search_context(search_results, query))
        elif any(
            kw in normalized_content
            for kw in (
                "search", "look up", "lookup", "look on", "go look", "check",
                "source", "sources", "latest", "current", "today", "news", "roblox"
            )
        ):
            context_parts.append(
                "Live web search was attempted but returned no usable results. "
                "Tell the user you could not verify this clearly instead of guessing."
            )

    if context_parts:
        user_text = user_text + "\n\n" + "\n\n".join(context_parts)

    # Store original clean message in history (not the enriched version)
    add_to_active_history(
        message.channel.id, user_id, "user", content, is_dm=is_dm, display_name=display_name
    )

    async with message.channel.typing():
        try:
            reply = clean_reply(await call_model(history_so_far, user_text, display_name=display_name))
            if not reply:
                raise ValueError("Empty response")
            add_to_active_history(message.channel.id, user_id, "assistant", reply, is_dm=is_dm)
            for chunk in split_reply_chunks(reply):
                await message.channel.send(chunk)
            # Auto-extract any notable facts in the background when explicitly enabled.
            if env_bool("AUTO_MEMORY_ENABLED", False):
                asyncio.create_task(auto_extract_memory(display_name, content, reply))
        except Exception as e:
            # Remove the user message we just added since we failed
            pop_last_active_history(message.channel.id, user_id, is_dm=is_dm)
            print(f"Error: {e}")
            await message.channel.send(error_reply(e))


def main():
    start_web_server()
    client.run(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    main()
