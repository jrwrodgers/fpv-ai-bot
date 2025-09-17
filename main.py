import os
import json
import asyncio
import logging
import discord
from discord.ext import commands
from openai import OpenAI
from tavily import TavilyClient
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fpv-bot")

# ---- Load config.json ----
CONFIG_PATH = "config.json"

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"Missing {CONFIG_PATH}. Create one with your keys.")

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

OPENAI_API_KEY = config.get("OPENAI_API_KEY")
DISCORD_TOKEN = config.get("DISCORD_TOKEN")
TAVILY_API_KEY = config.get("TAVILY_API_KEY")

if not (OPENAI_API_KEY and DISCORD_TOKEN and TAVILY_API_KEY):
    raise ValueError("config.json must contain OPENAI_API_KEY, DISCORD_TOKEN, and TAVILY_API_KEY")

# ---- Clients ----
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

FPV_SITES = [
    "betaflight.com",
    "github.com/betaflight",
    "inavflight.org",
    "oscarliang.com",
    "intofpv.com",
    "rotorbuilds.com",
    "mateksys.com",
    "holybro.com",
    "iflight-rc.com",
    "diatone.us"
]

SYSTEM_PROMPT = """
You are an FPV drone expert helping pilots troubleshoot, configure, and tune their drones.
Rules:
- Ask for more information, if the user is not specific
- Prefer trusted FPV resources provided.
- If none found, say so and suggest where to look.
- Explain step-by-step in clear language.
- Cite sources (PDF name or URL).
- Never invent or guess pinouts, firmware targets, or tuning values.
"""

# ---- Discord bot setup ----
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ---- Utility: split long messages into <=2000-char chunks ----
def chunk_text(text: str, limit: int = 2000) -> List[str]:
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), limit):
        chunks.append(text[i:i+limit])
    return chunks


async def send_long_message(destination, message: str):
    if not message:
        await destination.send("(no content)")
        return
    for chunk in chunk_text(message):
        await destination.send(chunk)


# ---- FPV web search ----
def fpv_search_sync(query: str) -> str:
    try:
        results = tavily.search(query, max_results=5, include_domains=FPV_SITES)
        logger.info(f"Found {len(results)} results for {query}")
    except Exception as e:
        logger.exception("Tavily search failed")
        return f"[Error calling Tavily search: {e}]"

    hits = results.get("results") or []
    if not hits:
        return ""
    formatted = []
    for r in hits:
        title = r.get("title", "No title")
        url = r.get("url", "")
        content = r.get("content", "")
        if len(content) > 800:
            content = content[:800] + "…"
        formatted.append(f"- {title} ({url})\n  {content}")
    return "\n".join(formatted)


async def call_openai_chat_system(user_question: str, context: str) -> str:
    def sync_call():
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {user_question}\n\nContext:\n{context}"}
                ],
                temperature=0
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.exception("OpenAI request failed")
            return f"[Error calling LLM: {e}]"

    return await asyncio.to_thread(sync_call)


# ---- Discord commands ----
@bot.event
async def on_ready():
    logger.info(f"✅ Bot ready as {bot.user}")


@bot.command(name="fpv")
async def fpv_cmd(ctx, *, question: str):
    """Ask the FPV agent a question. Usage: !fpv <question>"""
    async with ctx.typing():  # <-- FIXED
        try:
            web_context = await asyncio.to_thread(fpv_search_sync, question)
            context_text = web_context if web_context else "(no web resources found)"
            answer = await call_openai_chat_system(question, context_text)
            await send_long_message(ctx, answer)
        except Exception as exc:
            logger.exception("Unexpected error in !fpv")
            await ctx.send(f"An error occurred: {exc}")


# ---- Run bot ----
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.exception("Failed to start bot")
        raise
