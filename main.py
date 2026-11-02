import os
import re
import asyncio
import logging
from html import escape

import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dota-bot")

# ---------- env ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN в .env")
if not STEAM_API_KEY:
    log.warning("STEAM_API_KEY не задан: ссылки вида steamcommunity.com/id/... работать не будут")

# ---------- константы ----------
STEAM64_OFFSET = 76561197960265728
OPENDOTA_API = "https://api.opendota.com/api"
MIN_GAMES = 10  # минимум игр на герое, чтобы он попал в список
TOP_HEROES = 5  # сколько героев показывать
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

MEDALS = {
    1: "Рекрут", 2: "Страж", 3: "Рыцарь", 4: "Герой",
    5: "Легенда", 6: "Властелин", 7: "Божество", 8: "Титан",
}

# ---------- основа бота ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

HEROES_DICT: dict[str, str] = {}


class DotaProfile(StatesGroup):
    waiting_for_steam_id = State()


# ---------- работа с API ----------
async def fetch(session: aiohttp.ClientSession, url: str, params: dict | None = None):
    """Универсальный GET-запрос, возвращает JSON или None."""
    try:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            log.warning("API %s вернул код %s", url, response.status)
            return None
    except Exception as e:
        log.error("Ошибка соединения с %s: %s", url, e)
        return None


async def resolve_vanity_url(session: aiohttp.ClientSession, vanity_name: str):
    """Превращает кастомный steam-ник в Steam64ID."""
    if not STEAM_API_KEY:
        return None
    data = await fetch(
        session,
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/",
        params={"key": STEAM_API_KEY, "vanityurl": vanity_name},
    )
    if data and data.get("response", {}).get("success") == 1:
        return int(data["response"]["steamid"])
    return None


async def extract_steam32id(text: str, session: aiohttp.ClientSession):
    """Достаёт Steam32ID из ссылки Dotabuff/Steam, Steam64ID или Steam32ID."""
    match_db = re.search(r"dotabuff\.com/players/(\d+)", text)
    if match_db:
        return match_db.group(1)

    raw_id = None

    match_steam_number = re.search(r"steamcommunity\.com/profiles/(\d+)", text)
    if match_steam_number:
        raw_id = int(match_steam_number.group(1))
    else:
        match_steam_custom = re.search(r"steamcommunity\.com/id/([^/?#\s]+)", text)
        if match_steam_custom:
            raw_id = await resolve_vanity_url(session, match_steam_custom.group(1))
        elif text.isdigit():
            raw_id = int(text)

    if not raw_id:
        return None
    if raw_id > STEAM64_OFFSET:
        return str(raw_id - STEAM64_OFFSET)
    return str(raw_id)


# ---------- форматирование ----------
def format_rank(rank_tier) -> str:
    if not rank_tier:
        return "Калибровка"
    medal_id, stars = divmod(rank_tier, 10)
    medal_name = MEDALS.get(medal_id, "Неизвестно")
    if medal_id == 8:  # у Титана звёзд нет
        return medal_name
    return f"{medal_name} {stars}"


def format_heroes(data_player_heroes) -> str:
    if not data_player_heroes:
        return "Не удалось получить статистику матчей."

    played = [h for h in data_player_heroes if h.get("games", 0) > MIN_GAMES]
    if not played:
        return f"Нет героев с более чем {MIN_GAMES} играми."

    played.sort(key=lambda h: h["games"], reverse=True)

    lines = []
    for hero in played[:TOP_HEROES]:
        games = hero["games"]
        wins = hero.get("win", 0)
        winrate = round(wins / games * 100, 1)
        hero_id = str(hero.get("hero_id"))
        hero_name = HEROES_DICT.get(hero_id, f"Герой {hero_id}")
        lines.append(f"• {escape(hero_name)}: {games} игр ({winrate}%)")
    return "\n".join(lines)


# ---------- хендлеры ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот для сбора статистики Dota 2.\n"
        "Отправь команду /stats, чтобы посмотреть профиль и любимых героев."
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await message.answer("Отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_steam_id)


@router.message(DotaProfile.waiting_for_steam_id)
async def process_steam_id(
        message: Message, state: FSMContext, session: aiohttp.ClientSession
):
    if not message.text:
        await message.answer("Отправьте текст: цифры или ссылку на Steam / Dotabuff.")
        return
    text = message.text.strip()

    wait_msg = await message.answer("Ищу профиль, секунду...")

    steam_id = await extract_steam32id(text, session)
    if not steam_id:
        await wait_msg.edit_text(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return  # состояние сохраняем, чтобы можно было попробовать ещё раз

    data_profile, data_player_heroes = await asyncio.gather(
        fetch(session, f"{OPENDOTA_API}/players/{steam_id}"),
        fetch(session, f"{OPENDOTA_API}/players/{steam_id}/heroes"),
    )

    if not data_profile or not data_profile.get("profile"):
        await wait_msg.edit_text("Профиль не найден или скрыт.")
        await state.clear()
        return

    name = data_profile["profile"].get("personaname") or "Неизвестный игрок"

    mmr_estimate = data_profile.get("mmr_estimate")
    if isinstance(mmr_estimate, dict) and mmr_estimate.get("estimate"):
        mmr = mmr_estimate["estimate"]
    else:
        mmr = "Скрыт"

    rank_text = format_rank(data_profile.get("rank_tier"))
    heroes_text = format_heroes(data_player_heroes)

    final_text = (
        "<b>Профиль Dota 2</b>\n\n"
        f"👤 Игрок: {escape(name)}\n"
        f"🔢 MMR: {escape(str(mmr))}\n"
        f"🌟 Ранг: {escape(rank_text)}\n\n"
        "🧙‍♀️ <b>Сигнатурные герои:</b>\n"
        f"{heroes_text}"
    )

    await wait_msg.edit_text(final_text, parse_mode="HTML")
    await state.clear()


# ---------- запуск ----------
async def load_heroes(session: aiohttp.ClientSession, attempts: int = 3) -> bool:
    """Загружает список героев с повторными попытками."""
    log.info("Загружаю базу героев из OpenDota...")
    for attempt in range(1, attempts + 1):
        heroes_list = await fetch(session, f"{OPENDOTA_API}/heroes")
        if heroes_list:
            for hero in heroes_list:
                HEROES_DICT[str(hero["id"])] = hero["localized_name"]
            log.info("Успешно! Загружено %d героев.", len(HEROES_DICT))
            return True
        log.warning("Попытка %d/%d не удалась", attempt, attempts)
        await asyncio.sleep(2 * attempt)
    log.error("Не удалось загрузить героев, будут показаны ID")
    return False


async def main():
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=HTTP_HEADERS, timeout=timeout) as session:
        await load_heroes(session)
        dp["session"] = session  # доступна в хендлерах как аргумент session
        log.info("Бот запущен!")
        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())