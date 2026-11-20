import os
from dotenv import load_dotenv
import logging

# ---------- константы ----------
STEAM64_OFFSET = 76561197960265728
OPENDOTA_API = "https://api.opendota.com/api"
MIN_GAMES = 10  # минимум игр на герое, чтобы он попал в список
TOP_HEROES = 5  # сколько героев показывать
RECENT_MATCHES = 5 # сколько последних матчей обрабатывать
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
HEROES_DICT: dict[str, str] = {}

MEDALS = {
    1: "Рекрут", 2: "Страж", 3: "Рыцарь", 4: "Герой",
    5: "Легенда", 6: "Властелин", 7: "Божество", 8: "Титан",
}

# ---------- env ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
DB_FILE = os.getenv("DB_FILE", "userdata.db")

# ---------- log ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dota-bot")