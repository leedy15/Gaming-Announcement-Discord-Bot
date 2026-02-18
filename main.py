import discord
import feedparser
import asyncio
import os
import sys
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv
import re
from urllib.parse import urlparse, urlunparse

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

# === Utility functions ===
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

# === NEW: Local icon loader ===
def get_local_icon_path(source_name: str):
    filename = f"{source_name}.png"
    path = os.path.join(os.path.dirname(__file__), filename)
    return path if os.path.exists(path) else None

# --- HTML Cleaning ---
def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<img[^>]*>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    import html
    text = html.unescape(text)
    return text.strip()

def highlight_keywords(text):
    for kw in INCLUDE_KEYWORDS:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        text = pattern.sub(lambda m: f"**{m.group(0)}**", text)
    return text

def extract_image(entry):
    if 'media_content' in entry:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
    if 'media_thumbnail' in entry:
        for media in entry.media_thumbnail:
            if 'url' in media:
                return media['url']
    match = re.search(r'<img[^>]+src=\"([^\">]+)\"', entry.get('summary','') or '')
    if match:
        return match.group(1)
    return None

def normalize_link(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

# --- Main feed check ---
async def check_feeds():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    while True:
        for source, url in RSS_FEEDS.items():
            feed = feedparser.parse(url)
            new_links_added = False

            for entry in feed.entries[:10]:
                link = normalize_link(entry.link)
                if link in posted_links:
                    continue

                title = entry.title
                summary = highlight_keywords(clean_html(entry.get("summary","") or ""))

                if not is_big_announcement(title, summary):
                    continue

                posted_links.add(link)
                new_links_added = True
                event = detect_event(f"{title} {summary}")

                embed = discord.Embed(
                    title=title,
                    url=link,
                    description=(summary[:350]+"..." if len(summary)>350 else summary),
                    color=SOURCE_COLORS.get(source,0xF39C12),
                    timestamp=datetime.now(timezone.utc)
                )

                embed.set_footer(text="BIG GAMING ANNOUNCEMENT")

                image_url = extract_image(entry)
                if image_url:
                    embed.set_image(url=image_url)

                platform = ''
                if source=='PlayStation': platform='🟦 PS4 / PS5'
                elif source=='Xbox': platform='🟩 Xbox One / Xbox Series X|S'
                elif source=='Nintendo': platform='🔴 Switch'
                elif source in ['Steam','PC Gamer']: platform='💻 PC'
                if platform: embed.add_field(name="Platform", value=platform, inline=True)
                if event: embed.add_field(name="Event", value=event, inline=True)

                icon_path = get_local_icon_path(source)

                if icon_path:
                    file = discord.File(icon_path, filename="icon.png")
                    embed.set_author(name=source.upper(), icon_url="attachment://icon.png")
                    if event:
                        thread = await get_or_create_thread(channel,event)
                        await thread.send(embed=embed, file=file)
                    else:
                        await channel.send(embed=embed, file=file)
                else:
                    embed.set_author(name=source.upper())
                    if event:
                        thread = await get_or_create_thread(channel,event)
                        await thread.send(embed=embed)
                    else:
                        await channel.send(embed=embed)

            if new_links_added:
                save_posted_links()

        await asyncio.sleep(1800)

# --- HTTP server ---
async def handle(request): return web.Response(text="Bot is running")

async def run_webserver():
    port = int(os.getenv("PORT",10000))
    app = web.Application()
    app.router.add_get("/",handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner,"0.0.0.0",port)
    await site.start()

# --- Discord Client ---
class MyClient(discord.Client):
    async def setup_hook(self):
        await asyncio.sleep(30)
        self.loop.create_task(check_feeds())
        self.loop.create_task(run_webserver())

intents = discord.Intents.default()
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

client.run(TOKEN)

