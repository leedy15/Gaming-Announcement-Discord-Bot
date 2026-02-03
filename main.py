import discord
import feedparser
import asyncio
import os
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv

# Load .env file locally (optional; remove if using environment variables in hosting)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

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
    "Gearbox Software": "https://gearboxsoftware.com/feed",
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
    "review", "hotfix",
    "sale", "interview", "opinion",
    "guide", "rumor", "leak"
]

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# === Persistence helpers ===
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
        print("⚠️ ERROR: Channel not found. Check CHANNEL_ID.")
        return

    while not client.is_closed():
        for source, url in RSS_FEEDS.items():
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:
                if entry.link in posted_links:
                    continue

                title = entry.title
                summary = entry.get("summary", "")

                if not is_big_announcement(title, summary):
                    continue

                posted_links.add(entry.link)
                save_posted_links()

                embed = discord.Embed(
                    title=title,
                    url=entry.link,
                    description=summary[:400] + "...",
                    color=0xF39C12
                )
                embed.set_footer(text=f"BIG GAMING ANNOUNCEMENT • {source}")

                event = detect_event(f"{title} {summary}")

                if event:
                    thread = await get_or_create_thread(channel, event)
                    await thread.send(
                        content=f"🔗 **Direct link:** {entry.link}",
                        embed=embed
                    )
                else:
                    await channel.send(
                        content=f"🔗 **Direct link:** {entry.link}",
                        embed=embed
                    )

        await asyncio.sleep(900)  # 15 minutes

# HTTP server to keep Render awake
async def handle(request):
    return web.Response(text="Bot is alive!")

async def run_webserver():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("✅ HTTP server running on port 8080")

@client.event
async def on_ready():
    print(f"🔥 Bot online as {client.user}")

@client.event
async def setup_hook():
    client.loop.create_task(check_feeds())
    client.loop.create_task(run_webserver())

client.run(TOKEN)
