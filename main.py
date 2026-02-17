import discord
import feedparser
import asyncio
import os
import sys
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv

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


# === Embed style colors per source ===
SOURCE_COLORS = {
    "PlayStation": 0x003791,
    "Xbox": 0x107C10,
    "Nintendo": 0xE60012,
    "Steam": 0x1B2838,
    "IGN": 0xE60012,
    "GameSpot": 0xFF4500,
    "Polygon": 0x7B61FF,
    "Game Informer": 0xF39C12,
    "Eurogamer": 0x00A0E3,
    "PC Gamer": 0x008080,
    "Bethesda": 0xA3A3A3,
    "Blizzard": 0x00A2E8,
    "Ubisoft": 0x1CABE2,
    "Riot Games": 0xE6322A,
    "Capcom Unity": 0x003DA5,
    "Devolver Digital": 0xFF0080,
    "CD Projekt Red": 0xDA1E28
}

# === New function to extract feed images ===
def extract_image(entry):
    # 1. Check media_content
    if 'media_content' in entry:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
    # 2. Check media_thumbnail
    if 'media_thumbnail' in entry:
        for media in entry.media_thumbnail:
            if 'url' in media:
                return media['url']
    # 3. Parse summary for <img>
    import re
    match = re.search(r'<img[^>]+src="([^">]+)"', entry.get('summary', '') or '')
    if match:
        return match.group(1)
    # 4. Fallback
    return None


async def check_feeds():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("ERROR: Channel not found. Check CHANNEL_ID.")
        return

    while True:
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

                event = detect_event(f"{title} {summary}")

                # --- Embed Styling ---
                embed = discord.Embed(
                    title=title,
                    url=entry.link,
                    description=(summary[:300] + "..." if len(summary) > 300 else summary),
                    color=SOURCE_COLORS.get(source, 0xF39C12),
                    timestamp=datetime.now(timezone.utc)
                )

                embed.set_author(name=source)
                embed.set_footer(text="BIG GAMING ANNOUNCEMENT")

                # --- Set dynamic thumbnail ---
                image_url = extract_image(entry)
                if image_url:
                    embed.set_thumbnail(url=image_url)
                else:
                    embed.set_thumbnail(url="https://i.imgur.com/6r7ZJx5.png")  # fallback

                # --- Send to thread or channel ---
                if event:
                    thread = await get_or_create_thread(channel, event)
                    await thread.send(content=f"🔗 **Direct link:** {entry.link}", embed=embed)
                else:
                    await channel.send(content=f"🔗 **Direct link:** {entry.link}", embed=embed)

        await asyncio.sleep(1800)  # check every 30 min


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


# === Subclass Client to use setup_hook ===
class MyClient(discord.Client):
    async def setup_hook(self):
        print("Waiting 30 seconds before starting feeds to avoid rate limits...")
        await asyncio.sleep(30)
        self.loop.create_task(check_feeds())
        self.loop.create_task(run_webserver())


intents = discord.Intents.default()
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# === Run bot ===
client.run(TOKEN)
