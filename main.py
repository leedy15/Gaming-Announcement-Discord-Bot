import discord
import feedparser
import asyncio
import os
import sys
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv
import random

# === Load environment variables ===
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not TOKEN:
    print("FATAL: DISCORD_TOKEN missing")
    sys.exit(1)

if not CHANNEL_ID:
    print("FATAL: CHANNEL_ID missing")
    sys.exit(1)

CHANNEL_ID = int(CHANNEL_ID)

RSS_FEEDS = {
    "PlayStation": "https://blog.playstation.com/feed/",
    "Xbox": "https://news.xbox.com/en-us/feed/",
    "Nintendo": "https://www.nintendo.com/whatsnew/rss/",
    "Steam": "https://store.steampowered.com/feeds/news.xml",
    "IGN": "https://feeds.ign.com/ign/games-all",
    "GameSpot": "https://www.gamespot.com/feeds/news/",
    "Polygon": "https://www.polygon.com/rss/index.xml",
    "Game Informer": "https://www.gameinformer.com/rss",
    "Eurogamer": "https://www.eurogamer.net/?format=rss",
    "PC Gamer": "https://www.pcgamer.com/rss/",
    "Bethesda": "https://bethesda.net/en/rss",
    "Blizzard": "https://news.blizzard.com/en-us/rss.xml",
    "Ubisoft": "https://www.ubisoft.com/en-us/rss",
    "Riot Games": "https://www.riotgames.com/en/rss",
    "Capcom Unity": "https://www.capcom-unity.com/rss/",
    "Devolver Digital": "https://www.devolverdigital.com/rss",
    "CD Projekt Red": "https://en.cdprojektred.com/feed/"
}

EVENT_KEYWORDS = {
    "Nintendo Direct": "nintendo direct",
    "State of Play": "state of play",
    "Xbox Showcase": "xbox showcase",
    "Summer Game Fest": "summer game fest",
    "The Game Awards": "the game awards",
    "Gamescom": "gamescom",
    "E3": "e3",
    "PAX": "pax",
    "BlizzCon": "blizzcon",
    "Tokyo Game Show": "tokyo game show",
    "Ubisoft Forward": "ubisoft forward",
    "Bethesda Showcase": "bethesda showcase",
    "Devolver Direct": "devolver direct",
    "Sony State of Play": "state of play",
    "Microsoft Build": "microsoft build",
    "CD Projekt RED Night City Wire": "night city wire",
    "Capcom Showcase": "capcom showcase"
}

INCLUDE_KEYWORDS = [
    "announce", "announced", "reveal", "trailer",
    "world premiere", "new game", "launch",
    "release date", "expansion", "dlc",
    "gameplay reveal", "patch", "update"
]

EXCLUDE_KEYWORDS = [
    "review", "hotfix", "sale", "interview",
    "opinion", "guide", "rumor", "leak"
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)

POSTED_LINKS_FILE = "posted_links.txt"

def load_posted_links():
    try:
        with open(POSTED_LINKS_FILE, "r") as f:
            return set(line.strip() for line in f.readlines())
    except FileNotFoundError:
        return set()

def save_posted_links():
    with open(POSTED_LINKS_FILE, "w") as f:
        for link in posted_links:
            f.write(link + "\n")

posted_links = load_posted_links()
event_threads = {}

def is_big_announcement(title, summary):
    text = f"{title} {summary}".lower()
    if any(word in text for word in EXCLUDE_KEYWORDS):
        return False
    return any(word in text for word in INCLUDE_KEYWORDS)

def detect_event(text):
    text = text.lower()
    for event, keyword in EVENT_KEYWORDS.items():
        if keyword in text:
            return event
    return None

async def get_or_create_thread(channel, event_name):
    if event_name in event_threads:
        return event_threads[event_name]

    date = datetime.now(timezone.utc).strftime("%b %Y")
    message = await channel.send(f"🔥 **{event_name} announcements**")
    thread = await message.create_thread(
        name=f"🎮 {event_name} – {date}",
        auto_archive_duration=1440
    )

    event_threads[event_name] = thread
    return thread

async def check_feeds():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("ERROR: Channel not found. Check CHANNEL_ID.")
        return

    while not client.is_closed():
        for source, url in RSS_FEEDS.items():
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:
                if entry.link in posted_links:
                    continue

                title = entry.title
                summary = entry.get("summary", "") or ""

                if not is_big_announcement(title, summary):
                    continue

                posted_links.add(entry.link)
                save_posted_links()

                embed = discord.Embed(
                    title=title,
                    url=entry.link,
                    description=(summary[:400] + "...") if summary else "No summary available",
                    color=0xF39C12
                )
                embed.set_footer(text=f"BIG GAMING ANNOUNCEMENT • {source}")

                event = detect_event(f"{title} {summary}")

                if event:
                    thread = await get_or_create_thread(channel, event)
                    await thread.send(content=f"🔗 **Direct link:** {entry.link}", embed=embed)
                else:
                    await channel.send(content=f"🔗 **Direct link:** {entry.link}", embed=embed)

                # <-- small random delay between posts to reduce rate limit hits
                await asyncio.sleep(random.randint(2, 5))

        # Wait before checking feeds again
        await asyncio.sleep(1800)

# === HTTP server for Render health checks ===
async def handle(request):
    return web.Response(text="Bot is running")

async def run_webserver():
    port = int(os.getenv("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP server running on port {port}")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# === Asynchronous main for safe startup and Discord rate limit avoidance ===
async def main():
    print("Starting bot... waiting 30 seconds to avoid Discord rate limits")
    await asyncio.sleep(30)  # wait before doing anything
    client.loop.create_task(check_feeds())
    client.loop.create_task(run_webserver())
    await client.start(TOKEN, reconnect=True)

if __name__ == "__main__":
    asyncio.run(main())
