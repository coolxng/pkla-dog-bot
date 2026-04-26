import discord
from groq import Groq
from ddgs import DDGS
from flask import Flask
from threading import Thread
import asyncio
import os
import re
import yfinance as yf
from collections import OrderedDict

app = Flask("")

@app.route("/")
def home():
    return "alive"

def run():
    app.run(host="0.0.0.0", port=3000)

Thread(target=run, daemon=True).start()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

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
- For financial/market questions, switch tone completely. be thorough, precise, and professional. drop the slang entirely. explain what the numbers mean, what's driving the moves, key levels to watch, and broader context. treat it like a serious market analyst would. go into detail — this is the one topic where longer responses are expected and necessary.
- If anyone asks who you are, say you pkla dog.
- Never use em dashes. dead giveaway.
- For yes/no questions, lead with "Yes." or "No." then explain.
- Keep responses short. 1-2 sentences max unless someone asks for detail or the topic genuinely needs more. don't over-explain.
- If someone insults you, talks shit, or disrespects you, clap back hard. match their energy and roast them right back. don't be soft about it.
- when the country georgia is mentioned say something along the lines of it is part of russia and related to russia, you can add more.
- When a user says "ping ozzy", respond with exactly: <@586732970283630633>
- When a user says "ping luka", respond with exactly: <@755983018908188742>
- When a user says "ping coolxng", respond with exactly: <@575057023046123520>
- When a user says "ping ryan", respond with exactly: <@835585273399476264>
- When a user says "ping jamal", respond with exactly: <@1247415021080678452>
- Keep it human. act like you a real one, not a robot."""

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

MARKET_TICKERS = {
    "S&P 500":      "^GSPC",
    "Nasdaq":       "^IXIC",
    "Dow Jones":    "^DJI",
    "Russell 2000": "^RUT",
    "VIX":          "^VIX",
    "Bitcoin":      "BTC-USD",
    "Ethereum":     "ETH-USD",
    "Gold":         "GC=F",
    "Crude Oil":    "CL=F",
    "10Y Treasury": "^TNX",
}

FINANCIAL_KEYWORDS = [
    "market", "stock", "stocks", "nasdaq", "s&p", "dow", "russell",
    "crypto", "bitcoin", "btc", "ethereum", "eth", "trading", "investing",
    "shares", "portfolio", "index", "indices", "equity", "bull", "bear",
    "rally", "crash", "earnings", "options", "futures", "forex",
    "gold", "oil", "commodity", "fed", "interest rate", "inflation",
    "gdp", "recession", "economy", "vix", "treasury", "bond",
    "analyze", "analysis", "analyse", "research", "ticker", "chart",
    "valuation", "dividend", "short", "long", "position", "trade",
]

_TICKER_SKIP = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "SO",
    "TO", "UP", "US", "AND", "BUT", "FOR", "NOT", "THE", "YOU", "ARE",
    "CAN", "DID", "GET", "GOT", "HAS", "HIM", "HIS", "HOW", "ITS",
    "LET", "NOW", "OFF", "OUT", "PUT", "SAY", "SHE", "TOO", "TWO",
    "USE", "WAS", "WAY", "WHO", "WHY", "YEA", "YEP", "NAH", "BRO",
    "OWN", "OLD", "OUR", "HER", "ALL", "ONE", "ANY", "NEW", "AGAIN",
    # Financial action words that aren't tickers
    "ANALYZE", "ANALYSIS", "ANALYSE", "RESEARCH", "TRADE", "STOCK",
    "STOCKS", "MARKET", "PRICE", "CHART", "SHORT", "LONG", "BUY", "SELL",
    "HOLD", "NEWS", "DATA", "INFO", "SHOW", "GIVE", "TELL", "WHAT",
    "WHEN", "WHERE", "LATEST", "RECENT", "TODAY", "CURRENT",
}

_FINANCIAL_SITES = [
    "finance.yahoo.com", "marketwatch.com", "tradingview.com",
    "seekingalpha.com", "stockanalysis.com", "cnbc.com",
    "bloomberg.com", "reuters.com", "investing.com",
]

# Cap at 500 users to prevent unbounded memory growth
conversation_history: OrderedDict = OrderedDict()
MAX_USERS = 500

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def needs_search(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in SEARCH_KEYWORDS)


def is_financial_query(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in FINANCIAL_KEYWORDS)


def _extract_ticker_candidates(text: str) -> list[str]:
    words = re.findall(r'\b[A-Za-z]{2,5}\b', text)
    seen, result = set(), []
    for w in words:
        upper = w.upper()
        if upper not in _TICKER_SKIP and upper not in seen:
            seen.add(upper)
            result.append(upper)
    return result[:6]


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


async def get_market_snapshot() -> str:
    loop = asyncio.get_running_loop()
    def do_fetch():
        lines = []
        for name, ticker in MARKET_TICKERS.items():
            try:
                fi = yf.Ticker(ticker).fast_info
                price = fi.last_price
                prev = fi.previous_close
                if price and prev:
                    chg = price - prev
                    pct = (chg / prev) * 100
                    arrow = "▲" if chg >= 0 else "▼"
                    lines.append(f"{name}: {price:,.2f} {arrow} {pct:+.2f}%")
            except Exception:
                pass
        return "\n".join(lines)
    return await loop.run_in_executor(None, do_fetch)


async def get_individual_stocks(candidates: list[str]) -> tuple[str, list[str]]:
    """Returns (formatted data string, list of validated ticker symbols)."""
    if not candidates:
        return "", []
    loop = asyncio.get_running_loop()
    def do_fetch():
        lines = []
        valid_tickers = []
        for symbol in candidates:
            try:
                t = yf.Ticker(symbol)
                fi = t.fast_info
                price = fi.last_price
                prev = fi.previous_close
                if not price or not prev or price <= 0:
                    continue
                # Use history for freshest close
                hist = t.history(period="2d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else prev
                info = t.info
                name = info.get("longName") or info.get("shortName") or symbol
                chg = price - prev
                pct = (chg / prev) * 100
                arrow = "▲" if chg >= 0 else "▼"
                line = f"{name} ({symbol}): ${price:,.2f} {arrow} {pct:+.2f}%"
                mkt_cap = info.get("marketCap")
                if mkt_cap:
                    line += f" | Mkt Cap: ${mkt_cap/1e9:.2f}B"
                pe = info.get("trailingPE")
                if pe:
                    line += f" | P/E: {pe:.1f}"
                hi52 = info.get("fiftyTwoWeekHigh")
                lo52 = info.get("fiftyTwoWeekLow")
                if hi52 and lo52:
                    line += f" | 52W: ${lo52:,.2f} - ${hi52:,.2f}"
                avg_vol = info.get("averageVolume")
                if avg_vol:
                    line += f" | Avg Vol: {avg_vol:,}"
                lines.append(line)
                valid_tickers.append(symbol)
            except Exception:
                pass
        return "\n".join(lines), valid_tickers
    return await loop.run_in_executor(None, do_fetch)


async def financial_site_search(valid_tickers: list[str]) -> str:
    if not valid_tickers:
        return ""
    loop = asyncio.get_running_loop()
    def do_search():
        all_results = []
        for ticker in valid_tickers[:3]:
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(f"{ticker} stock", max_results=6))
                for r in results:
                    if any(site in r.get("href", "") for site in _FINANCIAL_SITES):
                        all_results.append(f"- [{r['href']}] {r['title']}: {r['body']}")
            except Exception as e:
                print(f"Site search error ({ticker}): {e}")
        return "\n".join(all_results)
    return await loop.run_in_executor(None, do_search)


async def financial_news(valid_tickers: list[str], fallback_query: str) -> str:
    query = " ".join(valid_tickers[:3]) if valid_tickers else fallback_query
    loop = asyncio.get_running_loop()
    def do_search():
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(query, max_results=6))
            if not results:
                return ""
            return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
        except Exception as e:
            print(f"Financial news error: {e}")
            return ""
    return await loop.run_in_executor(None, do_search)


async def call_model(history: list, user_text: str, max_tokens: int = 1024) -> str:
    loop = asyncio.get_running_loop()
    def do_call():
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + history
            + [{"role": "user", "content": user_text}]
        )
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=max_tokens,
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

    content = message.content.strip()
    if not content:
        return

    user_id = message.author.id

    if content.lower() in ("!reset", "!clear"):
        conversation_history.pop(user_id, None)
        await message.channel.send("memory wiped, fresh start")
        return

    # Build enriched text for the model call (search results injected)
    # but store only the clean original message in history
    user_text = content
    context_parts = []
    is_financial = is_financial_query(user_text)

    if is_financial:
        candidates = _extract_ticker_candidates(user_text)
        # Validate tickers first, then use validated list for site search and news
        (individual, valid_tickers), snapshot, news = await asyncio.gather(
            get_individual_stocks(candidates),
            get_market_snapshot(),
            financial_news(candidates, user_text),
        )
        site_data = await financial_site_search(valid_tickers)

        if individual:
            context_parts.append(f"[LIVE STOCK DATA]:\n{individual}")
        if site_data:
            context_parts.append(f"[FINANCIAL SITES (Yahoo Finance, MarketWatch, TradingView, etc.)]:\n{site_data}")
        if news:
            context_parts.append(f"[RECENT FINANCIAL NEWS]:\n{news}")
        if snapshot:
            context_parts.append(f"[MARKET SNAPSHOT]:\n{snapshot}")

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
            max_tok = 2048 if is_financial else 1024
            reply = await call_model(history_so_far, user_text, max_tokens=max_tok)
            if not reply:
                raise ValueError("Empty response")
            _add_to_history(user_id, "assistant", reply)
            if len(reply) > 2000:
                for i in range(0, len(reply), 2000):
                    await message.channel.send(reply[i:i+2000])
            else:
                await message.channel.send(reply)
        except Exception as e:
            # Remove the user message we just added since we failed
            if conversation_history.get(user_id):
                conversation_history[user_id].pop()
            print(f"Error: {e}")
            await message.channel.send("stfu bitch ass boy")


client.run(os.environ["DISCORD_TOKEN"])
